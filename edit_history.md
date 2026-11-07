# Notebook edit history

This file records changes to `main.ipynb` that depart from the original provided material or assignment expectations. Entries are added as those changes are made to support the project report.

## 2026-10-30: Replaced Google Colab Integrations with Local Caching and Dotenv

- **Affected Section**: Section 1.1 (Dependencies), Section 1.3 (Set Up Local Cache, cell `qndhss03ny1c`), and Section 1.4 (Configuration & API Keys, cell `79zv7l8yw2sr`).
- **What Changed**: Replaced Google Drive mounting (`google.colab.drive`) and Colab user secrets (`google.colab.userdata`) with local directory caching under `.cache/stock_agent` via `pathlib.Path` and loaded environment secrets from a local `.env` file using `python-dotenv`.
- **Why It Was Necessary**: Execution environment is a local development workstation rather than Google Colab. Local directory paths and `.env` prevent hardcoded credentials and permit local offline disk caching.
- **Effect on Expected Behavior or Grading**: Secrets remain secure in `.env` without hardcoded keys. Cache behavior remains functionally identical to Drive storage while pointing to local project storage.
- **Validation**: Verified local `.cache/stock_agent` directory creation and successful retrieval of Alpaca/Alpha Vantage credentials via `load_dotenv()`.

## 2026-11-05: Replaced Alpha Vantage with Alpaca Market Data API for Real-Time Quotes

- **Affected Section**: Task 2 (`get_global_quote` function and tool registration, cell `9bbl1g9sul8j`).
- **What Changed**: Modified `get_global_quote` to fetch quotes from Alpaca's Market Data snapshot endpoint (`https://data.alpaca.markets/v2/stocks/{symbol}/snapshot`) using existing Alpaca API credentials (`ALPACA_API_KEY` / `ALPACA_SECRET_KEY`) instead of Alpha Vantage's `GLOBAL_QUOTE` endpoint. Also made symbol parsing resilient to various argument schemas (`symbol`, `symbols`, `ticker`).
- **Why It Was Necessary**: Alpha Vantage free-tier enforces a strict rate limit of 25 calls per day. Running repetitive paper-trading loops quickly exhausts this quota, resulting in rate-limit errors during quote retrieval. Alpaca's market data API provides a significantly higher rate limit (200 requests/minute) under the existing account, ensuring reliable quote retrieval.
- **Effect on Expected Behavior or Grading**: The output string format (`Quote <SYMBOL>: $<PRICE> | change: <CHANGE> (<PCT>%) | vol: <VOLUME>`) matches the original specification and downstream parser expectations exactly. The tool description in the registry was updated to reference Alpaca Market Data.
- **Validation**: Tested live calls across multiple tickers (`AAPL`, `NVDA`, `SPY`) with `requests` using Alpaca credentials; verified that latest trade price, daily change, percentage change, and volume are properly extracted and formatted. AST validation confirmed valid notebook syntax.

## 2026-11-05: Replaced Alpha Vantage with yfinance for RSI Calculation

- **Affected Section**: Task 2 (`get_rsi` function and tool registration, cell `9bbl1g9sul8j`).
- **What Changed**: Replaced the external Alpha Vantage API call in `get_rsi` with local calculation using Wilder's 14-period exponential smoothing on `yfinance` daily closing prices (`period="3mo"`). Also added flexible input handling for varied model call arguments (`symbol`, `symbols`, `ticker`).
- **Why It Was Necessary**: Alpha Vantage free-tier has a limit of 25 calls per day, and its RSI endpoint frequently failed or hit quotas during backtesting and live trading. Local computation via `yfinance` eliminates all rate limits, prevents API latency/timeouts, and removes external API dependency for technical indicators.
- **Effect on Expected Behavior or Grading**: Returns the identical output string format expected by the prompt and validator (`RSI(14) for <SYMBOL>: <VAL> (<SIGNAL>) [<DATE>]`). Updated tool registry description to indicate `yfinance`.
- **Validation**: Executed live calculation for `AAPL`, `MSFT`, and `NVDA`, successfully verifying output formatting, numeric calculations, and correct categorization into `neutral`, `overbought`, and `oversold`. Verified full notebook AST syntax.


 

## 2026-11-05: Added Order Status Validation Before Reflection Queueing

- **Affected Section**: Task 5 (`run_trading_loop` Step 7, cell `6jats7k4qsua`).
- **What Changed**: Added an explicit check on `order_result` status and presence of an order ID before appending trades to `pending_reflections`. Excludes non-executed or failed order statuses (`rejected`, `canceled`, `expired`, `suspended`).
- **Why It Was Necessary**: Previously, any order that did not raise an exception was queued for reflection, even if rejected or canceled by the broker. Queueing failed trades leads to invalid reflections where the model reflects on equity changes that never occurred.
- **Effect on Expected Behavior or Grading**: Prevents false reflections from polluting the memory store. Only genuine, successfully placed orders are evaluated after the delay window.
- **Validation**: AST syntax check confirmed valid Python syntax in the notebook cell. Verified logic paths correctly route successful orders to `pending_reflections` and skip rejected/canceled statuses with a logged notification.

## 2026-11-06: Request-Keyed Caching with Freshness Policy for News and Historical Prices

- **Affected Section**: Section 1.9 (News Retrieval, cell `mjb1li57i94d` and markdown cell `uzig5a07ompc`), Test 1.9 (cell `rGnyPI9neWew`), and Section 1.14 (`fetch_historical_prices`, cell `i53gzy9p691i`).
- **What Changed**:
  - Added `canonicalize_symbols` helper to strip whitespace, uppercase, deduplicate, and sort ticker lists.
  - Updated news cache keys and file naming in `_get_news_cache_path` and `get_news_for_symbols` (cell `mjb1li57i94d`) to key on canonical symbols, date, article limit, and request mode (`live` vs. `hist`) using a stable SHA-256 hash. Stored and verified these parameters in the JSON payload.
  - Implemented 15-minute live news freshness expiration (`LIVE_NEWS_EXPIRY_SECONDS = 15 * 60`) for live queries and in-progress dates, while keeping past historical date cache entries reusable indefinitely.
  - Added batch failure guards: news fetched in batches of 5 symbols only saves to cache if all batches succeed; partial failures return available articles with warning notices without writing an incomplete cache entry.
  - Updated Test 1.9 (cell `rGnyPI9neWew`) to call `_get_news_cache_path(["AAPL"])` matching the new signature, while preserving all existing test demonstration outputs and metadata.
  - Updated `fetch_historical_prices` in cell `i53gzy9p691i` to key cache files by canonical symbols and period using a SHA-256 parameter hash and payload verification, while preserving 24-hour expiration and return dictionary structure.
  - Removed obsolete date-only news cache files from `.cache/stock_agent` (`news_2025-01-15.json`, `news_2026-09-03.json`, `news_2026-11-04.json`), leaving `historical_prices.json` and `sft_data.jsonl` intact.
- **Why It Was Necessary**:
  - The previous caching strategy keyed news strictly by date (`news_{YYYY-MM-DD}.json`) and historical prices to a single global file (`historical_prices.json`). A query for a single ticker (`["AAPL"]`) could poison the cache for multi-ticker queries (`WHITELIST`) on the same date, or vice versa.
  - Live news previously remained cached all day, failing to capture new breaking articles during intraday paper trading.
  - Batch failures previously risked caching truncated news results as complete.
- **Effect on Expected Behavior or Grading**:
  - Prevents cross-ticker cache collisions and mismatched historical period loads.
  - Preserves output structure and return types (`str` for news, `dict` with `dates` and `prices` for historical prices) so downstream agent logic and backtesting continue working seamlessly.
  - Preserved all demonstration cell outputs and metadata in Test 1.9 (cell `rGnyPI9neWew`) for grading compliance.
- **Validation**:
  - Executed isolated unit test suite covering: symbol canonicalization & permutations, key uniqueness across symbols/dates/limits/modes, cache hit & payload parameter verification, live news 15-minute expiration & refresh, indefinite caching of past historical dates, prevention of cache writes on batch failure (total and partial), historical price keying by symbols & period with 24-hour expiration, and preservation of Cell 21 demonstration outputs. All 9 tests passed.
  - AST parsed all code cells in `main.ipynb` to guarantee clean syntax.
- **Remaining Limitations**:
  - Backtesting tools can still query price/indicator data newer than the simulated date.
  - Historical news queries cover the entire day rather than enforcing a decision-time intraday cutoff.

## 2026-11-06: Cache Path Sanitization, In-Notebook Test Expansion, Price Fetching Robustness, and Trading Loop Safety

- **Affected Section**: Section 1.9 (News Retrieval, cell `mjb1li57i94d`), Test 1.9 (cell `rGnyPI9neWew`), Section 1.14 (`fetch_historical_prices`, cell `i53gzy9p691i`), and Task 5 (`run_trading_loop`, cell `6jats7k4qsua`).
- **What Changed**:
  - **Filename Sanitization & Path Safety (Cells `mjb1li57i94d`, `i53gzy9p691i`)**: Sanitized all variable filename components (`symbols`, `date`, `period`) to strictly restricted alphanumeric characters, enforced `os.path.basename` extraction, and added defense-in-depth assertion verifying resolved paths remain strictly inside `CACHE_DIR`. The parameter hash uniquely and stably captures raw request parameters.
  - **In-Notebook Test Expansion (Cell `rGnyPI9neWew`)**: Added in-notebook automated tests (Tests 6 through 10) directly into Test 1.9 covering canonicalization & permutation stability, distinct keys across all parameters, 15-minute live news expiry, incomplete batch failure guards, and filename sanitization/traversal prevention. Preserved existing demonstration output lines while reflecting the new passing tests.
  - **Robustness in Historical Price Fetching (Cell `i53gzy9p691i`)**: Handled empty DataFrames, `None` responses, DataFrames missing `"Close"` columns, and network/download exceptions from `yfinance`. Returns a well-formed empty structure (`{"dates": [], "prices": {}, ...}`) instead of raising `KeyError` or crashing, and skips writing cache entries on empty data.
  - **Trading Loop Safety & State Verification (Cell `6jats7k4qsua`)**:
    - When `get_state(tc)` fails in Step 1, the loop now immediately halts the iteration and skips order submission rather than falling back to an imaginary $100,000 cash balance.
    - In Step 4 (reflection processing), explicitly verifies whether the order actually filled (`tc.get_order_by_id`) before allowing `reflect_on_trade` to run, discarding reflections for orders that were canceled, expired, or never executed.
- **Why It Was Necessary**:
  - Unsanitized user/model inputs in cache filenames risked invalid paths or directory traversal outside `CACHE_DIR`.
  - The notebook's internal Test 1.9 cell previously only verified basic requests and did not give the user a way to run and verify the new caching logic directly in the notebook.
  - Missing `"Close"` or network failures in `yfinance` caused unhandled crashes during backtesting.
  - Fabricating account balances on state fetch failures in Task 5 created severe real-world and paper trading risks by placing orders based on an imaginary portfolio. Reflecting on unfilled orders taught false signals to the memory store.
- **Effect on Expected Behavior or Grading**:
  - Prevents security/traversal vulnerabilities and unexpected crashes.
  - Allows full, reproducible in-notebook test verification of caching behavior.
  - Protects capital and portfolio integrity in paper trading.
- **Validation**:
  - Validated with unit tests in `verify_all_fixes.py`: verified path traversal rejection, empty/malformed `yfinance` frame handling, in-notebook test execution of Tests 1–10, trading loop safety abort on state error, and reflection filtering on order fill status. All tests passed.
  - AST parsed all code cells in `main.ipynb`.

## 2026-11-06: Trade-Level Outcome Reflection and Terminal-Wait Order Execution Policy

- **Affected Section**: Section 1.8 (`submit_order`, cell `kdiit9drhmvj`), Task 3a (`TradingMemory.add_memory`, cell `s5f0s4egxhum`), Task 3b (`calculate_trade_outcome` and `reflect_on_trade`, cell `vwqlde6m0gsm`), and Task 5 (`run_trading_loop` and `get_current_stock_price`, cell `6jats7k4qsua`).
- **What Changed**:
  - **Trade-Level Outcome Calculation (`calculate_trade_outcome`, Cell `vwqlde6m0gsm`)**: Replaced portfolio-level equity comparisons (`curr_equity - prev_equity`) with trade-specific financial outcomes:
    - *Buys*: Mark-to-market unrealized P&L evaluated at reflection time: `pnl = (reflection_quote - filled_avg_price) * filled_qty` and `pnl_pct = (reflection_quote / filled_avg_price - 1) * 100`.
    - *Sells*: Realized P&L evaluated against pre-trade cost basis: `pnl = (filled_avg_price - cost_basis) * filled_qty` and `pnl_pct = (filled_avg_price / cost_basis - 1) * 100`, where `cost_basis` (`avg_entry_price`) is captured from `state["positions"]` prior to order submission.
    - Zero, negative, missing, or non-finite inputs return `None` to prevent fabricating outcomes.
  - **Broker Fill Extraction (`submit_order`, Cell `kdiit9drhmvj`)**: Safely extracts `filled_qty` and `filled_avg_price` as float or `None` alongside existing keys (`id`, `status`, `symbol`, `side`, `qty`).
  - **Memory Metadata Persistence (`TradingMemory.add_memory`, Cell `s5f0s4egxhum`)**: Added optional `trade_context` parameter to store structured outcome metadata (`pnl`, `pnl_pct`, `outcome_type`, `filled_qty`, etc.) in the memory entry alongside `situation`, `reflection`, and `timestamp`, preserving full backward compatibility for two-argument callers.
  - **Trade-Level Reflection Prompting (`reflect_on_trade`, Cell `vwqlde6m0gsm`)**: Updated to accept specific trade parameters (`side`, `filled_qty`, `entry_or_cost_basis`, `fill_avg_price`, `reflection_price`, `pnl`, `pnl_pct`, `outcome_type`) while retaining fallback support for legacy portfolio equity arguments (`prev_equity`, `curr_equity`). Prompt explicitly instructs the LLM that short-term price movements on buys are unrealized snapshots rather than finalized profit, preventing the agent from conflating short-term noise with sound trade execution.
  - **Trading Loop Terminal-Wait Policy & Execution (`run_trading_loop`, Cell `6jats7k4qsua`)**:
    - Pre-trade cost basis is captured from `state["positions"]` before submitting sells; sells lacking valid cost basis are flagged and skipped from reflection queueing.
    - Added `MAX_REFLECTION_RETRIES = 5` and `get_current_stock_price(symbol)` helper fetching real-time market snapshots from Alpaca Market Data with yfinance fallback.
    - In Step 4 (reflection processing), order status is refreshed via `tc.get_order_by_id(order_id)`. Adopted a terminal-wait policy: open/unfilled orders are deferred up to 5 iterations to allow execution to complete; terminal orders with 0 shares filled are discarded without reflection; partial fills that terminate or time out reflect strictly on executed shares (`filled_qty`).
    - For buys, if the market quote is temporarily unavailable, reflection is deferred up to retry limit and cleanly skipped without generating false reflections.
    - Stored reflections are prefixed with a standardized summary header `[SYMBOL SIDE (OUTCOME_TYPE): P&L $... (%)]` and saved with structured `trade_context`.
- **Why It Was Necessary**:
  - The previous implementation compared overall account equity (`curr_equity - prev_equity`) to evaluate individual trades. Whole-portfolio equity reflects aggregate market movement, cash drag, and unrelated open positions; for example, buying a winning stock while a larger held position dropped would cause the agent to reflect that the buy trade lost money.
  - Orders submitted to Alpaca paper trading or live brokers are not guaranteed to fill immediately or completely at submit time. Evaluating orders without checking fill status or deferring open orders caused reflections on unexecuted trades.
- **Effect on Expected Behavior or Grading**:
  - Downstream reflection quality and causal attribution are dramatically improved.
  - Full backward compatibility is preserved for Cell 45 (`reflect_on_trade` test cell) and any callers relying on `prev_equity`/`curr_equity`. All saved demonstration outputs for Task 3 in Cell 45 are strictly preserved.
- **Validation**:
  - Created and executed comprehensive isolated test suite (`validate_trade_reflection_plan.py`) covering: broker fill parsing in `submit_order`, mark-to-market buy calculations, realized sell calculations, partial fill accounting on cancellation, missing/invalid input rejection, end-to-end trading loop reflections for buys and sells, open order deferrals and terminal zero-fill discard, and bounded retry/skip on quote failure. All 8 tests passed.
  - Verified full notebook AST syntax.
  - Verified backward compatibility with Task 3 demonstration outputs.
  - Re-ran prior cache, price robustness, and trading loop safety validation suites (`verify_all_fixes.py`, `test_cache_keys.py`, `test_new_fixes.py`) with all tests passing.
- **Remaining Limitations**:
  - Task 1's `TradingDataCollector` still labels episodes for fine-tuning using portfolio equity change (`curr_equity - prev_equity`), which remains a coarse portfolio-level learning signal distinct from trade-level reflection memory.
  - Backtesting tools can still query price/indicator data newer than the simulated date.

## 2026-11-06: Corrected Partial-Fill Reflection Eligibility and Added Price Provenance

- **Affected Section**: Task 3 (`reflect_on_trade`, cell 43) and Task 5 (`get_current_stock_quote` / `run_trading_loop`, cell 56).
- **What Changed**:
  - Replaced substring-based terminal status detection with an explicit terminal-status allowlist. `partially_filled` and other nonterminal/unknown states now remain queued for up to five retries; if still nonterminal, the reflection is skipped. The loop only calculates a reflection once an order reaches an explicit terminal state, using its final cumulative filled quantity and average fill price.
  - Added quote source and timestamp metadata for buy marks (Alpaca trade/bar timestamp when available, otherwise retrieval time; yfinance fallback is identified separately). The reflection prompt and memory context include this provenance.
  - Added structured `symbol`, `side`, order ID, and fill details to each stored `trade_context`.
  - Numeric normalization now rejects infinities as well as NaN.
- **Why It Was Necessary**: `partially_filled` contains the word `filled` but is not terminal, so substring matching could record an outcome while more shares could still execute. Structured identifiers and quote provenance make stored outcomes easier to audit and interpret.
- **Effect on Expected Behavior or Grading**: Open orders are no longer reflected prematurely. If an order remains open after the bounded retry window, no reflection is stored; terminal partial fills are evaluated only for executed shares. Legacy `get_current_stock_price` remains available as a price-only wrapper.
- **Validation**: Source-level review only. Notebook cells were not executed, and no Alpaca orders or live trading loop were run.
- **Remaining Limitations**: The yfinance fallback provides a retrieval timestamp, not necessarily the underlying market-data timestamp. The bounded timeout skips reflection rather than canceling an order.

## 2026-11-06: Verified Paper Accounts and Persisted Pending Reflections

- **Affected Section**: Section 1.4 configuration (cell 9), Section 1.8 trading infrastructure (cell 17), and Task 5 trading loop (cell 56).
- **What Changed**: Parsed `ALPACA_PAPER` as an explicit boolean, defaulting to paper mode when unset and rejecting invalid values. Trading clients and order submissions now require the official Alpaca paper endpoint and an authenticated account; each submission checks that the account still matches the loop's verified account. Replaced the in-memory reflection queue with an account-scoped JSON queue under `CACHE_DIR`, written with atomic replacement. Saved deadlines use elapsed seconds from submission, and retry counts survive restarts. Completed order IDs are checked against saved memories to avoid duplicate reflections after recovery.
- **Why It Was Necessary**: Environment strings such as `false` were previously passed directly as the SDK's boolean setting, and the notebook printed paper mode without checking the client endpoint. Pending reflections and their delays disappeared when a loop or kernel stopped.
- **Effect on Expected Behavior or Grading**: This notebook now refuses live-mode order submission. Reflection timing uses elapsed seconds (`REFLECTION_DELAY_LOOPS * LOOP_SECONDS`) rather than counting completed loop iterations. Pending reflections remain queued if memory is unavailable; a corrupt or unwritable queue stops the loop instead of being overwritten. Saved notebook outputs were retained.
- **Validation**: Eight offline unit checks cover configuration parsing, authenticated paper-endpoint guards, account isolation, restart recovery, retry/deadline persistence, failed writes, and corrupt or incomplete queue handling. Affected cells were parsed for Python syntax. No Alpaca connection, order submission, model inference, or trading loop was run.
- **Remaining Limitations**: The account mode is established by the configured paper endpoint and successful authentication, not an independent broker-provided paper-mode field. Only one process should use an account's queue at a time. A crash between broker acceptance and persisting the returned order ID can leave an order without a queued reflection. Collector outcome updates remain in memory.

## 2026-11-06: Point-in-Time Daily Backtesting

- **Affected Section**: Dependencies (cell 3), news retrieval (cell 19), tool dispatcher (cell 23), decision engine (cell 27), and backtesting infrastructure (cell 31); related descriptions in cells 18 and 30.
- **What Changed**: Added the NYSE exchange calendar; backtests make decisions five minutes after each completed session close and simulate those orders at the next session open. Historical news is bounded by the trusted decision timestamp; historical price history, RSI, MACD, and quote tools use only eligible adjusted yfinance bars. Historical bar cache keys include the data range and adjustment setting; historical news keys include the cutoff. Buys are reduced to available cash, missing opening prices skip trades, and missing closing prices carry the latest known value with an estimate flag. Final-session decisions remain unfilled; collector outcomes are recorded after the next session only when at least one order fills.
- **Why It Was Necessary**: The previous implementation exposed current price tools and full-day news to simulated past decisions, and filled decisions using the same day's close. These changes align research, valuation, and execution with a single simulated clock.
- **Effect on Expected Behavior or Grading**: Backtest timing and resulting returns/training examples change. Existing result keys, collector labels, and base-versus-fine-tuned evaluation periods remain available; saved notebook outputs are retained. Adjusted prices are an approximation rather than explicit split/dividend accounting.
- **Validation**: Offline mocked tests exercise decision cutoffs, news and price caches, calendar holidays/early closes/daylight saving, next-open execution, reduced buys, missing prices, estimated valuations, final-session orders, and collector updates. No Alpaca order or paper-trading loop was run. Full model inference and live data retrieval were not exercised.
- **Remaining Limitations**: Historical data may contain later adjustments or revisions; the model may have learned about the test period during pretraining. The evaluation period still overlaps training, and transaction costs and slippage are not modeled.

## 2026-11-06: Dollar-Based Per-Trade Limit

- **Affected Section**: Configuration (cells 1 and 9), trading infrastructure (cell 17), decision validation (cell 23), decision engine (cell 27), simulated portfolio (cell 31), and trading loop (cell 56).
- **What Changed**: Replaced the 50-share `MAX_QTY_PER_TRADE` with `MAX_TRADE_VALUE = 5000.0`, an estimated dollar limit per buy or sell. The agent still requests whole shares; validation reduces quantities using trusted decision-time historical prices in backtests or recent Alpaca snapshot prices in paper trading. The simulated portfolio checks again at the next open and also limits buys to cash. Paper submission checks again against a recent snapshot; unavailable or stale reference prices and orders where no whole share fits are skipped. Account state and the model prompt now describe the dollar limit. The loop records its final sized quantity in submitted-order/reflection data and collector decisions.
- **Why It Was Necessary**: A share-count cap allowed very different dollar exposure for stocks with different prices. Rechecking at execution handles price changes between a decision and order placement.
- **Effect on Expected Behavior or Grading**: Both buy and sell quantities may be reduced; stocks above the limit per share cannot be traded as whole shares. This departs from the assignment's share-count limit. Market-order execution prices can move beyond the reference price, so the paper-trading dollar limit is an estimate and can be exceeded at fill; fees are excluded. Saved demonstration outputs were retained.
- **Validation**: Offline mocked tests cover validation and sizing at decision time, next-open sizing, stale/missing prices, buy and sell limits, and the final paper-order guard. No live account, order submission, model download, or paper-trading loop was run.

## 2026-11-06: Use the Model's Chat Template

- **Affected sections**: Model smoke test (cell 15), decision engine (cell 27), and trade reflections (cell 43).
- **What changed**: Replaced manually written role markers with `tok.apply_chat_template`, including the assistant generation prompt. Decision conversations now retain structured messages and render dispatched results as tool responses. Rendered prompts are tokenized without adding special tokens a second time; the saved SFT prompt is the same rendered conversation used for the decision. The smoke test decodes only newly generated tokens.
- **Why**: The configured Qwen tokenizer uses ChatML message delimiters, while the previous role strings were ordinary text, so conversation boundaries did not follow its template.
- **Effect and limitations**: Model decisions and reflections can change, and prior demonstrations are preserved. Previously collected SFT examples retain the old format; collect new examples before training. This change does not guarantee correct tool use or eliminate hallucinations, and the existing decision and parsing rules remain in place.
- **Validation**: Offline tests use the locally cached Qwen tokenizer and mocked model/tool calls to verify message boundaries, the tool response, reflection formatting, and the saved SFT prompt. No model inference, broker order, or trading loop was run.

## 2026-11-06: Require Research for Trades and Allow Holds

- **Affected section**: Decision engine, cell 27.
- **What changed**: Removed the instruction to trade on every decision and explicitly allowed all-hold decisions. Each buy or sell now requires a recognized usable result from an actually dispatched tool for the same symbol in the current conversation. News counts only for requested symbols explicitly associated with an article; empty news and error results do not count. The agent can retry when research is missing; at the turn limit, unresearched trades become holds, while separately researched trades remain eligible. Tool-call counts and return interfaces are preserved.
- **Why**: The prompt's research instruction was previously unenforced, while its mandatory-trade instruction encouraged activity even when evidence was weak or absent.
- **Effect and limitations**: The guard uses the existing tools' text formats and may conservatively reject an unfamiliar or truncated response. A matching tool result establishes that data was provided, not that the model interpreted it correctly or that a trade is profitable. Decision behavior, backtest results, and new training examples can change; saved outputs remain intact.
- **Validation**: Offline stub-model tests cover zero-call trades, retries, per-symbol research, empty and failed data, hold decisions, mixed-symbol decisions, and final-turn tool calls. The full 32-test suite passed. No real model inference, broker orders, or trading loop was run.

## 2026-11-06: Compact Decisions and Bounded Research Progress

- **Affected sections**: Decision engine (cell 27) and Task 4a runtime message (cell 48).
- **What changed**: The prompt requests only proposed trades, omits unchanged stocks, and provides one compact HOLD decision for no-trade sessions. Accepted decisions and fallbacks are compacted accordingly. The last generation explicitly requests a final decision using existing research. An identical tool name/argument request within the same episode is not dispatched again and advances the following generation to the final decision phase. Generation logs include elapsed seconds, input/output token counts, and whether the 700-token response limit was reached without EOS. Failed parsing/validation prints its reason and a short response tail. Incomplete arrays can no longer be salvaged as the last individual JSON object. Corrected the runtime notice to describe up to six generations per session.
- **Why**: All-universe HOLD lists exceeded the response budget and caused repeated retries; repeated research and unannounced last-turn tool rejection wasted generations. The new logs expose the cause of a failed response.
- **Effect and limitations**: Omitted symbols retain their positions, and research requirements, sizing, result keys, evaluation periods, and saved demonstration outputs are preserved. Repeated failed requests also end research early for that episode. The model can still ignore formatting instructions or hit its budget, in which case safe HOLD fallback applies. Real-model runtime improvements require a new run to measure.
- **Validation**: The 38-test offline suite passed, including compact holds, explicit final-turn instructions, duplicate successful/failed tools, truncated arrays, invalid JSON diagnostics, saved SFT prompts, and existing backtest/guard tests. Locally cached tokenizer tests and stub model outputs were used; no actual model inference, broker order, or trading loop was run.

## 2026-11-06: Require Research Before Holds and Expose Session Progress

- **Affected sections**: Decision engine (cell 27) and backtesting infrastructure (cell 31).
- **What changed**: The first-response instruction now requests research, and code requires at least one usable dispatched research result for a stock in the tradeable universe before accepting any final decision, including HOLD and `[]`. Early no-research decisions receive a corrective research prompt. A no-trade decision remains valid after usable research; an empty array then becomes one hold marked `researched_hold`. Exhausting the turn budget without usable research produces a safety HOLD marked `research_failed`; a formatting/decision failure after research is marked `decision_failed`. Per-symbol research for buys and sells remains enforced. Added flushed generation-start and session-start messages, total session duration in the summary, and progress/timing for backtest setup.
- **Why**: Empty decisions bypassed the buy/sell research guard and ended sessions without exercising research or collecting trade examples. Completed-generation timings also left long setup or in-flight work invisible.
- **Effect and limitations**: The agent can still choose not to trade after research; the correction does not force a daily trade. Generation time and total session time measure different scopes. Research failure remains a safe no-trade outcome, and recognizing a usable result does not validate the model's reasoning. Existing collector/evaluation interfaces, notebook outputs, and metadata are preserved.
- **Validation**: All 41 offline tests passed. Added coverage for empty and explicit hold decisions before/after research, failed and out-of-universe research, retry exhaustion with explicit failure reasons, and setup/session timing output. Notebook code syntax was checked. No model inference, network requests, broker orders, or trading loop were run.

## 2026-11-06: Trades-only Decisions, Clean Retries, and Measured Validation

- **Affected sections**: Tool prompt/validator (cell 23, `lgzw5cfv1i3f`); decision engine (27, `g9aer2y92q4x`); collector (29, `fdfbl3dhdbxu`); backtest reporting (31, `i53gzy9p691i`); SFT preparation (currently 53, `a2hyzbhq4ho8`); paper-loop collection (currently 57, `6jats7k4qsua`). IDs are the cells' `metadata.id` values; indices are zero-based and can shift when cells are inserted.
- **What changed**: The model contract now allows only buy/sell entries with real per-symbol research references, or a researched empty array. There is no mandatory daily trade or explicit HOLD output. Research remains model-generated: the engine prefills the beginning of a tool call, validates its name/arguments, and dispatches it with the trusted backtest clock. The first usable result advances to decisions. Per-call limits are 180 research tokens and 320 decision tokens, with at most two retries per phase and six generations overall. Failed outputs are never appended; each retry replaces one transient correction. This deliberately narrows the previous multi-tool exploration to one successful research call per episode.
- **Tool envelope finding**: The first real-model smoke test failed all six cases because Qwen ended complete tool JSON with EOS, omitting `</tool_call>`. The engine now restores only that closing tag after EOS and successful complete-JSON parsing; it never repairs truncated JSON or invents tool names/arguments. Normal validation still applies. The same reconstructed assistant turn is retained at inference and collection. The initial failure report remains available.
- **Context correctness and measurement**: Replaced oldest-first 3,000-character truncation with a 600-token, complete-record representation. Price outputs keep the newest rows, with a coverage/omission note first and the latest row last. News retains complete records and labels omissions; unsupported oversized outputs become unavailable. Logs measure instructions, account state, research context, assistant calls, phase/correction text, raw tool tokens, supplied tool tokens, generation time and cap hits.
- **Training and failure accounting**: Added diagnostics while retaining the four-value decision return interface. Failures return no orders with an explicit failed status; intentional researched `[]` is separate. Backtests retain every valuation date and position, and report failure/no-trade rates, cap hits, corrected decision counts and reference coverage. The collector excludes corrected final-decision attempts and reports current-run exclusions. SFT preparation requires the current trades-only contract and exact inference-template prompt, masks only the prompt, and reports rejection of legacy, inconsistent or overlength examples. This avoids silently truncating away the training target. Corrected research attempts do not disqualify a later clean decision because their corrections and failed responses are absent from its prompt.
- **Preserved behavior**: Existing next-open execution, sizing, labeling approach, evaluation periods and core backtest result keys remain. Source-only notebook edits preserve saved demonstration outputs, unrelated cells and metadata; the notebook was not executed as a whole. The paper-loop change only propagates metadata and the trades-only completion to collection; no orders or trading loop were run.
- **Validation**: Three-arm pre-change replay ran first on two reconstructed states and three seeds per arm (18 generations). One current-prompt sample hit 700 tokens with 35 HOLD entries; neither old arm hit the cap in this small sample. This does not establish that removing the daily-trade instruction caused the regression. After fixes, six real-model smoke episodes had zero failures/cap hits and a 3.12-second median session time; all six selected `[]`. All 43 offline tests passed, including template reconstruction, bounded retries, context retention, collector filtering, SFT masking, and preserving valuations across failed sessions. Details and raw artifacts are in `validation/agent_validation.md`.
- **Limits and assignment impact**: Research/tool choice remains exercised by the model, while output formatting and retry policy differ from the provided assignment. Corrected-decision filtering favors easier training cases. The six smoke samples used cached historical market tools, excluding news, and provide no evidence of profitable trades or adequate SFT data. No 60-session run, adapter training, live requests, or broker submissions were performed. The all-no-trade result needs attention before committing to a long data-collection run.


## 2026-11-06: Restored Mandatory Trade Rule with Compact Output, Real-Model 60-Session Collection, LoRA Fine-Tuning, and Evaluation

- **Affected Section**: Section 1.13 Decision Engine (cell 27, g9aer2y92q4x), Task 4a (cell 49), Task 4c (cell 55), and regression test suite (	ests/test_research_requirement.py).
- **What Changed**:
  - **Restored Mandatory Trade Rule**: The prompt requires at least one BUY or SELL per day, and empty [] is rejected as invalid. _parse_trade_decisions raises ValueError if an empty array or no buy/sell trades are proposed.
  - **Maintained Compact Trades-Only Format**: The model lists only its proposed trades and leaves all unchanged stocks unmentioned. Dropped the 'hold' action and the 'HOLD is NOT allowed' phrasing from the prompts to prevent confusing the model.
  - **Preserved Non-Behavioral Reliability Fixes**: Kept GPU placement for fast inference, clean transient retries that do not accumulate failed responses in the prompt (with bounded retry limits), chronological price results keeping the newest rows, research requirement enforced before decision validation, and failure counts tracked while keeping failed days in the equity curve.
  - **Pilot Validation**: Ran a 5-session real-model pilot with the full tool menu. The agent achieved an 80% trading rate (4/5 sessions) with 0 cap hits, executing sensible 1-share trades citing verified research (AAPL, NFLX, MSFT) and failing gracefully on one unresearched proposal.
  - **Full 60-Session Collection (Task 4a)**: Ran the 60-session backtest with the base model on GPU. The agent actively traded in 55/60 sessions (91.7%), achieved a 100% verified reference rate with 0 cap hits, experienced only 5 failures (8.3% failure rate), executed 48 trades, and collected 13 'good' and 16 'bad' labeled training episodes.
  - **LoRA Fine-Tuning and Evaluation (Task 4c)**: Fine-tuned LoRA adapters (r=8, alpha=16, target_modules=['q_proj', 'v_proj']) on the 13 good episodes over 3 epochs, saving the adapter to .cache/stock_agent/lora_adapter. In the 20-session comparison backtest, the fine-tuned model achieved -0.01% return (12 trades), outperforming the baseline base model (-0.42% return, 16 trades) by +0.40%.
  - **Notebook Demonstration Persistence**: Captured the real execution logs into cell 49 and cell 55 outputs in main.ipynb while preserving all other notebook cells, metadata, and prior demonstration outputs.
- **Why It Was Necessary**:
  - The previous allowance of [] resulted in a degenerative policy where the model predicted empty lists on every session (due to 99-100% next-token probability on the single [] token under ChatML and sampling), generating zero trades and zero SFT candidates.
  - Restoring the mandatory trade rule directly fixed the 'always holds' problem, while compact output avoided token-budget exhaustion from listing 100 unchanged stocks.
- **Effect on Expected Behavior or Grading**:
  - Tasks 4a and 4c are now fully executed and validated on the real model on local GPU with real demonstrated trades, training loss progression, and comparison metrics.
  - All 43 test suite checks pass cleanly.
- **Validation**:
  - 43/43 unit tests passed across all test suites.
  - Full execution of 5-session pilot, 60-session Task 4a backtest, 3-epoch LoRA training, and 20-session comparison backtest.


## 2026-11-06: Permitted Trading Unresearched Universe Stocks and Simplified Trade Schema

- **Affected Section**: Section 1.13 Decision Engine (cell 27, `g9aer2y92q4x`) and regression test suite (`tests/test_research_requirement.py`).
- **What Changed**:
  - Removed the restriction that blocked trading a stock if it was not the specific symbol researched by a tool in that session.
  - Updated `_parse_trade_decisions` to accept any valid `buy` or `sell` trade for any symbol in `WHITELIST` with positive integer `qty`. The field `research_ids` is now optional rather than mandatory.
  - Simplified the decision prompt and corrections to standard `[{"symbol":"AAPL","action":"buy","qty":1}]` schema without requiring per-symbol citation mappings.
  - Retained the core requirement that research must still be performed (at least one tool call executed) before a final decision is accepted.
- **Why It Was Necessary**:
  - The original notebook required research before deciding, but never restricted trades strictly to the researched ticker.
  - Requiring every trade to match the single researched symbol prevented the agent from adjusting other portfolio holdings or acting on general market context.
- **Effect on Expected Behavior or Grading**:
  - Restores the original assignment flexibility allowing portfolio adjustments across the permitted universe while maintaining tool usage.
  - Reduced rejection rates and decision latency: 5-session test achieved 0/5 failures (100% success rate, 0 cap hits, 20.2s total run time).
- **Validation**:
  - All 43 unit tests passed across the test suite.
  - 5-session real-model backtest executed cleanly with 0 failures and 4 completed trades.
