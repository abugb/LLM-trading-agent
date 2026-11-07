with open('AGENT_OVERVIEW.md', 'r', encoding='utf-8') as f:
    text = f.read()

old_sec = '''Each phase allows one attempt and up to two retries, within six generations overall. Research gets 180 new tokens per call and decisions get 320. The model proposes a JSON array containing only buy/sell trades, with symbol, quantity, and research_ids, requiring at least one BUY or SELL per day. Omitted holdings stay unchanged; empty arrays `[]` are invalid and rejected.

Both research and trading are mandatory. Code verifies that each proposed trade cites a result actually returned for that symbol. Decisions without research or with empty proposals are rejected and retried with transient correction messages. These checks establish that data was supplied and cited; they do not prove that the model used it well.'''

# Also handle without backticks around [] if that was written
if old_sec not in text:
    old_sec = '''Each phase allows one attempt and up to two retries, within six generations overall. Research gets 180 new tokens per call and decisions get 320. The model proposes a JSON array containing only buy/sell trades, with symbol, quantity, and research_ids, requiring at least one BUY or SELL per day. Omitted holdings stay unchanged; empty arrays [] are invalid and rejected.

Both research and trading are mandatory. Code verifies that each proposed trade cites a result actually returned for that symbol. Decisions without research or with empty proposals are rejected and retried with transient correction messages. These checks establish that data was supplied and cited; they do not prove that the model used it well.'''

new_sec = '''Each phase allows one attempt and up to two retries, within six generations overall. Research gets 180 new tokens per call and decisions get 320. The model proposes a JSON array containing buy/sell trades with symbol and quantity (and optional research IDs), requiring at least one BUY or SELL per day. Omitted holdings stay unchanged; empty arrays `[]` are invalid and rejected.

Research is mandatory before any decision is accepted, but the agent is permitted to trade any stock in the permitted universe (`allowed_symbols`), including stocks it did not directly query during the research phase. Decisions without research or with empty proposals are rejected and retried with transient correction messages.'''

assert old_sec in text, 'old_sec not found'
text = text.replace(old_sec, new_sec)

with open('AGENT_OVERVIEW.md', 'w', encoding='utf-8') as f:
    f.write(text)

print('Updated AGENT_OVERVIEW.md successfully')
