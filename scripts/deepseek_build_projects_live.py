"""Strict live build test: Largestack + DeepSeek must generate project files.

Unlike real_projects_capstone.py, this harness does not pre-write the project
implementations. It asks a Largestack Agent backed by DeepSeek to produce each
project as JSON files, saves those files, then runs compile, pytest, and hidden
acceptance checks.
"""
from __future__ import annotations

import asyncio
import json
import os
import py_compile
import re
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from largestack import Agent
from largestack._core.cost import CostTracker
from largestack.autonomous_builder import (
    AutonomousProjectBuilder,
    BuilderBudget,
    NoOpMemory,
    ProjectSpec,
    serialize_report,
    summarize_report,
)
from largestack.observability import Monitor


MODEL = "deepseek/deepseek-chat"
RUN_ID = os.environ.get("LARGESTACK_DEEPSEEK_BUILD_RUN_ID") or datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
OUTDIR = ROOT / "release_evidence" / "deepseek_build_projects_live" / RUN_ID
PROJECTS_DIR = OUTDIR / "projects"


@dataclass
class BuildRecord:
    name: str
    passed: bool
    project_path: str
    generated_files: list[str]
    compile_passed: bool
    pytest_passed: bool
    acceptance_passed: bool
    json_valid: bool
    trace_id: str
    tokens: int
    actual_cost: float
    estimated_cost: float
    attempts: int
    validation_output: str
    acceptance_output: str
    notes: str
    repair_history: list[str]


PROJECT_SPECS = {
    "jarvis_core": {
        "requirements": (
            "Create a stdlib-only Python Jarvis core. Public API must be class JarvisCore(db_path=':memory:') "
            "with methods remember(key, value), recall(key), plan_day(tasks), decide_action(action, payload). "
            "remember must serialize and retrieve arbitrary JSON-like Python values including dicts. "
            "plan_day(['code']) must return a list whose first item is a dict containing {'task':'code'}. "
            "Risky actions send_email, move_file, delete_file, publish_social, refund_payment, write_production "
            "must return {'decision':'require_approval','executed':False}. Include pytest tests."
        ),
        "acceptance": "from jarvis_core import JarvisCore\nj=JarvisCore(':memory:')\nj.remember('prefs', {'focus':'maker'})\nassert j.recall('prefs')['focus']=='maker'\nassert j.plan_day(['code'])[0]['task']=='code'\nassert j.decide_action('send_email', {'to':'x@example.com'})['executed'] is False\n",
    },
    "support_ticket_api": {
        "requirements": (
            "Create stdlib-only support_ticket.py. Public function handle_ticket(text) returns dict with category, "
            "approval_required, sop, response. Duplicate payment/refund must be category refund and approval_required True. "
            "Any refund or payment request must require approval; do not create a first-refund exception. "
            "Login reset must mention identity verification. Include pytest tests that match these rules."
        ),
        "acceptance": "from support_ticket import handle_ticket\nr=handle_ticket('duplicate payment refund')\nassert r['category']=='refund' and r['approval_required'] is True\nassert 'identity' in handle_ticket('login reset not working')['response'].lower()\n",
    },
    "rag_assistant": {
        "requirements": (
            "Create stdlib-only RAG assistant with docs/refund_policy.md and docs/security_policy.md. Public function "
            "answer(query, docs_dir='docs') returns {'answer': str, 'citations': list}. Duplicate payments must cite "
            "refund_policy.md and the answer must contain the word approval. docs/refund_policy.md must include the exact "
            "policy meaning: Duplicate payments require approval before refund. Unknown equity refresh policy must return "
            "Insufficient evidence and no citations. Use a relevance threshold to avoid matching only the word policy. "
            "docs/security_policy.md should describe account protection and access controls. "
            "Treat weak generic words like policy, equity, and refresh as low-value relevance terms. Include pytest tests."
        ),
        "acceptance": "from rag_assistant import answer\nr=answer('duplicate payments require what?', 'docs')\nassert 'refund_policy.md' in r['citations'] and 'approval' in r['answer'].lower()\nu=answer('equity refresh policy', 'docs')\nassert 'insufficient evidence' in u['answer'].lower() and u['citations']==[]\n",
    },
    "task_app": {
        "requirements": (
            "Create stdlib-only backend/app.py with functions create_task(title, owner='user'), list_tasks(owner=None), "
            "complete_task(task_id), health(). complete_task must return a dict with key done set to True, not only completed. "
            "health() must return exactly {'status':'ok'} with no done key. Include frontend/index.html and pytest tests. Empty title raises ValueError."
        ),
        "acceptance": "from backend.app import create_task, list_tasks, complete_task, health\nt=create_task('ship tests', owner='qa')\nassert t['id']>=1 and list_tasks('qa')\nassert complete_task(t['id'])['done'] is True\nassert health()['status']=='ok'\n",
    },
    "code_reviewer": {
        "requirements": (
            "Create stdlib-only code_reviewer.py with find_issues(source) and suggest_patch(source). It must detect "
            "hardcoded secrets like PASSWORD = 'changeme' and SQL f-string formatting. find_issues must return a list of "
            "string issue codes including exactly 'hardcoded_secret' and 'sql_string_formatting' when those issues exist. "
            "suggest_patch(\"PASSWORD = 'changeme'\") must return text containing APP_PASSWORD. For SQL f-strings with "
            "multiple interpolations, replace each interpolation with a ? placeholder. Include pytest tests."
        ),
        "acceptance": "from code_reviewer import find_issues, suggest_patch\nsrc=\"PASSWORD = 'changeme'\\nquery = f\\\"select * from users where id={user_id}\\\"\"\nissues=find_issues(src)\nassert 'hardcoded_secret' in issues and 'sql_string_formatting' in issues\nassert 'APP_PASSWORD' in suggest_patch(\"PASSWORD = 'changeme'\")\n",
    },
    "ml_automation": {
        "requirements": (
            "Create stdlib-only ml_automation.py with detect_task(rows, target) and baseline(rows, target). "
            "baseline must always return a dict, never a tuple. Classification returns keys task, accuracy, majority_class_rate. "
            "Regression returns keys task, mae, baseline_prediction. "
            "Rows are list[dict] and target is a string key. Numeric-looking strings must be converted to numbers. "
            "If all target values are numeric and there are more than 2 unique target values, detect_task must return regression. "
            "If target values are nonnumeric labels, detect_task must return classification. "
            "For a single regression row, baseline_prediction is that value and mae is 0.0. "
            "Include pytest tests."
        ),
        "acceptance": "from ml_automation import detect_task, baseline\nrows=[{'x':str(i),'label':'yes' if i>5 else 'no'} for i in range(10)]\nr=baseline(rows,'label')\nassert r['task']=='classification' and 'accuracy' in r\nreg=[{'x':str(i),'y':str(i*2)} for i in range(10)]\nassert detect_task(reg,'y')=='regression' and 'mae' in baseline(reg,'y')\n",
    },
    "website_builder": {
        "requirements": (
            "Create a static website project for an AI Security Gateway. Include index.html, README.md, and pytest tests. "
            "The page must contain the text AI Security Gateway, a hero section, a trust section, and a Request demo CTA."
        ),
        "acceptance": "from pathlib import Path\nhtml=Path('index.html').read_text().lower()\nassert 'ai security gateway' in html\nassert 'hero' in html and 'trust' in html\nassert 'request demo' in html\n",
    },
    "resume_builder": {
        "requirements": (
            "Create stdlib-only resume_builder.py with build_resume(profile) returning (markdown, metadata). "
            "For role data analyst always include SQL, Excel, dashboards, statistics in the markdown even when profile skills are missing. "
            "metadata['ats_score'] must be a positive number greater than 0. "
            "If no employment is supplied, explicitly say not to fabricate employers. Include pytest tests."
        ),
        "acceptance": "from resume_builder import build_resume\nmd, meta=build_resume({'name':'A','role':'data analyst'})\nassert 'SQL' in md and 'Excel' in md\nassert 'fabricate' in md.lower()\nassert meta['ats_score'] > 0\n",
    },
    "hr_interview": {
        "requirements": (
            "Create stdlib-only hr_interview.py with generate_questions(role) and score_answer(answer). "
            "Generate at least three role-aware questions. score_answer must include rubric, score, fairness_warning True, "
            "and recommendation containing recommend for next round. Do not include the words final hire in the recommendation. "
            "Include pytest tests."
        ),
        "acceptance": "from hr_interview import generate_questions, score_answer\nassert len(generate_questions('QA engineer')) >= 3\nr=score_answer('I tested APIs and improved automation quality.')\nassert r['fairness_warning'] is True\nassert 'next round' in r['recommendation'].lower() and 'final hire' not in r['recommendation'].lower()\n",
    },
    "video_social_pipeline": {
        "requirements": (
            "Create stdlib-only video_social.py with make_script(prompt), route_model(prompt), publish_decision(). "
            "make_script returns script and 3-step storyboard. route_model returns mock-video-fast for short/reel prompts. publish_decision requires approval and executed False. Include pytest tests."
        ),
        "acceptance": "from video_social import make_script, route_model, publish_decision\nr=make_script('product short')\nassert r['script'] and len(r['storyboard']) >= 3\nassert route_model('instagram reel') == 'mock-video-fast'\nassert publish_decision()['executed'] is False\n",
    },
}


def selected_project_specs() -> dict[str, dict[str, str]]:
    """Return the requested project subset, preserving PROJECT_SPECS order."""
    raw = os.environ.get("LARGESTACK_DEEPSEEK_PROJECTS", "").strip()
    if not raw:
        return PROJECT_SPECS
    requested = [item.strip() for item in raw.split(",") if item.strip()]
    unknown = [name for name in requested if name not in PROJECT_SPECS]
    if unknown:
        raise SystemExit(f"Unknown project names in LARGESTACK_DEEPSEEK_PROJECTS: {', '.join(unknown)}")
    wanted = set(requested)
    return {name: spec for name, spec in PROJECT_SPECS.items() if name in wanted}


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def write_json(path: Path, data: Any) -> None:
    write(path, json.dumps(data, indent=2, sort_keys=True))


def extract_json(text: str) -> dict[str, Any] | None:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    candidates = [cleaned]
    match = re.search(r"\{.*\}", cleaned, re.S)
    if match:
        candidates.append(match.group(0))
    for item in candidates:
        try:
            data = json.loads(item)
            if isinstance(data, dict) and isinstance(data.get("files"), list):
                return data
        except json.JSONDecodeError:
            pass
    return None


async def build_project(agent: Agent, name: str, requirements: str, feedback: str = "") -> tuple[dict[str, Any] | None, Any, int]:
    prompt = f"""
Generate a complete small project named {name}.

Requirements:
{requirements}

Previous validation feedback to fix:
{feedback or "None. This is the first attempt."}

Return ONLY valid JSON, no markdown, with this schema:
{{
  "notes": "short note",
  "files": [
    {{"path": "relative/path.py", "content": "complete file content"}}
  ]
}}

Rules:
- Use Python standard library only.
- Include tests under tests/test_*.py.
- Do not include API keys or secrets.
- Do not use network calls.
- Keep each file concise.
- Make the public API exactly match the requirements.
- If feedback mentions a hidden acceptance failure, infer the intended behavior and fix it.
"""
    attempts = 0
    last = None
    data = None
    for _ in range(2):
        attempts += 1
        result = await agent.run(prompt if last is None else f"Fix this into valid JSON only:\n{last.content[:6000]}", timeout=150, temperature=0.1, max_tokens=1800)
        last = result
        data = extract_json(result.content)
        if data:
            return data, result, attempts
    return None, last, attempts


class FailedRunResult:
    def __init__(self, error: Exception):
        self.content = ""
        self.trace_id = ""
        self.total_tokens = 0
        self.total_cost = 0.0
        self.error = f"{type(error).__name__}: {error}"


def validate_project(project_path: Path, acceptance_code: str) -> tuple[bool, bool, bool, str, str]:
    compile_ok, compile_out = compile_project(project_path)
    pytest_out = run_pytest(project_path)
    accept_out = run_acceptance(project_path, acceptance_code)
    validation = compile_out + "\n" + pytest_out["stdout"]
    return compile_ok, pytest_out["returncode"] == 0, accept_out["returncode"] == 0, validation, accept_out["stdout"]


def feedback_from_failure(
    *,
    json_valid: bool,
    files: list[str],
    compile_ok: bool,
    pytest_ok: bool,
    acceptance_ok: bool,
    validation: str,
    acceptance: str,
) -> str:
    bits = []
    if not json_valid:
        bits.append("The previous response was not valid JSON with a files list.")
    if not files:
        bits.append("No usable project files were generated.")
    if not compile_ok:
        bits.append("Python compile failed.")
    if not pytest_ok:
        bits.append("Generated pytest tests failed.")
    if not acceptance_ok:
        bits.append("Hidden acceptance checks failed. Match the public API and behavior exactly.")
    bits.append("Validation output:\n" + validation[-2500:])
    bits.append("Hidden acceptance output:\n" + acceptance[-1200:])
    return "\n\n".join(bits)


def save_generated(project_path: Path, data: dict[str, Any]) -> list[str]:
    files = []
    for item in data.get("files", []):
        rel = str(item.get("path", "")).strip().replace("\\", "/")
        if not rel or rel.startswith("/") or ".." in Path(rel).parts:
            continue
        content = str(item.get("content", ""))
        target = project_path / rel
        write(target, content)
        files.append(rel)
    return sorted(files)


def compile_project(path: Path) -> tuple[bool, str]:
    ok = True
    lines = []
    for file in sorted(path.rglob("*.py")):
        if "__pycache__" in file.parts:
            continue
        try:
            py_compile.compile(str(file), doraise=True)
            lines.append(f"compile ok {file.relative_to(path)}")
        except Exception as exc:
            ok = False
            lines.append(f"compile fail {file.relative_to(path)}: {exc}")
    return ok, "\n".join(lines)


def run_cmd(cmd: list[str], cwd: Path, timeout: int = 60) -> dict[str, Any]:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(cwd)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    p = subprocess.run(cmd, cwd=cwd, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout, check=False)
    return {"returncode": p.returncode, "stdout": p.stdout[-5000:]}


def run_pytest(path: Path) -> dict[str, Any]:
    if not (path / "tests").exists():
        return {"returncode": 1, "stdout": "missing tests directory"}
    return run_cmd([sys.executable, "-m", "pytest", "tests", "-q", "--tb=short"], path, timeout=90)


def run_acceptance(path: Path, code: str) -> dict[str, Any]:
    return run_cmd([sys.executable, "-c", code], path, timeout=30)


def estimate_cost(tokens: int) -> float:
    tracker = CostTracker()
    inp = max(tokens // 2, 1)
    out = max(tokens - inp, 1)
    return tracker.calc("deepseek-chat", inp, out)


def summarize_record(record: BuildRecord) -> str:
    return "\n".join(
        [
            f"# {record.name}",
            "",
            f"- Status: `{'PASS' if record.passed else 'FAIL'}`",
            f"- Trace ID: `{record.trace_id}`",
            f"- Attempts: `{record.attempts}`",
            f"- Generated files: `{len(record.generated_files)}`",
            f"- Compile: `{record.compile_passed}`",
            f"- Pytest: `{record.pytest_passed}`",
            f"- Acceptance: `{record.acceptance_passed}`",
            f"- Tokens: `{record.tokens}`",
            f"- Estimated cost: `${record.estimated_cost}`",
            "",
            "## Files",
            *[f"- `{file}`" for file in record.generated_files],
            "",
            "## Validation Output",
            "```text",
            record.validation_output[-3000:],
            "```",
            "",
            "## Acceptance Output",
            "```text",
            record.acceptance_output[-3000:],
            "```",
        "",
        "## Model Notes",
        record.notes,
        "",
        "## Repair History",
        *[f"- {item}" for item in record.repair_history],
    ]
    )


async def main_async() -> int:
    OUTDIR.mkdir(parents=True, exist_ok=True)
    PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
    key = os.environ.get("LARGESTACK_DEEPSEEK_API_KEY", "")
    print("DeepSeek Build Projects Live")
    print(f"OUTDIR={OUTDIR}")
    print(f"DEEPSEEK_KEY_LENGTH={len(key)}")
    if not key:
        print("ERROR: LARGESTACK_DEEPSEEK_API_KEY is required.")
        return 2

    agent = Agent(
        name="deepseek_project_builder",
        llm=MODEL,
        instructions="You are a careful senior Python developer. Return exact JSON only when asked.",
        cost_budget=1.0,
        max_turns=3,
        memory=NoOpMemory(),
    )
    monitor = Monitor()
    records: list[Any] = []
    started = time.monotonic()
    try:
        specs = selected_project_specs()
        print("PROJECTS=" + ",".join(specs))
        for name, spec in specs.items():
            project_path = PROJECTS_DIR / name
            if project_path.exists():
                shutil.rmtree(project_path)
            builder = AutonomousProjectBuilder(
                agent,
                budget=BuilderBudget(max_attempts=4, max_tokens=300_000, max_seconds=600, cost_budget=1.0),
            )
            project_spec = ProjectSpec(
                name=name,
                requirements=spec["requirements"],
                acceptance=spec["acceptance"],
                required_files=["tests/test_*.py"],
                forbidden_actions=["network", "secrets", "payments", "email_send", "social_publish"],
                evidence_required=["input", "generated_files", "validation", "acceptance", "repair_attempts"],
            )
            record = await builder.build(project_spec, project_path)
            record.project_path = str(project_path.relative_to(OUTDIR))
            records.append(record)
            write_json(OUTDIR / f"{name}.json", serialize_report(record))
            write(OUTDIR / f"{name}.md", summarize_report(record))
            print(
                f"[{len(records):02d}] {'PASS' if record.passed else 'FAIL'} {name} "
                f"files={len(record.generated_files)} attempts={len(record.attempts)} traces={len(record.trace_ids)}"
            )
    finally:
        await agent.aclose()

    passed = sum(1 for r in records if r.passed)
    summary = {
        "run_id": RUN_ID,
        "classification": "DEEPSEEK-BUILT-PROJECTS+LARGESTACK-LIVE",
        "total_projects": len(records),
        "passed": passed,
        "failed": len(records) - passed,
        "score": round((passed / max(len(records), 1)) * 100),
        "duration_seconds": round(time.monotonic() - started, 2),
        "deepseek_builds": sum(1 for r in records if r.trace_ids),
        "total_tokens": sum(r.tokens for r in records),
        "actual_cost_total": round(sum(r.actual_cost for r in records), 8),
        "estimated_cost_total": round(sum(r.estimated_cost for r in records), 8),
        "monitor_summary": monitor.summary(limit=50),
        "records": [serialize_report(r) for r in records],
        "strict_notes": [
            "Project implementations were generated or repaired by DeepSeek through Largestack Agent.",
            "The harness only saved generated files, ran validation, and fed failure summaries back for repair.",
            "Hidden acceptance checks were written by the tester and not provided as source code to the model.",
        ],
    }
    write_json(OUTDIR / "summary.json", summary)
    summary_md = summary_markdown(summary)
    write(OUTDIR / "SUMMARY.md", summary_md)
    write(ROOT / "release_evidence" / "DEEPSEEK_BUILD_PROJECTS_LATEST.md", summary_md)
    print(summary_md)
    return 0 if summary["score"] >= 90 else 1


def summary_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "# DeepSeek Build Projects Live Summary",
        "",
        f"- Classification: `{summary['classification']}`",
        f"- Total projects: `{summary['total_projects']}`",
        f"- Passed: `{summary['passed']}`",
        f"- Failed: `{summary['failed']}`",
        f"- Score: `{summary['score']}/100`",
        f"- DeepSeek/Largestack builds: `{summary['deepseek_builds']}`",
        f"- Total tokens: `{summary['total_tokens']}`",
        f"- Actual framework cost total: `${summary['actual_cost_total']}`",
        f"- Estimated DeepSeek cost total: `${summary['estimated_cost_total']}`",
        f"- Duration: `{summary['duration_seconds']}s`",
        "",
        "## Project Results",
    ]
    for r in summary["records"]:
        validation = r["validation"]
        lines.append(
            f"- `{'PASS' if r['passed'] else 'FAIL'}` {r['name']} "
            f"files={len(r['generated_files'])} attempts={len(r['attempts'])} "
            f"compile={validation['compile_passed']} pytest={validation['pytest_passed']} "
            f"acceptance={validation['acceptance_passed']} budget_exceeded={r['budget_exceeded']}"
        )
    lines.extend(
        [
            "",
            "## Strict Review",
            "- This is the strongest build test so far: DeepSeek generated the project code through Largestack, and hidden acceptance checks validated the public APIs.",
            "- Passing here proves bounded multi-project generation, not production readiness.",
            "- Still missing for production: real connectors, encrypted persistent memory, vector RAG, HITL UI, load testing, deployment hardening, browser/a11y testing, and long-running autonomous repair.",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    os.environ.setdefault("LARGESTACK_GUARDRAIL_MODE", "protect")
    os.environ.setdefault("LARGESTACK_CONTEXT", "planning")
    return asyncio.run(main_async())


if __name__ == "__main__":
    raise SystemExit(main())
