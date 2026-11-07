"""Offline checks for notebook paper-account guards and reflection persistence."""

import ast
import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict
from unittest.mock import patch


NOTEBOOK = Path(__file__).resolve().parents[1] / "main.ipynb"


def load_definitions():
    notebook = json.loads(NOTEBOOK.read_text(encoding="utf-8"))
    namespace = {"os": os, "json": json, "TradingClient": object, "Dict": Dict, "Any": Any}
    for index, names in (
        (9, {"parse_paper_setting"}),
        (17, {"verify_paper_account"}),
        (56, {"ReflectionPersistenceError", "PendingReflectionStore"}),
    ):
        source = next("".join(c["source"]) for c in notebook["cells"] if c["cell_type"] == "code" and all(("def " + name + "(") in "".join(c["source"]) or ("class " + name) in "".join(c["source"]) for name in names))
        tree = ast.parse(source, filename=f"main.ipynb cell {index}")
        definitions = [node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name in names]
        if {node.name for node in definitions} != names:
            raise RuntimeError(f"Missing definitions in cell {index}")
        exec(compile(ast.Module(body=definitions, type_ignores=[]), str(NOTEBOOK), "exec"), namespace)
    namespace.update(ALPACA_PAPER=True, PAPER_TRADING_URL="https://paper-api.alpaca.markets")
    return notebook, namespace


class PaperGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.notebook, cls.ns = load_definitions()

    def test_parse_setting_is_explicit(self):
        parse = self.ns["parse_paper_setting"]
        for value in (None, "true", "1", " YES ", "on"):
            self.assertIs(parse(value), True)
        for value in ("false", "0", "no", "off"):
            self.assertIs(parse(value), False)
        for value in ("", "maybe", "truth"):
            with self.assertRaises(ValueError):
                parse(value)

    def test_only_authenticated_paper_endpoint_passes(self):
        verify = self.ns["verify_paper_account"]
        paper = SimpleNamespace(_base_url="https://paper-api.alpaca.markets", get_account=lambda: SimpleNamespace(id="paper-account"))
        self.assertEqual(verify(paper), "paper-account")
        for url in ("https://api.alpaca.markets", "https://paper-api.alpaca.markets.example.com", None):
            client = SimpleNamespace(_base_url=url, get_account=lambda: self.fail("unexpected account request"))
            with self.assertRaises(RuntimeError):
                verify(client)
        with self.assertRaises(RuntimeError):
            verify(SimpleNamespace(_base_url=paper._base_url, get_account=lambda: SimpleNamespace(id=None)))
        with patch.dict(self.ns, {"ALPACA_PAPER": False}):
            with self.assertRaises(RuntimeError):
                verify(paper)

    def test_changed_cells_parse(self):
        for index in (9, 17, next(i for i, c in enumerate(self.notebook["cells"]) if "class PendingReflectionStore" in "".join(c["source"]))):
            ast.parse("".join(self.notebook["cells"][index]["source"]), filename=f"cell {index}")


class PendingReflectionStoreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _, cls.ns = load_definitions()
        cls.store_type = cls.ns["PendingReflectionStore"]
        cls.error_type = cls.ns["ReflectionPersistenceError"]

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = self.store_type(self.temp.name, "paper-account")
        self.item = {"order_id": "order-1", "due_at": 123456.0, "retry_count": 0,
                     "symbol": "AAPL", "side": "buy", "situation": "example",
                     "decision": {"symbol": "AAPL", "action": "buy"}}

    def test_restart_preserves_deadline_retries_and_removal(self):
        self.store.enqueue(self.item)
        restored = self.store_type(self.temp.name, "paper-account")
        self.assertEqual(restored.items, [self.item])
        restored.defer(restored.items[0])
        restored = self.store_type(self.temp.name, "paper-account")
        self.assertEqual(restored.items[0]["due_at"], 123456.0)
        self.assertEqual(restored.items[0]["retry_count"], 1)
        restored.remove("order-1")
        self.assertEqual(self.store_type(self.temp.name, "paper-account").items, [])

    def test_accounts_are_isolated_and_duplicates_rejected(self):
        self.store.enqueue(self.item)
        with self.assertRaises(self.error_type):
            self.store.enqueue(self.item)
        self.assertEqual(self.store_type(self.temp.name, "other-account").items, [])

    def test_failed_save_retains_previous_queue(self):
        self.store.enqueue(self.item)
        with patch("os.replace", side_effect=OSError("write failure")):
            with self.assertRaises(self.error_type):
                self.store.remove("order-1")
        self.assertEqual(self.store.items, [self.item])
        self.assertEqual(self.store_type(self.temp.name, "paper-account").items, [self.item])

    def test_corrupt_queue_is_not_overwritten(self):
        Path(self.store.path).write_text("not json", encoding="utf-8")
        with self.assertRaises(self.error_type):
            self.store_type(self.temp.name, "paper-account")
        self.assertEqual(Path(self.store.path).read_text(encoding="utf-8"), "not json")

    def test_incomplete_queue_item_is_not_overwritten(self):
        raw = json.dumps({"version": 1, "account_id": "paper-account",
                          "items": [{"order_id": "order-1", "due_at": 42}]})
        Path(self.store.path).write_text(raw, encoding="utf-8")
        with self.assertRaises(self.error_type):
            self.store_type(self.temp.name, "paper-account")
        self.assertEqual(Path(self.store.path).read_text(encoding="utf-8"), raw)


if __name__ == "__main__":
    unittest.main()
