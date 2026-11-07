"""Paired synthetic-evidence evaluation of the unchanged notebook agent, offline."""
import ast
import copy
import hashlib
import json
import math
from pathlib import Path
import statistics
import tempfile
import time
from collections import Counter
import torch
import transformers
from transformers import AutoModelForCausalLM, AutoTokenizer, set_seed
from notebook_validation import ROOT, load_namespace

OUTPUT = ROOT / 'validation' / 'varied_state_results.json'
CUTOFF = '2026-08-14T20:05:00Z'
SEEDS = [7, 17, 29]


def full_menu(ns):
    # Use the notebook's exact news schema/description, with a non-network placeholder.
    nb = json.loads((ROOT / 'main.ipynb').read_text(encoding='utf-8'))
    for cell in nb['cells']:
        source = ''.join(cell['source'])
        if cell['cell_type'] != 'code' or "register_tool(" not in source:
            continue
        for node in ast.parse(source).body:
            if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call) and getattr(node.value.func, 'id', '') == 'register_tool':
                args = {k.arg: k.value for k in node.value.keywords}
                if ast.literal_eval(args['name']) == 'get_news':
                    news = {k: ast.literal_eval(v) for k, v in args.items() if k != 'func'}
                    ns['register_tool'](**news, func=lambda **kw: None)
    ns['_tool_registry'] = {'get_news': ns['_tool_registry']['get_news'],
                            **{k: v for k, v in ns['_tool_registry'].items() if k != 'get_news'}}
    assert len(ns['_tool_registry']) == 5
    assert all(v['func'] is not None for v in ns['_tool_registry'].values())


def evidence_bars(ns, direction):
    days = ns['_backtest_calendar']().sessions_in_range('2026-01-02', '2026-08-14')[-120:]
    prices = [100 + direction * .28 * (i - len(days) + 1) + .6 * math.sin(i / 2) for i in range(len(days))]
    offset = prices[-1] - 100
    prices = [round(p - offset, 4) for p in prices]
    series = {d.strftime('%Y-%m-%d'): {'open': p - direction * .12, 'high': p + .5, 'low': p - .5,
                                       'close': p, 'volume': 1000000 + i * 1000}
              for i, (d, p) in enumerate(zip(days, prices))}
    return {'bars': {s: copy.deepcopy(series) for s in ns['WHITELIST']}}


def main():
    if not torch.cuda.is_available() or torch.cuda.mem_get_info()[0] < 4 * 1024**3:
        raise RuntimeError('Need 4 GiB free GPU memory; release notebook model first.')
    model_name = 'Qwen/Qwen2.5-1.5B-Instruct'
    tok = AutoTokenizer.from_pretrained(model_name, local_files_only=True)
    model = AutoModelForCausalLM.from_pretrained(model_name, local_files_only=True, dtype=torch.float16, device_map={'': 0})
    model.eval()
    with tempfile.TemporaryDirectory() as cache:
        ns = load_namespace(cache)
        full_menu(ns)
        cases = [('cash_only', 100000, {}), ('concentrated_holding', 5000, {'AAPL': 100}),
                 ('cash_constrained', 25, {'AAPL': 100}), ('diversified_holdings', 20000, {'MSFT': 50, 'NVDA': 50, 'GOOG': 50})]
        fixtures = {}
        for name, cash, holdings in cases:
            p = ns['SimulatedPortfolio'](cash)
            p.positions = {s: {'qty': qty, 'avg_price': 100} for s, qty in holdings.items()}
            fixtures[name] = p.get_state({s: 100 for s in ns['WHITELIST']}, timestamp=1786737900)
        bars = {'positive': evidence_bars(ns, 1), 'negative': evidence_bars(ns, -1)}
        report = {'design': {'model': model_name, 'seeds': SEEDS, 'cutoff': CUTOFF, 'sample_size': 24,
                   'states': fixtures, 'menu': {k: {x: v[x] for x in ('description', 'params')} for k,v in ns['_tool_registry'].items()},
                   'evidence': 'Synthetic paired rising/falling daily bars and positive/negative company news. Latest close $100 in both arms. All symbols share the scenario; not real market evidence.',
                   'criteria': {'zero_failures': True, 'zero_caps': True, 'median_session_seconds_below': 31.8,
                                'activity': 'Descriptive, not forced; no profitable-trading threshold.',
                                'evidence_response': 'Compare accepted trade signatures within identical-state/seed pairs. Differences demonstrate sensitivity, not rationality.'}},
                  'environment': {'torch': torch.__version__, 'transformers': transformers.__version__, 'gpu': torch.cuda.get_device_name(0)},
                  'notebook_sha256': hashlib.sha256((ROOT / 'main.ipynb').read_bytes()).hexdigest(), 'samples': []}
        (ROOT / 'validation' / 'varied_state_fixtures.json').write_text(json.dumps({'design': report['design'], 'series_shared_by_all_symbols': {arm: next(iter(data['bars'].values())) for arm, data in bars.items()}}, indent=2), encoding='utf-8')
        for case, state in fixtures.items():
            for seed in SEEDS:
                for arm in ('positive', 'negative'):
                    dispatched = []
                    def dispatch(name, arguments, date=None, historical_data=None):
                        assert date == CUTOFF
                        if name == 'get_news':
                            symbols = arguments['symbols']
                            headline = ('Earnings and revenue exceed expectations; guidance raised; operating cash flow improves.' if arm == 'positive'
                                        else 'Earnings and revenue miss expectations; guidance cut; operating cash flow deteriorates.')
                            result = '\n'.join(f'=== News: {s} ===\n[1] {s}: {headline}\n    Date: 2026-08-14T19:00:00Z\n    Tickers: {s}\n    Summary: The company reported the results and revised its outlook today.' for s in symbols)
                        else:
                            result = ns['historical_market_tool'](name, arguments, date, bars[arm])
                        dispatched.append({'name': name, 'arguments': arguments, 'result': result})
                        return result
                    ns['dispatch_tool'] = dispatch
                    set_seed(seed)
                    started = time.perf_counter()
                    result = ns['llm_agent_decide'](tok, model, copy.deepcopy(state), date=CUTOFF, historical_data=bars[arm], debug_tokens=True)
                    elapsed = time.perf_counter() - started
                    if result.diagnostics['sft_eligible']:
                        ns['validate_sft_example'](tok, {'prompt': result[1], 'completion': result[2], 'agent_metadata': result.diagnostics})
                    portfolio = ns['SimulatedPortfolio'](state['cash'])
                    portfolio.positions = {p['symbol']: {'qty': p['qty'], 'avg_price': p['avg_entry_price']} for p in state['positions']}
                    feasible = [portfolio.execute(d, {s: 100 for s in ns['WHITELIST']}) for d in result[0]]
                    report['samples'].append({'case': case, 'seed': seed, 'arm': arm, 'seconds': elapsed,
                                              'decisions': result[0], 'simulated_feasibility': feasible,
                                              'dispatched': dispatched, 'diagnostics': result.diagnostics})
                    OUTPUT.write_text(json.dumps(report, indent=2), encoding='utf-8')
                    print(f'CASE {case} {seed} {arm}: {result.diagnostics["status"]}; {elapsed:.2f}s', flush=True)
        rows = report['samples']
        calls = [c for r in rows for c in r['diagnostics']['calls']]
        pairs = []
        for case in fixtures:
            for seed in SEEDS:
                a, b = [r for r in rows if r['case'] == case and r['seed'] == seed]
                signature = lambda r: [(d['symbol'], d['action'], d['qty']) for d in r['decisions']]
                valid = all(r['diagnostics']['status'] != 'failed' for r in (a,b))
                pairs.append({'case': case, 'seed': seed, 'both_valid': valid, 'different_decisions': valid and signature(a) != signature(b),
                              'same_initial_research': a['dispatched'][:1] != [] and b['dispatched'][:1] != [] and
                              {k:a['dispatched'][0][k] for k in ('name','arguments')} == {k:b['dispatched'][0][k] for k in ('name','arguments')}})
        report['pairs'] = pairs
        report['summary'] = {'episodes': len(rows), 'statuses': dict(Counter(r['diagnostics']['status'] for r in rows)),
            'cap_hits': sum(c['cap_hit'] for c in calls), 'median_session_seconds': statistics.median(r['seconds'] for r in rows),
            'max_session_seconds': max(r['seconds'] for r in rows), 'median_call_seconds': statistics.median(c['seconds'] for c in calls),
            'tools_selected': dict(Counter(t['name'] for r in rows for t in r['dispatched'])),
            'usable_research_episodes': sum(bool(r['diagnostics']['evidence']) for r in rows),
            'sft_eligible': sum(r['diagnostics']['sft_eligible'] for r in rows),
            'trade_decisions': sum(len(r['decisions']) for r in rows),
            'feasible_trades': sum(bool(t) for r in rows for t in r['simulated_feasibility']),
            'valid_pairs': sum(p['both_valid'] for p in pairs), 'pairs_with_changed_decisions': sum(p['different_decisions'] for p in pairs)}
        OUTPUT.write_text(json.dumps(report, indent=2), encoding='utf-8')
        print('SUMMARY ' + json.dumps(report['summary']), flush=True)

if __name__ == '__main__': main()
