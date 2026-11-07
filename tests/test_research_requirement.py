"""Offline research-contract regressions with the actual cached chat tokenizer."""
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import sys
import unittest
import torch
from transformers import AutoTokenizer
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from notebook_validation import load_namespace
NB = json.loads((Path(__file__).resolve().parents[1] / 'main.ipynb').read_text(encoding='utf-8'))
TOK = AutoTokenizer.from_pretrained('Qwen/Qwen2.5-1.5B-Instruct', local_files_only=True)
PREFIX = '<tool_call>\n{"name": "'
RSI = 'RSI(14) for AAPL: 43.6 (neutral) [2026-08-14]'

def tool(name='get_rsi', args=None):
    return PREFIX + name + '", "arguments": ' + json.dumps(args or {'symbol': 'AAPL'}) + '}\n</tool_call>'

def decision(items=None):
    return json.dumps(items if items is not None else [{'symbol': 'AAPL', 'action': 'buy', 'qty': 1, 'research_ids': ['R1']}])

def setup(outputs, results=None):
    ns = load_namespace('unused-test-cache')
    ns['WHITELIST'] = ['AAPL', 'MSFT']
    ns['_decision_reference_prices'] = lambda *a: {'AAPL': 100, 'MSFT': 100}
    ns['dispatch_tool'] = lambda name, args, **kw: (results or {'get_rsi': RSI}).get(name, '')
    class Model:
        device = 'cpu'
        def __init__(self):
            self.outputs = iter(outputs)
            self.prompts, self.kwargs = [], []
        def generate(self, **kwargs):
            prompt = TOK.decode(kwargs['input_ids'][0], skip_special_tokens=False)
            self.prompts.append(prompt)
            self.kwargs.append(kwargs)
            text = next(self.outputs)
            eos = True
            if isinstance(text, tuple): text, eos = text
            if prompt.endswith(PREFIX) and text.startswith(PREFIX): text = text[len(PREFIX):]
            ids = TOK.encode(text, add_special_tokens=False) + ([TOK.eos_token_id] if eos else [])
            return torch.cat((kwargs['input_ids'], torch.tensor([ids])), dim=1)
    return ns, TOK, Model()

def run_case(outputs, results=None, **kwargs):
    ns, tok, model = setup(outputs, results)
    with redirect_stdout(io.StringIO()):
        result = ns['llm_agent_decide'](tok, model, {'cash': 1000}, debug_tokens=True, **kwargs)
    return result, ns, tok, model

class ResearchTests(unittest.TestCase):
    def test_unresearched_empty_is_failure_not_no_trade(self):
        result, _, _, model = run_case(['[]'] * 3)
        self.assertEqual(result[0], [])
        self.assertEqual(result.diagnostics['status'], 'failed')
        self.assertEqual(result.diagnostics['failure_reason'], 'research_failed')
        self.assertEqual(result[3], 0)
        self.assertEqual(len(model.prompts), 3)

    def test_researched_empty_is_rejected_and_valid_trade_succeeds(self):
        # [] is invalid under the rule requiring at least one BUY or SELL
        result, _, _, model = run_case([tool(), '[]', '[]', '[]'])
        self.assertEqual(result.diagnostics['status'], 'failed')
        self.assertEqual(result.diagnostics['failure_reason'], 'decision_failed')
        # Valid trade succeeds
        result_valid, _, _, model_valid = run_case([tool(), decision()])
        self.assertEqual(result_valid.diagnostics['status'], 'traded')
        self.assertEqual(json.loads(result_valid[2]), json.loads(decision()))
        self.assertEqual(result_valid[3], 1)
        self.assertEqual(model_valid.kwargs[0]['max_new_tokens'], 180)
        self.assertEqual(model_valid.kwargs[1]['max_new_tokens'], 320)
        self.assertEqual(model_valid.kwargs[0]['stop_strings'], ['</tool_call>'])

    def test_unresearched_stock_trade_allowed_and_out_of_universe_rejected(self):
        # Unresearched stock in universe is allowed
        trade = decision([{'symbol': 'MSFT', 'action': 'buy', 'qty': 1}])
        result, _, _, _ = run_case([tool(args={'symbol': 'AAPL'}), trade])
        self.assertEqual(result.diagnostics['status'], 'traded')
        self.assertEqual(result[0][0]['symbol'], 'MSFT')

        # Out-of-universe ticker is rejected
        bad = decision([{'symbol': 'UNKNOWN_TICKER', 'action': 'buy', 'qty': 1}])
        result_bad, _, _, _ = run_case([tool(), bad, bad, bad])
        self.assertEqual(result_bad.diagnostics['status'], 'failed')
        self.assertEqual(result_bad.diagnostics['failure_reason'], 'decision_failed')

    def test_hold_action_and_trailing_arrays_are_invalid(self):
        for bad in [decision([{'symbol': 'AAPL', 'action': 'hold', 'qty': 0, 'research_ids': ['R1']}]), '[],' + decision()]:
            result, _, _, _ = run_case([tool(), bad, decision()])
            self.assertEqual(result.diagnostics['status'], 'traded')
            self.assertTrue(result.diagnostics['corrected_decision'])

    def test_failed_unrelated_and_missing_tool_data_do_not_count(self):
        ns, _, _ = setup([])
        f = ns['_researched_symbols']
        for result in ('', 'Unknown tool', 'Historical RSI unavailable for AAPL.', 'RSI(14) for AAPL: nan (neutral)', 'RSI(14) for MSFT: 40.0 (neutral)'):
            self.assertEqual(f('get_rsi', {'symbol': 'AAPL'}, result), set())
        self.assertEqual(f('get_news', {'symbols': ['AAPL']}, '=== News: AAPL ===\n(0 articles)'), set())
        self.assertEqual(f('get_news', {'symbols': ['AAPL', 'MSFT']}, '=== News: AAPL,MSFT ===\n[1] Headline\n    Tickers: AAPL'), {'AAPL'})

    def test_model_cannot_override_trusted_time(self):
        bad = tool(args={'symbol': 'AAPL', 'date': '2099-01-01'})
        result, _, _, _ = run_case([bad] * 3, date='2024-11-29T18:05:00Z')
        self.assertEqual(result[3], 0)
        self.assertEqual(result.diagnostics['status'], 'failed')

    def test_only_complete_eos_terminated_json_gets_envelope_repair(self):
        call = tool().removesuffix('\n</tool_call>')
        result, _, _, model = run_case([call, decision()])
        self.assertTrue(result.diagnostics['calls'][0]['envelope_closed'])
        self.assertIn('</tool_call>', model.prompts[1])
        for bad in [call[:-1], call + '{}']:
            result, _, _, _ = run_case([bad] * 3)
            self.assertEqual(result[3], 0)
        result, _, _, _ = run_case([(call, False)] * 3)
        self.assertEqual(result[3], 0)

    def test_turn_budget_reserves_decision(self):
        result, _, _, _ = run_case([tool(), decision()], max_turns=2)
        self.assertEqual(result.diagnostics['status'], 'traded')
        ns, tok, model = setup([])
        with self.assertRaises(ValueError): ns['llm_agent_decide'](tok, model, {}, max_turns=1)

    def test_selling_unheld_stock_is_rejected_and_held_sell_succeeds(self):
        # 1. Unheld sell is rejected, triggers correction, and corrects to valid buy
        ns, tok, model = setup([tool(), decision([{'symbol': 'MSFT', 'action': 'sell', 'qty': 1}]), decision([{'symbol': 'MSFT', 'action': 'buy', 'qty': 1}])])
        with redirect_stdout(io.StringIO()):
            res = ns['llm_agent_decide'](tok, model, {'cash': 1000, 'positions': [{'symbol': 'AAPL', 'qty': 2}]})
        self.assertEqual(res.diagnostics['status'], 'traded')
        self.assertTrue(res.diagnostics['corrected_decision'])
        self.assertEqual(res[0][0]['action'], 'buy')
        self.assertIn('Cannot SELL MSFT: you hold 0 shares', model.prompts[-1])

        # 2. Held sell within quantity succeeds directly
        ns2, tok2, model2 = setup([tool(), decision([{'symbol': 'AAPL', 'action': 'sell', 'qty': 2}])])
        with redirect_stdout(io.StringIO()):
            res2 = ns['llm_agent_decide'](tok2, model2, {'cash': 1000, 'positions': [{'symbol': 'AAPL', 'qty': 2}]})
        self.assertEqual(res2.diagnostics['status'], 'traded')
        self.assertFalse(res2.diagnostics['corrected_decision'])
        self.assertEqual(res2[0][0]['action'], 'sell')
        self.assertEqual(res2[0][0]['qty'], 2)

        # 3. Excess sell quantity is rejected
        ns3, tok3, model3 = setup([tool(), decision([{'symbol': 'AAPL', 'action': 'sell', 'qty': 5}]), decision([{'symbol': 'AAPL', 'action': 'sell', 'qty': 2}])])
        with redirect_stdout(io.StringIO()):
            res3 = ns['llm_agent_decide'](tok3, model3, {'cash': 1000, 'positions': [{'symbol': 'AAPL', 'qty': 2}]})
        self.assertEqual(res3.diagnostics['status'], 'traded')
        self.assertTrue(res3.diagnostics['corrected_decision'])
        self.assertEqual(res3[0][0]['qty'], 2)
        self.assertIn('Cannot SELL 5 shares of AAPL: you only hold 2 shares', model3.prompts[-1])

if __name__ == '__main__': unittest.main()
