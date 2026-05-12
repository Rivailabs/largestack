"""
DeepSeek Capability Benchmark for Largestack AI.

Purpose:
- Use DeepSeek as live LLM.
- Run 10 medium-to-hard agentic scenarios.
- Use planner -> builder -> reviewer agent pattern.
- Save real outputs as markdown files.
- Produce a final benchmark summary.

Run:
    export LARGESTACK_DEEPSEEK_API_KEY='YOUR_REAL_KEY'
    python scripts/benchmarks/deepseek_capability_benchmark.py
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from largestack import Agent


LLM = "deepseek/deepseek-chat"
BENCHMARK_GUARDRAIL_MODE = os.environ.setdefault("LARGESTACK_GUARDRAIL_MODE", "warn")
BENCHMARK_CONTEXT = os.environ.setdefault("LARGESTACK_CONTEXT", "planning")


SCENARIOS = [
    {
        "id": "01_business_process_automation",
        "title": "Business Process Automation Agent",
        "difficulty": "Medium",
        "task": """
You are building an agentic automation system for a company process.

Use case:
- Intake customer request
- Classify request
- Extract required fields
- Trigger correct workflow
- Send response
- Escalate exceptions
- Log audit trail

Deliver:
1. Problem understanding
2. Proposed agent flow
3. Tool list
4. Data model
5. Validation checks
6. Failure handling
7. Output JSON schema
8. Production readiness risks
""",
    },
    {
        "id": "02_multi_agent_architecture_review",
        "title": "Multi-Agent Software Architecture Review",
        "difficulty": "Hard",
        "task": """
Design a multi-agent architecture reviewer for a Python/FastAPI/React project.

Agents:
- Code structure analyst
- Security reviewer
- API contract reviewer
- Test coverage reviewer
- Production readiness reviewer

Deliver:
1. Agent roles
2. Input/output contract
3. Review workflow
4. Scoring rubric out of 100
5. Required tools
6. Failure modes
7. Example final report structure
""",
    },
    {
        "id": "03_auto_website_development_tool",
        "title": "Auto Website Development Tool",
        "difficulty": "Hard",
        "task": """
Design an AI tool that can generate a production-grade website from a business idea.

Business idea:
A rental property management website with owner, tenant, manager dashboards.

Deliver:
1. Requirement breakdown
2. Page list
3. React/Next.js component structure
4. Backend API structure
5. Database schema
6. Auth/RBAC plan
7. Deployment plan
8. Test plan
9. What can be automated now vs what needs developer review
""",
    },
    {
        "id": "04_ml_model_build_automation",
        "title": "Machine Learning Model Build Automation",
        "difficulty": "Hard",
        "task": """
Design an agentic ML automation system.

Use case:
Given a CSV dataset, automatically:
- Profile the data
- Identify target column
- Detect regression/classification
- Train baseline models
- Evaluate metrics
- Generate explainability report
- Package model
- Create API endpoint

Deliver:
1. Agent workflow
2. Tools needed
3. Python module/file structure
4. Metrics strategy
5. Data validation rules
6. Model registry plan
7. Risks and human approval points
""",
    },
    {
        "id": "05_rag_knowledge_assistant",
        "title": "RAG Knowledge Assistant",
        "difficulty": "Hard",
        "task": """
Design a RAG assistant for enterprise internal documents.

Requirements:
- Upload PDFs/DOCX/CSV
- Chunk documents
- Embed and store vectors
- Retrieve relevant chunks
- Answer with citations
- Detect hallucinations
- Respect document permissions

Deliver:
1. Architecture
2. Retrieval strategy
3. Chunking strategy
4. Citation format
5. Guardrails
6. Evaluation metrics
7. Failure cases
8. Production deployment plan
""",
    },
    {
        "id": "06_enterprise_ai_security_gateway",
        "title": "Enterprise AI Security Gateway",
        "difficulty": "Very Hard",
        "task": """
Design an AI security gateway placed between enterprise users and LLM providers.

Requirements:
- Detect secrets, PII, financial data
- Mask before sending to LLM
- Unmask after response
- Route across providers
- Log every request
- Policy-based blocking
- Admin dashboard
- On-prem option

Deliver:
1. System architecture
2. Policy engine
3. Masking/unmasking flow
4. Provider routing logic
5. Audit logging model
6. Threat model
7. Enterprise/BFSI readiness gaps
8. Build roadmap
""",
    },
    {
        "id": "07_jarvis_intelligence_os",
        "title": "Jarvis-Like Intelligence Assistant",
        "difficulty": "Very Hard",
        "task": """
Design a Jarvis-like personal intelligence operating system.

Capabilities:
- Understand user goals
- Manage calendar/tasks
- Monitor emails/messages
- Suggest next best actions
- Build small automations
- Track finances, learning, health routines
- Respect privacy and permissions
- Escalate decisions to user

Deliver:
1. Core modules
2. Agent hierarchy
3. Memory design
4. Tool permission model
5. Daily planning loop
6. Risk controls
7. MVP vs advanced version
8. Why this is hard
""",
    },
    {
        "id": "08_document_extraction_automation",
        "title": "Document Extraction Automation",
        "difficulty": "Medium-Hard",
        "task": """
Design an agentic document extraction system.

Use case:
Extract data from invoices, IDs, bank statements, lease agreements, and forms.

Deliver:
1. Document classification flow
2. OCR/data extraction flow
3. Field validation
4. Confidence scoring
5. Human review queue
6. Database schema
7. API design
8. Compliance concerns
""",
    },
    {
        "id": "09_production_readiness_audit",
        "title": "Production Readiness Audit Agent",
        "difficulty": "Hard",
        "task": """
Create a production readiness audit framework for any software project.

It must evaluate:
- Architecture
- Security
- Tests
- Observability
- CI/CD
- Docker/deployment
- Performance
- Documentation
- Maintainability

Deliver:
1. Audit checklist
2. Scoring formula out of 100
3. Evidence required
4. Red/yellow/green classification
5. Sample final audit table
6. Common fake/mocked feature detection
""",
    },
    {
        "id": "10_startup_product_blueprint",
        "title": "End-to-End Startup Product Blueprint",
        "difficulty": "Very Hard",
        "task": """
Create a product blueprint for an AI agentic framework startup.

Product:
An enterprise agentic AI platform that offers agents, workflows, RAG, tools, guardrails, provider routing, cost tracking, dashboards, and deployment templates.

Deliver:
1. ICP/customer segments
2. Competitor positioning
3. Product modules
4. MVP plan
5. Pricing strategy
6. Enterprise sales motion
7. Technical roadmap
8. Risk register
9. 90-day execution plan
""",
    },
]


def selected_scenarios() -> list[dict[str, str]]:
    """Return optionally sharded scenarios for long live benchmark runs."""
    start = int(os.environ.get("LARGESTACK_BENCHMARK_START_INDEX", "1"))
    end = int(os.environ.get("LARGESTACK_BENCHMARK_END_INDEX", str(len(SCENARIOS))))
    start = max(1, start)
    end = min(len(SCENARIOS), end)
    return SCENARIOS[start - 1:end]


def now_stamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def content_of(result: Any) -> str:
    return str(getattr(result, "content", result))


async def close_agent(agent: Agent) -> None:
    closer = getattr(agent, "aclose", None)
    if closer:
        await closer()


async def ask_agent(name: str, instructions: str, prompt: str) -> str:
    agent = Agent(
        name=name,
        instructions=instructions,
        llm=LLM,
        guardrails=None,
    )
    try:
        result = await agent.run(prompt)
        return content_of(result)
    finally:
        await close_agent(agent)


async def run_scenario(scenario: dict[str, str], outdir: Path) -> dict[str, Any]:
    sid = scenario["id"]
    title = scenario["title"]
    difficulty = scenario["difficulty"]
    task = scenario["task"]

    print(f"\n===== RUNNING {sid}: {title} =====")
    start = time.perf_counter()

    planner_prompt = f"""
You are the PLANNER agent.

Scenario:
{title}

Difficulty:
{difficulty}

Task:
{task}

Return:
- Clear decomposition
- Assumptions
- Step-by-step execution plan
- Risks
- Required tools/data
- Success criteria
"""

    planner = await ask_agent(
        name=f"{sid}-planner",
        instructions="You are a senior AI solution planner. Be precise, structured, and practical.",
        prompt=planner_prompt,
    )

    builder_prompt = f"""
You are the BUILDER/ARCHITECT agent.

Use the planner output below and produce a complete implementable design.

Planner output:
{planner}

Now produce:
1. Final architecture
2. Component list
3. File/folder structure
4. API/data contracts where relevant
5. Agent workflow
6. Tool workflow
7. Validation strategy
8. Deployment/run strategy
9. Step-by-step build plan
"""

    builder = await ask_agent(
        name=f"{sid}-builder",
        instructions="You are a principal software architect and automation engineer.",
        prompt=builder_prompt,
    )

    reviewer_prompt = f"""
You are the REVIEWER/QA/SECURITY agent.

Review the proposed design below.

Scenario:
{title}

Planner output:
{planner}

Builder output:
{builder}

Return:
1. Score out of 100
2. What is strong
3. What is weak/missing
4. Production risks
5. Security risks
6. Test cases required
7. Final verdict: PASS / CONDITIONAL_PASS / FAIL
"""

    reviewer = await ask_agent(
        name=f"{sid}-reviewer",
        instructions="You are a strict reviewer. Be honest. Do not overpraise.",
        prompt=reviewer_prompt,
    )

    elapsed = time.perf_counter() - start

    output = f"""# {title}

**Scenario ID:** `{sid}`  
**Difficulty:** {difficulty}  
**Elapsed seconds:** {elapsed:.2f}

---

## 1. Planner Agent Output

{planner}

---

## 2. Builder / Architect Agent Output

{builder}

---

## 3. Reviewer / QA / Security Agent Output

{reviewer}
"""

    outfile = outdir / f"{sid}.md"
    outfile.write_text(output, encoding="utf-8")

    passed = (
        len(planner.strip()) > 200
        and len(builder.strip()) > 300
        and len(reviewer.strip()) > 200
        and any(word in reviewer.lower() for word in ["score", "pass", "conditional", "fail"])
    )

    print(f"RESULT {sid}: {'PASS' if passed else 'CHECK'} -> {outfile}")

    return {
        "id": sid,
        "title": title,
        "difficulty": difficulty,
        "elapsed_seconds": round(elapsed, 2),
        "output_file": str(outfile),
        "passed_basic_quality_gate": passed,
        "planner_chars": len(planner),
        "builder_chars": len(builder),
        "reviewer_chars": len(reviewer),
    }


async def main() -> None:
    key = os.environ.get("LARGESTACK_DEEPSEEK_API_KEY")
    if not key:
        raise SystemExit("ERROR: Set LARGESTACK_DEEPSEEK_API_KEY before running.")

    outdir = Path("release_evidence") / "deepseek_capability_benchmark" / now_stamp()
    outdir.mkdir(parents=True, exist_ok=True)

    print("Output directory:", outdir)
    print(
        "Guardrails:",
        f"mode={BENCHMARK_GUARDRAIL_MODE}",
        f"context={BENCHMARK_CONTEXT}",
    )
    print("Benchmark uses warn/planning mode for architecture planning; critical abuse guardrails remain active.")

    results = []
    scenarios = selected_scenarios()
    print(f"Scenario range: {scenarios[0]['id']} -> {scenarios[-1]['id']}")

    for scenario in scenarios:
        try:
            results.append(await run_scenario(scenario, outdir))
        except Exception as exc:
            print(f"FAILED {scenario['id']}: {exc}")
            results.append({
                "id": scenario["id"],
                "title": scenario["title"],
                "difficulty": scenario["difficulty"],
                "error": repr(exc),
                "passed_basic_quality_gate": False,
            })

    passed_count = sum(1 for r in results if r.get("passed_basic_quality_gate"))
    total = len(results)

    summary = {
        "benchmark": "DeepSeek Capability Benchmark",
        "llm": LLM,
        "total_scenarios": total,
        "scenario_range": [scenarios[0]["id"], scenarios[-1]["id"]],
        "passed_basic_quality_gate": passed_count,
        "failed_or_check": total - passed_count,
        "results": results,
    }

    (outdir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    md_lines = [
        "# DeepSeek Capability Benchmark Summary",
        "",
        f"- LLM: `{LLM}`",
        f"- Total scenarios: **{total}**",
        f"- Passed basic quality gate: **{passed_count}/{total}**",
        "",
        "| Scenario | Difficulty | Status | Output |",
        "|---|---|---:|---|",
    ]

    for r in results:
        status = "PASS" if r.get("passed_basic_quality_gate") else "CHECK"
        output_file = r.get("output_file", "")
        md_lines.append(
            f"| {r['title']} | {r['difficulty']} | {status} | `{output_file}` |"
        )

    (outdir / "SUMMARY.md").write_text("\n".join(md_lines), encoding="utf-8")

    print("\n===== FINAL BENCHMARK SUMMARY =====")
    print(json.dumps(summary, indent=2))
    print(f"\nSUMMARY_FILE={outdir / 'SUMMARY.md'}")


if __name__ == "__main__":
    asyncio.run(main())
