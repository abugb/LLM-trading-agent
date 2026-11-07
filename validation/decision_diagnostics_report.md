# Decision diagnostics — 2026-11-06

The requested sequence is complete: next-token probabilities, fixed-evidence contract comparison, and universe-order reversal. A separate forced-buy positive control tested the trade/collector/SFT path. The notebook, its saved outputs, and production training data were unchanged. All model inference used cached Qwen2.5-1.5B-Instruct on CUDA in FP16; synthetic evidence was reused from the varied-state run. No orders, external data requests, model training or full backtest occurred.

## 1. Token probabilities: the sampling configuration matters

Qwen encodes `[]` as **one token**, ID 1294. A literal `[` is token 58, `]` is token 60, and `[{` is token 52108. The two-token empty outputs were therefore `[]` followed by EOS, not two bracket tokens.

We measured forward-pass probabilities on all 24 saved final-decision contexts. The final calculations include every active sampling adjustment: inherited repetition penalty **1.1**, temperature **0.7**, inherited top-k **20**, and explicitly requested top-p **0.9**. The initial temperature/top-p-only calculation was incomplete and was replaced; raw model probabilities were unaffected. Processor-level calculations and a no-repetition-penalty distribution comparison were added without generating further decisions.

| Probability of the single `[]` token | Minimum | Median | Maximum |
|---|---:|---:|---:|
| Raw model | 43.44% | 85.24% | 96.80% |
| After repetition penalty | 71.10% | 94.46% | 98.47% |
| After temperature | 89.60% | 99.31% | 99.91% |
| After top-k and top-p | 92.15% | 100% | 100% |

**23/24 contexts have exactly 100% probability of `[]` after sampling adjustments.** The remaining context has 92.15% on `[]` and 7.85% on `[`. EOS has 100% sampling probability after `[]` in every context. More seeds with the current settings cannot change those 23 first-token decisions.

The raw probability of literal `[` ranges from 2.01% to 46.24% (median 11.55%). Alternatives and their top probabilities are saved, rather than treating every nonempty opening as a single token. In the diversified-holdings / seed-17 / negative-evidence context, raw `[` probability is 46.24%, higher than raw `[]` at 43.44%; the sampling adjustments reverse that balance.

The repetition penalty is consequential here: each prompt contains literal token `[` once or twice but **does not contain the exact standalone `[]` token**, despite mentioning empty arrays in natural-language context. The penalty acts on token IDs from the prompt as well as the generated continuation. It therefore penalizes a useful JSON-opening token that has already appeared while leaving the standalone empty-array token unpenalized.

Keeping temperature/top-k/top-p fixed but removing repetition penalty **in the distribution calculation only** reduces the number of deterministic-empty contexts from 23 to 16. In the least-empty context, sampling probability of `[]` becomes 47.77% instead of 92.15%. This was not a generated-policy test and does not establish that the resulting trades would be valid or sensible. It does mean the claim that only a prompt/contract change could help would be too strong: inherited decoding settings contribute materially.

For completeness, after hypothetically supplying a literal `[` prefix, raw probability of immediate `]` is only about 0.000007–0.000016%, and it is zero after sampling adjustments. The preferred continuation begins an object. This is a different token path from the single `[]` token; prefilling `[` would itself change the policy and could bias toward activity. It was used for conditional probabilities only, not to manufacture trades.

## 2. Explicit-task contract versus current contract

Each of the 24 recorded research contexts was replayed under both contracts with the same seed, fixed evidence, weights, 320-token decision budget and sampling settings. There was one generation per case, with no correction retries. The candidate replaces conflicting system/final-decision instructions together: one decision per researched ticker, `buy|sell|none`, positive size for trades or zero for none, and `research_ids`. It explicitly asks the model to consider evidence, holdings, cash and the $5,000 limit. Other conversation turns remain fixed.

| Measure | Current contract | Explicit-task candidate |
|---|---:|---:|
| Responses | 24 | 24 |
| Strictly valid | 24 | **0** |
| Accepted trade episodes | 0 | 0 |
| Token-cap hits | 0 | 0 |
| Output tokens, including EOS | 2 | 38–43 |
| Median decision-call time | 0.51s | 2.15s |

The current contract returned `[]` in every case. The explicit-task outputs all used the wrong field, `research_id`, instead of `research_ids`; 17 also wrapped JSON in Markdown fences. None was accepted or executed.

A separately labeled **inspection-only audit** removed outer fences to read the proposed action/size, without repairing fields for validation or execution. It found:

- 11/24 outputs proposed buy/sell actions, and 3/12 positive/negative pairs changed action/size.
- Two proposals bought a $100 share with only $25 cash.
- One proposed selling negative 50 shares from the cash-only state.
- The remaining pair differences and trade mentions are not valid trading outcomes; they only show that the alternate task can elicit nonempty, sometimes evidence-dependent text.

This candidate does not fix the pipeline and should not replace the notebook contract. The model did not remain entirely flat under the alternate prompt, so the experiment does not establish inability to react to evidence under every format. It does expose weak schema and constraint adherence. The comparison changes both task wording and output contract; it cannot isolate which component caused the differences.

## Positive control: real model output through the trade path

Three independent seeds received an explicit instruction to buy exactly one AAPL share citing R1, using the original trades-only contract and the fixed cash-only research context. This tests plumbing, not investment judgment.

- **2/3 passed** the original strict parser and reference check, sizing validator, and simulated execution at $100.
- Both passed the actual collector, JSON serialization round trip, inference-template verification, labeling and SFT preparation with non-masked completion tokens.
- The third generated the correct JSON trade followed by explanatory prose and was correctly rejected as extra data.

Collector files were created only inside a temporary directory that was cleaned up. No control example or experimental policy output was added to the project's SFT data. The tests demonstrate a working valid-output path, not reliable autonomous policy behavior.

## 3. Universe-order reversal

All 24 original end-to-end episodes were rerun with only the allowed-symbol ordering reversed, placing XLI first and AAPL last. State values, seed, evidence generator, full five-tool menu, prompts and sampling settings otherwise match the original run. The model still generated its own research.

| Measure | Original order | Reversed order |
|---|---:|---:|
| AAPL researched | 20 | 22 |
| MSFT researched | 4 | 2 |
| RSI calls | 16 | 16 |
| Price-history calls | 8 | 8 |
| Empty final decisions | 24 | 24 |
| Failures / cap hits | 0 / 0 | 0 / 0 |
| Median session time | 2.89s | 2.91s |

Only 2/24 research name/argument choices changed. No episode selected the new first ticker. This weakens the explanation that the agent merely copies the first ticker in the universe. AAPL preference persists when it is last; familiar-symbol bias and the AAPL example in the current decision instructions remain confounds. The order experiment does not isolate those factors.

All reversed-order research calls again needed closing-tag restoration: this is the observed normal path for this model/configuration, not a rare exception. News, MACD and quote tools remained unselected, so their model-driven interpretation and news compaction are still not validated by these runs.

## What to do next

Do not begin a long training-data collection run or adopt this explicit-task candidate. The current policy is effectively locked into an empty-array token by the combined prompt/model distribution and decoding settings; the alternate contract produces malformed and sometimes infeasible proposals. The positive control rules out a universally broken trade-to-SFT path.

The next narrowly justified experiment is to set `repetition_penalty=1.0` explicitly **in an isolated comparison**, retaining the current contract and fixed evidence, and measure valid trades, failures and evidence responsiveness. This tests a concrete decoding confound rather than another round of broad prompt tuning. It may still leave many cases empty; the probability-only ablation already shows 16/24 deterministic-empty contexts. If reliability remains poor, compare schema-constrained decoding or a stronger model on the same fixed cases rather than repeatedly expanding prompts or forcing daily trades.

## Artifacts and limitations

- `decision_diagnostics.json`: all probability tables and processor stages, exact messages, raw token IDs, responses, strict validation results, control results, order-swapped trajectories and inspection-only audit.
- `scripts/decision_diagnostics.py`: staged evaluator; `--probabilities-only` refreshes probabilities while preserving completed experiments.
- `scripts/summarize_decision_diagnostics.py`: derives summary metrics and the audit from the completed results.
- `decision_diagnostics_console.txt` and `decision_probability_console.txt`: execution logs.

The original stages ran in the requested order; the probability stage was subsequently recalculated to include the inherited settings and expose each processor's contribution. All outputs remain in validation artifacts. These are correlated synthetic cases from four states and three seeds, not independent production samples, a backtest, or evidence of profitability. Current research scopes each episode to its first successful result. No additional prompts were tried after the explicit candidate failed.

## Follow-up: repetition penalty 1.0

The [paired generation comparison](repetition_penalty_report.md) is complete. On the same 24 contexts and seeds, both penalty 1.1 and 1.0 produced `[]` in every case, with zero failures/cap hits and approximately 0.44-second median decision latency. The probability shift did not translate into different sampled decisions. This setting alone is not a demonstrated policy fix; the notebook remains unchanged.
