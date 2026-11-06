# How the trading agent works

This project uses a language model to research stocks and propose trades. Python code gives the model access to market data, checks its decisions, and either simulates trades or sends orders to Alpaca. The project is intended for paper trading: practicing with a simulated brokerage account.

The implementation lives in [main.ipynb](main.ipynb). This overview describes the current code, including the parts that still need to be connected. Some notebook headings still say “TODO” even where implementations already exist.

## The overall workflow

Each trading round is designed to follow this sequence:

1. Read the portfolio's cash, holdings, and total value.
2. Give that information to the model, along with the stocks it may trade.
3. Let the model request news and market data through tools.
4. Ask the model for its final trading decisions.
5. Check the decisions and execute the accepted orders.
6. Record the decisions and later outcomes for review and learning.

The model chooses what to investigate and what trades to propose. Python handles data retrieval, calculations, validation, and order submission.

**Current status:** the decision engine, data tools, backtesting, memory functions, fine-tuning functions, and the repeating paper-trading loop in Task 5 (`run_trading_loop`) are implemented. The workflow connects account state monitoring, news and tool context, memory reflection and retrieval, model inference, order execution, and collector logging.

## How the model researches a decision

The configured model is Qwen2.5-1.5B-Instruct. It receives an account snapshot and a description of the tools it can call. It can also receive additional market context and lessons retrieved from past trades.

A tool is a Python function exposed to the model. For example, the model might request Apple's recent news. The program recognizes that request, calls the news function, and adds its result to the conversation. The model can then request another tool or produce its final decisions.

This research loop has a turn limit so it cannot continue indefinitely. The model's final response is structured data containing the stock, action, and number of shares. The program parses that response and checks it before passing it to an executor.

The current prompt strongly encourages activity: it tells the model to use a tool and make at least one buy or sell decision. These are prompt instructions, not guarantees. The validation code can still return a hold decision when an output is unusable.

## Where the information comes from

| Information | Current source | Purpose |
|---|---|---|
| Account balance and holdings | Alpaca | Shows what the portfolio owns and can spend. |
| Financial news | Alpaca | Provides headlines and summaries for the model to interpret. |
| Recent price history | yfinance | Shows daily opening, high, low, closing prices, and volume. |
| RSI | Calculated locally from yfinance prices | Describes the balance of recent upward and downward price movements. |
| MACD | Calculated locally from yfinance prices | Compares shorter and longer price trends. |
| Quote summary | Alpaca live; yfinance in backtests | Provides price, change, and volume. |
| Historical prices for backtests | yfinance | Supplies prices for replaying past trading days. |

The news tool does not supply a separate sentiment score; the model interprets the text itself. RSI and MACD are additional evidence for its decision, rather than fixed rules that automatically trigger orders.

Both technical indicators (RSI and MACD) are calculated locally from yfinance prices, and real-time quote retrieval (`get_global_quote`) is fetched via Alpaca's Market Data snapshot API. Alpha Vantage is no longer required for live trading or backtesting.

## What happens to a proposed trade

The decision validator checks basic requirements, such as whether the stock is on the allowed list and whether the share count is a positive integer. `MAX_TRADE_VALUE` sets a $5,000 estimated value limit for each buy or sell. Quantities are reduced to whole shares that fit the limit; decisions without a usable price or where one share exceeds the limit become holds. Accepted buy and sell decisions are normalized to market orders.

There are two execution paths:

- **Backtesting:** a local simulated portfolio checks the trade-value limit using the decision-time historical close and checks it again at the next open. It reduces purchases to available cash and limits sales to shares already held.
- **Paper trading:** `ALPACA_PAPER` is parsed as a boolean and defaults to paper mode when unset. The notebook refuses order submission unless the setting is true, the client points to Alpaca's paper endpoint, and that endpoint returns an authenticated account. The loop also checks that the account has not changed before each order.

Validation checks the structure and basic constraints of a decision. It does not establish that the trade is a good investment or provide a complete portfolio risk strategy.

For paper orders, the limit is checked again immediately before submission using a recent Alpaca snapshot; missing or stale prices prevent submission. This is an estimated value limit: market prices can move before an order fills, so the actual fill value can exceed it. Fees are not included in the estimate.

## Why the project saves a cache

A cache is a saved copy of downloaded data. If the program needs the same information again, it can read a local file instead of making another API request. This speeds up repeated runs and reduces API usage.

The current cache lives in `.cache/stock_agent` beneath the notebook kernel's working directory. Older notebook comments refer to Google Drive, but the current setup uses local storage.

News entries are keyed by canonical symbols, date, article limit, request mode, and the historical decision cutoff when supplied. Live queries and in-progress dates refresh after 15 minutes. Past historical entries remain cached indefinitely. News requests fetched across symbol batches must succeed in full before being saved; failed batches return available articles with warnings but skip cache writing.

Historical backtest bars are keyed by canonical symbols, requested range or period, adjustment setting, and a schema version. Entries are verified against stored parameters on cache hits and expire after 24 hours. The price-fetching logic handles empty or malformed yfinance responses and avoids saving empty data. Existing close-only cache files do not satisfy the new keys.

The live price-history and indicator tools do not yet share a common price cache. During a backtest, the tools instead read the same historical data through the decision-time cutoff.

## How the agent can learn from experience

The project has two separate learning mechanisms.

### Memory: bringing old lessons into a new decision

After a trade has had time to develop, the agent reflects on the specific outcome of that trade rather than broad portfolio equity changes:
- **Buy orders:** Evaluated at reflection time against a fresh market quote snapshot to compute mark-to-market unrealized P&L: `(reflection_quote - fill_price) * filled_qty`. The prompt explicitly instructs the model to treat this as an interim unrealized snapshot rather than finalized profit.
- **Sell orders:** Evaluated against the position's pre-trade cost basis (`avg_entry_price`) captured before order submission to compute realized P&L: `(fill_price - cost_basis) * filled_qty`.
- **Order tracking and fill policy:** In the trading loop (Task 5), pending trades are refreshed using `tc.get_order_by_id`. The loop follows a terminal-wait policy with bounded retries (`MAX_REFLECTION_RETRIES = 5`): open orders, including `partially_filled`, are deferred; only explicit terminal statuses are eligible for reflection. A terminal order with zero fills is discarded, while a nonterminal order still open after the retry limit is skipped without reflection.

The model writes a concise reflection on the trade's execution and lesson learned, stored with structured `trade_context` fields for symbol, side, executed fill details, and price source/time when available. Alpaca market-data timestamps are recorded when supplied; yfinance fallback entries record retrieval time. The original market situation is kept for retrieval.

Pending reflections are saved under `CACHE_DIR` in a file scoped to the verified paper account. Their deadlines use elapsed seconds (`REFLECTION_DELAY_LOOPS * LOOP_SECONDS`), so a later run can resume them after a kernel restart. Queue updates use atomic replacement, and an order already recorded in memory is not reflected twice after a restart. Only one loop should use a given account's queue at a time. An interruption between broker acceptance and saving the returned order ID can still leave an order without a pending reflection; check broker orders after an interrupted submission.

For a later decision, a keyword-ranking method called BM25 finds similar past situations. Their reflections are included in the model's prompt. This approach is called retrieval-augmented generation, or RAG.

Memory changes the information the model sees; it does not retrain the model. The storage, search, and reflection functions exist, and the decision engine accepts retrieved reflections. Task 5 connects these pieces within the repeating trading loop by queueing trades, tracking order fills, calculating trade-level P&L, and retrieving top reflections for new decisions. The loop also protects against unverified account state: if retrieving account state from Alpaca fails, the loop safely halts the iteration rather than fabricating an artificial balance.

### Fine-tuning: training on recorded examples

Backtests collect the model's conversations and decisions. The collector keeps episodes that used tools and proposed valid buy or sell actions, then associates them with later changes in portfolio value.

The default labeling rule marks an eligible episode “good” when its recorded profit is zero or positive, and “bad” when it is negative. The training code uses the good examples to teach the model to reproduce those final decisions. This is supervised fine-tuning, or SFT.

LoRA makes this training smaller by updating added adapter weights while keeping the base model's weights frozen. The adapter is saved and can be loaded for later use. Training happens in a separate notebook stage; it does not happen automatically after every trade.

These labels are a rough learning signal. A change in the whole portfolio's value does not isolate the effect of one trade.

## What the backtest tells you

The backtest uses the NYSE calendar to make decisions five minutes after each close and fills those decisions at the next trading day's open. News is limited to the decision timestamp, and the historical price, indicator, and quote tools see only completed daily bars. Buys are reduced to the affordable whole-share quantity; trades with missing opening prices are skipped. If a held stock has no closing price, the latest known price is carried forward and the valuation is flagged as estimated. Final-session decisions remain unfilled. A comparison stage runs the model with its LoRA adapter disabled and enabled to compare returns and trade counts.

The current results need to be interpreted with these limitations in mind:

- Fills use adjusted yfinance opening prices without modeling transaction costs or slippage. Adjusted prices are an approximation, not a full simulation of dividends and splits.
- The comparison period overlaps the period used to collect training examples, so it is not an independent test on unseen data.
- The model may have learned about the historical period during pretraining, and historical data may have been revised after the fact.

The backtest is useful for inspecting the agent's behavior and exercising the training pipeline. These limitations must be addressed before treating its returns as evidence of future performance.

## Where to find each part

| Notebook area | What it contains |
|---|---|
| Task 1 | Configuration, model loading, Alpaca access, news, tool dispatch, decision engine, data collection, and backtesting. |
| Task 2 | Price history, RSI, MACD, quote retrieval, and combined market context. |
| Task 3 | Persistent trading memory, keyword retrieval, and trade reflections. |
| Task 4 | Training-data preparation, LoRA fine-tuning, and model comparisons. |
| Task 5 | The trading loop connecting research, decisions, order submission, and reflection. |

Downloaded data, training examples, model adapters, and logs can all live under `CACHE_DIR`. They serve different purposes: downloaded data avoids repeated requests, training examples support fine-tuning, memory stores lessons, and logs record what happened. Despite the folder's name, it contains more than disposable cached downloads.
