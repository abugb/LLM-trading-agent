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
| Quote summary | Alpaca | Provides price, change, and volume. |
| Historical prices for backtests | yfinance | Supplies prices for replaying past trading days. |

The news tool does not supply a separate sentiment score; the model interprets the text itself. RSI and MACD are additional evidence for its decision, rather than fixed rules that automatically trigger orders.

Both technical indicators (RSI and MACD) are calculated locally from yfinance prices, and real-time quote retrieval (`get_global_quote`) is fetched via Alpaca's Market Data snapshot API. Alpha Vantage is no longer required for live trading or backtesting.

## What happens to a proposed trade

The decision validator checks basic requirements, such as whether the stock is on the allowed list and whether the share count is a positive integer within the per-trade limit. Invalid decisions may be discarded or changed to holds. Accepted buy and sell decisions are normalized to market orders.

There are two execution paths:

- **Backtesting:** a local simulated portfolio updates its cash and holdings using historical closing prices. It limits purchases to available cash and sales to shares already held.
- **Paper trading:** the intended trading loop sends orders to Alpaca and receives an order status. The Alpaca client takes its paper-account setting from configuration.

Validation checks the structure and basic constraints of a decision. It does not establish that the trade is a good investment or provide a complete portfolio risk strategy.

## Why the project saves a cache

A cache is a saved copy of downloaded data. If the program needs the same information again, it can read a local file instead of making another API request. This speeds up repeated runs and reduces API usage.

The current cache lives in `.cache/stock_agent` beneath the notebook kernel's working directory. Older notebook comments refer to Google Drive, but the current setup uses local storage.

News is saved by date. Historical backtest prices are saved in a single file and reused for up to 24 hours. The individual price-history and indicator tools do not yet share a common price cache.

There are limitations: the news cache checks the date without checking which stocks were requested, and the historical-price cache checks its age without checking the requested stocks or time period. As a result, a changed request can receive an earlier request's data. Cached news also does not refresh during the day.

## How the agent can learn from experience

The project has two separate learning mechanisms.

### Memory: bringing old lessons into a new decision

After a trade has had time to develop, the intended workflow compares portfolio value before and after it. The model writes a short reflection about the outcome, which is saved with a description of the original situation.

For a later decision, a keyword-ranking method called BM25 finds similar past situations. Their reflections are included in the model's prompt. This approach is called retrieval-augmented generation, or RAG.

Memory changes the information the model sees; it does not retrain the model. The storage, search, and reflection functions exist, and the decision engine accepts retrieved reflections. Task 5 connects these pieces within the repeating trading loop by queueing trades, reflecting after a delay, and retrieving top reflections for new decisions.

### Fine-tuning: training on recorded examples

Backtests collect the model's conversations and decisions. The collector keeps episodes that used tools and proposed valid buy or sell actions, then associates them with later changes in portfolio value.

The default labeling rule marks an eligible episode “good” when its recorded profit is zero or positive, and “bad” when it is negative. The training code uses the good examples to teach the model to reproduce those final decisions. This is supervised fine-tuning, or SFT.

LoRA makes this training smaller by updating added adapter weights while keeping the base model's weights frozen. The adapter is saved and can be loaded for later use. Training happens in a separate notebook stage; it does not happen automatically after every trade.

These labels are a rough learning signal. A change in the whole portfolio's value does not isolate the effect of one trade.

## What the backtest tells you

The backtest steps through historical trading days, asks the agent for decisions, simulates fills at each day's closing prices, and tracks portfolio value. A comparison stage runs the model with its LoRA adapter disabled and enabled to compare returns and trade counts.

The current results need to be interpreted with these limitations in mind:

- Historical dates are passed to the news tool, but the price and indicator tools still fetch current data. That can expose the agent to information unavailable on the simulated day.
- Trades fill at daily closing prices without modeling transaction costs or differences between an expected price and an actual execution price.
- The comparison period overlaps the period used to collect training examples, so it is not an independent test on unseen data.

The backtest is useful for inspecting the agent's behavior and exercising the training pipeline. These limitations must be addressed before treating its returns as evidence of future performance.

## Where to find each part

| Notebook area | What it contains |
|---|---|
| Task 1 | Configuration, model loading, Alpaca access, news, tool dispatch, decision engine, data collection, and backtesting. |
| Task 2 | Price history, RSI, MACD, quote retrieval, and combined market context. |
| Task 3 | Persistent trading memory, keyword retrieval, and trade reflections. |
| Task 4 | Training-data preparation, LoRA fine-tuning, and model comparisons. |
| Task 5 | The unfinished loop intended to connect research, decisions, orders, and reflection. |

Downloaded data, training examples, model adapters, and logs can all live under `CACHE_DIR`. They serve different purposes: downloaded data avoids repeated requests, training examples support fine-tuning, memory stores lessons, and logs record what happened. Despite the folder's name, it contains more than disposable cached downloads.
