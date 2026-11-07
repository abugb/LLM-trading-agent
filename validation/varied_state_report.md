# Varied-state full-menu evaluation — 2026-11-06

The unchanged notebook agent was evaluated offline on 24 episodes: four portfolio states × three seeds × two evidence scenarios. All five notebook tools were available with their actual descriptions and schemas. The model selected and generated its own research calls.

## Design

- States: $100,000 cash only; 100 AAPL shares plus $5,000 cash; the same holding with only $25 cash; and 50 shares each of MSFT, NVDA and GOOG plus $20,000 cash.
- Each positive/negative pair uses identical state, universe order, seed, weights and settings. Synthetic rising/falling OHLCV histories end at the same $100 close; synthetic company news contrasts positive and negative earnings/guidance. The notebook calculates RSI, MACD and quotes from these bars. No instructions to buy or sell were added.
- Decision cutoff: August 14, 2026 at 20:05 UTC. Every synthetic news timestamp precedes it. These scenarios are controlled tests, not claims about actual market events.
- Seeds: 7, 17, 29. Cached Qwen2.5-1.5B-Instruct, CUDA FP16. Generation budgets and prompts were unchanged. Only accepted decisions were checked for feasibility in a local simulated portfolio; there were no broker calls.

## Results

| Measure | Result |
|---|---:|
| Episodes with usable research | 24/24 |
| Failed episodes | 0/24 |
| Token-cap hits | 0 |
| Trade episodes | 0/24 |
| Researched no-trade episodes | 24/24 |
| Median / maximum session time | 2.89s / 3.28s |
| Median / maximum call time | 1.43s / 2.86s |
| Pairs with different visible evidence | 12/12 |
| Pairs with changed accepted decisions | 0/12 |
| SFT-eligible episodes | 0/24 |

### Research quality

Tool selections: `{"get_price_history": 8, "get_rsi": 16}`. Researched symbols: `{"AAPL": 20, "MSFT": 4}`. All results passed the existing mechanical usable-data guard. There were 0 research parse failures and 24 closing-tag repairs.

16/18 episodes with positions researched an owned stock. In the diversified portfolio, four of six episodes investigated its MSFT holding; two still investigated unheld AAPL. Research choices therefore show some response to portfolio state, while AAPL dominates overall. An order-swapped test would be needed to distinguish ticker/order preference from justified selection.

News, MACD and the quote tool were available but were not selected. Therefore this run tests the full menu being presented, not successful use of every tool. It cannot establish news interpretation quality. RSI sometimes indicates overbought/oversold conditions, so the evidence scenarios are not unambiguous instructions to buy/sell.

### Evidence responsiveness and activity

All 12/12 pairs made the same initial research choice. All 12/12 received different tool text in the final decision context, yet every final decision was `[]`. Both state variation and evidence variation produced no observable trading response in this sample.

This does not prove the model ignores evidence internally, nor does every evidence change warrant a trade. It does show that this configuration did not demonstrate an active evidence-sensitive trading policy across these controlled cases. No trades means reference accuracy among trades and trade profitability cannot be measured, and there are no SFT candidates.

### Latency and reliability

Input length ranged from 898 to 1408 tokens. Research generated 22–23 tokens; every decision generated 2 tokens. Short empty outputs contribute substantially to the good latency. There were no corrected final decisions; retry stability therefore remains covered by the earlier forced-failure unit tests.

The runtime/format gates (zero failures/caps and median session time under 31.8 seconds) pass. Behavioral activity and evidence sensitivity are not demonstrated. The paired seeds share only four synthetic states, so this is not an independent statistical estimate of production failure rate.

## Recommended next step

Keep the long data-collection backtest paused. Diagnose the decision phase with a small controlled comparison of the current output contract against an equally trades-only contract with a more explicit decision task, keeping tool evidence fixed. Also swap universe ordering to check the AAPL selection pattern. Do not force a daily trade or treat `[]` as an error simply to manufacture training data.

No notebook code or saved demonstration outputs were changed for this evaluation. Full fixtures, dispatch results, raw token IDs, reconstructed model responses, decisions, timings and pair comparisons are stored alongside this report.

Reproduce: `python scripts/varied_state_agent.py`, then `python scripts/summarize_varied_state.py` in the project environment with the notebook model released from GPU memory. These scripts use local cached weights and synthetic data only.

## Follow-up: decoding, contract and ordering diagnostics

The [decision diagnostics](decision_diagnostics_report.md) found a material decoding confound: `[]` is one token, and inherited repetition penalty 1.1 plus the active sampling settings makes it deterministic in 23/24 contexts. An explicit per-ticker contract elicited trade proposals but all 24 responses violated its schema; two of three forced-buy controls passed through simulated execution and temporary SFT preparation. Reversing the universe retained the AAPL preference and all-empty decisions. No notebook behavior or production datasets were changed.
