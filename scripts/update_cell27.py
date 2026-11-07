import json

with open('main.ipynb', 'r', encoding='utf-8') as f:
    nb = json.load(f)

cell = nb['cells'][27]
src = ''.join(cell['source'])

old_parse = '''def _parse_trade_decisions(response, universe, evidence):
    """Strict trades-only contract: [] is a researched decision to keep positions."""
    items = json.loads(response)
    if not isinstance(items, list):
        raise ValueError("Expected one JSON array")
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

new_parse = '''def _parse_trade_decisions(response, universe, evidence):
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

old_system = '''    system = ("You manage a stock portfolio using verified research. "
              "In the research phase output one tool call. In the decision phase output "
              "only a JSON array of buy/sell trades. Omit all unchanged stocks. "
              "An empty array [] means no trades; never list unchanged stocks. "
              "Each trade must cite a returned research ID for its symbol. "
              f"Whole shares only; estimated value per trade is at most ${MAX_TRADE_VALUE:,.2f}. "
              "Only allowed_symbols from the account state may be traded.\\n" + _build_tools_prompt())'''

new_system = '''    system = ("You manage a stock portfolio using verified research. "
              "In the research phase output one tool call. In the decision phase output "
              "only a JSON array of buy/sell trades, requiring at least one BUY or SELL per day. "
              "Omit all unchanged stocks. An empty array [] is invalid; never output []. "
              "Each trade must cite a returned research ID for its symbol. "
              f"Whole shares only; estimated value per trade is at most ${MAX_TRADE_VALUE:,.2f}. "
              "Only allowed_symbols from the account state may be traded.\\n" + _build_tools_prompt())'''

old_prompt = '''    decision_prompt = ('Decision phase: use the returned research. Output ONLY one JSON array, e.g. '
                       '[{"symbol":"AAPL","action":"buy","qty":1,"research_ids":["R1"]}]. '
                       'Use actual evidence IDs and symbols. If no trade is justified, output []. '
                       'No tool calls or unchanged-stock entries.')
    corrections = {
        "research": "Correction: output exactly ONE registered tool call with valid arguments. Select another tool or stock if data was unavailable. No decisions or invented results.",
        "decision": "Correction: output exactly one valid trades-only JSON array. Use positive integer qty and real research_ids for each symbol. If no trade is justified, output [].",
    }'''

new_prompt = '''    decision_prompt = ('Decision phase: use the returned research. Output ONLY one JSON array with at least one BUY or SELL trade, e.g. '
                       '[{"symbol":"AAPL","action":"buy","qty":1,"research_ids":["R1"]}]. '
                       'Every trade must include symbol, action, qty, and research_ids. Omit all unchanged stocks. [] is invalid.')
    corrections = {
        "research": "Correction: output exactly ONE registered tool call with valid arguments. Select another tool or stock if data was unavailable. No decisions or invented results.",
        "decision": "Correction: output exactly one valid trades-only JSON array with at least one BUY or SELL. Use positive integer qty and real research_ids for each symbol. Omit unchanged stocks. [] is invalid.",
    }'''

old_finish = '''            trades = _parse_trade_decisions(response, universe, evidence)
            call_log["parsed"] = True
            if not evidence:
                raise ValueError("Decision requires research")
            prices = _decision_reference_prices(trades, date, historical_data)
            normalized = _validate_decisions(trades, prices)
            if len(normalized) != len(trades) or any(d.get("action") not in ("buy", "sell") for d in normalized):
                raise ValueError("Trade failed quantity/price validation")
            for d, source in zip(normalized, trades):
                d["research_ids"] = source["research_ids"]
            info["decision_messages"] = copy.deepcopy(current)
            info["corrected_decision"] = bool(correction)
            # Corrected decision completions are executed if valid, but excluded from SFT.
            return finish("traded" if normalized else "no_trade", trades=normalized)'''

new_finish = '''            trades = _parse_trade_decisions(response, universe, evidence)
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

assert old_parse in src, 'old_parse not found'
assert old_system in src, 'old_system not found'
assert old_prompt in src, 'old_prompt not found'
assert old_finish in src, 'old_finish not found'

src = src.replace(old_parse, new_parse)
src = src.replace(old_system, new_system)
src = src.replace(old_prompt, new_prompt)
src = src.replace(old_finish, new_finish)

cell['source'] = [line + '\n' for line in src.splitlines()]
if cell['source']:
    cell['source'][-1] = cell['source'][-1].rstrip('\n')

with open('main.ipynb', 'w', encoding='utf-8') as f:
    json.dump(nb, f, indent=1)

print('Updated cell 27 successfully in main.ipynb')
