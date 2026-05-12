# Tutorial 4: Guardrails and Safety

Protect your agents from PII leaks, prompt injection, and hallucinations.

## Quick Setup

```python
from largestack import Agent, create_guardrails

agent = Agent(
    name="safe-agent",
    guardrails=create_guardrails(
        pii=True,              # Detect emails, SSN, credit cards
        injection=True,        # Block prompt injection
        hallucination=True,    # NLI faithfulness check (for RAG)
        toxicity=True,         # Block toxic content
        topic_blocklist=["politics", "religion"],
    ),
)
```

## By Name

```python
agent = Agent(
    name="safe",
    guardrails=["pii", "injection", "hallucination", "toxicity"],
)
```

## PII Redaction

```python
from largestack._guard.pii import PIIGuard

guard = PIIGuard()
text = "Email me at john@company.com, my SSN is 123-45-6789"
clean = guard.redact(text)
# "Email me at [EMAIL_REDACTED], my SSN is [SSN_REDACTED]"
```

## Steering Hooks

```python
from largestack import steer_before_tool, proceed, interrupt

@steer_before_tool
def block_writes(tool_name, params, context):
    if tool_name in ("write_file", "shell_command", "database_query"):
        return interrupt("Write operations not allowed in this mode")
    return proceed()

agent = Agent(name="read-only", steering=[block_writes])
```

## Kill Switch

```bash
largestack resume  # Resume after emergency stop
```

```python
from largestack._guard.kill_switch import activate, deactivate
activate("security incident")  # All agents halt immediately
deactivate()                    # Resume
```

## Next: [RAG and knowledge bases →](05_rag_knowledge.md)
