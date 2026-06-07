# CLI reference

The `largestack` command is installed with the package. Run `largestack --help` for the
live list, or `largestack <command> --help` for a command's options.

```bash
largestack --help
```

## Project & scaffolding
| Command | What it does |
|---|---|
| `largestack version` | Show the installed version. |
| `largestack setup` | First-run: pick a provider, store its key in a gitignored `.env` (interactive, or `--provider/--api-key/--model` for CI). |
| `largestack init` | Initialize a production-shaped project in the current directory. |
| `largestack new` | Create a new project from a template (`largestack templates` to list). |
| `largestack templates` | List and explain the bundled project templates. |
| `largestack explain` | Explain a generated project or a beginner-facing section. |
| `largestack add` | Add knowledge, integrations, agents, or tools to a project. |

## Run & serve
| Command | What it does |
|---|---|
| `largestack run <file|config>` | Run a Python agent file or a YAML agent/workflow config. |
| `largestack serve <agent.py>` | Serve an agent as a REST API. |
| `largestack dev` | Dev server with hot-reload + playground (http://localhost:4111). |
| `largestack dashboard` | Start the observability dashboard. |
| `largestack graph` | Explain or regenerate a workflow graph. |

## Diagnostics & observability
| Command | What it does |
|---|---|
| `largestack doctor` | Diagnose setup: Python, API keys, Ollama, dependencies. |
| `largestack providers` | Show provider routing (never prints API keys). |
| `largestack trace` | View recent traces (`~/.largestack/traces.db`). |
| `largestack cost` | Cost breakdown per agent (from the audit trail). |
| `largestack resume` | Resume after the kill switch was activated. |

## Security & compliance
| Command | What it does |
|---|---|
| `largestack owasp` | Print the OWASP LLM-Top-10 / Agentic coverage matrix. |
| `largestack redteam` | Run the offline guardrail red-team eval (non-zero exit if a core attack passes). |
| `largestack siem-export --fmt cef --out audit.cef` | Export the audit trail (JSON-lines / CEF / LEEF) to file. |
| `largestack sbom --fmt cyclonedx --out sbom.json` | Generate a Software Bill of Materials (CycloneDX/SPDX). |

## Knowledge, RAG, integrations, protocols
| Command | What it does |
|---|---|
| `largestack knowledge` | Manage local project knowledge sources. |
| `largestack rag` | Build, test, and explain a local RAG config. |
| `largestack mcp` | Manage MCP tool servers. |

## Lifecycle
| Command | What it does |
|---|---|
| `largestack test` | Run tests for your agents. |
| `largestack deploy` | Deploy an agent (see [Deployment](deployment.md)). |
| `largestack migrate` | Check and apply compatibility migrations. |
| `largestack license` | Activate or check a license. |
