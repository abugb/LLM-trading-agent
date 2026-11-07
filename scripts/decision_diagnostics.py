"""Offline staged policy diagnostics; all outputs are quarantined from training."""
import copy, hashlib, json, statistics, tempfile, time, sys
from collections import Counter
from pathlib import Path
import torch
import transformers
from transformers import AutoTokenizer, AutoModelForCausalLM, set_seed, TemperatureLogitsWarper, TopPLogitsWarper, TopKLogitsWarper, RepetitionPenaltyLogitsProcessor
from notebook_validation import ROOT, load_namespace
from varied_state_agent import full_menu, CUTOFF
OUT = ROOT / 'validation' / 'decision_diagnostics.json'

def main():
    if not torch.cuda.is_available() or torch.cuda.mem_get_info()[0] < 4 * 1024**3:
        raise RuntimeError('Release notebook model; need 4 GiB GPU memory.')
    old=json.loads((ROOT/'validation/varied_state_results.json').read_text())
    fixture=json.loads((ROOT/'validation/varied_state_fixtures.json').read_text())
    tok=AutoTokenizer.from_pretrained('Qwen/Qwen2.5-1.5B-Instruct',local_files_only=True)
    model=AutoModelForCausalLM.from_pretrained('Qwen/Qwen2.5-1.5B-Instruct',local_files_only=True,dtype=torch.float16,device_map={'':0}).eval()
    report={'notebook_sha256':hashlib.sha256((ROOT/'main.ipynb').read_bytes()).hexdigest(),
            'environment':{'torch':torch.__version__,'transformers':transformers.__version__},
            'tokenization':{s:tok.encode(s,add_special_tokens=False) for s in ['[',']','[]','[{']},
            'probabilities':[],'contract_comparison':[],'positive_control':[],'order_swap':[],
            'design': 'Stages executed in order: original-prompt token probabilities; fixed-evidence original versus explicit per-researched-ticker contract; forced-buy plumbing control; reversed universe end-to-end. No retries in isolated decision experiments. No training dataset writes.'}
    if '--probabilities-only' in sys.argv:
        prior=json.loads(OUT.read_text(encoding='utf-8'))
        prior['probabilities']=[]
        report=prior
    report['probability_method']={'repetition_penalty':model.generation_config.repetition_penalty,
                                  'temperature':.7,'top_k':model.generation_config.top_k,'top_p':.9,
                                  'note':'Raw model probabilities and probabilities after all active generation processors/warpers, in generation order.'}
    def save(): OUT.write_text(json.dumps(report,indent=2),encoding='utf-8')
    def token_dist(ids):
        tensor=torch.tensor([ids],device=model.device)
        with torch.inference_mode(): logits=model(input_ids=tensor).logits[:,-1,:].float()
        steps={'raw':float(logits.softmax(-1)[0,tok.encode('[]',add_special_tokens=False)[0]])}
        processed=RepetitionPenaltyLogitsProcessor(model.generation_config.repetition_penalty)(tensor,logits.clone())
        steps['after_repetition_penalty']=float(processed.softmax(-1)[0,tok.encode('[]',add_special_tokens=False)[0]])
        processed=TemperatureLogitsWarper(.7)(tensor,processed)
        steps['after_temperature']=float(processed.softmax(-1)[0,tok.encode('[]',add_special_tokens=False)[0]])
        processed=TopKLogitsWarper(model.generation_config.top_k)(tensor,processed)
        steps['after_top_k']=float(processed.softmax(-1)[0,tok.encode('[]',add_special_tokens=False)[0]])
        processed=TopPLogitsWarper(.9)(tensor,processed)
        steps['after_top_p']=float(processed.softmax(-1)[0,tok.encode('[]',add_special_tokens=False)[0]])
        no_penalty=TopPLogitsWarper(.9)(tensor,TopKLogitsWarper(model.generation_config.top_k)(tensor,TemperatureLogitsWarper(.7)(tensor,logits.clone())))
        steps['sampling_without_repetition_penalty']=float(no_penalty.softmax(-1)[0,tok.encode('[]',add_special_tokens=False)[0]])
        result={'empty_array_probability_by_processor':steps}
        for label,scores in [('raw',logits),('sampled',processed)]:
            probs=scores.softmax(-1)[0]; vals,indices=probs.topk(8)
            result[label]={'top':[{'id':int(i),'text':tok.decode([int(i)]),'p':float(v)} for i,v in zip(indices,vals)],
                          'literal_tokens':{s:float(probs[tok.encode(s,add_special_tokens=False)[0]]) for s in ['[',']','[]','[{'] if len(tok.encode(s,add_special_tokens=False))==1},
                          'eos':float(probs[tok.eos_token_id])}
        return result
    # Stage 1. Inspect actual next-token distributions, not a sampling estimate.
    for row in old['samples']:
        prompt=tok.apply_chat_template(row['diagnostics']['decision_messages'],tokenize=False,add_generation_prompt=True)
        ids=tok.encode(prompt,add_special_tokens=False)
        report['probabilities'].append({'case':row['case'],'seed':row['seed'],'arm':row['arm'],
            'first':token_dist(ids),'after_literal_open_bracket':token_dist(ids+tok.encode('[',add_special_tokens=False)),
            'after_empty_array':token_dist(ids+tok.encode('[]',add_special_tokens=False))})
        save()
    print('STAGE 1 complete: tokenization '+json.dumps(report['tokenization']),flush=True)
    if '--probabilities-only' in sys.argv: return
    def generate(messages,seed):
        prompt=tok.apply_chat_template(messages,tokenize=False,add_generation_prompt=True)
        inputs=tok(prompt,return_tensors='pt',add_special_tokens=False).to(model.device)
        set_seed(seed); start=time.perf_counter()
        with torch.inference_mode(): out=model.generate(**inputs,max_new_tokens=320,do_sample=True,temperature=.7,top_p=.9,eos_token_id=tok.eos_token_id,pad_token_id=tok.eos_token_id,use_cache=True)
        ids=out[0,inputs.input_ids.shape[1]:].tolist()
        return {'response':tok.decode(ids,skip_special_tokens=True).strip(),'raw_response':tok.decode(ids,skip_special_tokens=False),'token_ids':ids,'seconds':time.perf_counter()-start,'input_tokens':inputs.input_ids.shape[1], 'output_tokens':len(ids),'cap_hit':len(ids)>=320 and ids[-1]!=tok.eos_token_id,'messages':messages,'prompt':prompt}
    with tempfile.TemporaryDirectory() as cache:
        ns=load_namespace(cache);full_menu(ns)
        def parse_explicit(text,evidence):
            items=json.loads(text)
            expected={s for values in evidence.values() for s in values}
            if not isinstance(items,list) or len(items)!=len(expected) or {d.get('symbol') for d in items if isinstance(d,dict)}!=expected: raise ValueError('Need one decision per researched ticker')
            trades=[]
            for d in items:
                if not isinstance(d,dict) or set(d)!={'symbol','action','qty','research_ids'}: raise ValueError('Invalid keys')
                if d['action']=='none':
                    if type(d['qty']) is not int or d['qty']!=0: raise ValueError('none requires zero qty')
                    probe={**d,'action':'buy','qty':1}
                    ns['_parse_trade_decisions'](json.dumps([probe]),ns['WHITELIST'],evidence)
                else: trades.extend(ns['_parse_trade_decisions'](json.dumps([d]),ns['WHITELIST'],evidence))
            return trades
        def assess(result,row,explicit=False):
            try:
                if result['cap_hit']: raise ValueError('cap hit')
                evidence=row['diagnostics']['evidence']
                trades=parse_explicit(result['response'],evidence) if explicit else ns['_parse_trade_decisions'](result['response'],ns['WHITELIST'],evidence)
                normalized=ns['_validate_decisions'](trades,{s:100 for s in ns['WHITELIST']})
                if len(normalized)!=len(trades) or any(d['action'] not in ('buy','sell') for d in normalized):raise ValueError('Sizing validation failed')
                for d,t in zip(normalized,trades):d['research_ids']=t['research_ids']
                state=old['design']['states'][row['case']]
                p=ns['SimulatedPortfolio'](state['cash']);p.positions={x['symbol']:{'qty':x['qty'],'avg_price':x['avg_entry_price']} for x in state['positions']}
                result.update(valid=True,trades=normalized,feasible=[p.execute(d,{s:100 for s in ns['WHITELIST']}) for d in normalized])
            except (ValueError,TypeError,KeyError) as e:result.update(valid=False,error=str(e),trades=[])
        # Stage 2: paired fixed evidence; replace conflicting contract instructions together.
        for row in old['samples']:
            for contract in ['current','explicit']:
                messages=copy.deepcopy(row['diagnostics']['decision_messages'])
                if contract=='explicit':
                    messages[0]['content']=('You manage a stock portfolio using the supplied research and account state. Decide separately for every researched ticker: buy, sell, or none. '
                        'Buy adds shares; sell reduces shares already owned; none leaves the position unchanged. Consider the evidence, current holdings and available cash. '
                        'Use whole shares; value at most $5000 per trade. Do not sell shares not held or buy beyond available cash. '
                        'Return only a JSON array with exactly one object for each researched ticker. Each object has symbol, action (buy, sell, or none), qty, research_ids. '
                        'Use a positive integer qty for buy/sell and zero for none. Cite a returned research ID for that symbol. Do not include unresearched tickers.')
                    messages[-1]['content']='Evaluate each researched ticker using the returned evidence and account state. Choose buy, sell, or none and a size. Return the decision array only.'
                result=generate(messages,row['seed']);assess(result,row,contract=='explicit')
                report['contract_comparison'].append({'case':row['case'],'seed':row['seed'],'arm':row['arm'],'contract':contract,**result});save()
                print(f'STAGE 2 {row["case"]} {row["seed"]} {row["arm"]} {contract}: {result["response"][:180]}',flush=True)
        # Positive control: model must produce the trade; original parser/collector/SFT path.
        row=next(x for x in old['samples'] if x['case']=='cash_only' and x['arm']=='positive')
        for seed in [7,17,29]:
            messages=copy.deepcopy(row['diagnostics']['decision_messages'])
            messages[-1]['content']='Plumbing test only: output exactly one buy of 1 share of AAPL citing R1. Return the JSON array with symbol, action, qty, research_ids. This is an explicit test instruction, not an investment recommendation.'
            result=generate(messages,seed);assess(result,row)
            result['expected_trade']=result['valid'] and [(d['symbol'],d['action'],d['qty']) for d in result['trades']]==[('AAPL','buy',1)]
            if result['expected_trade']:
                meta=copy.deepcopy(row['diagnostics']);meta.update(status='traded',sft_eligible=True,corrected_decision=False,decision_messages=messages)
                collector=ns['TradingDataCollector']()
                index=collector.log(result['prompt'],ns['_trade_completion'](result['trades']),result['trades'],100000,1,metadata=meta)
                entry=json.loads(json.dumps(collector.entries[index]));ns['validate_sft_example'](tok,entry)
                collector.update_outcome(index,100001);collector.auto_label()
                from datasets import Dataset
                ns['Dataset']=Dataset
                dataset=ns['prepare_sft_dataset'](collector,tok)
                result['serialization_and_sft_passed']=len(dataset)>0 and any(x!=-100 for x in dataset[-1]['labels'])
            report['positive_control'].append({'seed':seed,**result});save()
        print('POSITIVE CONTROL complete',flush=True)
        # Stage 3. Reverse only allowed-symbol order; same model-generated research and evidence scenario.
        for row in old['samples']:
            state=copy.deepcopy(old['design']['states'][row['case']]);universe=list(reversed(ns['WHITELIST']));state['allowed_symbols']=universe
            bars={'bars':{s:fixture['series_shared_by_all_symbols'][row['arm']] for s in universe}}
            dispatched=[]
            def dispatch(name,args,date=None,historical_data=None):
                assert date==CUTOFF
                if name=='get_news':
                    headline=('Earnings and revenue exceed expectations; guidance raised; operating cash flow improves.' if row['arm']=='positive' else 'Earnings and revenue miss expectations; guidance cut; operating cash flow deteriorates.')
                    text='\n'.join(f'=== News: {s} ===\n[1] {s}: {headline}\n    Date: 2026-08-14T19:00:00Z\n    Tickers: {s}\n    Summary: The company reported the results and revised its outlook today.' for s in args['symbols'])
                else:text=ns['historical_market_tool'](name,args,date,bars)
                dispatched.append({'name':name,'arguments':args,'result':text});return text
            ns['dispatch_tool']=dispatch
            set_seed(row['seed']);start=time.perf_counter()
            outcome=ns['llm_agent_decide'](tok,model,state,universe=universe,date=CUTOFF,historical_data=bars,debug_tokens=True)
            report['order_swap'].append({'case':row['case'],'seed':row['seed'],'arm':row['arm'],'seconds':time.perf_counter()-start,'decisions':outcome[0],'diagnostics':outcome.diagnostics,'dispatched':dispatched});save()
        print('ALL STAGES COMPLETE',flush=True)

if __name__=='__main__':main()
