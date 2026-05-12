"""Autonomous project build-and-repair primitives.

This module is intentionally small and stdlib-first: it gives Largestack a
first-class capability for generating project workspaces, validating them, and
repairing them with bounded, auditable patches.
"""
from __future__ import annotations

import json
import os
import py_compile
import re
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Callable

from pydantic import BaseModel, Field, field_validator

from largestack._core.cost import CostTracker


class GeneratedFile(BaseModel):
    path: str
    content: str

    @field_validator("path")
    @classmethod
    def validate_relative_path(cls, value: str) -> str:
        return normalize_project_path(value)


class ProjectSpec(BaseModel):
    name: str
    requirements: str
    acceptance: str = ""
    required_files: list[str] = Field(default_factory=list)
    forbidden_actions: list[str] = Field(default_factory=list)
    evidence_required: list[str] = Field(default_factory=list)
    classification: str = "DEEPSEEK-BUILT-PROJECT"


class ProjectBuildPlan(BaseModel):
    project_name: str
    summary: str = ""
    files: list[str] = Field(default_factory=list)
    tests: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)


class PatchFile(BaseModel):
    path: str
    content: str
    reason: str = ""

    @field_validator("path")
    @classmethod
    def validate_relative_path(cls, value: str) -> str:
        return normalize_project_path(value)


class PatchSet(BaseModel):
    notes: str = ""
    files: list[PatchFile] = Field(default_factory=list)


class ProjectFiles(BaseModel):
    notes: str = ""
    files: list[GeneratedFile] = Field(default_factory=list)


class ValidationResult(BaseModel):
    compile_passed: bool
    pytest_passed: bool
    acceptance_passed: bool
    validation_output: str = ""
    acceptance_output: str = ""
    failed_checks: list[str] = Field(default_factory=list)
    duration_seconds: float = 0.0

    @property
    def passed(self) -> bool:
        return self.compile_passed and self.pytest_passed and self.acceptance_passed


class RepairAttempt(BaseModel):
    round: int
    json_valid: bool
    files_changed: list[str] = Field(default_factory=list)
    validation: ValidationResult
    trace_id: str = ""
    tokens: int = 0
    actual_cost: float = 0.0
    estimated_cost: float = 0.0
    failure_summary: str = ""
    mode: str = "generate"


class BuildReport(BaseModel):
    name: str
    passed: bool
    project_path: str
    generated_files: list[str]
    validation: ValidationResult
    trace_ids: list[str] = Field(default_factory=list)
    tokens: int = 0
    actual_cost: float = 0.0
    estimated_cost: float = 0.0
    attempts: list[RepairAttempt] = Field(default_factory=list)
    artifact_count: int = 0
    budget_exceeded: bool = False
    notes: str = ""


class BuilderBudget(BaseModel):
    max_attempts: int = 4
    max_tokens: int = 300_000
    max_seconds: float = 600.0
    cost_budget: float = 1.0


class NoOpMemory:
    """Memory adapter for isolated benchmark/build calls."""

    def get_messages(self) -> list[dict[str, Any]]:
        return []

    async def add_messages(self, messages: list[dict[str, Any]]) -> None:
        return None


class ModelRunResult(BaseModel):
    content: str = ""
    trace_id: str = ""
    total_tokens: int = 0
    total_cost: float = 0.0
    error: str = ""


def normalize_project_path(path: str) -> str:
    rel = str(path or "").strip().replace("\\", "/")
    if not rel:
        raise ValueError("file path is empty")
    if rel.startswith("/") or Path(rel).is_absolute():
        raise ValueError(f"absolute paths are not allowed: {path}")
    if ".." in Path(rel).parts:
        raise ValueError(f"path traversal is not allowed: {path}")
    return rel


def extract_json_object(text: str) -> dict[str, Any] | None:
    cleaned = (text or "").strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    candidates = [cleaned]
    start = cleaned.find("{")
    if start >= 0:
        depth = 0
        for index, char in enumerate(cleaned[start:], start):
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
            if depth == 0:
                candidates.append(cleaned[start : index + 1])
                break
    match = re.search(r"\{.*\}", cleaned, re.S)
    if match:
        candidates.append(match.group(0))
    for candidate in candidates:
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            return data
    return None


def parse_model_json(text: str, model_class: type[BaseModel]) -> BaseModel:
    data = extract_json_object(text)
    if data is None:
        raise ValueError("model response did not contain a JSON object")
    return model_class.model_validate(data)


def safe_write_files(project_path: Path, files: list[GeneratedFile | PatchFile]) -> list[str]:
    written: list[str] = []
    project_path.mkdir(parents=True, exist_ok=True)
    for item in files:
        rel = normalize_project_path(item.path)
        if "/" not in rel and rel.startswith("test_") and rel.endswith(".py"):
            rel = f"tests/{rel}"
        target = project_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(item.content)
        written.append(rel)
    return sorted(written)


def compile_project(path: Path) -> tuple[bool, str]:
    ok = True
    lines: list[str] = []
    for file in sorted(path.rglob("*.py")):
        if "__pycache__" in file.parts:
            continue
        try:
            py_compile.compile(str(file), doraise=True)
            lines.append(f"compile ok {file.relative_to(path)}")
        except Exception as exc:
            ok = False
            lines.append(f"compile fail {file.relative_to(path)}: {exc}")
    if not lines:
        lines.append("no python files found")
    return ok, "\n".join(lines)


def run_cmd(cmd: list[str], cwd: Path, timeout: int = 60) -> dict[str, Any]:
    env = dict(os.environ)
    repo_root = Path(__file__).resolve().parents[1]
    pythonpath_parts = [str(cwd), str(repo_root)]
    if env.get("PYTHONPATH"):
        pythonpath_parts.append(env["PYTHONPATH"])
    env["PYTHONPATH"] = os.pathsep.join(pythonpath_parts)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    try:
        proc = subprocess.run(
            cmd,
            cwd=cwd,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            check=False,
        )
        return {"returncode": proc.returncode, "stdout": proc.stdout[-5000:]}
    except subprocess.TimeoutExpired as exc:
        output = (exc.stdout or "") if isinstance(exc.stdout, str) else ""
        return {"returncode": 124, "stdout": (output + "\ncommand timed out")[-5000:]}


def run_pytest(path: Path) -> dict[str, Any]:
    if not (path / "tests").exists():
        return {"returncode": 1, "stdout": "missing tests directory"}
    return run_cmd([sys.executable, "-m", "pytest", "tests", "-q", "--tb=short"], path, timeout=90)


def run_acceptance(path: Path, code: str) -> dict[str, Any]:
    if not code.strip():
        return {"returncode": 0, "stdout": "no hidden acceptance configured"}
    return run_cmd([sys.executable, "-c", code], path, timeout=30)


def validate_project(project_path: Path, acceptance_code: str) -> ValidationResult:
    started = time.monotonic()
    compile_ok, compile_out = compile_project(project_path)
    pytest_out = run_pytest(project_path)
    accept_out = run_acceptance(project_path, acceptance_code)
    failed: list[str] = []
    if not compile_ok:
        failed.append("compile")
    if pytest_out["returncode"] != 0:
        failed.append("pytest")
    if accept_out["returncode"] != 0:
        failed.append("acceptance")
    return ValidationResult(
        compile_passed=compile_ok,
        pytest_passed=pytest_out["returncode"] == 0,
        acceptance_passed=accept_out["returncode"] == 0,
        validation_output=(compile_out + "\n" + pytest_out["stdout"])[-5000:],
        acceptance_output=str(accept_out["stdout"])[-3000:],
        failed_checks=failed,
        duration_seconds=round(time.monotonic() - started, 2),
    )


def classify_failure(validation: ValidationResult, json_valid: bool = True, files: list[str] | None = None) -> str:
    bits: list[str] = []
    if not json_valid:
        bits.append("invalid_json")
    if not files:
        bits.append("missing_files")
    bits.extend(validation.failed_checks)
    return ",".join(bits) if bits else "none"


def build_failure_feedback(validation: ValidationResult, *, json_valid: bool, files: list[str]) -> str:
    messages: list[str] = []
    if not json_valid:
        messages.append("The previous response was not valid JSON for the requested schema.")
    if not files:
        messages.append("No usable project files were generated.")
    if validation.failed_checks:
        messages.append("Failed checks: " + ", ".join(validation.failed_checks))
    messages.append(
        "Validation state: "
        f"compile={validation.compile_passed} "
        f"pytest={validation.pytest_passed} "
        f"hidden_acceptance={validation.acceptance_passed}."
    )
    if validation.acceptance_passed and not validation.pytest_passed:
        messages.append(
            "Hidden acceptance passed but generated pytest failed. The requirements and hidden acceptance are authoritative; "
            "repair the generated tests if they contradict the requirements."
        )
    if not validation.acceptance_passed:
        messages.append(
            "Hidden acceptance is the release contract. If the traceback says a function got an unexpected keyword, "
            "missing positional argument, wrong return type, or assertion failure, change the public function signature "
            "and return shape to match the contract exactly. Keep the implementation simple and deterministic."
        )
    messages.append("Validation output:\n" + validation.validation_output[-2500:])
    messages.append("Hidden acceptance output:\n" + validation.acceptance_output[-2200:])
    return "\n\n".join(messages)


def estimate_deepseek_cost(tokens: int) -> float:
    inp = max(tokens // 2, 1)
    out = max(tokens - inp, 1)
    return CostTracker().calc("deepseek-chat", inp, out)


def redact_sensitive(text: str) -> str:
    text = re.sub(r"sk-[A-Za-z0-9_-]{12,}", "sk-REDACTED", text)
    text = re.sub(r"(?i)(api[_-]?key|token|secret)\s*[:=]\s*[\"']?[^\"'\s]+", r"\1=REDACTED", text)
    return text


class AutonomousProjectBuilder:
    """Build projects with an LLM agent, validation, and minimal patch repair."""

    def __init__(self, agent: Any, budget: BuilderBudget | None = None):
        self.agent = agent
        self.budget = budget or BuilderBudget()

    async def build(self, spec: ProjectSpec, project_path: Path) -> BuildReport:
        started = time.monotonic()
        trace_ids: list[str] = []
        attempts: list[RepairAttempt] = []
        all_files: list[str] = []
        total_tokens = 0
        total_cost = 0.0
        notes = ""

        project_path.mkdir(parents=True, exist_ok=True)
        plan = await self._plan(spec)
        if plan.trace_id:
            trace_ids.append(plan.trace_id)
        total_tokens += plan.total_tokens
        total_cost += plan.total_cost

        generated = await self._generate(spec, plan.content)
        if generated.trace_id:
            trace_ids.append(generated.trace_id)
        total_tokens += generated.total_tokens
        total_cost += generated.total_cost

        try:
            project_files = parse_model_json(generated.content, ProjectFiles)
            json_valid = True
            changed = safe_write_files(project_path, project_files.files)
            notes = project_files.notes
        except Exception as exc:
            project_files = ProjectFiles()
            json_valid = False
            changed = []
            notes = f"generation parse failed: {exc}"
        all_files = sorted(set(all_files + changed))
        validation = validate_project(project_path, spec.acceptance)
        attempts.append(
            self._attempt(
                round_number=1,
                json_valid=json_valid,
                files_changed=changed,
                validation=validation,
                run=generated,
                mode="generate",
                failure_summary=classify_failure(validation, json_valid, changed),
            )
        )

        round_number = 1
        while not validation.passed and round_number < self.budget.max_attempts:
            if self._budget_exceeded(started, total_tokens):
                break
            round_number += 1
            feedback = build_failure_feedback(validation, json_valid=json_valid, files=all_files)
            patch_run = await self._patch(spec, project_path, feedback)
            if patch_run.trace_id:
                trace_ids.append(patch_run.trace_id)
            total_tokens += patch_run.total_tokens
            total_cost += patch_run.total_cost
            try:
                patch = parse_model_json(patch_run.content, PatchSet)
                json_valid = True
                changed = safe_write_files(project_path, patch.files)
                notes = patch.notes or notes
            except Exception as exc:
                json_valid = False
                changed = []
                notes = f"patch parse failed: {exc}"
            all_files = sorted(set(all_files + changed))
            validation = validate_project(project_path, spec.acceptance)
            attempts.append(
                self._attempt(
                    round_number=round_number,
                    json_valid=json_valid,
                    files_changed=changed,
                    validation=validation,
                    run=patch_run,
                    mode="patch",
                    failure_summary=classify_failure(validation, json_valid, all_files),
                )
            )

        budget_exceeded = self._budget_exceeded(started, total_tokens)
        return BuildReport(
            name=spec.name,
            passed=validation.passed and not budget_exceeded,
            project_path=str(project_path),
            generated_files=sorted(all_files),
            validation=validation,
            trace_ids=trace_ids,
            tokens=total_tokens,
            actual_cost=round(total_cost, 8),
            estimated_cost=round(estimate_deepseek_cost(total_tokens), 8),
            attempts=attempts,
            artifact_count=len(all_files) + len(attempts),
            budget_exceeded=budget_exceeded,
            notes=redact_sensitive(notes),
        )

    def _budget_exceeded(self, started: float, tokens: int) -> bool:
        return tokens > self.budget.max_tokens or (time.monotonic() - started) > self.budget.max_seconds

    def _attempt(
        self,
        *,
        round_number: int,
        json_valid: bool,
        files_changed: list[str],
        validation: ValidationResult,
        run: ModelRunResult,
        mode: str,
        failure_summary: str,
    ) -> RepairAttempt:
        return RepairAttempt(
            round=round_number,
            json_valid=json_valid,
            files_changed=files_changed,
            validation=validation,
            trace_id=run.trace_id,
            tokens=run.total_tokens,
            actual_cost=round(run.total_cost, 8),
            estimated_cost=round(estimate_deepseek_cost(run.total_tokens), 8),
            failure_summary=redact_sensitive(failure_summary),
            mode=mode,
        )

    async def _run_agent(self, prompt: str, **kw: Any) -> ModelRunResult:
        try:
            result = await self.agent.run(prompt, **kw)
            return ModelRunResult(
                content=str(getattr(result, "content", result)),
                trace_id=str(getattr(result, "trace_id", "")),
                total_tokens=int(getattr(result, "total_tokens", 0) or 0),
                total_cost=float(getattr(result, "total_cost", 0.0) or 0.0),
            )
        except Exception as exc:
            return ModelRunResult(error=f"{type(exc).__name__}: {exc}")

    async def _plan(self, spec: ProjectSpec) -> ModelRunResult:
        prompt = f"""
Create a concise implementation plan for project {spec.name}.

Requirements:
{spec.requirements}

Return ONLY valid JSON matching:
{{"project_name":"{spec.name}","summary":"...","files":["..."],"tests":["..."],"risks":["..."]}}
"""
        return await self._run_agent(prompt, timeout=90, temperature=0.1, max_tokens=900)

    async def _generate(self, spec: ProjectSpec, plan_json: str) -> ModelRunResult:
        prompt = f"""
Generate the complete small project named {spec.name}.

Requirements:
{spec.requirements}

Plan:
{plan_json[:3000]}

Return ONLY valid JSON matching:
{{"notes":"short note","files":[{{"path":"relative/path.py","content":"complete file content"}}]}}

Rules:
- Use Python standard library only unless requirements explicitly say otherwise.
- Include tests under tests/test_*.py.
- Generated tests must assert only the stated requirements; do not invent contradictory product rules.
- Generated tests must be isolated from each other. If a module uses in-memory globals, clear or recreate them before each test.
- Do not include API keys or secrets.
- Do not import or use network libraries such as requests, httpx, urllib.request, or socket.
- Keep each file concise.
- Make the public API exactly match the requirements, including function names, keyword parameters, positional parameters, return types, and dictionary keys.
- Do not over-validate simple example inputs from the requirements. If the contract passes a@example.com, 2026-05-12T10:00, or similar simple values, accept them.
- Prefer simple module-level functions and plain dictionaries/lists unless the requirements explicitly ask for a class.
- Always write complete, non-truncated files.
"""
        return await self._run_agent(prompt, timeout=180, temperature=0.05, max_tokens=5000)

    async def _patch(self, spec: ProjectSpec, project_path: Path, feedback: str) -> ModelRunResult:
        existing = collect_project_snapshot(project_path)
        prompt = f"""
Repair project {spec.name} with the smallest possible file replacements.

Requirements:
{spec.requirements}

Current files:
{existing[:5000]}

Validation feedback:
{feedback}

Return ONLY valid JSON matching:
{{"notes":"what was fixed","files":[{{"path":"relative/path.py","content":"complete replacement content","reason":"why"}}]}}

Rules:
- Return only files that need changes.
- Do not delete files.
- Do not include secrets.
- Do not import or use network libraries such as requests, httpx, urllib.request, or socket.
- Preserve the exact required public API.
- Requirements and hidden acceptance are more authoritative than generated pytest tests.
- If generated tests contradict requirements, patch the tests instead of weakening correct behavior.
- If hidden acceptance passes but pytest fails, preserve the working implementation and repair only contradictory or state-leaky tests when possible.
- Do not re-break signatures or return shapes fixed in earlier attempts.
- Prefer simple module-level functions and plain dictionaries/lists unless the requirements explicitly ask for a class.
- Always return complete replacement file content, never a diff or truncated file.
"""
        return await self._run_agent(prompt, timeout=180, temperature=0.02, max_tokens=4000)


def collect_project_snapshot(path: Path, limit_per_file: int = 2400) -> str:
    chunks: list[str] = []
    for file in sorted(path.rglob("*")):
        if not file.is_file() or "__pycache__" in file.parts:
            continue
        rel = file.relative_to(path)
        if file.stat().st_size > 50_000:
            continue
        try:
            text = file.read_text()
        except UnicodeDecodeError:
            continue
        chunks.append(f"--- {rel} ---\n{text[:limit_per_file]}")
    return "\n\n".join(chunks)


def build_trace_id(prefix: str = "autobuild") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


def make_static_agent(responses: list[str]) -> Any:
    """Small test helper for deterministic builder tests."""

    class _StaticAgent:
        def __init__(self, items: list[str]):
            self.items = list(items)
            self.calls = 0

        async def run(self, prompt: str, **kw: Any) -> ModelRunResult:
            self.calls += 1
            content = self.items.pop(0) if self.items else "{}"
            return ModelRunResult(content=content, trace_id=build_trace_id("test"), total_tokens=len(prompt) // 4)

    return _StaticAgent(responses)


def serialize_report(report: BuildReport) -> dict[str, Any]:
    return report.model_dump()


def summarize_report(report: BuildReport) -> str:
    return "\n".join(
        [
            f"# {report.name}",
            "",
            f"- Status: `{'PASS' if report.passed else 'FAIL'}`",
            f"- Attempts: `{len(report.attempts)}`",
            f"- Generated files: `{len(report.generated_files)}`",
            f"- Compile: `{report.validation.compile_passed}`",
            f"- Pytest: `{report.validation.pytest_passed}`",
            f"- Acceptance: `{report.validation.acceptance_passed}`",
            f"- Tokens: `{report.tokens}`",
            f"- Estimated cost: `${report.estimated_cost}`",
            f"- Budget exceeded: `{report.budget_exceeded}`",
            "",
            "## Files",
            *[f"- `{file}`" for file in report.generated_files],
            "",
            "## Validation Output",
            "```text",
            report.validation.validation_output[-3000:],
            "```",
            "",
            "## Acceptance Output",
            "```text",
            report.validation.acceptance_output[-3000:],
            "```",
            "",
            "## Attempts",
            *[
                f"- round {item.round}: mode={item.mode} json={item.json_valid} "
                f"checks={item.validation.failed_checks} trace={item.trace_id}"
                for item in report.attempts
            ],
        ]
    )


ProjectAcceptance = Callable[[Path], tuple[bool, str]]
