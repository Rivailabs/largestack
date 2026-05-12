# LARGESTACK_KILL_SWITCH — Emergency Stop

**Error:** `KillSwitchActivatedError`  
**Retryable:** No (until deactivated)

**When:** The kill switch was activated — all agents halt immediately.

**What happens:**
- Every agent checks the kill switch before each LLM call
- Parent agent kill cascades to all child agents in a Team
- No new LLM calls, tool executions, or agent runs are allowed
- In-progress operations complete their current step then halt

**File-based (default):**  
Creates `~/.largestack/.kill_switch` file. Checked by all agents on the same machine.

**Redis-based (distributed):**  
Publishes to `largestack:kill_switch` channel. All nodes with Redis access halt within 1 second.  
Configure: `kill_switch_backend: redis` and `redis_url: redis://...` in `largestack.yaml`.

**Activate:**
```python
from largestack._guard.kill_switch import activate
activate("security incident detected", by="monitoring-system")
```

**Deactivate:**
```bash
largestack resume
```
Or programmatically:
```python
from largestack._guard.kill_switch import deactivate
deactivate()
```

**What state persists:** Kill switch state is stored in the file or Redis key. It survives process restarts. You must explicitly call `largestack resume` or `deactivate()` to clear it.
