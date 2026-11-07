"""Test real sessions with the rule requiring at least one BUY or SELL per day."""
import datetime
import json
import os
from pathlib import Path
import time
import pandas as pd
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, set_seed
from notebook_validation import ROOT, load_namespace

def main():
    print("Loading model and tokenizer...")
    tok = AutoTokenizer.from_pretrained('Qwen/Qwen2.5-1.5B-Instruct', local_files_only=True)
    model = AutoModelForCausalLM.from_pretrained(
        'Qwen/Qwen2.5-1.5B-Instruct',
        local_files_only=True,
        dtype=torch.float16,
        device_map={'': 0}
    )
    model.eval()

    cache_dir = ROOT / '.cache' / 'stock_agent'
    ns = load_namespace(cache_dir)

    # Register all Task 2 tools in ns if needed
    # Let's inspect tools registered in ns
    print("Registered tools:", list(ns['_tool_registry'].keys()))

    # Run 5 real backtest sessions
    set_seed(42)
    print("\nRunning 5 real backtest sessions with the updated rule...")
    start_time = time.time()
    results = ns['run_backtest'](tok, model, collector=None, n_days=5, verbose=True)
    elapsed = time.time() - start_time

    print(f"\n--- Completed 5 sessions in {elapsed:.1f}s ---")
    print("Quality metrics:", results['agent_quality'])
    print("Trades executed:", len(results['trades']))
    for t in results['trades']:
        print(f"  {t['date']}: {t['side'].upper()} {t['qty']} {t['symbol']} @ ${t['price']:.2f}")

    print("\nSession diagnostics:")
    for diag in results['session_diagnostics']:
        date = diag.get('date')
        status = diag.get('status')
        trades = diag.get('trade_decisions', 0)
        tools = [t['name'] + ' ' + str(t['symbols']) for t in diag.get('tools', [])]
        print(f"  {date}: status={status}, trades={trades}, tools={tools}")

if __name__ == '__main__':
    main()
