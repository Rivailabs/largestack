from __future__ import annotations

import ast
import compileall
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys


REPO = Path.cwd()
OUT = REPO / "release_evidence" / "mac_validation" / "20260512-203121"
SCRATCH = OUT / "step6_project_scratch"
LOG_DIR = OUT / "step6_project_logs"
SCRATCH.mkdir(parents=True, exist_ok=True)
LOG_DIR.mkdir(parents=True, exist_ok=True)

ROOTS = [
    REPO / "release_evidence" / "final_95_plus" / "20260512-realfeatures24-final06",
    REPO / "release_evidence" / "final_95_plus" / "20260512-b2b-agentic24-final02",
    REPO / "release_evidence" / "final_95_plus" / "mac-bfsi-plus2-autofix2-20260512-203121",
]

FAKE_PATTERNS = [
    re.compile(r"^\s*class\s+(Agent|Workflow|Team)\b"),
    re.compile(r"^\s*def\s+(Agent|Workflow|Team)\b"),
    re.compile(r"^\s*(Agent|Workflow|Team)\s*=\s*(MagicMock|Mock|type\()"),
]


def imports_largestack(path: Path) -> bool:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except Exception:
        return False
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(a.name == "largestack" or a.name.startswith("largestack.") for a in node.names):
                return True
        if isinstance(node, ast.ImportFrom):
            if node.module and (node.module == "largestack" or node.module.startswith("largestack.")):
                return True
    return False


def fake_matches(project: Path) -> list[str]:
    out: list[str] = []
    for path in sorted(project.rglob("*.py")):
        rel = path.relative_to(project)
        if "tests" in rel.parts:
            continue
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if any(pattern.search(line) for pattern in FAKE_PATTERNS):
                out.append(f"{rel}:{lineno}:{line.strip()}")
    return out


def run_pytest(project: Path, suite: str, name: str) -> str:
    tests = project / "tests"
    if not tests.exists() or not any(tests.rglob("test*.py")):
        return "not_run"
    env = os.environ.copy()
    for key in ("LARGESTACK_DEEPSEEK_API_KEY", "DEEPSEEK_API_KEY", "OPENAI_API_KEY"):
        env.pop(key, None)
    env["PYTHONPATH"] = os.pathsep.join([str(project), str(REPO), env.get("PYTHONPATH", "")])
    log = LOG_DIR / f"{suite}__{name}__pytest.log"
    with log.open("w", encoding="utf-8") as fh:
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "tests", "-q", "--tb=short"],
            cwd=project,
            env=env,
            stdout=fh,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=180,
        )
    return "passed" if proc.returncode == 0 else "failed"


def report_exists(root: Path, name: str) -> bool:
    reports = root / "project_reports"
    return (reports / f"{name}.json").exists() or (reports / f"{name}.md").exists()


def main() -> int:
    rows = []
    for root in ROOTS:
        projects = root / "projects"
        if not projects.exists():
            continue
        suite = root.name
        for original in sorted(p for p in projects.iterdir() if p.is_dir()):
            work = SCRATCH / suite / original.name
            if work.exists():
                shutil.rmtree(work)
            shutil.copytree(original, work)

            app = work / "largestack_app.py"
            row = {
                "suite": suite,
                "project": original.name,
                "compile_ok": bool(compileall.compile_dir(str(work), quiet=1, force=True)),
                "pytest_status": run_pytest(work, suite, original.name),
                "largestack_app_exists": app.exists(),
                "largestack_app_imports_largestack": imports_largestack(app) if app.exists() else False,
                "readme_exists": (work / "README.md").exists(),
                "report_exists": report_exists(root, original.name),
                "fake_mock_matches": fake_matches(work),
            }
            row["validation_ok"] = (
                row["compile_ok"]
                and row["pytest_status"] in {"passed", "not_run"}
                and row["largestack_app_exists"]
                and row["largestack_app_imports_largestack"]
                and row["readme_exists"]
                and row["report_exists"]
                and not row["fake_mock_matches"]
            )
            rows.append(row)

    summary = {
        "total_projects_found": len(rows),
        "total_compiled": sum(r["compile_ok"] for r in rows),
        "total_pytest_passed": sum(r["pytest_status"] == "passed" for r in rows),
        "total_pytest_not_run": sum(r["pytest_status"] == "not_run" for r in rows),
        "total_failed": sum(not r["validation_ok"] for r in rows),
        "missing_largestack_app": sum(not r["largestack_app_exists"] for r in rows),
        "missing_largestack_import": sum(
            r["largestack_app_exists"] and not r["largestack_app_imports_largestack"] for r in rows
        ),
        "missing_readme": sum(not r["readme_exists"] for r in rows),
        "missing_report": sum(not r["report_exists"] for r in rows),
        "fake_mock_usage_found": sum(bool(r["fake_mock_matches"]) for r in rows),
    }
    result = {"summary": summary, "projects": rows}
    (OUT / "step6_generated_projects_validation.json").write_text(
        json.dumps(result, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2))
    return 0 if summary["total_failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
