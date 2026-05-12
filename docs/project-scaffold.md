# Project Scaffold

`largestack init <name>` generates the productized support-ticket template by default. `largestack init <name> --template agent` and `largestack new <name> --type agent` generate the generic agent scaffold.

Generated projects include `largestack.yaml`, `providers.yaml`, `agents.yaml`, `agent_groups.yaml`, `tools.yaml`, `workflow.yaml`, `workflow_graph.mmd`, `rag.yaml`, `guardrails.yaml`, `app/agents`, `app/tools`, `app/workflows`, `app/rag`, `tests`, `deploy`, scripts, `.env.example`, `AGENTS.md`, and a README that explains the edit points.

Run `largestack doctor`, `largestack explain`, `largestack providers`, `largestack graph`, `largestack knowledge list`, `largestack run app/main.py`, and `largestack test` inside the generated project before adding live provider credentials.

Built-in product templates:

- `support-ticket`
- `rag`
- `code-review`
- `ml-automation`
- `website-builder`
- `video-pipeline`
- `social-media`
- `bfsi`
- `document-extraction`

Use `largestack templates` to print the installed catalog.
