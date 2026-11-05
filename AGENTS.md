# Project guidance

This project is a notebook-based LLM trading-agent assignment. The main implementation is `main.ipynb`; `AGENT_OVERVIEW.md` provides a readable overview of its workflow and current limitations. Inspect the notebook's code before relying on its prose: some assignment instructions and TODO labels may be outdated.

The notebook combines Alpaca paper trading and news, yfinance historical prices and MACD, Alpha Vantage RSI and quotes, a tool-calling model, backtesting, memory, and optional fine-tuning. The repeating trading loop is not yet implemented. Treat backtest results cautiously: the current research tools can access data newer than the simulated date, and the simulation uses daily closing prices for fills.

## Working on the notebook

- Assignment instructions and grading requirements are not mandatory. Depart from them when appropriate for the user's goals, and record each departure in `edit_history.md` so it can be explained in the report. Preserve the notebook's structure and instructions where useful. An implemented function may still have an old TODO label.
- Make focused changes and preserve unrelated notebook cells, metadata, outputs, and the user's existing work. Avoid clearing outputs or rerunning the whole notebook as a side effect of an edit. Preserve the key demonstration outputs for the graded functions across Tasks 1–5 (e.g., test cells in 1.15, Test Task 2, Test Task 3, 4a/4c backtests and training loss, and Task 5 loop iterations).
- Check the affected code and run appropriate focused validation when practical. Full execution can require credentials, network access, a model download, and a GPU; report what could not be verified.
- Keep credentials in environment variables; never include secrets in notebook output, documentation, or history. Treat `.cache/stock_agent` as local working data: it may contain training examples, saved adapters, memory, and logs as well as replaceable downloads.
- Keep simulated backtesting distinct from Alpaca order submission. Do not submit orders or run a trading loop unless the user has explicitly requested it, and verify the account mode before doing so.
- Update `AGENT_OVERVIEW.md` when a change materially alters the behavior it describes.

## Notebook change history

Use `edit_history.md` to record notebook changes that depart from the original provided material or assignment expectations. This history is intended to support the user's eventual report.

- Read the existing history before making a relevant change. Append an entry in the same work session whenever making a non-original or unexpected notebook change, including a bug fix, replacement data source, altered behavior, or deviation from assignment instructions.
- Use a dated Markdown heading and briefly describe the affected notebook section and specific cell (by cell ID or index), what changed, why it was necessary, and any effect on expected behavior or grading. Record validation and unresolved limitations when relevant.
- Distinguish departures from routine completion of tasks the notebook explicitly asks for; routine task completion does not need an entry unless it also introduces an unexpected change. If uncertain, document the change.
- Preserve earlier entries and the existing `edit_history.txt`; do not invent prior changes or silently migrate its contents. Do not record credentials or other sensitive data.
- Documentation-only edits outside the notebook do not require a history entry. If `edit_history.md` does not exist when an entry is needed, create it.
