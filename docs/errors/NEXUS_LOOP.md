# LARGESTACK_LOOP — Loop Detected

**Error:** `LoopDetectedError`

**When:** One of 5 loop detectors triggered:
- `max_turns` — exceeded iteration limit (default: 25)
- `timeout` — wall-clock time exceeded (default: 300s)
- `fingerprint` — 3 identical tool call sequences in a row
- `no_progress` — 5 turns with no new information

**Solutions:**

1. **Improve instructions** — vague prompts cause loops. Be specific about when to stop.
2. **Check tool responses** — if tools return errors, the agent retries forever.
3. **Increase max_turns** — `Agent(max_turns=50)` for complex research tasks.
4. **Add a steering hook** — force completion after N tool calls.
