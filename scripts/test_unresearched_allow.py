"""Verify real-model backtest behavior when unresearched stocks are tradeable."""
import time
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, set_seed
from notebook_validation import ROOT, load_namespace

def main():
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

    set_seed(42)
    print("Running 5 real sessions with unresearched stocks permitted...")
    start = time.time()
    results = ns['run_backtest'](tok, model, collector=None, n_days=5, verbose=True)
    print(f"\n5 sessions completed in {time.time() - start:.1f}s")
    print("Trades:", len(results['trades']))
    for t in results['trades']:
        print(f"  {t['date']}: {t['side'].upper()} {t['qty']} {t['symbol']} @ ${t['price']:.2f}")

if __name__ == '__main__':
    main()
