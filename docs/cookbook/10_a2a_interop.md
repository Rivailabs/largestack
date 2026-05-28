# Recipe 10 — A2A Cross-Framework Interop

**Use case:** Your LARGESTACK KYC agent needs to call a LangGraph
underwriting agent and a CrewAI document-collection agent. All three
are different frameworks, different teams, different deploys. **A2A
makes them talk.**

## What is A2A?

Agent2Agent (A2A) is an open protocol from Google, donated to the
Linux Foundation. It standardizes:

- **Discovery** — `GET /.well-known/agent.json` returns an `AgentCard`
- **Tasks** — `POST /tasks/send` to invoke; `GET /tasks/{id}` to query status
- **Lifecycle** — submitted → working → completed/failed/canceled

LARGESTACK supports A2A via `largestack._a2a`. Currently 150+ orgs in production
including SAP, ServiceNow, Salesforce, Workday.

A2A complements MCP:

- **MCP** — agent ↔ tools/data
- **A2A** — agent ↔ other agents

## Exposing a LARGESTACK agent over A2A

```python
from largestack._a2a import expose_largestack_agent, AgentSkill
from largestack._core import Agent

# Your existing LARGESTACK agent
kyc_agent = Agent(
    name="kyc-agent",
    model="openai/gpt-4o-mini",
    instructions="Verify customer identity using Aadhaar + PAN",
    tools=["aadhaar_okyc", "pan_verify"],
)

# Wrap it as an A2A server
server = expose_largestack_agent(
    kyc_agent,
    name="LARGESTACK KYC Agent",
    description="DPDP-compliant Aadhaar + PAN verification",
    url="https://kyc.example.com",
    skills=[
        AgentSkill(
            id="verify_kyc",
            name="Verify Customer KYC",
            description="Cross-checks Aadhaar OKYC and PAN",
            tags=["kyc", "india", "dpdp"],
            examples=["Verify customer Rajesh with Aadhaar 1234"],
        ),
    ],
    provider_name="RivaiLabs",
)


# Mount on FastAPI / aiohttp
from aiohttp import web

async def handle_a2a(request: web.Request):
    body = await request.json() if request.body_exists else None
    status, response = await server.handle_request(
        request.method, request.path, body,
    )
    return web.json_response(response, status=status)


app = web.Application()
app.router.add_route("*", "/.well-known/agent.json", handle_a2a)
app.router.add_route("*", "/tasks/{tail:.*}", handle_a2a)
web.run_app(app, host="0.0.0.0", port=8080)
```

## Calling a remote A2A agent (LangGraph, CrewAI, ADK)

```python
import asyncio
from largestack._a2a import A2AClient

async def underwrite_loan(customer_id: str):
    # Discover the underwriting agent
    underwriter = A2AClient(
        base_url="https://underwrite.example.com",
        api_key="bearer-token-xyz",
    )
    card = await underwriter.discover()
    print(f"Calling {card.name} v{card.version}")

    # Send a task
    task = await underwriter.send_task(
        f"Underwrite loan for customer {customer_id}",
        metadata={"loan_amount_inr": 500000},
    )
    if task.state == "completed":
        return task.messages[-1].get_text()
    elif task.state == "failed":
        raise RuntimeError(f"underwriting failed: {task.error}")
    elif task.state == "input-required":
        # Agent needs more info
        # ... handle interactively ...
        pass


asyncio.run(underwrite_loan("cust42"))
```

## Multi-framework workflow

```python
async def end_to_end_loan_origination(customer_id: str):
    # 1) LARGESTACK KYC agent (in-process)
    from largestack._core import Agent as LargestackAgent
    kyc_agent = LargestackAgent(name="kyc", ...)
    kyc_resp = await kyc_agent.run(f"verify {customer_id}")

    # 2) LangGraph Underwriter (remote, A2A)
    underwriter = A2AClient(base_url="https://uw.example.com")
    uw_task = await underwriter.send_task(
        f"Underwrite for {customer_id}, KYC result: {kyc_resp.content}"
    )

    # 3) CrewAI Doc-Collector (remote, A2A)
    docs = A2AClient(base_url="https://docs.example.com")
    doc_task = await docs.send_task(
        f"Collect KYC + ITR + bank statements for {customer_id}"
    )

    # All three different frameworks, talking via A2A
    return {
        "kyc": kyc_resp.content,
        "underwrite": uw_task.messages[-1].get_text(),
        "docs": doc_task.artifacts,
    }
```

## AgentCard schema

```json
{
  "name": "LARGESTACK KYC Agent",
  "description": "DPDP-compliant Aadhaar + PAN verification",
  "url": "https://kyc.example.com",
  "version": "1.0.0",
  "protocol_version": "0.3.0",
  "capabilities": {
    "streaming": false,
    "push_notifications": false,
    "state_transition_history": true
  },
  "skills": [
    {
      "id": "verify_kyc",
      "name": "Verify Customer KYC",
      "description": "Cross-checks Aadhaar OKYC and PAN",
      "tags": ["kyc", "india", "dpdp"],
      "examples": ["Verify customer Rajesh with Aadhaar 1234"]
    }
  ],
  "default_input_modes": ["text/plain"],
  "default_output_modes": ["text/plain"],
  "provider_name": "RivaiLabs",
  "provider_url": "https://largestack.ai"
}
```

## Discovery

To make your LARGESTACK agent discoverable in agent registries:

1. Host the agent at a public URL with HTTPS
2. Submit the URL to:
   - [a2a-protocol.org/registry](https://a2a-protocol.org/) (Linux Foundation)
   - Google Vertex AI Agent Garden
   - Anthropic MCP/A2A directory

## Why this matters

- **Cross-team interop**: KYC team uses LARGESTACK, underwriting team uses LangGraph, doc-team uses CrewAI — all interoperate
- **Vendor flexibility**: swap a LARGESTACK agent for a LangGraph one without changing callers
- **Industry standard**: 150+ orgs already on A2A; this is where the ecosystem is heading

## Read more

- A2A protocol spec: https://a2a-protocol.org/
- Google ADK + A2A codelabs: https://codelabs.developers.google.com/
- Linux Foundation governance: https://linuxfoundation.org
