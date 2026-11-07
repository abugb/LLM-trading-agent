"""Seeded real-model smoke test on cached historical bars; no network or orders."""
import argparse
import hashlib
import json
from pathlib import Path
import tempfile
import time
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, set_seed
from notebook_validation import ROOT, load_namespace


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', default=str(ROOT / 'validation' / 'agent_smoke_results.json'))
    args = parser.parse_args()
    fixture = json.loads((ROOT / 'validation' / 'prompt_replay_fixture.json').read_text(encoding='utf-8'))
    # Gates are fixed before generation; failures are reported, never hidden or reclassified.
    criteria = {'sample_size': 6, 'max_cap_hits': 0, 'max_failed_episodes': 0,
                'retry_input_tokens_identical_after_first_correction': True,
                'max_short_call_seconds': 6.0, 'short_call_definition': 'output<=35,input<=2600',
                'reference_short_call_seconds': 2.0, 'reference_session_seconds': 10.6,
                'max_median_session_seconds': 31.8}
    if not torch.cuda.is_available() or torch.cuda.mem_get_info()[0] < 4 * 1024**3:
        raise RuntimeError('Release notebook GPU model before smoke test (need 4 GiB free).')
    bars_path = next((ROOT / '.cache' / 'stock_agent').glob('historical_bars_v2_*.json'))
    bars_bytes = bars_path.read_bytes()
    bars = json.loads(bars_bytes)
    tok = AutoTokenizer.from_pretrained(fixture['model'], local_files_only=True)
    model = AutoModelForCausalLM.from_pretrained(fixture['model'], local_files_only=True,
                                               dtype=torch.float16, device_map={'': 0})
    model.eval()
    rows = []
    with tempfile.TemporaryDirectory() as cache:
        ns = load_namespace(cache)
        # Only historical market tools are exposed; recorded news payloads are not available for all symbols.
        ns['dispatch_tool'] = lambda name, arguments, date=None, historical_data=None: ns['historical_market_tool'](name, arguments, date, bars)
        for case in fixture['states']:
            for seed in fixture['seeds']:
                set_seed(seed)
                start = time.perf_counter()
                result = ns['llm_agent_decide'](tok, model, case['state'],
                    date=case['date'] + 'T20:05:00Z', historical_data=bars, debug_tokens=True)
                diag = result.diagnostics
                if diag['sft_eligible']:
                    ns['validate_sft_example'](tok, {'prompt': result[1], 'completion': result[2], 'agent_metadata': diag})
                row = {'date': case['date'], 'seed': seed, 'seconds': time.perf_counter()-start,
                       'decisions': result[0], 'diagnostics': diag}
                rows.append(row)
                report = {'criteria': criteria, 'bars_sha256': hashlib.sha256(bars_bytes).hexdigest(),
                          'limitations': ['Six episodes from two reconstructed failing states; no network or order submission.',
                                          'Historical market tools only; news omitted because complete recorded news fixtures are unavailable.',
                                          'Latency gate allows 3x the observed short-call/session baselines; not a hardware benchmark.'],
                          'samples': rows}
                Path(args.output).write_text(json.dumps(report, indent=2), encoding='utf-8')
    import statistics
    calls = [c for r in rows for c in r['diagnostics']['calls']]
    short = [c['seconds'] for c in calls if c['output_tokens'] <= 35 and c['input_tokens'] <= 2600]
    flat = True
    for r in rows:
        for phase in ('research', 'decision'):
            sizes = [c['input_tokens'] for c in r['diagnostics']['calls'] if c['phase'] == phase and c['attempt'] >= 2]
            flat &= len(set(sizes)) <= 1
    report['summary'] = {'failures': sum(r['diagnostics']['status'] == 'failed' for r in rows),
                         'no_trade': sum(r['diagnostics']['status'] == 'no_trade' for r in rows),
                         'cap_hits': sum(c['cap_hit'] for c in calls), 'flat_retries': flat,
                         'median_short_call_seconds': statistics.median(short) if short else None,
                         'median_session_seconds': statistics.median(r['seconds'] for r in rows)}
    s = report['summary']
    report['passed'] = (s['failures'] == 0 and s['cap_hits'] == 0 and flat and bool(short)
                        and max(short) <= criteria['max_short_call_seconds']
                        and s['median_session_seconds'] <= criteria['max_median_session_seconds'])
    Path(args.output).write_text(json.dumps(report, indent=2), encoding='utf-8')
    print('SMOKE RESULT', json.dumps({'passed': report['passed'], **s}), flush=True)


if __name__ == '__main__':
    main()
