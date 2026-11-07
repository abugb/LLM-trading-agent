# Agent validation — 2026-11-06

Implementation: `main.ipynb`. Environment: local Qwen/Qwen2.5-1.5B-Instruct, FP16 on CUDA; PyTorch 2.6.0+cu124, Transformers 5.22.1. Cached weights and historical bars only; no broker orders, live data calls, notebook demonstration execution, or full backtest.

## Pre-change replay

The pre-change engine and prompts were preserved before implementation. `scripts/replay_prompts.py` ran three arms against two reconstructed states with seeds 7, 17 and 29, temperature 0.7, top_p 0.9 and a 700-token cap. Each arm used identical weights, state, seed, generation settings and fixed tool responses.

| Arm | Samples | Token-cap hits | Total explicit HOLD entries |
|---|---:|---:|---:|
| Old prompt | 6 | 0 | 1 |
| Old minus all daily-trade requirements | 6 | 0 | 0 |
| Current pre-fix prompt | 6 | 1 | 35 |

For August 17, seed 29, the current prompt emitted 700 tokens and 35 HOLD entries, while the old and old-minus-rule prompts emitted 58 and 211 tokens respectively. On August 14, all arms emitted 18 tokens and no HOLD entries. This reproduces the long-output failure but does **not** establish that removing the daily-trade rule caused it. The old-minus-rule arm also permits HOLD in the schema as part of removing all trade requirements.

All arms use the corrected Qwen chat template, so this does not test the former broken role formatting. One state has a fixed recorded quote conversation and one has no prior tool response. The states are reconstructed, not exact full captured transcripts; fixed responses cannot reproduce differences in model-selected research. These are small seeded samples, not a causal or performance study.

Artifacts: `pre_change_agent.json`, `prompt_replay_fixture.json` (including removed clauses), and `prompt_replay_results.json` (text, raw IDs, tokens, timings and component counts).

## Real-model smoke test

`scripts/smoke_agent.py` used both reconstructed states and three seeds: six independent episodes. Gates fixed before generation: zero failures, zero cap hits, identical corrected-retry input lengths, short calls under 6 seconds (reference 2 seconds; input <=2,600 and output <=35 tokens), and median session time under 31.8 seconds (3 × the earlier 10.6-second reference).

The first attempt failed all six episodes: Qwen emitted complete tool JSON followed by `<|im_end|>` without the closing tool tag. `agent_smoke_initial_failures.json` preserves that result. After narrow EOS-envelope normalization, the final run passed:

| Measure | Result |
|---|---:|
| Failed episodes | 0 / 6 |
| Cap hits | 0 |
| Intentional researched no-trade episodes | 6 / 6 (100%) |
| Median session time | 3.12 seconds |
| Median call time | 1.50 seconds |
| Longest call | 2.93 seconds |
| Research input / generated tokens | 840 / 22–23 |
| Decision input / generated tokens | 948–1,476 / 2 |

Every research call ended at EOS; all six needed closing-tag normalization. Thus `</tool_call>` stopping was not exercised by these real outputs; offline tests cover the closing-tag path. The raw token IDs/text are preserved in `agent_smoke_results.json`. Research prefixes are reconstructed before parsing and history storage. The closing-tag repair is permitted only for a complete JSON document at EOS; no truncated calls are salvaged.

Raw one-month price results measured 1,241–1,353 tokens and became 558-token context while retaining the latest complete rows. Five-day results measured 288 tokens, becoming 332 with the explicit coverage/omission note. RSI results were 30 tokens. This measures actual research costs; it does not attribute the previous 4,807-token retry prompt to research data.

No retry occurred in the passing smoke run, so its flat-retry check is vacuous. Forced malformed-response unit tests verify identical input lengths across corrected retries and prove failed outputs/corrections do not accumulate. The 6-second/31.8-second gates are generous sanity checks, not matched-length benchmarks; these short empty decisions are not directly comparable to earlier long generations.

The smoke registers historical market tools only. It does not test the full news-enabled menu, live news retrieval, varied positions, or trading competence. All six episodes selected AAPL research and no trades. Consequently there were **zero SFT candidates**, not six useful training examples, and no nonempty denominator for measuring corrected-trade exclusion in the real run. The mechanical reference check proves only that cited evidence was supplied, not that it influenced a decision.

The final notebook also adds trade/reference counters to diagnostics; this reporting-only addition followed the smoke run and does not alter prompts or generation. Deterministic tests cover those counters.

## Offline regression checks

`python -m unittest discover -s tests -v`: **43 passed**. See `unit_tests.txt`.

Coverage includes:

- Unresearched empty decisions, out-of-universe or fabricated references, unsupported clock arguments, malformed and EOS-terminated tool calls, strict trades-only arrays and phase budgets.
- Bounded retries from clean history, no failed-response accumulation, no research correction in final prompts, and exclusion of corrected final decisions.
- Recent complete price rows, omission notes, complete article boundaries and unavailable oversized unknown formats.
- Exact chat-template serialization through a JSON round trip; prompt masking, EOS supervision, legacy/tampered/overlength rejection, collector exclusion counters.
- Existing calendar/cutoff/cache, next-open fill, dollar sizing, estimated valuation, account guard and reflection storage tests.
- Failed sessions retain holdings, all valuation dates and market-driven returns; result fields remain usable by existing callers.
- Valid Python syntax for all ordinary notebook code cells; the existing package-install magic cell is excluded from AST parsing.

Notebook edits replace source blocks only. Existing saved outputs and metadata were not cleared or regenerated. Working-tree differences already include the user's notebook executions and additional cell, so Git HEAD is not an exact pre-task output baseline.

## Before a long run

Reload the changed definitions in notebook order and the implemented Task 2 tool registrations. Existing kernel functions do not update just because the notebook is saved. Use freshly collected examples for the new SFT contract; old files are preserved but incompatible entries are rejected during preparation.

Keep the 60-session run paused until a small run with the full tool menu confirms acceptable research, latency, failure rate **and activity**. The mechanical smoke gates passed, but 100% no-trade in this sample warrants inspecting decisions before spending time on collection. Do not restore forced daily trading merely to produce examples. Training and evaluation periods and label definitions remain unchanged.

## Follow-up: varied states and full tool menu

The [24-episode varied-state evaluation](varied_state_report.md) is complete. All five tools were available. There were zero failures or cap hits and median session time was 2.89 seconds, but all 24 decisions were empty and none of the 12 contrasting-evidence pairs changed the accepted decision. Research choices showed some response to holdings (MSFT in four diversified-portfolio episodes), while no trading activity or SFT candidates emerged. This supersedes the six-episode smoke test as the broader behavioral check; it still does not establish useful trading behavior.
