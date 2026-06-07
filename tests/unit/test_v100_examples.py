"""v0.10.0: Tests for the v0.10 examples directory additions."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest


EXAMPLES_DIR = Path(__file__).parent.parent.parent / "examples"

# Just the v0.10 examples we added (don't validate legacy 01_hello/etc.)
V10_EXAMPLE_NAMES = {
    "rag_basic",
    "fintech_kyc",
    "multi_agent_research",
    "observability",
    "resilient_llm",
}


def _v10_example_dirs():
    return [d for d in EXAMPLES_DIR.iterdir() if d.is_dir() and d.name in V10_EXAMPLE_NAMES]


def test_examples_dir_has_readme():
    assert (EXAMPLES_DIR / "README.md").exists()


def test_each_v10_example_dir_has_py_file():
    """Every v0.10 example directory has at least one .py file."""
    for d in _v10_example_dirs():
        py_files = list(d.glob("*.py"))
        assert py_files, f"Example {d.name} has no .py file"


def test_v10_examples_are_syntactically_valid():
    """Every v0.10 example .py file must parse as valid Python."""
    for d in _v10_example_dirs():
        for py in d.glob("*.py"):
            try:
                ast.parse(py.read_text())
            except SyntaxError as e:
                pytest.fail(f"{py} has syntax error: {e}")


def test_each_v10_example_has_docstring():
    """Every v0.10 example file should have a substantial docstring."""
    for d in _v10_example_dirs():
        for py in d.glob("*.py"):
            tree = ast.parse(py.read_text())
            doc = ast.get_docstring(tree)
            assert doc is not None and len(doc) > 100, (
                f"{py.name} needs a top-level docstring (≥100 chars)"
            )


def test_v10_examples_handle_missing_credentials():
    """v0.10 examples that need creds should check + exit gracefully."""
    examples_with_creds_check = 0
    for d in _v10_example_dirs():
        for py in d.glob("*.py"):
            content = py.read_text()
            if "os.environ" in content:
                if any(pattern in content for pattern in ["if not os.environ", "os.environ.get"]):
                    examples_with_creds_check += 1
                    break
    assert examples_with_creds_check >= 2, (
        f"Only {examples_with_creds_check} v0.10 examples handle missing creds"
    )


def test_expected_v10_examples_present():
    """Five core v0.10 examples must ship."""
    actual = {d.name for d in _v10_example_dirs()}
    assert V10_EXAMPLE_NAMES.issubset(actual), f"Missing: {V10_EXAMPLE_NAMES - actual}"


def test_v10_examples_have_run_instructions_in_docstring():
    """Each v0.10 example docstring should explain how to run it."""
    for d in _v10_example_dirs():
        for py in d.glob("*.py"):
            doc = ast.get_docstring(ast.parse(py.read_text())) or ""
            assert any(p in doc.lower() for p in ["run::", "python ", "pip install"]), (
                f"{py.name} docstring needs run instructions"
            )
