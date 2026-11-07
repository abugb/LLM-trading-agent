"""Load only notebook definitions for offline validation; never execute demo cells."""
import ast
import datetime
import json
import os
from pathlib import Path
import re
import time
from datasets import Dataset
import pandas as pd
from peft import LoraConfig, get_peft_model, TaskType
import torch
import yfinance as yf

ROOT = Path(__file__).resolve().parents[1]


def load_namespace(cache_dir):
    notebook = json.loads((ROOT / 'main.ipynb').read_text(encoding='utf-8'))
    fixture = json.loads((ROOT / 'validation' / 'prompt_replay_fixture.json').read_text(encoding='utf-8'))
    ns = dict(json=json, torch=torch, pd=pd, datetime=datetime, time=time, os=os,
              re=re, _re=re, yf=yf, Dataset=Dataset, LoraConfig=LoraConfig,
              get_peft_model=get_peft_model, TaskType=TaskType,
              _tool_registry={}, WHITELIST=fixture['states'][0]['state']['allowed_symbols'],
              MAX_TRADE_VALUE=5000.0, CACHE_DIR=str(cache_dir), NEWS_LIMIT=5)
    for needle, only in [('def canonicalize_symbols', None),
                         ('def cap_trade_quantity', {'cap_trade_quantity'}),
                         ('def extract_json_array', None), ('def register_tool', None),
                         ('def llm_agent_decide', None), ('class TradingDataCollector', None),
                         ('def run_backtest', None), ('def prepare_sft_dataset', None)]:
        source = next(''.join(c['source']) for c in notebook['cells']
                      if c['cell_type'] == 'code' and needle in ''.join(c['source']))
        nodes = [n for n in ast.parse(source).body if isinstance(n, (ast.FunctionDef, ast.ClassDef))
                 and (only is None or n.name in only)]
        exec(compile(ast.Module(body=nodes, type_ignores=[]), str(ROOT / 'main.ipynb'), 'exec'), ns)
    source = next(''.join(c['source']) for c in notebook['cells']
                  if c['cell_type'] == 'code' and 'def get_price_history(' in ''.join(c['source']))
    for node in ast.parse(source).body:
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name) and node.value.func.id == 'register_tool':
            kw = {k.arg: (lambda **kwargs: None) if k.arg == 'func' else ast.literal_eval(k.value)
                  for k in node.value.keywords}
            ns['register_tool'](**kw)
    return ns
