"""Studio Pyodide eval embed (v0.14.0).

Closes Tier A #7. Produces a single-HTML Studio export with an
**embedded Pyodide eval runner** — the user can run an eval suite
*client-side in the browser* (no server, no Python installation
beyond the browser).

Workflow:

1. LARGESTACK exports a Studio HTML containing the eval suite YAML +
   Pyodide bootloader
2. User opens the HTML in any modern browser
3. Pyodide loads (~5 MB), then runs the eval cases against an
   inlined Python evaluator
4. Results render as a pass/fail grid in the same HTML

This is **read-only** — the eval results don't get persisted back to
LARGESTACK. Use cases:
- Demo a regression suite to a stakeholder without standing up a server
- Embed in a PR comment as a self-contained reproducer
- Distribute eval results offline

Usage::

    from largestack._studio.pyodide_eval import render_pyodide_eval_html

    html = render_pyodide_eval_html(
        suite_yaml=Path("evals/kyc.yaml").read_text(),
        title="KYC eval demo",
    )
    Path("kyc_demo.html").write_text(html)
"""

from __future__ import annotations
import html as _html
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# Pyodide CDN — pinned for reproducibility
PYODIDE_VERSION = "0.26.4"
PYODIDE_BASE_URL = f"https://cdn.jsdelivr.net/pyodide/v{PYODIDE_VERSION}/full/"


# A minimal pure-Python eval runner that runs inside Pyodide.
# Implements: contains, equals, similarity (cosine on hash embeddings).
_INLINE_RUNNER_PY = """
import math, hashlib, json

def _hash_embed(text, dim=128):
    v = [0.0] * dim
    for tok in text.lower().split():
        h = int.from_bytes(hashlib.sha256(tok.encode()).digest()[:8], "big")
        v[h % dim] += 1.0 if (h // dim) & 1 else -1.0
    n = math.sqrt(sum(x * x for x in v))
    return [x / n for x in v] if n > 0 else v

def _cosine(a, b):
    if len(a) != len(b): return 0.0
    return sum(x * y for x, y in zip(a, b))

def evaluate_case(case, agent_outputs):
    name = case.get("name", "unnamed")
    actual = agent_outputs.get(name, "")
    results = []
    contains = case.get("contains", [])
    if isinstance(contains, str):
        contains = [contains]
    for needle in contains:
        ok = needle.lower() in (actual or "").lower()
        results.append({
            "type": "contains", "needle": needle,
            "passed": ok,
            "reason": (f"contains '{needle}'" if ok
                       else f"missing '{needle}'"),
        })
    if "equals" in case:
        ok = (actual or "").strip() == str(case["equals"]).strip()
        results.append({
            "type": "equals", "passed": ok,
            "reason": "equals" if ok else "not equal",
        })
    sim = case.get("similarity")
    if isinstance(sim, dict):
        threshold = float(sim.get("threshold", 0.7))
        expected = sim.get("expected", "")
        score = _cosine(_hash_embed(actual or ""), _hash_embed(expected))
        ok = score >= threshold
        results.append({
            "type": "similarity", "passed": ok,
            "score": round(score, 3), "threshold": threshold,
            "reason": f"sim={score:.3f} {'>=' if ok else '<'} {threshold}",
        })
    elif isinstance(sim, str):
        score = _cosine(_hash_embed(actual or ""), _hash_embed(sim))
        ok = score >= 0.7
        results.append({
            "type": "similarity", "passed": ok,
            "score": round(score, 3), "threshold": 0.7,
            "reason": f"sim={score:.3f}",
        })
    case_passed = all(r["passed"] for r in results) if results else True
    return {"name": name, "passed": case_passed, "assertions": results}

def run_suite(suite, agent_outputs):
    cases = suite.get("cases", [])
    results = [evaluate_case(c, agent_outputs) for c in cases]
    n_total = len(results)
    n_passed = sum(1 for r in results if r["passed"])
    return {
        "suite_name": suite.get("name", "suite"),
        "total": n_total,
        "passed": n_passed,
        "pass_rate": (n_passed / n_total) if n_total else 0.0,
        "cases": results,
    }
"""


@dataclass
class PyodideEvalConfig:
    """Configuration for the Pyodide-embedded eval HTML."""

    suite_yaml: str
    title: str = "LARGESTACK Studio — Eval Demo"
    agent_outputs: dict[str, str] = field(default_factory=dict)
    fail_under: float = 0.7
    pyodide_version: str = PYODIDE_VERSION


def render_pyodide_eval_html(
    suite_yaml: str,
    *,
    title: str = "LARGESTACK Studio — Eval Demo",
    agent_outputs: dict[str, str] | None = None,
    fail_under: float = 0.7,
) -> str:
    """Render a single-HTML page that runs the eval suite via Pyodide.

    Args:
        suite_yaml: the YAML text of the eval suite
        title: page title
        agent_outputs: optional ``{case_name: actual_output}`` map. If
            omitted, the page asks the user to paste outputs into a
            text area.
        fail_under: pass-rate threshold; below this is shown as fail
    """
    if not suite_yaml or not suite_yaml.strip():
        raise ValueError("suite_yaml is required")
    if not (0.0 <= fail_under <= 1.0):
        raise ValueError("fail_under must be in [0.0, 1.0]")

    safe_title = _html.escape(title)
    # Embed YAML + outputs as JSON (XSS-safe via </script> escape)
    suite_payload = json.dumps({"yaml": suite_yaml}).replace("</", "<\\/")
    outputs_payload = json.dumps(
        agent_outputs or {},
        indent=2,
    ).replace("</", "<\\/")
    runner_payload = json.dumps(_INLINE_RUNNER_PY).replace("</", "<\\/")
    fail_under_str = f"{fail_under:.2f}"

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{safe_title}</title>
<style>
  body {{ background:#0f172a; color:#e2e8f0;
         font-family: ui-sans-serif, system-ui; margin:0; padding:24px; }}
  h1 {{ color:#f8fafc; font-size:20px; margin:0 0 16px; }}
  .badge {{ display:inline-block; padding:2px 10px; border-radius:10px;
           font-size:12px; }}
  .pyodide-status {{ background:#1e293b; padding:12px; border-radius:8px;
                    margin:16px 0; font-family: ui-monospace, monospace;
                    font-size:13px; }}
  .panel {{ background:#1e293b; border-radius:8px; padding:16px;
           margin-bottom:16px; }}
  .panel h2 {{ font-size:14px; color:#94a3b8; margin:0 0 12px; }}
  textarea {{ width:100%; min-height:120px; background:#0f172a;
             color:#e2e8f0; border:1px solid #334155; border-radius:6px;
             padding:8px; font-family: ui-monospace, monospace;
             font-size:12px; }}
  button {{ background:#2563eb; color:white; border:none; padding:8px 16px;
           border-radius:6px; cursor:pointer; font-size:13px;
           margin-top:8px; }}
  button:disabled {{ background:#334155; cursor:not-allowed; }}
  .case {{ padding:8px 12px; border-radius:6px; margin:4px 0;
          background:#0f172a; }}
  .case.passed {{ border-left:3px solid #10b981; }}
  .case.failed {{ border-left:3px solid #ef4444; }}
  .summary {{ font-size:18px; padding:12px; border-radius:8px;
              margin:12px 0; }}
  .summary.pass {{ background:#064e3b; color:#10b981; }}
  .summary.fail {{ background:#7f1d1d; color:#fca5a5; }}
  pre {{ background:#0f172a; padding:8px; border-radius:4px;
        overflow-x:auto; font-size:11px; color:#94a3b8; }}
</style>
</head>
<body>
<h1>{safe_title}</h1>
<div>
  <span class="badge" style="background:#1e3a5f; color:#7dd3fc;">
    Pyodide v{PYODIDE_VERSION}
  </span>
  <span class="badge" style="background:#3a1f5f; color:#c4b5fd;">
    fail-under: {fail_under_str}
  </span>
</div>

<div class="pyodide-status" id="status">
  Loading Pyodide... (~5 MB, one-time download)
</div>

<div class="panel">
  <h2>Eval suite (YAML)</h2>
  <pre id="suite-preview"></pre>
</div>

<div class="panel">
  <h2>Agent outputs (paste JSON: {{case_name: output_string}})</h2>
  <textarea id="outputs"></textarea>
  <br>
  <button id="run-btn" disabled>Run eval suite</button>
</div>

<div id="results"></div>

<script type="text/javascript"
        src="{PYODIDE_BASE_URL}pyodide.js"></script>
<script>
const SUITE = {suite_payload};
const DEFAULT_OUTPUTS = {outputs_payload};
const RUNNER_CODE = {runner_payload};
const FAIL_UNDER = {fail_under_str};

document.getElementById('suite-preview').textContent = SUITE.yaml;
document.getElementById('outputs').value = JSON.stringify(
  DEFAULT_OUTPUTS, null, 2,
);

let pyodide = null;

async function bootPyodide() {{
  const status = document.getElementById('status');
  try {{
    pyodide = await loadPyodide();
    status.textContent = 'Loading PyYAML...';
    await pyodide.loadPackage(['pyyaml']);
    pyodide.runPython(RUNNER_CODE);
    status.textContent = '✓ Pyodide ready. Click "Run eval suite".';
    document.getElementById('run-btn').disabled = false;
  }} catch (e) {{
    status.textContent = '✗ Pyodide load failed: ' + e.message;
  }}
}}

async function runSuite() {{
  if (!pyodide) return;
  const btn = document.getElementById('run-btn');
  btn.disabled = true;
  btn.textContent = 'Running...';
  let outputs;
  try {{
    outputs = JSON.parse(
      document.getElementById('outputs').value || '{{}}'
    );
  }} catch (e) {{
    document.getElementById('results').innerHTML =
      '<div class="summary fail">Invalid JSON in outputs: '
      + e.message + '</div>';
    btn.disabled = false; btn.textContent = 'Run eval suite';
    return;
  }}

  pyodide.globals.set('SUITE_YAML', SUITE.yaml);
  pyodide.globals.set('AGENT_OUTPUTS', JSON.stringify(outputs));

  const resultJson = pyodide.runPython(`
import yaml, json
suite = yaml.safe_load(SUITE_YAML) or {{}}
outputs = json.loads(AGENT_OUTPUTS)
result = run_suite(suite, outputs)
json.dumps(result)
  `);

  const result = JSON.parse(resultJson);
  renderResult(result);
  btn.disabled = false; btn.textContent = 'Run eval suite';
}}

function renderResult(result) {{
  let html = '';
  const passed = result.pass_rate >= FAIL_UNDER;
  html += `<div class="summary ${{passed ? 'pass' : 'fail'}}">`;
  html += `<strong>${{passed ? '✓ PASS' : '✗ FAIL'}}</strong> &mdash; `;
  html += `${{result.passed}} / ${{result.total}} cases passed `;
  html += `(${{(result.pass_rate * 100).toFixed(1)}}%)</div>`;

  html += '<div class="panel"><h2>Cases</h2>';
  result.cases.forEach(c => {{
    html += `<div class="case ${{c.passed ? 'passed' : 'failed'}}">`;
    html += `<strong>${{c.passed ? '✓' : '✗'}} ${{c.name}}</strong>`;
    if (c.assertions.length > 0) {{
      html += '<ul>';
      c.assertions.forEach(a => {{
        html += `<li>${{a.passed ? '✓' : '✗'}} ${{a.type}}: ${{a.reason}}</li>`;
      }});
      html += '</ul>';
    }}
    html += '</div>';
  }});
  html += '</div>';
  document.getElementById('results').innerHTML = html;
}}

document.getElementById('run-btn').addEventListener('click', runSuite);
bootPyodide();
</script>
</body>
</html>
"""


def export_pyodide_eval(
    suite_yaml: str,
    output_path: str | Path,
    *,
    title: str = "LARGESTACK Studio — Eval Demo",
    agent_outputs: dict[str, str] | None = None,
    fail_under: float = 0.7,
) -> Path:
    """Render and write the Pyodide eval HTML to a file."""
    p = Path(output_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        render_pyodide_eval_html(
            suite_yaml,
            title=title,
            agent_outputs=agent_outputs,
            fail_under=fail_under,
        ),
        encoding="utf-8",
    )
    return p


__all__ = [
    "PyodideEvalConfig",
    "render_pyodide_eval_html",
    "export_pyodide_eval",
    "PYODIDE_VERSION",
]
