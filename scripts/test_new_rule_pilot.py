"""Pilot test for the new rule requiring at least one BUY or SELL per day."""
import datetime
import json
import os
from pathlib import Path
import time
import copy
import pandas as pd
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, set_seed
from notebook_validation import ROOT, load_namespace

def run_pilot():
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
    print("Registered tools:", list(ns['_tool_registry'].keys()))

    # Define updated _parse_trade_decisions with the rule:
    # at least one BUY or SELL per day, and [] is invalid again.
    def new_parse_trade_decisions(response, universe, evidence):
        """Strict trades-only contract: at least one BUY or SELL required; [] is invalid."""
        text = response.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            text = "\n".join(lines).strip()
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
        return items

    # Updated llm_agent_decide
    def new_llm_agent_decide(tok, model, state: dict, universe: list = None,
                             date: str = None, max_turns: int = 6, extra_context: str = "",
                             past_reflections: list = None, historical_data: dict = None,
                             diagnostics: dict = None, debug_tokens: bool = False):
        import time as _agent_time
        universe = list(ns['WHITELIST'] if universe is None else universe)
        if not isinstance(max_turns, int) or isinstance(max_turns, bool) or max_turns < 2:
            raise ValueError("max_turns must reserve at least one research and one decision call")
        info = diagnostics if diagnostics is not None else {}
        info.clear()
        info.update(contract_version=2, status="running", failure_reason=None, calls=[],
                    tools=[], evidence={}, universe=universe, retries=0,
                    corrected_decision=False, sft_eligible=False, decision_messages=[])
        evidence, executed = info["evidence"], set()
        clean_state = dict(state)
        clean_state["allowed_symbols"] = universe

        system = ("You manage a stock portfolio using verified research. "
                  "In the research phase output one tool call. In the decision phase output "
                  "only a JSON array of buy/sell trades, requiring at least one BUY or SELL per day. "
                  "Omit all unchanged stocks. An empty array [] is invalid; never output []. "
                  "Each trade must cite a returned research ID for its symbol. "
                  f"Whole shares only; estimated value per trade is at most ${ns['MAX_TRADE_VALUE']:,.2f}. "
                  "Only allowed_symbols from the account state may be traded.\n" + ns['_build_tools_prompt']())

        messages = [{"role": "system", "content": system},
                    {"role": "user", "content": "Account State:\n" + json.dumps(clean_state)}]
        if extra_context:
            messages.append({"role": "user", "content": "Additional context (not verified research):\n" + extra_context})
        if past_reflections:
            messages.append({"role": "user", "content": "Past lessons:\n" + "\n".join(past_reflections)})

        account_tokens = ns['_context_tokens'](tok, messages[1]["content"])
        instruction_tokens = ns['_context_tokens'](tok, system)
        tool_calls = 0
        prompt = ""
        phase = "research"
        phase_attempt = 0
        correction = ""

        research_prompt = ("Research phase: select a relevant stock from allowed_symbols and request ONE available tool. "
                           "Generate only the tool call; do not generate decisions or tool results.")
        decision_prompt = ('Decision phase: use the returned research. Output ONLY one JSON array with at least one BUY or SELL trade, e.g. '
                           '[{"symbol":"AAPL","action":"buy","qty":1,"research_ids":["R1"]}]. '
                           'Use actual evidence IDs and symbols. Omit all unchanged stocks. [] is invalid.')
        corrections = {
            "research": "Correction: output exactly ONE registered tool call with valid arguments. Select another tool or stock if data was unavailable. No decisions or invented results.",
            "decision": "Correction: output exactly one valid trades-only JSON array with at least one BUY or SELL. Use positive integer qty and real research_ids for each symbol. Omit unchanged stocks. [] is invalid.",
        }

        def finish(status, reason=None, trades=None):
            trades = trades or []
            info.update(status=status, failure_reason=reason, no_trade=(status == "no_trade"),
                        trade_decisions=len(trades), verified_reference_decisions=len(trades),
                        sft_eligible=(status == "traded" and not info["corrected_decision"]))
            if status == "failed":
                print(f"  [Decision failed] {reason}; no orders, existing positions retained", flush=True)
            else:
                print(f"  [Decision] {status}; {len(trades)} trade(s)", flush=True)
            return ns['AgentDecisionResult'](trades, prompt, ns['_trade_completion'](trades), tool_calls, copy.deepcopy(info))

        for turn in range(max_turns):
            phase_text = research_prompt if phase == "research" else decision_prompt
            current = messages + [{"role": "user", "content": phase_text}]
            if correction:
                current += [{"role": "user", "content": correction}]
            base_prompt = tok.apply_chat_template(current, tokenize=False, add_generation_prompt=True)
            prefix = '<tool_call>\n{"name": "' if phase == "research" else ""
            prompt = base_prompt + prefix
            cap = 180 if phase == "research" else 320
            print(f"  [Generation {turn+1}/{max_turns}] Starting {phase}, attempt {phase_attempt+1}...", flush=True)
            inputs = tok(prompt, return_tensors="pt", add_special_tokens=False)
            inputs = {k: v.to(model.device) for k, v in inputs.items()}
            component = {"instructions": instruction_tokens, "account_state": account_tokens,
                         "tool_results": sum(ns['_context_tokens'](tok, m["content"]) for m in messages if m["role"] == "tool"),
                         "assistant_calls": sum(ns['_context_tokens'](tok, m["content"]) for m in messages if m["role"] == "assistant"),
                         "phase": ns['_context_tokens'](tok, phase_text), "retry": ns['_context_tokens'](tok, correction),
                         "extra_context": sum(ns['_context_tokens'](tok, m["content"]) for m in messages[2:] if m["role"] == "user")}
            generation_args = dict(max_new_tokens=cap, do_sample=True, temperature=0.7, top_p=0.9,
                                   eos_token_id=tok.eos_token_id, pad_token_id=tok.eos_token_id, use_cache=True)
            if phase == "research":
                generation_args.update(stop_strings=["</tool_call>"], tokenizer=tok)
            started = _agent_time.perf_counter()
            with torch.inference_mode():
                output = model.generate(**inputs, **generation_args)
            ids = output[0][inputs["input_ids"].shape[1]:].tolist()
            raw = tok.decode(ids, skip_special_tokens=False)
            response = prefix + tok.decode(ids, skip_special_tokens=True).strip()

            envelope_closed = False
            if phase == "research" and ids and ids[-1] == tok.eos_token_id and not response.rstrip().endswith("</tool_call>"):
                try:
                    json.loads(response[len("<tool_call>"):].strip())
                    response += "\n</tool_call>"
                    envelope_closed = True
                except (ValueError, TypeError):
                    pass
            elapsed = _agent_time.perf_counter() - started
            hit_cap = len(ids) >= cap and (not ids or ids[-1] != tok.eos_token_id) and not (phase == "research" and response.rstrip().endswith("</tool_call>"))
            call_log = dict(phase=phase, attempt=phase_attempt+1, input_tokens=inputs["input_ids"].shape[1],
                            output_tokens=len(ids), cap=cap, cap_hit=hit_cap, seconds=elapsed,
                            parsed=False, components=component, envelope_closed=envelope_closed)
            if debug_tokens:
                call_log.update(token_ids=ids, raw_response=raw, reconstructed_response=response)
            info["calls"].append(call_log)
            print(f"  [Generation] {phase}: {elapsed:.1f}s | input={call_log['input_tokens']} | "
                  f"output={len(ids)}/{cap} | cap_hit={hit_cap} | components={component}", flush=True)
            try:
                if hit_cap:
                    raise ValueError("Response token budget exhausted")
                if phase == "research":
                    call = ns['_parse_research_call'](response, universe)
                    call_log["parsed"] = True
                    key = json.dumps(call, sort_keys=True)
                    if key in executed:
                        raise ValueError("Repeated research call")
                    executed.add(key)
                    print(f"  [Tool] {call['name']} {call['arguments']}", flush=True)
                    result = ns['dispatch_tool'](call["name"], call["arguments"], date=date, historical_data=historical_data)
                    tool_calls += 1
                    context = ns['_format_research_context'](tok, call["name"], result)
                    symbols = ns['_researched_symbols'](call["name"], call["arguments"], context).intersection(universe)
                    info["tools"].append(dict(name=call["name"], raw_tokens=ns['_context_tokens'](tok, str(result)),
                                              context_tokens=ns['_context_tokens'](tok, context), symbols=sorted(symbols)))
                    print(f"  [Tool context] raw={info['tools'][-1]['raw_tokens']} tokens; "
                          f"sent={info['tools'][-1]['context_tokens']} tokens; usable={sorted(symbols)}")
                    if not symbols:
                        raise ValueError("Tool returned no usable evidence for allowed symbols")
                    ref = f"R{len(evidence)+1}"
                    evidence[ref] = sorted(symbols)
                    messages += [{"role": "assistant", "content": response},
                                 {"role": "tool", "content": f"Research ID: {ref}\n" + context}]
                    phase, phase_attempt, correction = "decision", 0, ""
                    continue
                trades = new_parse_trade_decisions(response, universe, evidence)
                call_log["parsed"] = True
                if not evidence:
                    raise ValueError("Decision requires research")
                prices = ns['_decision_reference_prices'](trades, date, historical_data)
                normalized = ns['_validate_decisions'](trades, prices)
                if not normalized or len(normalized) != len(trades) or any(d.get("action") not in ("buy", "sell") for d in normalized):
                    raise ValueError("Trade failed quantity/price validation")
                for d, source in zip(normalized, trades):
                    d["research_ids"] = source["research_ids"]
                info["decision_messages"] = copy.deepcopy(current)
                info["corrected_decision"] = bool(correction)
                return finish("traded", trades=normalized)
            except (ValueError, TypeError, KeyError) as exc:
                call_log["error"] = str(exc)
                print(f"  [Rejected {phase}] {exc} | response was: {response[:80]!r}", flush=True)
                info["retries"] += 1
                phase_attempt += 1
                correction = corrections[phase]
                if phase_attempt >= 3 or (phase == "research" and turn >= max_turns - 2):
                    return finish("failed", f"{phase}_failed")
        return finish("failed", f"{phase}_failed")

    ns['llm_agent_decide'] = new_llm_agent_decide
    ns['_parse_trade_decisions'] = new_parse_trade_decisions

    # Run 5 real backtest sessions
    set_seed(42)
    print("\n" + "="*60)
    print("RUNNING 5 REAL SESSIONS WITH UPDATED RULE")
    print("="*60)
    start_time = time.time()
    results = ns['run_backtest'](tok, model, collector=None, n_days=5, verbose=True)
    elapsed = time.time() - start_time

    print(f"\n--- Completed 5 sessions in {elapsed:.1f}s ---")
    print("Quality metrics:", json.dumps(results['agent_quality'], indent=2))
    print(f"Trades executed ({len(results['trades'])}):")
    for t in results['trades']:
        print(f"  {t['date']}: {t['side'].upper()} {t['qty']} {t['symbol']} @ ${t['price']:.2f}")

    print("\nSession Details:")
    for diag in results['session_diagnostics']:
        date = diag.get('date')
        status = diag.get('status')
        trades = diag.get('trade_decisions', 0)
        tools = [t['name'] + ' ' + str(t['symbols']) for t in diag.get('tools', [])]
        print(f"  Date: {date} | Status: {status} | Trades: {trades} | Tools: {tools}")

if __name__ == '__main__':
    run_pilot()
