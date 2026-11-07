"""Bounded retries, context compaction and clean training examples."""
from contextlib import redirect_stdout
import io
import json
import tempfile
import unittest
from test_research_requirement import run_case, setup, tool, decision

class DecisionProgressTests(unittest.TestCase):
    def test_retries_do_not_accumulate_responses_or_corrections(self):
        bad = 'MALFORMED_UNIQUE_TEXT ' * 40
        result, _, _, model = run_case([tool(), bad, bad, decision()])
        calls = result.diagnostics['calls']
        self.assertEqual(calls[2]['input_tokens'], calls[3]['input_tokens'])
        self.assertNotIn('MALFORMED_UNIQUE_TEXT', model.prompts[-1])
        self.assertEqual(model.prompts[-1].count('Correction:'), 1)
        self.assertFalse(result.diagnostics['sft_eligible'])
        self.assertEqual(result.diagnostics['status'], 'traded')

    def test_research_correction_disappears_before_decision(self):
        result, ns, tok, model = run_case(['[]', tool(), decision()])
        self.assertNotIn('Correction:', model.prompts[-1])
        self.assertTrue(result.diagnostics['sft_eligible'])
        entry = {'prompt': result[1], 'completion': result[2], 'agent_metadata': result.diagnostics}
        self.assertEqual(ns['validate_sft_example'](tok, entry), model.prompts[-1])
        self.assertEqual(len(result), 4)

    def test_cap_hit_is_not_salvaged(self):
        result, _, _, _ = run_case([(' invalid' * 180, False)] * 3)
        self.assertTrue(all(c['cap_hit'] for c in result.diagnostics['calls']))
        self.assertEqual(result[3], 0)
        self.assertEqual(result.diagnostics['status'], 'failed')

    def test_recent_complete_price_rows_and_omission_note(self):
        ns, tok, _ = setup([])
        text = 'Price history for AAPL (1mo):\n' + '\n'.join(f'  2026-08-{d:02}: O=100.00 H=110.00 L=90.00 C=105.00 V=1234567' for d in range(1, 29))
        compact = ns['_format_research_context'](tok, 'get_price_history', text, budget=250)
        self.assertTrue(compact.startswith('[Context]'))
        self.assertIn('older rows omitted', compact)
        self.assertTrue(compact.endswith('2026-08-28: O=100.00 H=110.00 L=90.00 C=105.00 V=1234567'))
        self.assertLessEqual(len(tok.encode(compact, add_special_tokens=False)), 250)
        self.assertEqual(compact.splitlines()[2:], sorted(compact.splitlines()[2:]))
        self.assertEqual(ns['_researched_symbols']('get_price_history', {'symbol': 'AAPL'}, compact), {'AAPL'})

    def test_news_keeps_whole_records_and_unknown_json_not_sliced(self):
        ns, tok, _ = setup([])
        text = '=== News: AAPL ===\n' + '\n'.join(f'[{i}] Headline {i}\n    Tickers: AAPL\n    Summary: ' + 'news ' * 20 for i in range(12))
        compact = ns['_format_research_context'](tok, 'get_news', text, budget=160)
        self.assertTrue(compact.startswith('[Context]'))
        self.assertLessEqual(len(tok.encode(compact, add_special_tokens=False)), 160)
        self.assertIn('Tickers: AAPL', compact)
        self.assertIn('unavailable', ns['_format_research_context'](tok, 'other', json.dumps(list(range(500))), budget=10))

    def test_collector_excludes_corrected_decision_and_persists_clean_contract(self):
        clean, ns, tok, _ = run_case([tool(), decision()])
        corrected, _, _, _ = run_case([tool(), 'bad', decision()])
        with tempfile.TemporaryDirectory() as path, redirect_stdout(io.StringIO()):
            ns['CACHE_DIR'] = path
            collector = ns['TradingDataCollector']()
            for result in (clean, corrected):
                collector.log(result[1], result[2], result[0], 1000, result[3], metadata=result.diagnostics)
            self.assertEqual(collector.collection_stats['corrected_decision'], 1)
            self.assertEqual(collector.collection_stats['recorded'], 1)
            saved = collector.entries[0]
            roundtrip = json.loads(json.dumps(saved))
            ns['validate_sft_example'](tok, roundtrip)
            roundtrip['prompt'] += 'changed'
            with self.assertRaises(ValueError): ns['validate_sft_example'](tok, roundtrip)

    def test_sft_masks_only_prompt_and_drops_legacy_or_overlong(self):
        result, ns, tok, _ = run_case([tool(), decision()])
        entry = {'prompt': result[1], 'completion': result[2], 'agent_metadata': result.diagnostics}
        class Collector:
            def get_labeled(self, label): return [entry, {'prompt': 'legacy', 'completion': '[]'}, {**entry, 'prompt': entry['prompt'] + 'tampered'}]
        from datasets import Dataset
        ns['Dataset'] = Dataset
        log = io.StringIO()
        with redirect_stdout(log): dataset = ns['prepare_sft_dataset'](Collector(), tok)
        self.assertEqual(len(dataset), 1)
        self.assertIn('66.7%', log.getvalue())
        row = dataset[0]
        n = len(tok.encode(entry['prompt'], add_special_tokens=False))
        self.assertTrue(all(x == -100 for x in row['labels'][:n]))
        supervised = [x for x in row['labels'] if x != -100]
        self.assertEqual(tok.decode(supervised), entry['completion'] + tok.eos_token)
        with redirect_stdout(io.StringIO()), self.assertRaises(ValueError): ns['prepare_sft_dataset'](Collector(), tok, max_length=10)

if __name__ == '__main__': unittest.main()
