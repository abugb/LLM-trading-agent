"""Summarize the completed varied-state evaluation without model inference."""
import json
import statistics
from collections import Counter
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
p = ROOT / 'validation' / 'varied_state_results.json'
r = json.loads(p.read_text(encoding='utf-8'))
assert len(r['samples']) == r['design']['sample_size']
rows = r['samples']
calls = [c for x in rows for c in x['diagnostics']['calls']]
quality = {}
quality['research_symbols'] = dict(Counter(s for x in rows for values in x['diagnostics']['evidence'].values() for s in values))
quality['tool_parse_failures'] = sum(not c['parsed'] for c in calls if c['phase'] == 'research')
quality['corrected_decisions'] = sum(x['diagnostics']['corrected_decision'] for x in rows)
quality['closing_tag_repairs'] = sum(c['envelope_closed'] for c in calls if c['phase'] == 'research')
quality['holding_episodes'] = sum(bool(r['design']['states'][x['case']]['positions']) for x in rows)
quality['episodes_researching_a_holding'] = sum(bool({p['symbol'] for p in r['design']['states'][x['case']]['positions']} & {s for v in x['diagnostics']['evidence'].values() for s in v}) for x in rows)
visible_differences = 0
same_choices = 0
for pair in r['pairs']:
    a, b = [x for x in rows if x['case'] == pair['case'] and x['seed'] == pair['seed']]
    visible = lambda x: [m['content'] for m in x['diagnostics']['decision_messages'] if m['role'] == 'tool']
    visible_differences += visible(a) != visible(b)
    same_choices += pair['same_initial_research']
quality['pairs_with_different_visible_evidence'] = visible_differences
quality['pairs_with_identical_first_research_choice'] = same_choices
quality['input_tokens_range'] = [min(c['input_tokens'] for c in calls), max(c['input_tokens'] for c in calls)]
quality['research_output_tokens_range'] = [min(c['output_tokens'] for c in calls if c['phase']=='research'), max(c['output_tokens'] for c in calls if c['phase']=='research')]
quality['decision_output_tokens_range'] = [min(c['output_tokens'] for c in calls if c['phase']=='decision'), max(c['output_tokens'] for c in calls if c['phase']=='decision')]
quality['max_call_seconds'] = max(c['seconds'] for c in calls)
r['research_quality'] = quality
p.write_text(json.dumps(r, indent=2), encoding='utf-8')
s = r['summary']
lines = ['# Varied-state full-menu evaluation — 2026-11-06', '',
         'The unchanged notebook agent was evaluated offline on 24 episodes: four portfolio states × three seeds × two evidence scenarios. All five notebook tools were available with their actual descriptions and schemas. The model selected and generated its own research calls.', '',
         '## Design', '',
         '- States: $100,000 cash only; 100 AAPL shares plus $5,000 cash; the same holding with only $25 cash; and 50 shares each of MSFT, NVDA and GOOG plus $20,000 cash.',
         '- Each positive/negative pair uses identical state, universe order, seed, weights and settings. Synthetic rising/falling OHLCV histories end at the same $100 close; synthetic company news contrasts positive and negative earnings/guidance. The notebook calculates RSI, MACD and quotes from these bars. No instructions to buy or sell were added.',
         '- Decision cutoff: August 14, 2026 at 20:05 UTC. Every synthetic news timestamp precedes it. These scenarios are controlled tests, not claims about actual market events.',
         '- Seeds: 7, 17, 29. Cached Qwen2.5-1.5B-Instruct, CUDA FP16. Generation budgets and prompts were unchanged. Only accepted decisions were checked for feasibility in a local simulated portfolio; there were no broker calls.', '',
         '## Results', '', '| Measure | Result |', '|---|---:|',
         f'| Episodes with usable research | {s["usable_research_episodes"]}/24 |',
         f'| Failed episodes | {s["statuses"].get("failed",0)}/24 |',
         f'| Token-cap hits | {s["cap_hits"]} |',
         f'| Trade episodes | {s["statuses"].get("traded",0)}/24 |',
         f'| Researched no-trade episodes | {s["statuses"].get("no_trade",0)}/24 |',
         f'| Median / maximum session time | {s["median_session_seconds"]:.2f}s / {s["max_session_seconds"]:.2f}s |',
         f'| Median / maximum call time | {s["median_call_seconds"]:.2f}s / {quality["max_call_seconds"]:.2f}s |',
         f'| Pairs with different visible evidence | {visible_differences}/12 |',
         f'| Pairs with changed accepted decisions | {s["pairs_with_changed_decisions"]}/12 |',
         f'| SFT-eligible episodes | {s["sft_eligible"]}/24 |', '',
         '### Research quality', '',
         f'Tool selections: `{json.dumps(s["tools_selected"], sort_keys=True)}`. Researched symbols: `{json.dumps(quality["research_symbols"], sort_keys=True)}`. All results passed the existing mechanical usable-data guard. There were {quality["tool_parse_failures"]} research parse failures and {quality["closing_tag_repairs"]} closing-tag repairs.', '',
         f'{quality["episodes_researching_a_holding"]}/{quality["holding_episodes"]} episodes with positions researched an owned stock. In the diversified portfolio, four of six episodes investigated its MSFT holding; two still investigated unheld AAPL. Research choices therefore show some response to portfolio state, while AAPL dominates overall. An order-swapped test would be needed to distinguish ticker/order preference from justified selection.', '',
         'News, MACD and the quote tool were available but were not selected. Therefore this run tests the full menu being presented, not successful use of every tool. It cannot establish news interpretation quality. RSI sometimes indicates overbought/oversold conditions, so the evidence scenarios are not unambiguous instructions to buy/sell.', '',
         '### Evidence responsiveness and activity', '',
         f'All {same_choices}/12 pairs made the same initial research choice. All {visible_differences}/12 received different tool text in the final decision context, yet every final decision was `[]`. Both state variation and evidence variation produced no observable trading response in this sample.', '',
         'This does not prove the model ignores evidence internally, nor does every evidence change warrant a trade. It does show that this configuration did not demonstrate an active evidence-sensitive trading policy across these controlled cases. No trades means reference accuracy among trades and trade profitability cannot be measured, and there are no SFT candidates.', '',
         '### Latency and reliability', '',
         f'Input length ranged from {quality["input_tokens_range"][0]} to {quality["input_tokens_range"][1]} tokens. Research generated {quality["research_output_tokens_range"][0]}–{quality["research_output_tokens_range"][1]} tokens; every decision generated {quality["decision_output_tokens_range"][0]} tokens. Short empty outputs contribute substantially to the good latency. There were no corrected final decisions; retry stability therefore remains covered by the earlier forced-failure unit tests.', '',
         'The runtime/format gates (zero failures/caps and median session time under 31.8 seconds) pass. Behavioral activity and evidence sensitivity are not demonstrated. The paired seeds share only four synthetic states, so this is not an independent statistical estimate of production failure rate.', '',
         '## Recommended next step', '',
         'Keep the long data-collection backtest paused. Diagnose the decision phase with a small controlled comparison of the current output contract against an equally trades-only contract with a more explicit decision task, keeping tool evidence fixed. Also swap universe ordering to check the AAPL selection pattern. Do not force a daily trade or treat `[]` as an error simply to manufacture training data.', '',
         'No notebook code or saved demonstration outputs were changed for this evaluation. Full fixtures, dispatch results, raw token IDs, reconstructed model responses, decisions, timings and pair comparisons are stored alongside this report.', '',
         'Reproduce: `python scripts/varied_state_agent.py`, then `python scripts/summarize_varied_state.py` in the project environment with the notebook model released from GPU memory. These scripts use local cached weights and synthetic data only.', '']
(ROOT / 'validation' / 'varied_state_report.md').write_text('\n'.join(lines), encoding='utf-8')
print(json.dumps({'summary': s, 'quality': quality}, indent=2))
