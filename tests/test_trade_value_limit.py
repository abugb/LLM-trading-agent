"""Offline checks for the per-trade dollar limit; no broker orders are sent."""
import ast
import datetime
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict
import unittest

NOTEBOOK = Path(__file__).resolve().parents[1] / "main.ipynb"


def load_definitions():
    notebook = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    ns = {"MAX_TRADE_VALUE": 10000.0, "MAX_REFERENCE_AGE_SECONDS": 300,
          "WHITELIST": ["AAPL", "MSFT"], "datetime": datetime,
          "TradingClient": object, "Dict": Dict, "Any": Any,
          "ALPACA_API_KEY": "fake", "ALPACA_SECRET_KEY": "fake"}
    for index, names in ((17, {"cap_trade_quantity", "get_trade_reference_price", "submit_order"}),
                         (23, {"_validate_decisions"}), (27, {"_decision_reference_prices"})):
        tree = ast.parse("".join(notebook["cells"][index]["source"]))
        selected = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in names]
        if {n.name for n in selected} != names:
            raise RuntimeError(f"Missing definitions in cell {index}")
        exec(compile(ast.Module(body=selected, type_ignores=[]), str(NOTEBOOK), "exec"), ns)
    return ns


class TradeValueTests(unittest.TestCase):
    def setUp(self):
        self.ns = load_definitions()

    def test_caps_whole_shares_at_10000_for_buy_and_sell(self):
        validate = self.ns["_validate_decisions"]
        decisions = [{"symbol": "AAPL", "action": side, "qty": 9} for side in ("buy", "sell")]
        result = validate(decisions, {"AAPL": 1800})
        self.assertEqual([d["qty"] for d in result], [5, 5])
        self.assertTrue(all(d["qty"] * 1800 <= 10000 for d in result))
        self.assertEqual(validate([{"symbol": "AAPL", "action": "buy", "qty": 5}], {"AAPL": 1000})[0]["qty"], 5)

    def test_invalid_or_missing_prices_and_quantities_fail_closed(self):
        validate = self.ns["_validate_decisions"]
        for price in (None, 0, -1, float("nan"), float("inf"), 10001):
            result = validate([{"symbol": "AAPL", "action": "buy", "qty": 1}], {"AAPL": price})
            self.assertEqual(result[0]["action"], "hold")
        for qty in (0, -1, True, 1.5, "1"):
            result = validate([{"symbol": "AAPL", "action": "buy", "qty": qty}], {"AAPL": 100})
            self.assertEqual(result[0]["action"], "hold")

    def test_backtest_sizing_uses_cutoff_close_and_never_live_price(self):
        ns = self.ns
        ns["_completed_session_for"] = lambda date: "2024-11-29"
        ns["get_trade_reference_price"] = lambda symbol: self.fail("live price requested during backtest")
        data = {"bars": {"AAPL": {"2024-11-29": {"close": 2000}, "2024-12-02": {"close": 1}}}}
        items = [{"symbol": "AAPL", "action": "buy", "qty": 9}]
        refs = ns["_decision_reference_prices"](items, "2024-11-29T18:05:00Z", data)
        self.assertEqual(ns["_validate_decisions"](items, refs)[0]["qty"], 5)
        self.assertEqual(ns["_decision_reference_prices"](items, "2024-11-29T18:05:00Z", None), {"AAPL": None})

    def test_live_reference_rejects_stale_data_and_uses_highest_fresh_price(self):
        ns = self.ns
        now = datetime.datetime.now(datetime.timezone.utc)
        snapshot = {"latestTrade": {"p": 100, "t": (now - datetime.timedelta(minutes=6)).isoformat()},
                    "latestQuote": {"ap": 110, "bp": 105, "t": now.isoformat()}}
        ns["requests"] = SimpleNamespace(get=lambda *a, **kw: SimpleNamespace(status_code=200, json=lambda: snapshot))
        self.assertEqual(ns["get_trade_reference_price"]("AAPL"), 110)
        snapshot["latestQuote"]["t"] = (now - datetime.timedelta(minutes=6)).isoformat()
        self.assertIsNone(ns["get_trade_reference_price"]("AAPL"))

    def test_submission_rechecks_value_and_uses_final_quantity(self):
        ns = self.ns
        ns["verify_paper_account"] = lambda client: "paper"
        ns["get_trade_reference_price"] = lambda symbol: 2100
        ns["OrderSide"] = SimpleNamespace(BUY="buy", SELL="sell")
        ns["TimeInForce"] = SimpleNamespace(DAY="day")
        ns["MarketOrderRequest"] = lambda **kwargs: SimpleNamespace(**kwargs)
        sent = []
        fake = SimpleNamespace(submit_order=lambda order_data: sent.append(order_data) or
                               SimpleNamespace(id="fake-id", status="accepted", filled_qty="0", filled_avg_price=None))
        decision = {"symbol": "AAPL", "action": "buy", "qty": 5, "order_type": "market"}
        result = ns["submit_order"](fake, decision, expected_account_id="paper")
        self.assertEqual(sent[0].qty, 4)
        self.assertEqual(result["qty"], 4)
        self.assertEqual(decision["qty"], 4)
        ns["get_trade_reference_price"] = lambda symbol: None
        with self.assertRaises(ValueError):
            ns["submit_order"](fake, {"symbol": "AAPL", "action": "buy", "qty": 1, "order_type": "market"})
        self.assertEqual(len(sent), 1)


if __name__ == "__main__":
    unittest.main()
