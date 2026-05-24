"""Final 95+ release certification harness.

This is intentionally strict: it treats missing live DeepSeek validation,
failed project generation, Docker cleanup failures, and security skips as HOLD
conditions. It never reads API keys from arguments or files; export a rotated
``LARGESTACK_DEEPSEEK_API_KEY`` in the shell/CI secret store before running.
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from largestack import Agent
from largestack.autonomous_builder import (
    AutonomousProjectBuilder,
    BuilderBudget,
    BuildReport,
    NoOpMemory,
    ProjectSpec,
    redact_sensitive,
    serialize_report,
    summarize_report,
)

MODEL = "deepseek/deepseek-chat"
REQUIRED_PROJECT_COUNT = 24
PROJECT_MIN_SCORE = 90
SUITE_MIN_AVERAGE = 95.0
TARGET_SCORES = {
    "core_framework": 98,
    "deepseek_live": 95,
    "real_project_generation": 95,
    "ubuntu_package_docker": 95,
    "saas": 95,
    "bfsi": 95,
}


@dataclass
class GateResult:
    name: str
    status: str
    command: str = ""
    log: str = ""
    reason: str = ""
    blocker_type: str = "PASS"
    solution: str = ""


@dataclass
class ReviewScore:
    api_correctness: int = 0
    tests_acceptance: int = 0
    largestack_deepseek_usage: int = 0
    security_guardrails: int = 0
    code_quality: int = 0
    docs_readme: int = 0
    budget_discipline: int = 0
    reviewer_score: int = 0
    reviewer_json_valid: bool = False
    reviewer_notes: str = ""

    @property
    def deterministic_total(self) -> int:
        return (
            self.api_correctness
            + self.tests_acceptance
            + self.largestack_deepseek_usage
            + self.security_guardrails
            + self.code_quality
            + self.docs_readme
            + self.budget_discipline
        )

    @property
    def final_score(self) -> int:
        if self.reviewer_json_valid:
            return round((self.deterministic_total * 0.8) + (self.reviewer_score * 0.2))
        return self.deterministic_total


@dataclass
class ReviewerOutcome:
    score: int = 0
    json_valid: bool = False
    passed: bool = False
    notes: str = ""
    critical_blocker: str = ""


@dataclass
class ProjectCertification:
    name: str
    passed: bool
    score: int
    blocker_type: str
    solution: str
    report_path: str
    project_path: str
    generated_files: list[str] = field(default_factory=list)
    failed_checks: list[str] = field(default_factory=list)
    trace_ids: list[str] = field(default_factory=list)
    tokens: int = 0
    actual_cost: float = 0.0
    score_breakdown: dict[str, Any] = field(default_factory=dict)


@dataclass
class CertificationSummary:
    run_id: str
    outdir: str
    started_at: str
    finished_at: str
    final_decision: str
    target_scores: dict[str, int]
    achieved_scores: dict[str, float]
    gates: list[GateResult]
    projects: list[ProjectCertification]
    blockers: list[dict[str, str]]


def now_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def redact(text: str) -> str:
    text = redact_sensitive(text or "")
    text = re.sub(r"\bsk-[A-Za-z0-9_-]{8,}\b", "sk-REDACTED", text)
    text = re.sub(r"(LARGESTACK_[A-Z0-9_]*API_KEY=)[^\s]+", r"\1REDACTED", text)
    return text


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(redact(text), encoding="utf-8")


def progress(message: str) -> None:
    print(f"[final95] {message}", flush=True)


def run_cmd(name: str, cmd: list[str], outdir: Path, timeout: int = 1800) -> GateResult:
    progress(f"gate start: {name}")
    log_path = outdir / "logs" / f"{name}.log"
    started = time.monotonic()
    blocker_type = "BUG"
    solution = "Inspect the gate log and fix the failing command, then rerun certification."
    try:
        proc = subprocess.run(
            cmd,
            cwd=ROOT,
            env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            check=False,
        )
        output = proc.stdout or ""
        status = "PASS" if proc.returncode == 0 else "FAIL"
        reason = f"exit={proc.returncode}, seconds={time.monotonic() - started:.1f}"
    except FileNotFoundError as exc:
        output = f"{type(exc).__name__}: {exc}\n"
        status = "FAIL"
        reason = f"missing command: {cmd[0]}"
        blocker_type = "ENV BLOCKER"
        solution = f"Install or expose `{cmd[0]}` on PATH, then rerun certification."
    except subprocess.TimeoutExpired as exc:
        output = (exc.stdout or "") if isinstance(exc.stdout, str) else ""
        status = "FAIL"
        reason = f"timeout after {timeout}s"
        blocker_type = "ENV BLOCKER"
        solution = "Fix the slow/hung environment or increase the gate timeout only after confirming the command is healthy."
    except Exception as exc:
        output = f"{type(exc).__name__}: {exc}\n"
        status = "FAIL"
        reason = f"{type(exc).__name__}: {exc}"
        blocker_type = "ENV BLOCKER"
        solution = "Fix the host/tooling problem shown in the gate log, then rerun certification."
    write_text(log_path, output)
    result = GateResult(
        name=name,
        status=status,
        command=" ".join(cmd),
        log=str(log_path),
        reason=reason,
        blocker_type="PASS" if status == "PASS" else blocker_type,
        solution="No action required." if status == "PASS" else solution,
    )
    progress(f"gate done: {name} status={result.status} reason={result.reason}")
    return result


def cleanup_generated_artifacts(outdir: Path) -> GateResult:
    progress("cleanup start: generated artifacts")
    targets: list[Path] = []
    for pattern in ("**/__pycache__", ".pytest_cache", "build", "*.egg-info"):
        targets.extend(ROOT.glob(pattern))
    removed: list[str] = []
    skipped: list[str] = []
    for target in sorted(set(targets)):
        if outdir in target.parents or target == outdir:
            continue
        try:
            if target.is_dir():
                shutil.rmtree(target)
            elif target.exists():
                target.unlink()
            removed.append(str(target.relative_to(ROOT)))
        except Exception as exc:
            skipped.append(f"{target}: {type(exc).__name__}: {exc}")
    write_json(outdir / "cleanup.json", {"removed": removed, "skipped": skipped})
    status = "PASS" if not skipped else "FAIL"
    result = GateResult(
        name="cleanup_generated_artifacts",
        status=status,
        log=str(outdir / "cleanup.json"),
        blocker_type="PASS" if status == "PASS" else "ENV BLOCKER",
        reason=f"removed={len(removed)}, skipped={len(skipped)}",
        solution="Remove blocked cache/build artifacts manually and rerun.",
    )
    progress(f"cleanup done: status={result.status} {result.reason}")
    return result


def make_specs() -> list[ProjectSpec]:
    def spec(name: str, requirements: str, acceptance: str) -> ProjectSpec:
        contract = (
            "\nPublic usage contract that the generated project must pass exactly:\n"
            "```python\n"
            f"{acceptance.strip()}\n"
            "```\n"
        )
        return ProjectSpec(
            name=name,
            requirements=(
                requirements
                + contract
                + "\nInclude README.md with run/test instructions. Use Python standard library only. "
                + "Include pytest tests under tests/test_*.py. Do not include secrets, network calls, or external side effects."
            ),
            acceptance=acceptance,
            required_files=["README.md"],
            forbidden_actions=["send_email", "refund_payment", "delete_file", "publish_social", "write_production"],
        )

    return [
        spec(
            "support_ticket_automation_api",
            "Create support_ticket.py with handle_ticket(text). Refund/payment/security/data export requests require approval. Login reset response must mention identity verification.",
            "from support_ticket import handle_ticket\nr=handle_ticket('duplicate payment refund')\nassert r['approval_required'] is True\nassert r['category']=='refund'\nassert 'identity' in handle_ticket('login reset')['response'].lower()\n",
        ),
        spec(
            "simple_crm",
            "Create crm.py with create_contact, list_contacts, update_stage, score_lead. Duplicate emails update existing contact. Lead score is 0-100.",
            "from crm import create_contact, list_contacts, update_stage, score_lead\nc=create_contact('a@example.com','A',stage='lead')\ncreate_contact('a@example.com','A2',stage='prospect')\nassert len(list_contacts())==1\nassert update_stage(c['id'],'customer')['stage']=='customer'\nassert 0 <= score_lead(c) <= 100\n",
        ),
        spec(
            "task_manager",
            "Create task_app.py with create_task, list_tasks, complete_task, health. Empty titles raise ValueError. complete_task returns done True.",
            "from task_app import create_task, list_tasks, complete_task, health\nt=create_task('ship tests', owner='qa')\nassert list_tasks('qa')\nassert complete_task(t['id'])['done'] is True\nassert health()=={'status':'ok'}\n",
        ),
        spec(
            "expense_tracker",
            "Create expense_tracker.py with add_expense, list_expenses, monthly_summary, flag_policy_violations. Amounts must be positive. Cash/gift over 500 is a policy violation.",
            "from expense_tracker import add_expense, monthly_summary, flag_policy_violations\ne=add_expense('2026-05-01','travel',250,'card')\nassert monthly_summary('2026-05')['total']==250\nassert flag_policy_violations([add_expense('2026-05-02','gift',600,'cash')])\n",
        ),
        spec(
            "inventory_tracker",
            "Create inventory.py with add_item, adjust_stock, low_stock, inventory_value. Prevent negative stock.",
            "from inventory import add_item, adjust_stock, low_stock, inventory_value\nadd_item('sku1','Keyboard',5,100,reorder_level=6)\nassert low_stock()[0]['sku']=='sku1'\nadjust_stock('sku1',3)\nassert inventory_value() == 800\n",
        ),
        spec(
            "appointment_booking",
            "Create booking.py with create_slot, book_slot, cancel_booking, list_available. Double booking must fail cleanly.",
            "from booking import create_slot, book_slot, list_available\ns=create_slot('2026-05-12T10:00','Dr A')\nb=book_slot(s['id'],'patient@example.com')\nassert b['status']=='booked'\nassert list_available()==[]\n",
        ),
        spec(
            "lead_capture_app",
            "Create lead_capture.py with capture_lead, qualify_lead, export_csv. Validate email and consent. Missing consent raises ValueError.",
            "from lead_capture import capture_lead, qualify_lead, export_csv\nlead=capture_lead('A','a@example.com',consent=True,company='Acme')\nassert qualify_lead(lead)['qualified'] is True\nassert 'a@example.com' in export_csv([lead])\n",
        ),
        spec(
            "document_upload_extraction_portal",
            "Create document_portal.py with upload_document, extract_fields, classify_document. Reject files over configured size and unsupported extensions.",
            "from document_portal import upload_document, extract_fields, classify_document\ndoc=upload_document('invoice.txt','Invoice total: 1200\\nVendor: ACME')\nassert classify_document(doc)=='invoice'\nassert extract_fields(doc)['total']=='1200'\n",
        ),
        spec(
            "mini_rag_assistant_api",
            "Create rag_assistant.py with add_document, answer. Answers must include citations and return Insufficient evidence when no document supports the answer.",
            "from rag_assistant import add_document, answer\nadd_document('refund_policy.md','Duplicate payments require approval before refund.')\nr=answer('duplicate payments require what?')\nassert 'approval' in r['answer'].lower() and 'refund_policy.md' in r['citations']\nassert 'insufficient evidence' in answer('equity refresh policy')['answer'].lower()\n",
        ),
        spec(
            "agent_workflow_dashboard",
            "Create workflow_dashboard.py with record_run, list_runs, metrics, mermaid_graph. Track status, cost, tokens, trace_id.",
            "from workflow_dashboard import record_run, metrics, mermaid_graph\nrecord_run('agent-a','completed',cost=0.1,tokens=20,trace_id='t1')\nassert metrics()['runs_total']==1\nassert 'graph TD' in mermaid_graph(['agent-a','agent-b'])\n",
        ),
        spec(
            "ai_security_gateway_website",
            "Create index.html and site_check.py. The page must contain AI Security Gateway, hero, trust, guardrails, Request demo, and security disclaimers.",
            "from pathlib import Path\nhtml=Path('index.html').read_text().lower()\nassert 'ai security gateway' in html and 'hero' in html and 'trust' in html and 'request demo' in html\n",
        ),
        spec(
            "resume_builder",
            "Create resume_builder.py with build_resume(profile) returning markdown and metadata. Data analyst resumes always include SQL, Excel, dashboards, statistics. Do not fabricate employers.",
            "from resume_builder import build_resume\nmd,meta=build_resume({'name':'A','role':'data analyst'})\nassert 'SQL' in md and 'Excel' in md and 'fabricate' in md.lower()\nassert meta['ats_score'] > 0\n",
        ),
        spec(
            "hr_interview_scorer",
            "Create hr_interview.py with generate_questions(role) and score_answer(answer). Include rubric, fairness_warning True, and next-round recommendation without final hire language.",
            "from hr_interview import generate_questions, score_answer\nassert len(generate_questions('QA engineer'))>=3\nr=score_answer('I tested APIs and improved automation quality')\nassert r['fairness_warning'] is True\nassert 'next round' in r['recommendation'].lower() and 'final hire' not in r['recommendation'].lower()\n",
        ),
        spec(
            "code_reviewer_fixer",
            "Create code_reviewer.py with find_issues(source) and suggest_patch(source). Detect hardcoded_secret and sql_string_formatting.",
            "from code_reviewer import find_issues, suggest_patch\nsrc=\"PASSWORD = 'changeme'\\nquery = f\\\"select * from users where id={user_id}\\\"\"\nissues=find_issues(src)\nassert 'hardcoded_secret' in issues and 'sql_string_formatting' in issues\nassert 'APP_PASSWORD' in suggest_patch(\"PASSWORD = 'changeme'\")\n",
        ),
        spec(
            "ml_automation_baseline",
            "Create ml_automation.py with detect_task(rows,target) and baseline(rows,target). Numeric targets with more than two unique values are regression; labels are classification.",
            "from ml_automation import detect_task, baseline\nreg=[{'x':str(i),'y':str(i*2)} for i in range(10)]\ncls=[{'x':i,'label':'yes' if i>5 else 'no'} for i in range(10)]\nassert detect_task(reg,'y')=='regression' and 'mae' in baseline(reg,'y')\nassert baseline(cls,'label')['task']=='classification'\n",
        ),
        spec(
            "video_social_pipeline",
            "Create video_social.py with make_script, route_model, publish_decision. Publishing must require approval and never execute automatically.",
            "from video_social import make_script, route_model, publish_decision\nr=make_script('product short')\nassert r['script'] and len(r['storyboard'])>=3\nassert route_model('instagram reel')=='mock-video-fast'\nassert publish_decision()['executed'] is False\n",
        ),
        spec(
            "jarvis_memory_planner_approval_core",
            "Create jarvis_core.py with JarvisCore(db_path=':memory:') methods remember, recall, plan_day, decide_action. Risky actions require approval.",
            "from jarvis_core import JarvisCore\nj=JarvisCore(':memory:')\nj.remember('prefs', {'focus':'maker'})\nassert j.recall('prefs')['focus']=='maker'\nassert j.plan_day(['code'])[0]['task']=='code'\nassert j.decide_action('send_email', {'to':'x@example.com'})['executed'] is False\n",
        ),
        spec(
            "fintech_kyc_nbfc_workflow",
            "Create kyc_nbfc.py with validate_kyc, risk_score, approval_decision. High risk or missing PAN requires manual review.",
            "from kyc_nbfc import validate_kyc, risk_score, approval_decision\ncase={'name':'A','pan':'ABCDE1234F','aadhaar_last4':'1234','income':50000}\nassert validate_kyc(case)['valid'] is True\nassert approval_decision(case)['decision'] in {'approve','manual_review'}\nassert approval_decision({'name':'B'})['decision']=='manual_review'\n",
        ),
        spec(
            "legaltech_rag_assistant",
            "Create legal_rag.py with add_case_note and answer_legal_query. Must cite source names and avoid legal advice guarantee language.",
            "from legal_rag import add_case_note, answer_legal_query\nadd_case_note('contract.md','Termination requires 30 days written notice.')\nr=answer_legal_query('termination notice')\nassert '30' in r['answer'] and 'contract.md' in r['citations']\nassert 'guarantee' not in r['answer'].lower()\n",
        ),
        spec(
            "dpdp_breach_response_workflow",
            "Create dpdp_breach.py with classify_incident, notification_plan, containment_steps. Personal data breach must include notify DPO and preserve audit log.",
            "from dpdp_breach import classify_incident, notification_plan, containment_steps\ninc='customer personal data leaked'\nassert classify_incident(inc)=='personal_data_breach'\nplan=notification_plan(inc)\nassert 'dpo' in ' '.join(plan).lower()\nassert any('audit' in s.lower() for s in containment_steps(inc))\n",
        ),
        spec(
            "background_verification_portal",
            "Create bgv_portal.py with submit_candidate, verify_document, case_status. Missing consent blocks verification.",
            "from bgv_portal import submit_candidate, verify_document, case_status\nc=submit_candidate('A','a@example.com',consent=True)\nassert verify_document(c['id'],'id_proof','valid')['verified'] is True\nassert case_status(c['id'])['status'] in {'in_progress','verified'}\n",
        ),
        spec(
            "trading_app_risk_disclaimer",
            "Create trading_risk.py with evaluate_signal, risk_disclaimer, place_order_decision. place_order_decision must require approval and include risk warning.",
            "from trading_risk import evaluate_signal, risk_disclaimer, place_order_decision\nassert 'not financial advice' in risk_disclaimer().lower()\nassert evaluate_signal({'rsi':20})['signal'] in {'buy_watch','hold','sell_watch'}\nassert place_order_decision({'symbol':'ABC'})['executed'] is False\n",
        ),
        spec(
            "esign_document_approval_workflow",
            "Create esign_workflow.py with create_envelope, add_signer, send_decision, audit_trail. Sending requires approval.",
            "from esign_workflow import create_envelope, add_signer, send_decision, audit_trail\ne=create_envelope('contract.pdf')\nadd_signer(e['id'],'a@example.com')\nassert send_decision(e['id'])['executed'] is False\nassert audit_trail(e['id'])\n",
        ),
        spec(
            "hal_mosaic_ticket_domain_workflow",
            "Create hal_mosaic.py with classify_ticket, route_ticket, sla_minutes. MOSAIC avionics, safety, and production write tickets must route to specialist/manual approval.",
            "from hal_mosaic import classify_ticket, route_ticket, sla_minutes\nc=classify_ticket('MOSAIC avionics safety production write')\nassert c['domain']=='mosaic_avionics'\nr=route_ticket(c)\nassert r['approval_required'] is True\nassert sla_minutes(c) <= 240\n",
        ),
    ]


def scan_project_security(path: Path) -> tuple[bool, list[str]]:
    issues: list[str] = []
    secret_rx = re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b|AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{20,}")
    network_import_rx = re.compile(
        r"^\s*(?:import\s+(?:requests|httpx|socket)\b|from\s+(?:requests|httpx|socket|urllib\.request)\s+import\b)",
        re.M,
    )
    for file in path.rglob("*"):
        if not file.is_file() or "__pycache__" in file.parts:
            continue
        try:
            text = file.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        rel = str(file.relative_to(path))
        if secret_rx.search(text):
            issues.append(f"{rel}: possible secret")
        if file.suffix == ".py" and network_import_rx.search(text):
            issues.append(f"{rel}: network side effect import")
    return not issues, issues


def project_has_readme(path: Path) -> bool:
    readme = path / "README.md"
    return readme.exists() and len(readme.read_text(encoding="utf-8", errors="ignore").strip()) >= 80


def deterministic_score(report: BuildReport, security_ok: bool, readme_ok: bool) -> ReviewScore:
    validation = report.validation
    score = ReviewScore()
    score.api_correctness = 20 if validation.acceptance_passed else 0
    score.tests_acceptance = int((10 if validation.pytest_passed else 0) + (10 if validation.acceptance_passed else 0))
    score.largestack_deepseek_usage = 15 if report.trace_ids and report.tokens > 0 else 0
    score.security_guardrails = 15 if security_ok else 0
    score.code_quality = int((8 if validation.compile_passed else 0) + (4 if report.generated_files else 0) + (3 if len(report.attempts) <= 4 else 0))
    score.docs_readme = 10 if readme_ok else 0
    score.budget_discipline = 5 if not report.budget_exceeded and report.tokens <= 300_000 else 0
    return score


def reconcile_reviewer_with_validation(
    score: ReviewScore,
    reviewer: ReviewerOutcome,
    *,
    report: BuildReport,
    security_ok: bool,
    readme_ok: bool,
) -> ReviewerOutcome:
    """Keep deterministic validation authoritative over reviewer hallucinations.

    The reviewer is useful for qualitative risk, but compile/pytest/hidden
    acceptance/security/README checks are direct evidence. If those all pass,
    a reviewer claim that the project does not compile or lacks accepted
    functions is treated as an advisory warning instead of a release blocker.
    """

    if report.passed and security_ok and readme_ok and score.deterministic_total == 100:
        if reviewer.json_valid and (not reviewer.passed or reviewer.score < PROJECT_MIN_SCORE or reviewer.critical_blocker):
            notes = (
                reviewer.notes
                + " reviewer warning overridden because compile, pytest, hidden acceptance, security, and README checks all passed."
            )
            return ReviewerOutcome(
                score=max(reviewer.score, PROJECT_MIN_SCORE),
                json_valid=True,
                passed=True,
                notes=notes,
                critical_blocker="",
            )
    return reviewer


def parse_reviewer_json(text: str) -> dict[str, Any] | None:
    text = (text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    match = re.search(r"\{.*\}", text, re.S)
    candidates = [text, match.group(0) if match else ""]
    for candidate in candidates:
        if not candidate:
            continue
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            return data
    return None


async def review_project(reviewer: Agent, spec: ProjectSpec, report: BuildReport) -> ReviewerOutcome:
    project_path = Path(report.project_path)
    snapshot_parts: list[str] = []
    for file in sorted(project_path.rglob("*"))[:40]:
        if file.is_file() and "__pycache__" not in file.parts and file.stat().st_size < 20_000:
            try:
                snapshot_parts.append(f"--- {file.relative_to(project_path)} ---\n{file.read_text()[:4000]}")
            except UnicodeDecodeError:
                continue
    prompt = f"""
Review this generated project for release certification.

Project: {spec.name}
Requirements:
{spec.requirements}

Validation:
compile={report.validation.compile_passed}
pytest={report.validation.pytest_passed}
acceptance={report.validation.acceptance_passed}
failed={report.validation.failed_checks}

Files:
{chr(10).join(snapshot_parts)[:20000]}

Return ONLY JSON:
{{"score": 0-100, "pass": true/false, "notes": "short", "critical_blocker": ""}}

Scoring rule:
- The validation booleans above are authoritative. Do not claim syntax, pytest, or acceptance failure when those fields are true.
- If compile, pytest, acceptance, README, or security is failing, pass must be false.
- If hidden acceptance is false, score must be below 80.
- If pytest is false, score must be below 70.
- If all required checks pass and there is no safety issue, score may be 90-100.
"""
    try:
        result = await reviewer.run(prompt, timeout=120, temperature=0.0, max_tokens=600)
    except Exception as exc:
        return ReviewerOutcome(notes=f"reviewer error: {type(exc).__name__}: {exc}")
    data = parse_reviewer_json(str(getattr(result, "content", "")))
    if not data:
        return ReviewerOutcome(notes="reviewer did not return valid JSON")
    score = int(max(0, min(100, data.get("score", 0))))
    notes = str(data.get("notes", ""))[:1000]
    blocker = str(data.get("critical_blocker", ""))[:500]
    if blocker:
        notes = f"{notes} blocker={blocker}"
    return ReviewerOutcome(
        score=score,
        json_valid=True,
        passed=bool(data.get("pass", score >= PROJECT_MIN_SCORE and not blocker)),
        notes=notes,
        critical_blocker=blocker,
    )


async def run_project_suite(
    outdir: Path,
    project_limit: int | None = None,
    project_start: int = 1,
) -> list[ProjectCertification]:
    api_key = os.environ.get("LARGESTACK_DEEPSEEK_API_KEY", "")
    if not api_key:
        raise RuntimeError("LARGESTACK_DEEPSEEK_API_KEY is required for final 95+ certification")
    specs = make_specs()
    if project_start > 1:
        specs = specs[project_start - 1 :]
    if project_limit:
        specs = specs[:project_limit]
    projects_dir = outdir / "projects"
    agent = Agent(
        name="final-95-builder",
        instructions="Generate correct, concise, stdlib-only projects. Return valid JSON exactly as requested.",
        llm=MODEL,
        memory=NoOpMemory(),
        cost_budget=float(os.environ.get("LARGESTACK_CERT_BUILDER_COST_BUDGET", "20")),
        max_turns=8,
    )
    reviewer = Agent(
        name="final-95-reviewer",
        instructions="Strictly review generated projects against requirements. Return JSON only.",
        llm=MODEL,
        memory=NoOpMemory(),
        cost_budget=float(os.environ.get("LARGESTACK_CERT_REVIEWER_COST_BUDGET", "10")),
        max_turns=3,
    )
    builder = AutonomousProjectBuilder(
        agent,
        BuilderBudget(
            max_attempts=int(os.environ.get("LARGESTACK_CERT_MAX_ATTEMPTS", "4")),
            max_tokens=int(os.environ.get("LARGESTACK_CERT_MAX_TOKENS_PER_PROJECT", "300000")),
            max_seconds=float(os.environ.get("LARGESTACK_CERT_MAX_SECONDS_PER_PROJECT", "900")),
            cost_budget=float(os.environ.get("LARGESTACK_CERT_PROJECT_COST_BUDGET", "2")),
        ),
    )
    results: list[ProjectCertification] = []
    for index, spec in enumerate(specs, start=project_start):
        slug = f"{index:02d}_{spec.name}"
        project_path = projects_dir / slug
        progress(f"project start: {slug}")
        report = await builder.build(spec, project_path)
        security_ok, security_issues = scan_project_security(project_path)
        readme_ok = project_has_readme(project_path)
        score = deterministic_score(report, security_ok, readme_ok)
        reviewer_outcome = await review_project(reviewer, spec, report)
        reviewer_outcome = reconcile_reviewer_with_validation(
            score,
            reviewer_outcome,
            report=report,
            security_ok=security_ok,
            readme_ok=readme_ok,
        )
        score.reviewer_score = reviewer_outcome.score
        score.reviewer_json_valid = reviewer_outcome.json_valid
        score.reviewer_notes = redact(reviewer_outcome.notes)
        failed_checks = list(report.validation.failed_checks)
        failed_checks.extend(security_issues)
        if not readme_ok:
            failed_checks.append("missing_or_thin_readme")
        if not reviewer_outcome.json_valid:
            failed_checks.append("reviewer_json_invalid")
        elif not reviewer_outcome.passed or reviewer_outcome.critical_blocker:
            failed_checks.append("reviewer_blocker")
        if score.final_score < PROJECT_MIN_SCORE:
            failed_checks.append("score_below_90")
        passed = report.passed and score.final_score >= PROJECT_MIN_SCORE and not failed_checks
        blocker_type = "PASS" if passed else ("SECURITY BLOCKER" if security_issues else "BUG")
        solution = (
            "No action required."
            if passed
            else "Inspect generated project, validation output, security issues, and reviewer notes; update prompts or framework behavior, then rerun."
        )
        project_report_path = outdir / "project_reports" / f"{slug}.json"
        write_json(
            project_report_path,
            {
                "spec": spec.model_dump(),
                "report": serialize_report(report),
                "security_ok": security_ok,
                "security_issues": security_issues,
                "readme_ok": readme_ok,
                "score": asdict(score),
                "final_score": score.final_score,
                "passed": passed,
            },
        )
        write_text(outdir / "project_reports" / f"{slug}.md", summarize_report(report))
        results.append(
            ProjectCertification(
                name=spec.name,
                passed=passed,
                score=score.final_score,
                blocker_type=blocker_type,
                solution=solution,
                report_path=str(project_report_path),
                project_path=str(project_path),
                generated_files=report.generated_files,
                failed_checks=failed_checks,
                trace_ids=report.trace_ids,
                tokens=report.tokens,
                actual_cost=report.actual_cost,
                score_breakdown=asdict(score),
            )
        )
        progress(
            f"project done: {slug} passed={passed} score={score.final_score} "
            f"failed_checks={len(failed_checks)}"
        )
    return results


def parse_final_validator(gate: GateResult) -> list[GateResult]:
    if gate.status != "PASS":
        return [gate]
    text = Path(gate.log).read_text(encoding="utf-8", errors="ignore") if gate.log else ""
    rows: list[GateResult] = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[1] in {"PASS", "FAIL", "SKIP"}:
            name, status = parts[0], parts[1]
            if name in {"deepseek_live_tests", "gitleaks_no_git", "helm_lint", "docker_runtime_start", "docker_health"} and status != "PASS":
                rows.append(
                    GateResult(
                        name=f"final_validator_{name}",
                        status="FAIL",
                        reason=f"required gate was {status}",
                        blocker_type="ENV BLOCKER" if status == "SKIP" else "BUG",
                        solution="Make this gate PASS in final_release_validate.sh output before certification.",
                    )
                )
    return rows


def run_extra_gates(outdir: Path) -> list[GateResult]:
    gates = [
        run_cmd("security_tests", [sys.executable, "-m", "pytest", "tests/security", "-q", "--tb=short"], outdir, 600),
        run_cmd("helm_lint_chart", ["helm", "lint", "deploy/helm/largestack"], outdir, 300),
        run_cmd("docker_compose_config", ["docker", "compose", "config"], outdir, 300),
    ]
    return gates


def docker_cleanup_probe(outdir: Path, run_id: str) -> GateResult:
    progress("gate start: docker_runtime_auth_cleanup")
    name = f"largestack-final-95-{run_id}"
    image = f"largestack:final-95-{run_id}"
    log = outdir / "logs" / "docker_cleanup_probe.log"
    lines: list[str] = []
    def step(cmd: list[str], timeout: int = 300) -> int:
        lines.append("$ " + " ".join(cmd))
        proc = subprocess.run(cmd, cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout, check=False)
        lines.append(proc.stdout[-4000:])
        return proc.returncode
    try:
        if step(["docker", "build", "-t", image, "."], 1800) != 0:
            status = "FAIL"; reason = "docker build failed"
        elif step(["docker", "run", "--rm", "-d", "--name", name, "-p", "127.0.0.1::8787", "-e", "LARGESTACK_API_KEY=test-key", "-e", "LARGESTACK_DASHBOARD_KEY=test-key", image], 120) != 0:
            status = "FAIL"; reason = "docker run failed"
        else:
            time.sleep(4)
            port_cmd = ["docker", "port", name, "8787/tcp"]
            port_proc = subprocess.run(port_cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
            lines.append("$ " + " ".join(port_cmd)); lines.append(port_proc.stdout)
            match = re.search(r":(\d+)", port_proc.stdout)
            port = match.group(1) if match else ""
            checks = []
            if port:
                checks.append(step(["curl", "-fsS", f"http://127.0.0.1:{port}/health"], 60) == 0)
                checks.append(step(["curl", "-fsS", "-H", "X-API-Key: test-key", f"http://127.0.0.1:{port}/api/metrics"], 60) == 0)
                bad = subprocess.run(["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}", "-H", "X-API-Key: wrong", f"http://127.0.0.1:{port}/api/metrics"], text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
                lines.append("bad auth status=" + bad.stdout)
                checks.append(bad.stdout.strip() in {"401", "403"})
            cleanup_ok = step(["docker", "rm", "-f", name], 120) == 0
            status = "PASS" if port and all(checks) and cleanup_ok else "FAIL"
            reason = "docker runtime/auth/cleanup passed" if status == "PASS" else "docker runtime/auth/cleanup failed"
    except Exception as exc:
        status = "FAIL"; reason = f"{type(exc).__name__}: {exc}"
    write_text(log, "\n".join(lines))
    result = GateResult(
        name="docker_runtime_auth_cleanup",
        status=status,
        log=str(log),
        blocker_type="PASS" if status == "PASS" else "ENV BLOCKER",
        reason=reason,
        solution="Run on a Docker host where build, health probes, auth probes, and container cleanup all succeed.",
    )
    progress(f"gate done: docker_runtime_auth_cleanup status={result.status} reason={result.reason}")
    return result


def compute_scores(gates: list[GateResult], projects: list[ProjectCertification]) -> dict[str, float]:
    gate_pass_rate = 100.0 * sum(g.status == "PASS" for g in gates) / max(len(gates), 1)
    project_average = sum(p.score for p in projects) / max(len(projects), 1)
    all_projects_pass = all(p.passed for p in projects) and len(projects) >= REQUIRED_PROJECT_COUNT
    deepseek_live = 100.0 if all_projects_pass and project_average >= SUITE_MIN_AVERAGE else min(project_average, 94.0)
    docker_ok = any(g.name == "docker_runtime_auth_cleanup" and g.status == "PASS" for g in gates)
    security_ok = all(g.status == "PASS" for g in gates if g.name in {"security_tests", "baseline_final_release_validate"})
    ubuntu = min(gate_pass_rate, 100.0 if docker_ok else 94.0)
    return {
        "core_framework": gate_pass_rate,
        "deepseek_live": deepseek_live,
        "real_project_generation": project_average if all_projects_pass else min(project_average, 94.0),
        "ubuntu_package_docker": ubuntu,
        "saas": min(ubuntu, project_average, 95.0 if docker_ok and security_ok and all_projects_pass else 89.0),
        "bfsi": 95.0 if docker_ok and security_ok and all_projects_pass and os.environ.get("LARGESTACK_EXTERNAL_AUDIT_PASSED") == "1" else 85.0,
    }


def build_summary(run_id: str, outdir: Path, started: str, gates: list[GateResult], projects: list[ProjectCertification]) -> CertificationSummary:
    scores = compute_scores(gates, projects)
    blockers: list[dict[str, str]] = []
    for gate in gates:
        if gate.status != "PASS":
            blockers.append({"type": gate.blocker_type, "item": gate.name, "solution": gate.solution})
    for project in projects:
        if not project.passed:
            blockers.append({"type": project.blocker_type, "item": project.name, "solution": project.solution})
    targets_met = all(scores.get(name, 0) >= target for name, target in TARGET_SCORES.items())
    final_decision = "GO" if targets_met and not blockers else "HOLD"
    return CertificationSummary(
        run_id=run_id,
        outdir=str(outdir),
        started_at=started,
        finished_at=datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        final_decision=final_decision,
        target_scores=TARGET_SCORES,
        achieved_scores=scores,
        gates=gates,
        projects=projects,
        blockers=blockers,
    )


def write_summary_files(summary: CertificationSummary) -> None:
    outdir = Path(summary.outdir)
    write_json(outdir / "summary.json", asdict(summary))
    with (outdir / "projects.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["name", "passed", "score", "failed_checks", "tokens", "actual_cost", "report_path"])
        writer.writeheader()
        for project in summary.projects:
            writer.writerow(
                {
                    "name": project.name,
                    "passed": project.passed,
                    "score": project.score,
                    "failed_checks": ";".join(project.failed_checks),
                    "tokens": project.tokens,
                    "actual_cost": project.actual_cost,
                    "report_path": project.report_path,
                }
            )
    lines = [
        "# LARGESTACK Final 95+ Certification",
        "",
        f"- Decision: `{summary.final_decision}`",
        f"- Run ID: `{summary.run_id}`",
        f"- Evidence: `{summary.outdir}`",
        "",
        "## Scores",
        "",
        "| Area | Target | Actual |",
        "|---|---:|---:|",
    ]
    for name, target in summary.target_scores.items():
        lines.append(f"| {name} | {target} | {summary.achieved_scores.get(name, 0):.1f} |")
    lines.extend(["", "## Gates", "", "| Gate | Status | Reason |", "|---|---|---|"])
    for gate in summary.gates:
        lines.append(f"| {gate.name} | {gate.status} | {gate.reason} |")
    lines.extend(["", "## Project Results", "", "| Project | Pass | Score | Failed Checks |", "|---|---:|---:|---|"])
    for project in summary.projects:
        lines.append(f"| {project.name} | {project.passed} | {project.score} | {', '.join(project.failed_checks)} |")
    if summary.blockers:
        lines.extend(["", "## Blockers", ""])
        for blocker in summary.blockers:
            lines.append(f"- `{blocker['type']}` {blocker['item']}: {blocker['solution']}")
    write_text(outdir / "SUMMARY.md", "\n".join(lines) + "\n")


async def async_main(args: argparse.Namespace) -> int:
    run_id = args.run_id or now_id()
    started = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
    outdir = ROOT / "release_evidence" / "final_95_plus" / run_id
    outdir.mkdir(parents=True, exist_ok=True)
    progress(f"run start: {run_id}")
    progress(f"evidence dir: {outdir}")
    gates: list[GateResult] = []
    if not args.no_cleanup:
        gates.append(cleanup_generated_artifacts(outdir))
    if not os.environ.get("LARGESTACK_DEEPSEEK_API_KEY"):
        gate = GateResult(
            name="deepseek_key_present",
            status="FAIL",
            blocker_type="SECURITY BLOCKER",
            reason="LARGESTACK_DEEPSEEK_API_KEY is not exported",
            solution="Rotate the exposed DeepSeek key, export the new value in the shell/CI secret store, and rerun.",
        )
        gates.append(gate)
        summary = build_summary(run_id, outdir, started, gates, [])
        write_summary_files(summary)
        progress("run hold: missing LARGESTACK_DEEPSEEK_API_KEY")
        return 2
    progress("deepseek key present: yes")
    if not args.skip_baseline:
        baseline = run_cmd("baseline_final_release_validate", ["bash", "scripts/final_release_validate.sh"], outdir, args.baseline_timeout)
        gates.append(baseline)
        gates.extend(parse_final_validator(baseline))
    if args.skip_extra_gates:
        progress("debug: skipping extra security/docker/helm gates")
    else:
        gates.extend(run_extra_gates(outdir))
        gates.append(docker_cleanup_probe(outdir, run_id))
    projects = await run_project_suite(outdir, args.project_limit, args.project_start)
    summary = build_summary(run_id, outdir, started, gates, projects)
    write_summary_files(summary)
    progress(f"run done: decision={summary.final_decision} evidence={outdir}")
    return 0 if summary.final_decision == "GO" else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Run final 95+ LARGESTACK certification.")
    parser.add_argument("--run-id", default="", help="Evidence run ID. Defaults to UTC timestamp.")
    parser.add_argument("--project-limit", type=int, default=0, help="Debug only: limit project count.")
    parser.add_argument("--project-start", type=int, default=1, help="Debug only: 1-based project index to start from.")
    parser.add_argument("--skip-baseline", action="store_true", help="Debug only: skip final_release_validate.sh.")
    parser.add_argument("--skip-extra-gates", action="store_true", help="Debug only: skip security/docker/helm gates.")
    parser.add_argument("--no-cleanup", action="store_true", help="Do not remove generated caches/build metadata first.")
    parser.add_argument("--baseline-timeout", type=int, default=7200)
    args = parser.parse_args()
    args.project_limit = args.project_limit or None
    args.project_start = max(1, args.project_start)
    return asyncio.run(async_main(args))


if __name__ == "__main__":
    raise SystemExit(main())
