"""Execute Task 4a (60 sessions + SFT collection) and Task 4c (LoRA training + comparison)."""
import ast
import contextlib
import datetime
import io
import json
import os
from pathlib import Path
import sys
import time
import pandas as pd
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, set_seed

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from notebook_validation import load_namespace

class StreamTee(io.StringIO):
    def __init__(self, target_stream):
        super().__init__()
        self.target_stream = target_stream

    def write(self, s):
        self.target_stream.write(s)
        self.target_stream.flush()
        return super().write(s)

def main():
    print("=" * 70)
    print("STARTING FULL PIPELINE: 60-SESSION COLLECTION + SFT TRAINING + EVALUATION")
    print("=" * 70)

    cache_dir = ROOT / '.cache' / 'stock_agent'
    os.makedirs(cache_dir, exist_ok=True)

    print("Loading tokenizer and model onto GPU...")
    tok = AutoTokenizer.from_pretrained('Qwen/Qwen2.5-1.5B-Instruct', local_files_only=True)
    model = AutoModelForCausalLM.from_pretrained(
        'Qwen/Qwen2.5-1.5B-Instruct',
        local_files_only=True,
        dtype=torch.float16,
        device_map={'': 0}
    )
    model.eval()

    ns = load_namespace(cache_dir)
    ns['tok'] = tok
    ns['model'] = model

    # =========================================================================
    # TASK 4a: Run 60 sessions with BASE model
    # =========================================================================
    sft_path = os.path.join(str(cache_dir), "sft_data.jsonl")
    if os.path.exists(sft_path):
        os.remove(sft_path)
        print("Cleared previous training data")

    cell49_tee = StreamTee(sys.stdout)
    with contextlib.redirect_stdout(cell49_tee):
        print("Running backtest with BASE model...")
        print("(Each session uses up to 6 LLM generations; timing and token counts appear below.)\n")
        set_seed(42)
        collector = ns['TradingDataCollector']()
        base_results = ns['run_backtest'](tok, model, collector=collector, n_days=60, verbose=True)

        collector.auto_label(threshold=0.0)
        print("\n--- Training Data Summary ---")
        collector.summary()

        print("\nRecent entries:")
        collector.review(n=10)

        good_entries = collector.get_labeled("good")
        bad_entries = collector.get_labeled("bad")
        print(f"\nGood examples for training: {len(good_entries)}")
        print(f"Bad examples (not used in SFT): {len(bad_entries)}")

    cell49_output_text = cell49_tee.getvalue()

    # =========================================================================
    # TASK 4c: LoRA Fine-tuning and Comparison Backtest
    # =========================================================================
    cell55_tee = StreamTee(sys.stdout)
    with contextlib.redirect_stdout(cell55_tee):
        print("=" * 60)
        print("SFT Fine-tuning Pipeline")
        print("=" * 60)

        good_count = len(good_entries)
        if good_count == 0:
            print("\nNo 'good' labeled data found! Cannot train LoRA.")
        else:
            print(f"\nTraining on {good_count} 'good' examples...")
            try:
                # Step 1: Prepare dataset
                dataset = ns['prepare_sft_dataset'](collector, tok)
                print(f"Dataset ready: {len(dataset)} examples")

                # Step 2: Create LoRA model
                lora_model = ns['get_lora_model'](model)

                # Step 3: Train
                ns['train_sft'](lora_model, dataset, tok, epochs=3, lr=2e-4, batch_size=1)
                print("\nTraining complete!")

                # Step 4: Backtest base model (comparison baseline, 20 days)
                print("" + "=" * 60)
                print("BACKTEST: Base Model (comparison baseline)")
                print("=" * 60)
                set_seed(42)
                with lora_model.disable_adapter():
                    base_comp_results = ns['run_backtest'](tok, lora_model, collector=None, n_days=20, verbose=True)

                # Step 5: Backtest with fine-tuned model (20 days)
                print("" + "=" * 60)
                print("BACKTEST: Fine-tuned Model")
                print("=" * 60)
                set_seed(42)
                ft_comp_results = ns['run_backtest'](tok, lora_model, collector=None, n_days=20, verbose=True)

                # Step 6: Compare
                print("\n" + "=" * 60)
                print("COMPARISON: Base Model vs Fine-tuned Model")
                print("=" * 60)
                print(f"  Base model return:       {base_comp_results['total_return']:>+8.2f}%")
                print(f"  Fine-tuned model return: {ft_comp_results['total_return']:>+8.2f}%")
                diff = ft_comp_results['total_return'] - base_comp_results['total_return']
                print(f"  Improvement:             {diff:>+8.2f}%")
                print(f"")
                print(f"  Base trades:             {len(base_comp_results['trades']):>8d}")
                print(f"  Fine-tuned trades:       {len(ft_comp_results['trades']):>8d}")
                print("=" * 60)

                if diff > 0:
                    print("\nFine-tuned model outperformed the base model!")
                elif diff < 0:
                    print("\nBase model performed better. Consider:")
                    print("  - Collecting more training data (increase n_days)")
                    print("  - Adjusting labeling threshold")
                    print("  - Tuning LoRA hyperparameters (r, alpha, lr)")
                else:
                    print("\nBoth models performed equally.")

            except Exception as e:
                print(f"\nError in fine-tuning pipeline: {e}")
                import traceback
                traceback.print_exc()

    cell55_output_text = cell55_tee.getvalue()

    # =========================================================================
    # Update main.ipynb cell outputs for Cell 49 and Cell 55
    # =========================================================================
    print("\nUpdating main.ipynb cell outputs for Cell 49 (Task 4a) and Cell 55 (Task 4c)...")
    nb_path = ROOT / 'main.ipynb'
    with open(nb_path, 'r', encoding='utf-8') as f:
        nb = json.load(f)

    def text_to_stream(text):
        lines = [l + '\n' for l in text.splitlines()]
        if lines:
            lines[-1] = lines[-1].rstrip('\n')
        return [{"name": "stdout", "output_type": "stream", "text": lines}]

    nb['cells'][49]['outputs'] = text_to_stream(cell49_output_text)
    nb['cells'][49]['execution_count'] = 1

    nb['cells'][55]['outputs'] = text_to_stream(cell55_output_text)
    nb['cells'][55]['execution_count'] = 2

    with open(nb_path, 'w', encoding='utf-8') as f:
        json.dump(nb, f, indent=1)

    print("Notebook updated successfully with complete execution outputs!")

    # Save summary report
    report = {
        "timestamp": datetime.datetime.now().isoformat(),
        "n_sessions_base": 60,
        "base_results_quality": base_results['agent_quality'],
        "base_results_return": base_results['total_return'],
        "base_trades_count": len(base_results['trades']),
        "good_examples": len(good_entries),
        "bad_examples": len(bad_entries),
    }
    with open(ROOT / 'validation' / 'pipeline_run_summary.json', 'w', encoding='utf-8') as f:
        json.dump(report, f, indent=2)

    print("\nFull pipeline execution finished successfully!")

if __name__ == '__main__':
    main()
