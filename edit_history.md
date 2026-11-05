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


 