# Repetition-penalty comparison — 2026-11-06

**Changing `repetition_penalty` from 1.1 to 1.0 did not change any generated decision in this test.** Both settings returned `[]` in all 24 saved contexts.

## Controlled comparison

The evaluator ran 48 generations: each of the 24 fixed decision contexts under both penalty settings. Prompts, recorded synthetic tool evidence, model weights, seed, temperature 0.7, top-k 20, top-p 0.9, and the 320-token budget were identical within each pair. The configured model was cached Qwen2.5-1.5B-Instruct in CUDA FP16. Each generation used one attempt, without corrective retries.

The contexts cover the same four portfolio states, three seeds (7, 17, 29), and two contrasting evidence scenarios as the prior evaluations. Research was not regenerated: this isolates decision-phase decoding and does not test the effect of disabling the penalty during research or reflection.

## Results

| Measure | Penalty 1.1 | Penalty 1.0 |
|---|---:|---:|
| Valid researched empty decisions | 24/24 | 24/24 |
| Trade proposals / simulated fills | 0 / 0 | 0 / 0 |
| Failed responses | 0 | 0 |
| Token-cap hits | 0 | 0 |
| Evidence pairs with changed trade decisions | 0/12 | 0/12 |
| Generated tokens, including EOS | 2 each | 2 each |
| Median decision-call latency | 0.440s | 0.441s |
| Maximum decision-call latency | 0.727s | 0.577s |

All 24 penalty comparisons produced identical response text. Latencies measure decision generation only, excluding research and model loading. They should not be compared directly with full-session timings from earlier runs.

## Interpretation

The earlier probability diagnostic remains valid: removing the repetition penalty reduced deterministic-empty contexts from 23 to 16, leaving some mass on nonempty openings in eight contexts. Allowing those alternatives does not guarantee sampling them. The chosen seeds still selected `[]` in every case; these correlated seeded contexts are not an independent statistical estimate of a trade rate.

This intervention alone has not demonstrated useful trading activity or evidence sensitivity. The valid format and low latency remain, but there are still no SFT candidates. Feasibility and nonempty SFT serialization could not be exercised in this experiment because no trade was proposed; those paths were tested separately by the prior forced-buy control.

I would not start the long backtest or adopt this setting as a demonstrated policy fix. This result supports stopping broad prompt/sampling tweaks as the immediate approach. A next controlled comparison should separate schema compliance from policy quality: test the explicit per-researched-ticker contract under constrained decoding, or compare a stronger model against the same fixed evidence. Constraints can prevent formatting failures but cannot guarantee sensible decisions. No such follow-up was run here.

## Artifacts and checks

- `scripts/repetition_penalty_comparison.py`: reproducible offline evaluator.
- `validation/repetition_penalty_results.json`: full responses, raw token IDs, timings, prompt hashes, validation outcomes, pair summaries, environment and source hashes.
- `validation/repetition_penalty_console.txt`: generation log.

Verified all 48 samples, matching prompt hashes/input lengths within every pair, script syntax, and the unchanged notebook hash. No notebook cells or outputs were edited or executed, no external tool APIs or broker orders were called, and no training examples were saved. Temporary evaluation state was cleaned up.
