"""Paired fixed-evidence repetition-penalty comparison. No notebook or dataset edits."""
import copy, hashlib, json, statistics, tempfile, time
from collections import Counter
import torch
import transformers
from transformers import AutoTokenizer, AutoModelForCausalLM, set_seed
from notebook_validation import ROOT, load_namespace
OUT=ROOT/'validation/repetition_penalty_results.json'

def main():
    if not torch.cuda.is_available() or torch.cuda.mem_get_info()[0]<4*1024**3:
        raise RuntimeError('Release notebook model; need 4 GiB GPU memory.')
    source=ROOT/'validation/varied_state_results.json'
    fixture=json.loads(source.read_text())
    tok=AutoTokenizer.from_pretrained('Qwen/Qwen2.5-1.5B-Instruct',local_files_only=True)
    model=AutoModelForCausalLM.from_pretrained('Qwen/Qwen2.5-1.5B-Instruct',local_files_only=True,dtype=torch.float16,device_map={'':0}).eval()
    report={'design':{'contexts':24,'generations':48,'penalties':[1.1,1.0], 'max_new_tokens':320,'temperature':.7,'top_p':.9,'top_k':20,
                      'note':'Identical recorded decision messages, seed and sampling settings in each pair; only repetition_penalty varies. One attempt; no retries or research regeneration. Synthetic evidence. No training writes or broker calls.'},
            'notebook_sha256':hashlib.sha256((ROOT/'main.ipynb').read_bytes()).hexdigest(),
            'fixture_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
            'environment':{'torch':torch.__version__,'transformers':transformers.__version__,'gpu':torch.cuda.get_device_name(0)},'samples':[]}
    with tempfile.TemporaryDirectory() as cache:
        ns=load_namespace(cache)
        for case in fixture['samples']:
            messages=copy.deepcopy(case['diagnostics']['decision_messages'])
            prompt=tok.apply_chat_template(messages,tokenize=False,add_generation_prompt=True)
            inputs=tok(prompt,return_tensors='pt',add_special_tokens=False).to(model.device)
            for penalty in [1.1,1.0]:
                set_seed(case['seed']);start=time.perf_counter()
                with torch.inference_mode():
                    output=model.generate(**inputs,repetition_penalty=penalty,max_new_tokens=320,do_sample=True,temperature=.7,top_p=.9,top_k=20,eos_token_id=tok.eos_token_id,pad_token_id=tok.eos_token_id,use_cache=True)
                ids=output[0,inputs.input_ids.shape[1]:].tolist()
                row={k:case[k] for k in ['case','seed','arm']}
                row.update(penalty=penalty,seconds=time.perf_counter()-start,input_tokens=inputs.input_ids.shape[1],output_tokens=len(ids),token_ids=ids,
                           raw_response=tok.decode(ids,skip_special_tokens=False),response=tok.decode(ids,skip_special_tokens=True).strip(),
                           prompt_sha256=hashlib.sha256(prompt.encode()).hexdigest(),cap_hit=len(ids)>=320 and ids[-1]!=tok.eos_token_id)
                try:
                    if row['cap_hit']:raise ValueError('token cap hit')
                    trades=ns['_parse_trade_decisions'](row['response'],ns['WHITELIST'],case['diagnostics']['evidence'])
                    normalized=ns['_validate_decisions'](trades,{s:100 for s in ns['WHITELIST']})
                    if len(trades)!=len(normalized) or any(d['action'] not in ('buy','sell') for d in normalized):raise ValueError('sizing validation failed')
                    for d,t in zip(normalized,trades):d['research_ids']=t['research_ids']
                    state=fixture['design']['states'][case['case']]
                    portfolio=ns['SimulatedPortfolio'](state['cash'])
                    portfolio.positions={p['symbol']:{'qty':p['qty'],'avg_price':p['avg_entry_price']} for p in state['positions']}
                    fills=[portfolio.execute(d,{s:100 for s in ns['WHITELIST']}) for d in normalized]
                    row.update(status='trade' if trades else 'no_trade',trades=normalized,simulated_fills=fills)
                    if trades:
                        meta=copy.deepcopy(case['diagnostics']);meta.update(status='traded',sft_eligible=True,corrected_decision=False,decision_messages=messages)
                        ns['validate_sft_example'](tok,{'prompt':prompt,'completion':ns['_trade_completion'](normalized),'agent_metadata':meta})
                        row['sft_serialization_valid']=True
                except (ValueError,KeyError,TypeError) as exc:
                    row.update(status='failed',error=str(exc),trades=[],simulated_fills=[])
                report['samples'].append(row)
                OUT.write_text(json.dumps(report,indent=2),encoding='utf-8')
                print(f'{case["case"]} seed={case["seed"]} {case["arm"]} penalty={penalty}: {row["status"]} {row["response"][:170]}',flush=True)
    report['summary']={}
    for penalty in [1.1,1.0]:
        rows=[x for x in report['samples'] if x['penalty']==penalty]
        pairs=[]
        for case in fixture['design']['states']:
            for seed in [7,17,29]:
                a,b=[x for x in rows if x['case']==case and x['seed']==seed]
                valid=all(x['status']!='failed' for x in [a,b])
                signature=lambda x:[(d['symbol'],d['action'],d['qty']) for d in x['trades']]
                pairs.append({'case':case,'seed':seed,'both_valid':valid,'changed_trade_decision':valid and signature(a)!=signature(b),'different_raw_output':a['response']!=b['response']})
        report['summary'][str(penalty)]={'statuses':dict(Counter(x['status'] for x in rows)),'caps':sum(x['cap_hit'] for x in rows),'median_seconds':statistics.median(x['seconds'] for x in rows),'max_seconds':max(x['seconds'] for x in rows),'output_tokens_range':[min(x['output_tokens'] for x in rows),max(x['output_tokens'] for x in rows)],'trade_proposals':sum(len(x['trades']) for x in rows),'simulated_fills':sum(bool(f) for x in rows for f in x['simulated_fills']),'valid_evidence_pairs':sum(x['both_valid'] for x in pairs),'changed_trade_pairs':sum(x['changed_trade_decision'] for x in pairs),'pairs':pairs}
    OUT.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print('COMPLETE',flush=True)

if __name__=='__main__':main()
