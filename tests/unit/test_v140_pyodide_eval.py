"""v0.14.0: Tests for Studio Pyodide eval embed."""

from __future__ import annotations

import textwrap

import pytest


_SAMPLE_YAML = textwrap.dedent("""\
    name: kyc-test
    cases:
      - name: pan_valid
        contains: ["AAACR1234C"]
      - name: aadhaar_redact
        similarity:
          expected: "redacted aadhaar"
          threshold: 0.5
""")


def test_render_requires_yaml():
    from largestack._studio.pyodide_eval import render_pyodide_eval_html

    with pytest.raises(ValueError, match="suite_yaml"):
        render_pyodide_eval_html("")


def test_render_validates_fail_under():
    from largestack._studio.pyodide_eval import render_pyodide_eval_html

    with pytest.raises(ValueError, match="fail_under"):
        render_pyodide_eval_html(_SAMPLE_YAML, fail_under=1.5)


def test_render_returns_html_with_pyodide_loader():
    from largestack._studio.pyodide_eval import (
        render_pyodide_eval_html,
        PYODIDE_VERSION,
    )

    html = render_pyodide_eval_html(_SAMPLE_YAML)
    assert "<!doctype html>" in html.lower() or "<!DOCTYPE html>" in html
    assert "pyodide.js" in html
    assert PYODIDE_VERSION in html
    assert "loadPyodide" in html


def test_render_embeds_suite_yaml():
    from largestack._studio.pyodide_eval import render_pyodide_eval_html

    html = render_pyodide_eval_html(_SAMPLE_YAML)
    # YAML is in the embedded JSON SUITE.yaml
    assert "kyc-test" in html
    assert "pan_valid" in html


def test_render_xss_safe_for_title():
    from largestack._studio.pyodide_eval import render_pyodide_eval_html

    html = render_pyodide_eval_html(
        _SAMPLE_YAML,
        title="<script>alert(1)</script>",
    )
    assert "&lt;script&gt;" in html


def test_render_xss_safe_for_yaml_with_closing_script():
    from largestack._studio.pyodide_eval import render_pyodide_eval_html

    bad_yaml = "name: x\ndescription: '</script><script>alert(1)</script>'"
    html = render_pyodide_eval_html(bad_yaml)
    # The </script> from YAML should not break out of the embedded JSON
    # It should be escaped to <\/script>
    assert "<\\/script>" in html


def test_render_includes_default_outputs_when_provided():
    from largestack._studio.pyodide_eval import render_pyodide_eval_html

    html = render_pyodide_eval_html(
        _SAMPLE_YAML,
        agent_outputs={"pan_valid": "Output: AAACR1234C verified"},
    )
    assert "AAACR1234C" in html


def test_export_writes_file(tmp_path):
    from largestack._studio.pyodide_eval import export_pyodide_eval

    out = tmp_path / "eval.html"
    written = export_pyodide_eval(_SAMPLE_YAML, out, title="My Demo")
    assert written.exists()
    content = written.read_text(encoding="utf-8")
    assert "My Demo" in content
