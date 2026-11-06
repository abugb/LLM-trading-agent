# Cache key implementation plan

## Goal and scope

Key news cache entries by the requested symbols and date, and historical-price entries by symbols and period. This prevents a request from receiving cached data for a different set of stocks or a different historical period. Preserve the agent's current stock selection, decision-making, and order execution behavior.

The cache currently contains two date-only news files, which may be discarded without migration. Delete those files explicitly rather than clearing `.cache/stock_agent`: that directory can also contain trading memory, training examples, adapters, and logs.

## Implementation

1. **Canonicalize symbol lists.** Add a helper that strips whitespace, converts symbols to uppercase, removes duplicates, and sorts the result. For example, `["nvda", "AAPL", "aapl"]` becomes `["AAPL", "NVDA"]`. Use the canonical list for both cache keys and underlying requests so equivalent requests use consistent batching. Reject or clearly handle an empty list before fetching or caching.

2. **Key news by the full request.** Update `_get_news_cache_path` and `get_news_for_symbols` in notebook cell 19. Include the canonical symbols, requested date, article limit, and live/recent versus historical request mode in the key. The modes must differ because the current API parameters differ even when their dates match. Use a readable filename and a short stable hash of the full parameters to avoid excessively long filenames. Store the parameters and creation timestamp in the payload, and verify the parameters on a cache hit.

3. **Add a live-news freshness policy.** Reuse a matching live/recent news entry for a configurable period; start with 15 minutes, then refresh it. Historical-date entries can remain reusable without the short expiry, except when the requested date is still in progress, in which case use the live freshness policy. This changes the current all-day behavior and may increase API calls. A decision-time cutoff for historical news is separate backtest work: the present historical request covers the whole day.

4. **Avoid caching incomplete news responses as complete.** News requests are batched in groups of five symbols. Track whether every batch succeeded. If a batch fails, return any available results with a clear indication of the failure, but do not save the combined result as a complete cache entry. Do not cache a total failure.

5. **Key historical prices by symbols and period.** Update `fetch_historical_prices` in cell 31 to use canonical symbols and the requested period as the cache key. Record and check those parameters in the payload, preserve the current 24-hour expiry, and keep the existing return structure so backtest callers continue to work.

6. **Update affected notebook descriptions and the news test cell.** The existing test in cell 21 calls `_get_news_cache_path()` directly, so update it for the new signature. Update descriptions that say news is cached only by date. Preserve the notebook's structure, unrelated cells, metadata, and saved demonstration outputs; editing the cell should not itself clear or rerun its output.

7. **Remove only the obsolete news cache files.** Delete the two existing date-only news files. Do not delete the cache directory or other files that may appear there.

8. **Document the changes.** Append a dated entry to `edit_history.md` identifying cells 19, 21, and 31, the changed keys and freshness behavior, the rationale, validation, and remaining backtest limitations. Update `AGENT_OVERVIEW.md` to describe the new behavior and its limits.

9. **Validate with focused, isolated checks.** Use mocked news and yfinance responses and a temporary cache directory. Verify that:

   - Reordering symbols, changing their case, and adding duplicates produce the same key.
   - Different symbols, dates, limits, or live/historical modes produce different news entries.
   - Matching requests hit the cache and expired live requests refresh.
   - A failed news batch does not create a complete cache entry.
   - Historical-price requests with different symbols or periods do not share entries, and matching entries expire after 24 hours.
   - Existing callers still receive the expected string or dictionary formats.
   - Affected notebook code has valid syntax and unrelated cells, metadata, and saved outputs are preserved.

   These checks should not require credentials, network calls, a model download, a trading loop, or order submission. Report any validation that cannot be completed.

## Expected effects and limitations

The agent should receive cached data for the request it actually made, rather than potentially receiving another symbol's news or a different historical-price request. Live news can refresh during the day. More distinct requests will produce more cache entries and may increase API calls, particularly when focus-symbol combinations change. Correct inputs do not guarantee better trading decisions.

This change does not add a stock-ranking mechanism, improve reflection attribution, or make backtesting point-in-time correct. In particular, historical news needs a decision-time cutoff, and price and indicator tools currently can retrieve information newer than the simulated date. Those changes require separate work.
