"""Isolated point-in-time checks; no broker, model, or network calls."""
import ast
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import time
import unittest
from types import SimpleNamespace

import pandas as pd

NOTEBOOK = Path(__file__).resolve().parents[1] / "main.ipynb"


def namespace_for(tempdir):
    notebook = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    ns = {"pd": pd, "datetime": datetime, "time": time, "os": os, "json": json,
          "hashlib": hashlib, "re": re, "CACHE_DIR": tempdir, "NEWS_LIMIT": 5,
          "WHITELIST": ["AAPL", "MSFT"], "MAX_TRADE_VALUE": 5000.0,
          "ALPACA_API_KEY": "fake", "ALPACA_SECRET_KEY": "fake"}
    tree = ast.parse("".join(notebook["cells"][17]["source"]))
    cap = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "cap_trade_quantity")
    exec(compile(ast.Module(body=[cap], type_ignores=[]), str(NOTEBOOK), "exec"), ns)
    for index in (19, 31):
        source = "".join(notebook["cells"][index]["source"])
        tree = ast.parse(source, filename=f"cell {index}")
        definitions = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef))]
        exec(compile(ast.Module(body=definitions, type_ignores=[]), str(NOTEBOOK), "exec"), ns)
    tree = ast.parse("".join(notebook["cells"][23]["source"]))
    dispatch = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "dispatch_tool")
    exec(compile(ast.Module(body=[dispatch], type_ignores=[]), str(NOTEBOOK), "exec"), ns)
    return ns


def row(open_, close, volume=1000):
    return {"open": open_, "high": max(open_, close), "low": min(open_, close),
            "close": close, "volume": volume}


class PointInTimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.ns = namespace_for(self.temp.name)

    def test_calendar_holidays_early_closes_and_dst(self):
        sessions = self.ns["_backtest_sessions"](3, end_date="2024-12-02", now="2024-12-03T00:00:00Z")
        self.assertEqual([s.strftime("%Y-%m-%d") for s, _ in sessions], ["2024-11-27", "2024-11-29", "2024-12-02"])
        self.assertEqual(sessions[1][1].isoformat(), "2024-11-29T18:00:00+00:00")
        cal = self.ns["_backtest_calendar"]()
        self.assertEqual(cal.session_close("2024-03-08").hour, 21)
        self.assertEqual(cal.session_close("2024-03-11").hour, 20)
        self.assertEqual(self.ns["_completed_session_for"]("2024-12-02T15:00:00Z"), "2024-11-29")

    def test_historical_tools_never_see_future_bars_or_use_live_tool(self):
        rows = {"2024-11-27": row(98, 100), "2024-11-29": row(100, 105),
                "2024-12-02": row(9999, 9999)}
        data = {"bars": {"AAPL": rows}}
        ns = self.ns
        called = []
        ns["_tool_registry"] = {name: {"func": lambda **kw: called.append(kw)} for name in
                                ("get_price_history", "get_rsi", "get_macd", "get_global_quote")}
        quote = ns["dispatch_tool"]("get_global_quote", {"symbol": "AAPL", "date": "2099-01-01"},
                                    date="2024-11-29T18:05:00Z", historical_data=data)
        self.assertIn("$105.00", quote)
        self.assertNotIn("9999", quote)
        history = ns["dispatch_tool"]("get_price_history", {"symbol": "AAPL"},
                                      date="2024-11-29T18:05:00Z", historical_data=data)
        self.assertNotIn("2024-12-02", history)
        self.assertIn("unavailable", ns["dispatch_tool"]("get_global_quote", {"symbol": "MSFT"},
                                                       date="2024-11-29T18:05:00Z", historical_data=data).lower())
        self.assertEqual(called, [])
        self.assertIn("unavailable", ns["dispatch_tool"]("get_global_quote", {"symbol": "AAPL"},
                                                       date="2024-11-29T18:05:00Z").lower())

    def test_news_cutoff_and_cache_key(self):
        ns = self.ns
        seen = []
        articles = [{"created_at": "2024-11-29T17:59:00Z", "headline": "before", "symbols": ["AAPL"]},
                    {"created_at": "2024-11-29T18:06:00Z", "headline": "after", "symbols": ["AAPL"]}]
        def get(url, params, headers, timeout):
            seen.append(dict(params))
            return SimpleNamespace(status_code=200, json=lambda: {"news": articles})
        ns["requests"] = SimpleNamespace(get=get)
        ns["LIVE_NEWS_EXPIRY_SECONDS"] = 900
        early = "2024-11-29T18:05:00Z"
        late = "2024-11-29T18:10:00Z"
        a = ns["_get_news_cache_path"](["AAPL"], date="2024-11-29", is_live=False, as_of=early)
        b = ns["_get_news_cache_path"](["AAPL"], date="2024-11-29", is_live=False, as_of=late)
        self.assertNotEqual(a, b)
        text = ns["get_news_for_symbols"](["AAPL"], as_of=early)
        self.assertIn("before", text)
        self.assertNotIn("after", text)
        self.assertEqual(pd.Timestamp(seen[0]["end"]), pd.Timestamp(early))
        self.assertEqual(pd.Timestamp(seen[0]["start"]), pd.Timestamp("2024-11-29T05:00:00Z"))
        self.assertEqual(ns["get_news_for_symbols"](["AAPL"], as_of=early), text)
        self.assertEqual(len(seen), 1)

    def test_indicators_ignore_future_bars(self):
        ns = self.ns
        ns["_completed_session_for"] = lambda cutoff: "2024-11-29"
        dates = pd.bdate_range("2024-04-01", "2024-11-29")
        rows = {date.strftime("%Y-%m-%d"): row(100 + i / 3, 100 + i / 3 + (i % 7))
                for i, date in enumerate(dates)}
        before = {"bars": {"AAPL": dict(rows)}}
        rows["2024-12-02"] = row(999999, 999999)
        after = {"bars": {"AAPL": rows}}
        for name in ("get_rsi", "get_macd"):
            first = ns["historical_market_tool"](name, {"symbol": "AAPL"}, "2024-11-29T18:05:00Z", before)
            second = ns["historical_market_tool"](name, {"symbol": "AAPL"}, "2024-11-29T18:05:00Z", after)
            self.assertNotIn("unavailable", first.lower())
            self.assertEqual(first, second)

    def test_live_dispatch_keeps_using_registered_tool(self):
        ns = self.ns
        ns["_tool_registry"] = {"get_news": {"func": lambda symbols, date=None: (symbols, date)}}
        self.assertEqual(ns["dispatch_tool"]("get_news", {"symbols": ["AAPL"]}), (["AAPL"], None))

    def test_quote_does_not_use_an_older_day_as_previous_close(self):
        ns = self.ns
        data = {"bars": {"AAPL": {"2024-11-26": row(95, 100), "2024-11-29": row(100, 105)}}}
        quote = ns["historical_market_tool"]("get_global_quote", {"symbol": "AAPL"},
                                              "2024-11-29T18:05:00Z", data)
        self.assertIn("change: unavailable", quote)

    def test_all_python_cells_have_valid_syntax(self):
        notebook = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
        for index, cell in enumerate(notebook["cells"]):
            if cell["cell_type"] == "code" and index != 3:
                ast.parse("".join(cell["source"]), filename=f"cell {index}")

    def test_bar_cache_respects_date_range_and_adjustment(self):
        ns = self.ns
        calls = []
        columns = pd.MultiIndex.from_tuples([(name, "AAPL") for name in ("Open", "High", "Low", "Close", "Volume")])
        frame = pd.DataFrame([[10, 12, 9, 11, 100]], index=pd.to_datetime(["2024-11-29"]), columns=columns)
        ns["yf"] = SimpleNamespace(download=lambda symbols, **kwargs: calls.append(kwargs) or frame)
        fetch = ns["fetch_historical_prices"]
        first = fetch(["AAPL"], start="2024-11-01", end="2024-12-01")
        self.assertEqual(first["bars"]["AAPL"]["2024-11-29"]["open"], 10)
        fetch(["AAPL"], start="2024-11-01", end="2024-12-01")
        fetch(["AAPL"], start="2024-11-01", end="2024-12-02")
        self.assertEqual(len(calls), 2)
        self.assertTrue(all(call["auto_adjust"] is True for call in calls))

    def test_next_open_reduced_buy_missing_trade_and_estimated_valuation(self):
        ns = self.ns
        days = ["2024-11-27", "2024-11-29", "2024-12-02"]
        times = ["2024-11-27T21:00:00Z", "2024-11-29T18:00:00Z", "2024-12-02T21:00:00Z"]
        ns["_backtest_sessions"] = lambda n, end_date=None: [(pd.Timestamp(d), pd.Timestamp(t)) for d, t in zip(days, times)]
        ns["fetch_historical_prices"] = lambda **kw: {"bars": {"AAPL": {
            days[0]: row(100, 100), days[1]: row(120, 125), days[2]: {"open": 130, "close": None}}}}
        calls = []
        decisions = [[{"action": "buy", "symbol": "AAPL", "qty": 2}],
                     [{"action": "buy", "symbol": "MSFT", "qty": 1}],
                     [{"action": "buy", "symbol": "AAPL", "qty": 1}]]
        def decide(tok, model, state, universe, date, historical_data):
            calls.append((date, state))
            return decisions[len(calls)-1], "prompt", "completion", 1
        ns["llm_agent_decide"] = decide
        class Collector:
            def __init__(self): self.logged, self.outcomes = [], []
            def log(self, *args): self.logged.append(args); return len(self.logged)-1
            def update_outcome(self, idx, equity): self.outcomes.append((idx, equity))
        collector = Collector()
        result = ns["run_backtest"](None, None, collector=collector, n_days=3, initial_cash=150, verbose=False)
        self.assertEqual(result["trades"][0]["date"], days[1])
        self.assertEqual((result["trades"][0]["qty"], result["trades"][0]["requested_qty"]), (1, 2))
        self.assertEqual(result["final_equity"], 155)
        self.assertTrue(result["equity_history"][-1]["estimated"])
        self.assertEqual(result["equity_history"][-1]["estimated_symbols"], ["AAPL"])
        self.assertEqual(result["skipped_orders"][0]["reason"], "missing opening price")
        self.assertEqual(result["unfilled_decisions"], decisions[-1])
        self.assertEqual(collector.outcomes, [(0, 155)])
        self.assertEqual(pd.Timestamp(calls[1][0]), pd.Timestamp("2024-11-29T18:05:00Z"))

    def test_sell_cannot_exceed_holdings_and_zero_affordable_buy_is_skipped(self):
        portfolio = self.ns["SimulatedPortfolio"](100)
        self.assertIsNone(portfolio.execute({"action": "buy", "symbol": "AAPL", "qty": 1}, {"AAPL": 101}))
        portfolio.execute({"action": "buy", "symbol": "AAPL", "qty": 1}, {"AAPL": 100})
        self.assertIsNone(portfolio.execute({"action": "sell", "symbol": "AAPL", "qty": 2}, {"AAPL": 100}))
        self.assertEqual(portfolio.positions["AAPL"]["qty"], 1)

    def test_missing_close_uses_prior_close_or_initial_fill(self):
        portfolio = self.ns["SimulatedPortfolio"](150)
        portfolio.get_state({"AAPL": 100})  # A known close before the position exists.
        portfolio.execute({"action": "buy", "symbol": "AAPL", "qty": 1}, {"AAPL": 120})
        state = portfolio.get_state({})
        self.assertEqual(state["equity"], 130)
        self.assertEqual(state["estimated_symbols"], ["AAPL"])
        no_history = self.ns["SimulatedPortfolio"](150)
        no_history.execute({"action": "buy", "symbol": "AAPL", "qty": 1}, {"AAPL": 120})
        self.assertEqual(no_history.get_state({})["equity"], 150)

    def test_next_open_applies_trade_value_limit_to_buys_and_sells(self):
        portfolio = self.ns["SimulatedPortfolio"](20000)
        buy = portfolio.execute({"action": "buy", "symbol": "AAPL", "qty": 10}, {"AAPL": 1200})
        self.assertEqual((buy["qty"], buy["requested_qty"]), (4, 10))
        sell = portfolio.execute({"action": "sell", "symbol": "AAPL", "qty": 4}, {"AAPL": 2000})
        self.assertEqual((sell["qty"], sell["requested_qty"]), (2, 4))
        self.assertEqual(portfolio.positions["AAPL"]["qty"], 2)


if __name__ == "__main__":
    unittest.main()
