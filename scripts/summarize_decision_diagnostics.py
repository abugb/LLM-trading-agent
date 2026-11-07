"""Report completed decision diagnostics; inspection never accepts malformed trades."""
import json, statistics
from pathlib import Path
from collections import Counter
ROOT=Path(__file__).resolve().parents[1]
r=json.loads((ROOT/'validation/decision_diagnostics.json').read_text())
old=json.loads((ROOT/'validation/varied_state_results.json').read_text())
assert len(r['probabilities'])==24 and len(r['contract_comparison'])==48 and len(r['order_swap'])==24
assert 'probability_method' in r
summary={}
for stage, key in [('first','[]'),('after_literal_open_bracket',']'),('after_empty_array','eos')]:
    summary[stage]={}
    for distribution in ['raw','sampled']:
        vals=[x[stage][distribution]['eos'] if key=='eos' else x[stage][distribution]['literal_tokens'][key] for x in r['probabilities']]
        summary[stage][distribution]={'min':min(vals),'median':statistics.median(vals),'max':max(vals),'equal_one':sum(x==1 for x in vals)}
summary['contracts']={}
audit=[]
for contract in ['current','explicit']:
    rows=[x for x in r['contract_comparison'] if x['contract']==contract]
    summary['contracts'][contract]={'valid':sum(x['valid'] for x in rows),'trade_episodes':sum(bool(x['trades']) for x in rows),'caps':sum(x['cap_hit'] for x in rows),'median_seconds':statistics.median(x['seconds'] for x in rows),'output_tokens':[min(x['output_tokens'] for x in rows),max(x['output_tokens'] for x in rows)]}
    if contract!='explicit':continue
    for x in rows:
        text=x['response'].strip(); fenced=text.startswith('```')
        if fenced:text='\n'.join(text.splitlines()[1:-1])
        try: items=json.loads(text)
        except ValueError:items=[]
        violations=[]
        state=old['design']['states'][x['case']]
        holdings={p['symbol']:p['qty'] for p in state['positions']}
        for d in items:
            if d.get('action') in ('buy','sell'):
                qty=d.get('qty',0)
                if type(qty)!=int or qty<=0: violations.append('nonpositive_or_invalid_qty')
                elif d['action']=='buy' and qty*100>state['cash']:violations.append('unaffordable_buy')
                elif d['action']=='sell' and qty>holdings.get(d['symbol'],0):violations.append('sell_exceeds_holdings')
        audit.append({'case':x['case'],'seed':x['seed'],'arm':x['arm'],'fenced':fenced,'items':items,'violations':violations})
summary['audit_only']={'fenced':sum(x['fenced'] for x in audit),'singular_reference_key':sum(any('research_id' in d for d in x['items']) for x in audit),'trade_mentions':sum(any(d.get('action') in ('buy','sell') for d in x['items']) for x in audit),'constraint_violations':dict(Counter(v for x in audit for v in x['violations'])),'changed_pairs':0}
for case in old['design']['states']:
    for seed in [7,17,29]:
        a,b=[x for x in audit if x['case']==case and x['seed']==seed]
        sig=lambda x:[(d.get('symbol'),d.get('action'),d.get('qty')) for d in x['items']]
        summary['audit_only']['changed_pairs']+=sig(a)!=sig(b)
summary['positive_control']={'expected_trade':sum(x['expected_trade'] for x in r['positive_control']),'sft_passed':sum(x.get('serialization_and_sft_passed',False) for x in r['positive_control'])}
changed=0
for x in r['order_swap']:
    original=next(a for a in old['samples'] if all(a[k]==x[k] for k in ['case','seed','arm']))
    call=lambda row:[(d['name'],d['arguments']) for d in row['dispatched']]
    changed+=call(x)!=call(original)
summary['order_swap']={'statuses':dict(Counter(x['diagnostics']['status'] for x in r['order_swap'])),'symbols':dict(Counter(s for x in r['order_swap'] for vals in x['diagnostics']['evidence'].values() for s in vals)), 'tools':dict(Counter(d['name'] for x in r['order_swap'] for d in x['dispatched'])),'research_changed':changed,'median_seconds':statistics.median(x['seconds'] for x in r['order_swap']),'caps':sum(c['cap_hit'] for x in r['order_swap'] for c in x['diagnostics']['calls'])}
r['summary']=summary;r['audit_only_explicit_outputs']=audit
(ROOT/'validation/decision_diagnostics.json').write_text(json.dumps(r,indent=2),encoding='utf-8')
print(json.dumps(summary,indent=2))
