import json

with open('main.ipynb', 'r', encoding='utf-8') as f:
    nb = json.load(f)

cell = nb['cells'][27]
src = ''.join(cell['source'])

old_parse = '''def _parse_trade_decisions(response, universe, evidence):
    """Strict trades-only contract: at least one BUY or SELL required; [] is invalid."""
    text = response.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\\n".join(lines).strip()
    items = json.loads(text)
    if not isinstance(items, list):
        raise ValueError("Expected one JSON array")
    if not items:
        raise ValueError("At least one BUY or SELL trade is required; [] is invalid")
    for item in items:
        if not isinstance(item, dict) or set(item) != {"symbol", "action", "qty", "research_ids"}:
            raise ValueError("Each trade requires symbol, action, qty and research_ids")
        symbol, action, qty, refs = (item[k] for k in ("symbol", "action", "qty", "research_ids"))
        if not isinstance(symbol, str) or symbol not in universe or action not in ("buy", "sell"):
            raise ValueError("Only buy/sell trades in the permitted universe are accepted")
        if not isinstance(qty, int) or isinstance(qty, bool) or qty <= 0:
            raise ValueError("Quantity must be a positive whole number")
        if not isinstance(refs, list) or not refs or any(not isinstance(r, str) or r not in evidence or symbol not in evidence[r] for r in refs):
            raise ValueError("Research references must name actual results for this stock")
    return items'''

new_parse = '''def _parse_trade_decisions(response, universe, evidence=None):
    """Strict trades-only contract: at least one BUY or SELL required; [] is invalid."""
    text = response.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\\n".join(lines).strip()
    items = json.loads(text)
    if not isinstance(items, list):
        raise ValueError("Expected one JSON array")
    if not items:
        raise ValueError("At least one BUY or SELL trade is required; [] is invalid")
    for item in items:
        if not isinstance(item, dict):
            raise ValueError("Each trade must be an object")
        allowed_keys = {"symbol", "action", "qty", "research_ids"}
        if not {"symbol", "action", "qty"}.issubset(set(item)) or not set(item).issubset(allowed_keys):
            raise ValueError("Each trade requires symbol, action, and qty")
        symbol, action, qty = item["symbol"], item["action"], item["qty"]
        if not isinstance(symbol, str) or symbol not in universe or action not in ("buy", "sell"):
            raise ValueError("Only buy/sell trades in the permitted universe are accepted")
        if not isinstance(qty, int) or isinstance(qty, bool) or qty <= 0:
            raise ValueError("Quantity must be a positive whole number")
    return items'''

old_completion = '''def _trade_completion(decisions):
    return json.dumps([{k: d[k] for k in ("symbol", "action", "qty", "research_ids")}
                       for d in decisions], separators=(",", ":"))'''

new_completion = '''def _trade_completion(decisions):
    keys = ("symbol", "action", "qty", "research_ids")
    return json.dumps([{k: d[k] for k in keys if k in d}
                       for d in decisions], separators=(",", ":"))'''

old_system = '''    system = ("You manage a stock portfolio using verified research. "
              "In the research phase output one tool call. In the decision phase output "
              "only a JSON array of buy/sell trades, requiring at least one BUY or SELL per day. "
              "Omit all unchanged stocks. An empty array [] is invalid; never output []. "
              "Each trade must cite a returned research ID for its symbol. "
              f"Whole shares only; estimated value per trade is at most ${MAX_TRADE_VALUE:,.2f}. "
              "Only allowed_symbols from the account state may be traded.\\n" + _build_tools_prompt())'''

new_system = '''    system = ("You manage a stock portfolio using market research. "
              "In the research phase output one tool call. In the decision phase output "
              "only a JSON array of buy/sell trades, requiring at least one BUY or SELL per day. "
              "Omit all unchanged stocks. An empty array [] is invalid; never output []. "
              f"Whole shares only; estimated value per trade is at most ${MAX_TRADE_VALUE:,.2f}. "
              "Only allowed_symbols from the account state may be traded.\\n" + _build_tools_prompt())'''

old_prompt = '''    decision_prompt = ('Decision phase: use the returned research. Output ONLY one JSON array with at least one BUY or SELL trade, e.g. '
                       '[{"symbol":"AAPL","action":"buy","qty":1,"research_ids":["R1"]}]. '
                       'Every trade must include symbol, action, qty, and research_ids. Omit all unchanged stocks. [] is invalid.')
    corrections = {
        "research": "Correction: output exactly ONE registered tool call with valid arguments. Select another tool or stock if data was unavailable. No decisions or invented results.",
        "decision": "Correction: output exactly one valid trades-only JSON array with at least one BUY or SELL. Use positive integer qty and real research_ids for each symbol. Omit unchanged stocks. [] is invalid.",
    }'''

new_prompt = '''    decision_prompt = ('Decision phase: use the returned research. Output ONLY one JSON array with at least one BUY or SELL trade, e.g. '
                       '[{"symbol":"AAPL","action":"buy","qty":1}]. '
                       'Every trade must include symbol, action, and qty. Omit all unchanged stocks. [] is invalid.')
    corrections = {
        "research": "Correction: output exactly ONE registered tool call with valid arguments. Select another tool or stock if data was unavailable. No decisions or invented results.",
        "decision": "Correction: output exactly one valid trades-only JSON array with at least one BUY or SELL. Every trade must include symbol, action, and qty (e.g. [{\\"symbol\\":\\"AAPL\\",\\"action\\":\\"buy\\",\\"qty\\":1}]). Omit unchanged stocks. [] is invalid.",
    }'''

old_finish_loop = '''            trades = _parse_trade_decisions(response, universe, evidence)
            call_log["parsed"] = True
            if not evidence:
                raise ValueError("Decision requires research")
            prices = _decision_reference_prices(trades, date, historical_data)
            normalized = _validate_decisions(trades, prices)
            if not normalized or len(normalized) != len(trades) or any(d.get("action") not in ("buy", "sell") for d in normalized):
                raise ValueError("Trade failed quantity/price validation")
            for d, source in zip(normalized, trades):
                d["research_ids"] = source["research_ids"]
            info["decision_messages"] = copy.deepcopy(current)
            info["corrected_decision"] = bool(correction)
            # Corrected decision completions are executed if valid, but excluded from SFT.
            return finish("traded", trades=normalized)'''

new_finish_loop = '''            trades = _parse_trade_decisions(response, universe, evidence)
            call_log["parsed"] = True
            if not evidence:
                raise ValueError("Decision requires research")
            prices = _decision_reference_prices(trades, date, historical_data)
            normalized = _validate_decisions(trades, prices)
            if not normalized or len(normalized) != len(trades) or any(d.get("action") not in ("buy", "sell") for d in normalized):
                raise ValueError("Trade failed quantity/price validation")
            for d, source in zip(normalized, trades):
                if "research_ids" in source:
                    d["research_ids"] = source["research_ids"]
                elif evidence:
                    matched = [ref for ref, syms in evidence.items() if d["symbol"] in syms]
                    if matched:
                        d["research_ids"] = matched
            info["decision_messages"] = copy.deepcopy(current)
            info["corrected_decision"] = bool(correction)
            # Corrected decision completions are executed if valid, but excluded from SFT.
            return finish("traded", trades=normalized)'''

old_finish_fn = '''    def finish(status, reason=None, trades=None):
        trades = trades or []
        info.update(status=status, failure_reason=reason, no_trade=(status == "no_trade"),
                    trade_decisions=len(trades), verified_reference_decisions=len(trades),
                    sft_eligible=(status == "traded" and not info["corrected_decision"]))
        if status == "failed":
            print(f"  [Decision failed] {reason}; no orders, existing positions retained", flush=True)
        else:
            print(f"  [Decision] {status}; {len(trades)} trade(s)", flush=True)
        return AgentDecisionResult(trades, prompt, _trade_completion(trades), tool_calls, copy.deepcopy(info))'''

new_finish_fn = '''    def finish(status, reason=None, trades=None):
        trades = trades or []
        verified = sum(1 for d in trades if any(d.get("symbol") in evidence.get(r, []) for r in d.get("research_ids", [])))
        info.update(status=status, failure_reason=reason, no_trade=False,
                    trade_decisions=len(trades), verified_reference_decisions=verified,
                    sft_eligible=(status == "traded" and not info["corrected_decision"]))
        if status == "failed":
            print(f"  [Decision failed] {reason}; no orders, existing positions retained", flush=True)
        else:
            print(f"  [Decision] {status}; {len(trades)} trade(s)", flush=True)
        return AgentDecisionResult(trades, prompt, _trade_completion(trades), tool_calls, copy.deepcopy(info))'''

assert old_parse in src, 'old_parse not found'
assert old_completion in src, 'old_completion not found'
assert old_system in src, 'old_system not found'
assert old_prompt in src, 'old_prompt not found'
assert old_finish_loop in src, 'old_finish_loop not found'
assert old_finish_fn in src, 'old_finish_fn not found'

src = src.replace(old_parse, new_parse)
src = src.replace(old_completion, new_completion)
src = src.replace(old_system, new_system)
src = src.replace(old_prompt, new_prompt)
src = src.replace(old_finish_loop, new_finish_loop)
src = src.replace(old_finish_fn, new_finish_fn)

cell['source'] = [line + '\n' for line in src.splitlines()]
if cell['source']:
    cell['source'][-1] = cell['source'][-1].rstrip('\n')

with open('main.ipynb', 'w', encoding='utf-8') as f:
    json.dump(nb, f, indent=1)

print('Updated cell 27 successfully to allow unresearched stock trading')
