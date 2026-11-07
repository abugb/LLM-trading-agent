"""Offline seeded prompt replay. Uses cached weights and fixed fixtures; no tools/orders."""
import argparse
import json
from pathlib import Path
import re
import time

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, set_seed

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', default=str(ROOT / 'validation' / 'prompt_replay_results.json'))
    args = parser.parse_args()
    fixture = json.loads((ROOT / 'validation' / 'prompt_replay_fixture.json').read_text(encoding='utf-8'))
    if not torch.cuda.is_available() or torch.cuda.mem_get_info()[0] < 4 * 1024**3:
        raise RuntimeError('Replay needs at least 4 GiB free GPU memory; release notebook models first.')
    tok = AutoTokenizer.from_pretrained(fixture['model'], local_files_only=True)
    model = AutoModelForCausalLM.from_pretrained(fixture['model'], local_files_only=True,
                                               dtype=torch.float16, device_map={'': 0})
    model.eval()
    results = []
    for case in fixture['states']:
        for seed in fixture['seeds']:
            for arm, system in fixture['arms'].items():
                messages = [{'role': 'system', 'content': system},
                            {'role': 'user', 'content': 'Account State:\n' + json.dumps(case['state'], indent=2)}]
                if case['fixed_research']:
                    messages.extend([
                        {'role': 'assistant', 'content': '<tool_call>\n{"name":"get_global_quote","arguments":{"symbol":"GOOG"}}\n</tool_call>'},
                        {'role': 'tool', 'content': case['fixed_research']},
                    ])
                prompt = tok.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
                inputs = tok(prompt, add_special_tokens=False, return_tensors='pt').to(model.device)
                set_seed(seed)
                started = time.perf_counter()
                with torch.inference_mode():
                    output = model.generate(**inputs, max_new_tokens=fixture['max_new_tokens'],
                                            do_sample=True, temperature=fixture['temperature'], top_p=fixture['top_p'],
                                            eos_token_id=tok.eos_token_id, pad_token_id=tok.eos_token_id)
                ids = output[0, inputs.input_ids.shape[1]:].tolist()
                elapsed = time.perf_counter() - started
                response = tok.decode(ids, skip_special_tokens=True)
                row = {'date': case['date'], 'seed': seed, 'arm': arm, 'input_tokens': inputs.input_ids.shape[1],
                       'output_tokens': len(ids), 'wall_seconds': elapsed,
                       'cap_hit': len(ids) >= fixture['max_new_tokens'] and ids[-1] != tok.eos_token_id,
                       'hold_entries': len(re.findall(r'"action"\s*:\s*"hold"', response)),
                       'response': response, 'raw_response': tok.decode(ids, skip_special_tokens=False),
                       'token_ids': ids,
                       'components': {role: sum(len(tok.encode(m['content'], add_special_tokens=False))
                                               for m in messages if m['role'] == role)
                                      for role in ('system', 'user', 'assistant', 'tool')}}
                results.append(row)
                Path(args.output).write_text(json.dumps({'limitations': fixture['limitations'], 'samples': results}, indent=2), encoding='utf-8')
                print(f"{case['date']} seed={seed} {arm}: {len(ids)} tokens, cap={row['cap_hit']}, holds={row['hold_entries']}, {elapsed:.1f}s", flush=True)


if __name__ == '__main__':
    main()
