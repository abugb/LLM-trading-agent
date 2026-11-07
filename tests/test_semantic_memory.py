"""Offline semantic-memory checks with deterministic embeddings and FAISS stub."""
import ast
import json
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch
import numpy as np

NB = Path(__file__).resolve().parents[1] / 'main.ipynb'

def load_class():
    nb = json.loads(NB.read_text(encoding='utf-8'))
    src = next(''.join(c['source']) for c in nb['cells'] if 'class TradingMemory:' in ''.join(c['source']))
    cls = next(x for x in ast.parse(src).body if isinstance(x, ast.ClassDef) and x.name == 'TradingMemory')
    import time
    ns = {'os': os, 'json': json, 'time': time, 'CACHE_DIR': '.', 'MEMORY_MIN_SIMILARITY': 0.35}
    exec(compile(ast.Module(body=[cls], type_ignores=[]), str(NB), 'exec'), ns)
    return ns['TradingMemory']

class Embedder:
    loads = 0
    def __init__(self, name, device):
        assert name == 'sentence-transformers/all-MiniLM-L6-v2' and device == 'cpu'
        Embedder.loads += 1
    def encode(self, texts, **kwargs):
        def vector(text):
            text = text.lower()
            if 'zero-vector' in text: return [0., 0., 0.]
            if any(x in text for x in ('apple', 'aapl', 'quarterly profits')): return [1., 0., 0.]
            if any(x in text for x in ('tesla', 'tsla', 'ev maker')): return [0., 1., 0.]
            return [0., 0., 1.]
        return np.array([vector(x) for x in texts], dtype=np.float32)

class Index:
    def __init__(self, dims): self.dims, self.rows = dims, None
    def add(self, rows): self.rows = rows.copy()
    def search(self, query, k):
        scores = query @ self.rows.T
        ids = np.argsort(-scores, axis=1, kind='stable')[:, :k]
        return np.take_along_axis(scores, ids, axis=1), ids

class SemanticMemoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = str(Path(self.tmp.name) / 'memories.json')
        self.cls = load_class()
        Embedder.loads = 0
        mods = {'faiss': types.SimpleNamespace(IndexFlatIP=Index),
                'sentence_transformers': types.SimpleNamespace(SentenceTransformer=Embedder)}
        self.patcher = patch.dict(sys.modules, mods)
        self.patcher.start()
        self.addCleanup(self.patcher.stop)

    def test_empty_query_and_empty_memory_do_not_load_model(self):
        memory = self.cls(self.path)
        self.assertEqual(memory.get_memories('AAPL'), [])
        self.assertEqual(memory.get_memories(''), [])
        self.assertEqual(Embedder.loads, 0)

    def test_top_k_paraphrase_and_weak_match_filter(self):
        memory = self.cls(self.path)
        memory.add_memory('AAPL strong earnings', 'Apple lesson')
        memory.add_memory('TSLA shares weak', 'Tesla lesson')
        self.assertEqual(memory.get_memories('Apple quarterly profits rose', 2), ['Apple lesson'])
        self.assertEqual(memory.get_memories('EV maker shares declined', 2), ['Tesla lesson'])
        self.assertEqual(memory.get_memories('unrelated subject', 2), [])
        self.assertEqual(memory.get_memories('  ', 2), [])
        self.assertEqual(memory.get_memories('apple', 0), [])

    def test_load_restart_metadata_and_external_edits(self):
        memory = self.cls(self.path)
        context = {'order_id': 'order-1', 'account_id': 'paper', 'filled_qty': 2}
        memory.add_memory('AAPL strong earnings', 'old', trade_context=context)
        self.assertEqual(self.cls(self.path).memories[0]['trade_context'], context)
        entries = json.loads(Path(self.path).read_text(encoding='utf-8'))
        entries[0]['reflection'] = 'edited'
        entries.append({'situation': 'TSLA weak', 'reflection': 'added externally', 'timestamp': 1})
        Path(self.path).write_text(json.dumps(entries), encoding='utf-8')
        self.assertEqual(memory.get_memories('apple earnings'), ['edited'])
        self.assertEqual(memory.get_memories('EV maker'), ['added externally'])
        memory.add_memory('TSLA earnings', 'new')
        self.assertEqual(len(json.loads(Path(self.path).read_text(encoding='utf-8'))), 3)
        self.assertEqual(memory.memories[0]['trade_context'], context)

    def test_nonempty_file_with_unavailable_backend_is_not_overwritten(self):
        original = json.dumps([{'situation': 'AAPL', 'reflection': 'saved', 'timestamp': 1}])
        Path(self.path).write_text(original, encoding='utf-8')
        with patch.dict(sys.modules, {'faiss': None}):
            with self.assertRaisesRegex(RuntimeError, 'Semantic memory unavailable'):
                self.cls(self.path)
        self.assertEqual(Path(self.path).read_text(encoding='utf-8'), original)

    def test_corrupt_external_file_is_never_overwritten(self):
        memory = self.cls(self.path)
        memory.add_memory('AAPL', 'lesson')
        Path(self.path).write_text('broken', encoding='utf-8')
        with self.assertRaisesRegex(RuntimeError, 'existing data was not changed'):
            memory.get_memories('AAPL')
        with self.assertRaises(RuntimeError): memory.add_memory('TSLA', 'lesson')
        self.assertEqual(Path(self.path).read_text(encoding='utf-8'), 'broken')

    def test_missing_backend_preserves_saved_reflection(self):
        memory = self.cls(self.path)
        with patch.dict(sys.modules, {'faiss': None}):
            memory.add_memory('AAPL', 'saved despite missing dependency')
            self.assertEqual(len(json.loads(Path(self.path).read_text(encoding='utf-8'))), 1)
            with self.assertRaisesRegex(RuntimeError, 'Semantic memory unavailable'):
                memory.get_memories('apple')

    def test_atomic_write_failure_does_not_lose_old_data(self):
        memory = self.cls(self.path)
        memory.add_memory('AAPL', 'old')
        with patch('os.replace', side_effect=OSError('unavailable')):
            with self.assertRaises(OSError): memory.add_memory('TSLA', 'new')
        self.assertEqual(len(memory.memories), 1)
        self.assertEqual(json.loads(Path(self.path).read_text(encoding='utf-8'))[0]['reflection'], 'old')

    def test_threshold_override(self):
        memory = self.cls(self.path, min_similarity=-0.1)
        memory.add_memory('AAPL', 'lesson')
        self.assertEqual(memory.get_memories('unrelated'), ['lesson'])
        with self.assertRaises(ValueError): self.cls(self.path, min_similarity=2)

if __name__ == '__main__': unittest.main()
