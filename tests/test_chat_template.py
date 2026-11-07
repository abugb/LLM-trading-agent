"""Offline chat-template checks; no model download, broker, or trading loop."""
import ast
import json
from pathlib import Path
import unittest
from unittest.mock import patch

NOTEBOOK = Path(__file__).resolve().parents[1] / 'main.ipynb'

class ChatTemplateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            from transformers import AutoTokenizer
            cls.tok = AutoTokenizer.from_pretrained('Qwen/Qwen2.5-1.5B-Instruct', local_files_only=True)
            import torch
            cls.torch = torch
        except (ImportError, OSError) as exc:
            raise unittest.SkipTest(f'Locally cached Qwen tokenizer unavailable: {exc}')
        cls.nb = json.loads(NOTEBOOK.read_text(encoding='utf-8'))

    def test_decision_tool_turn_and_sft_prompt(self):
        from test_research_requirement import run_case, tool, decision
        result, ns, tok, model = run_case([tool(), decision()])
        decisions, prompt, completion, count = result
        self.assertEqual(decisions[0]['action'], 'buy')
        self.assertEqual(count, 1)
        self.assertIn('<|im_start|>system\n', model.prompts[0])
        self.assertIn('<|im_start|>assistant\n<tool_call>', model.prompts[1])
        self.assertIn('<tool_response>\nResearch ID: R1\nRSI', model.prompts[1])
        self.assertEqual(prompt, model.prompts[1])
        self.assertEqual(json.loads(completion)[0]['research_ids'], ['R1'])
        self.assertTrue(prompt.endswith('<|im_start|>assistant\n'))
        prompt_ids = tok(prompt, add_special_tokens=False)['input_ids']
        full_ids = tok(prompt + completion, add_special_tokens=False)['input_ids']
        self.assertEqual(full_ids[:len(prompt_ids)], prompt_ids)
        ns['validate_sft_example'](tok, {'prompt': prompt, 'completion': completion, 'agent_metadata': result.diagnostics})

    def test_reflection_uses_qwen_template(self):
        tree = ast.parse(''.join(self.nb['cells'][43]['source']))
        fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'reflect_on_trade')
        tok, torch = self.tok, self.torch
        seen = []
        class Model:
            device = 'cpu'
            def generate(self, **kwargs):
                seen.append(tok.decode(kwargs['input_ids'][0], skip_special_tokens=False))
                return torch.cat((kwargs['input_ids'], torch.tensor([tok.encode('AAPL buy gained.', add_special_tokens=False)])), dim=1)
        ns = {'json': json, 'torch': torch}
        exec(compile(ast.Module(body=[fn], type_ignores=[]), str(NOTEBOOK), 'exec'), ns)
        with patch.object(torch.cuda, 'is_available', return_value=False):
            result = ns['reflect_on_trade'](tok, Model(), 'test', {'symbol': 'AAPL', 'action': 'buy'}, prev_equity=100, curr_equity=101)
        self.assertEqual(result, 'AAPL buy gained.')
        self.assertIn('<|im_start|>system\n', seen[0])
        self.assertIn('<|im_end|>\n<|im_start|>user\n', seen[0])
        self.assertTrue(seen[0].endswith('<|im_start|>assistant\n'))

if __name__ == '__main__':
    unittest.main()
