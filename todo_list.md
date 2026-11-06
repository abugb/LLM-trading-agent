Fix cache to differentiate stocks
Use stock's quote value rather than portfolio value in reflections
Confirm orders fill before queuing reflection
set MAX_QTY_PER_TRADE to be a dollar amount rather than a share amount (might complicate things) - should be consistent across validators & agent loop as well
refactor "focus list" - agent should have a "held positions" list and the rest should be broadly researched (i think this is a good idea?)
Run paper trading several times to populate reflections (or populate some other way)