# Developer Guide

## Public APIs

Use `largestack.Agent` for ordinary agents, `largestack.decorators.Agent` for typed/dependency-injected agents, `@tool` for tool registration, `Team` for multi-agent execution, `Workflow` for DAG/state-machine flows, and `largestack.testing` for deterministic tests.

## Execution Flow

1. An agent receives a task and builds messages from instructions, memory, tools, and runtime context.
2. Guardrails inspect input when configured.
3. `LLMGateway` routes `provider/model` to the selected provider adapter.
4. Tool calls are validated, permission-checked, retried if configured, and executed with timeout controls.
5. Output guardrails inspect the response.
6. Cost, health, trace, and audit hooks record the run.

## Provider Flow

Models use `provider/model` strings such as `deepseek/deepseek-chat` or `openai/gpt-4o-mini`. Provider adapters read keys from `LARGESTACK_*` environment variables. Missing providers fail loudly with a setup hint.

## Tests

Use `TestModel` or `FunctionModel` for unit tests. Live-provider tests must be gated by env vars and have explicit skip reasons.

## Repository Hygiene

Generated files belong in `/tmp` or ignored folders. Do not commit `.env`, `dist/`, `build/`, caches, local venvs, logs, or copied validation output.
