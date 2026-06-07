from __future__ import annotations

import asyncio
import json

import pytest

from largestack.autonomous_builder import (
    AutonomousProjectBuilder,
    BuilderBudget,
    GeneratedFile,
    NoOpMemory,
    PatchSet,
    ProjectFiles,
    ProjectSpec,
    build_failure_feedback,
    make_static_agent,
    parse_model_json,
    redact_sensitive,
    safe_write_files,
    validate_project,
)


def _json(data):
    return json.dumps(data)


def test_generated_file_blocks_path_traversal():
    with pytest.raises(ValueError):
        GeneratedFile(path="../secret.txt", content="nope")


def test_parse_model_json_extracts_fenced_payload():
    parsed = parse_model_json(
        '```json\n{"notes":"ok","files":[{"path":"app.py","content":"x=1"}]}\n```',
        ProjectFiles,
    )

    assert parsed.files[0].path == "app.py"


def test_parse_model_json_extracts_fenced_payload_after_prose_and_braces():
    parsed = parse_model_json(
        'Here is the project:\n```JSON\n{"notes":"ok {literal}","files":[{"path":"app.py","content":"DATA={\\"x\\": 1}\\n"}]}\n```',
        ProjectFiles,
    )

    assert parsed.notes == "ok {literal}"
    assert parsed.files[0].content == 'DATA={"x": 1}\n'


def test_safe_write_files_blocks_absolute_paths(tmp_path):
    with pytest.raises(ValueError):
        safe_write_files(
            tmp_path, [GeneratedFile.model_construct(path="/tmp/bad.py", content="x=1")]
        )


def test_safe_write_files_normalizes_root_pytest_files(tmp_path):
    written = safe_write_files(
        tmp_path, [GeneratedFile(path="test_app.py", content="def test_ok():\n    assert True\n")]
    )

    assert written == ["tests/test_app.py"]
    assert (tmp_path / "tests" / "test_app.py").exists()


def test_validation_and_feedback_reports_acceptance_failure(tmp_path):
    safe_write_files(
        tmp_path,
        [
            GeneratedFile(path="app.py", content="def add(a, b):\n    return a - b\n"),
            GeneratedFile(
                path="tests/test_app.py",
                content="from app import add\n\ndef test_add():\n    assert add(1, 1) == 0\n",
            ),
        ],
    )

    validation = validate_project(tmp_path, "from app import add\nassert add(1, 2) == 3\n")
    feedback = build_failure_feedback(validation, json_valid=True, files=["app.py"])

    assert validation.compile_passed is True
    assert validation.pytest_passed is True
    assert validation.acceptance_passed is False
    assert "acceptance" in feedback


def test_feedback_prefers_hidden_acceptance_over_generated_tests(tmp_path):
    safe_write_files(
        tmp_path,
        [
            GeneratedFile(path="app.py", content="def ok():\n    return True\n"),
            GeneratedFile(
                path="tests/test_app.py",
                content="from app import ok\n\ndef test_wrong():\n    assert ok() is False\n",
            ),
        ],
    )

    validation = validate_project(tmp_path, "from app import ok\nassert ok() is True\n")
    feedback = build_failure_feedback(
        validation, json_valid=True, files=["app.py", "tests/test_app.py"]
    )

    assert validation.acceptance_passed is True
    assert validation.pytest_passed is False
    assert "repair the generated tests" in feedback


def test_patchset_schema_requires_safe_paths():
    with pytest.raises(ValueError):
        PatchSet.model_validate({"files": [{"path": "../app.py", "content": "x=1"}]})


def test_redact_sensitive_masks_keys():
    fake_key = "sk-" + "test-redaction-key"
    assert "sk-REDACTED" in redact_sensitive(f"token {fake_key}")
    assert "secret=REDACTED" in redact_sensitive("secret='value123'")


def test_noop_memory_isolates_agent_history():
    memory = NoOpMemory()

    assert memory.get_messages() == []
    asyncio.run(memory.add_messages([{"role": "user", "content": "large prior project"}]))
    assert memory.get_messages() == []


def test_autonomous_builder_repairs_with_patch(tmp_path):
    responses = [
        _json(
            {
                "project_name": "calc",
                "summary": "tiny",
                "files": ["app.py"],
                "tests": ["tests/test_app.py"],
            }
        ),
        _json(
            {
                "notes": "initial",
                "files": [
                    {"path": "app.py", "content": "def add(a, b):\n    return a - b\n"},
                    {
                        "path": "tests/test_app.py",
                        "content": "from app import add\n\ndef test_callable():\n    assert callable(add)\n",
                    },
                ],
            }
        ),
        _json(
            {
                "notes": "fixed add",
                "files": [
                    {
                        "path": "app.py",
                        "content": "def add(a, b):\n    return a + b\n",
                        "reason": "acceptance expected sum",
                    }
                ],
            }
        ),
    ]
    agent = make_static_agent(responses)
    builder = AutonomousProjectBuilder(
        agent, BuilderBudget(max_attempts=3, max_tokens=20_000, max_seconds=60)
    )
    spec = ProjectSpec(
        name="calc",
        requirements="Create add(a,b).",
        acceptance="from app import add\nassert add(1, 2) == 3\n",
    )

    report = asyncio.run(builder.build(spec, tmp_path))

    assert report.passed is True
    assert len(report.attempts) == 2
    assert report.attempts[0].validation.acceptance_passed is False
    assert report.attempts[1].mode == "patch"
    assert "app.py" in report.generated_files


def test_autonomous_builder_regenerates_when_initial_json_has_no_files(tmp_path):
    responses = [
        _json(
            {
                "project_name": "calc",
                "summary": "tiny",
                "files": ["app.py"],
                "tests": ["tests/test_app.py"],
            }
        ),
        "I cannot provide JSON for this one.",
        _json(
            {
                "notes": "regenerated",
                "files": [
                    {"path": "app.py", "content": "def add(a, b):\n    return a + b\n"},
                    {
                        "path": "tests/test_app.py",
                        "content": "from app import add\n\ndef test_add():\n    assert add(1, 2) == 3\n",
                    },
                ],
            }
        ),
    ]
    agent = make_static_agent(responses)
    builder = AutonomousProjectBuilder(
        agent, BuilderBudget(max_attempts=3, max_tokens=20_000, max_seconds=60)
    )
    spec = ProjectSpec(
        name="calc",
        requirements="Create add(a,b).",
        acceptance="from app import add\nassert add(1, 2) == 3\n",
    )

    report = asyncio.run(builder.build(spec, tmp_path))

    assert report.passed is True
    assert [item.mode for item in report.attempts] == ["generate", "generate"]
    assert report.attempts[0].json_valid is False
    assert report.attempts[1].json_valid is True
    assert sorted(report.generated_files) == ["app.py", "tests/test_app.py"]


def test_autonomous_builder_fails_honestly_after_budget(tmp_path):
    responses = [
        _json(
            {
                "project_name": "bad",
                "summary": "tiny",
                "files": ["app.py"],
                "tests": ["tests/test_app.py"],
            }
        ),
        _json({"notes": "bad", "files": [{"path": "app.py", "content": "def nope(:\n    pass\n"}]}),
    ]
    agent = make_static_agent(responses)
    builder = AutonomousProjectBuilder(
        agent, BuilderBudget(max_attempts=1, max_tokens=20_000, max_seconds=60)
    )
    spec = ProjectSpec(name="bad", requirements="Create valid Python.", acceptance="import app\n")

    report = asyncio.run(builder.build(spec, tmp_path))

    assert report.passed is False
    assert report.validation.compile_passed is False
    assert report.attempts[0].failure_summary in {
        "compile",
        "missing_files,compile",
        "compile,pytest,acceptance",
    }
