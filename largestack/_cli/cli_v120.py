"""v0.12.0: CLI commands for CI/CD eval gating + Studio export.

Adds two new ``largestack`` subcommands:

- ``largestack eval-block`` — runs a YAML eval suite and exits with non-zero
  status if pass-rate is below ``--fail-under``. Designed for CI/CD
  pipelines (GitHub Actions, GitLab CI, Jenkins).

- ``largestack studio-export`` — runs an agent.yaml + audit log through
  ``StudioBuilder`` and writes a single-HTML visualizer.

These are independent of ``cli_v09.py`` and use ``argparse`` directly.
"""
from __future__ import annotations
import argparse
import asyncio
import json
import logging
import sys
from pathlib import Path
from typing import Any

log = logging.getLogger("largestack.cli_v120")


# Default fail-under threshold for CI gating
DEFAULT_FAIL_UNDER = 0.7


# -------------------- Exit codes --------------------

EXIT_OK = 0
EXIT_FAIL_UNDER = 1  # eval pass-rate below threshold
EXIT_USAGE = 2  # bad args
EXIT_ERROR = 3  # runtime error (suite not found, etc.)


# -------------------- eval-block command --------------------

async def _run_eval_block(args: argparse.Namespace) -> int:
    """Run an eval suite and exit non-zero if below threshold."""
    from largestack._eval.runner import (
        run_suite, format_console_report,
    )

    suite_path = Path(args.suite)
    if not suite_path.exists():
        print(
            f"error: eval suite not found: {suite_path}",
            file=sys.stderr,
        )
        return EXIT_ERROR

    # Build the agent runner from --agent or use a no-op echo runner
    agent_runner = _build_agent_runner(args)

    try:
        result = await run_suite(
            suite_path,
            agent_runner=agent_runner,
            judge_runner=None,  # smoke-test mode: contains-only checks
        )
    except Exception as e:
        print(f"error: eval suite failed to run: {e}", file=sys.stderr)
        return EXIT_ERROR

    # Print human-readable report unless --quiet
    if not args.quiet:
        print(format_console_report(result))

    # JUnit XML output (for CI integration)
    if args.junit:
        junit_path = Path(args.junit)
        junit_path.parent.mkdir(parents=True, exist_ok=True)
        junit_path.write_text(result.to_junit_xml(), encoding="utf-8")
        if not args.quiet:
            print(f"[junit] Wrote {junit_path}")

    # JSON report output
    if args.json_out:
        json_path = Path(args.json_out)
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(
            json.dumps(result.to_dict(), indent=2),
            encoding="utf-8",
        )
        if not args.quiet:
            print(f"[json] Wrote {json_path}")

    # Decide on exit code based on --fail-under
    threshold = args.fail_under
    pass_rate = result.pass_rate
    if pass_rate < threshold:
        msg = (
            f"FAIL: pass-rate {pass_rate:.1%} below threshold "
            f"{threshold:.1%} ({result.passed_count}/{len(result.cases)})"
        )
        print(msg, file=sys.stderr)
        return EXIT_FAIL_UNDER

    if not args.quiet:
        print(
            f"OK: pass-rate {pass_rate:.1%} meets threshold "
            f"{threshold:.1%} ({result.passed_count}/{len(result.cases)})"
        )
    return EXIT_OK


def _build_agent_runner(args: argparse.Namespace):
    """Build an agent runner. If --agent is provided, load it; else use
    an echo runner suitable for smoke-testing the eval pipeline.

    The returned object is an **async callable** that takes a prompt
    string and returns the agent's answer string — matching the
    ``run_case(agent_runner=...)`` contract.
    """
    if not getattr(args, "agent", None):
        return _echo_runner
    spec = args.agent
    if spec.endswith(".yaml") or spec.endswith(".yml"):
        return _make_yaml_runner(Path(spec))
    if ":" in spec:
        module_path, attr = spec.split(":", 1)
        import importlib
        mod = importlib.import_module(module_path)
        return getattr(mod, attr)
    raise ValueError(
        f"agent spec must be 'module:callable' or *.yaml: {spec}"
    )


async def _echo_runner(prompt: str) -> str:
    """No-op runner that echoes the input. Useful for smoke-testing
    the eval pipeline without an LLM."""
    return prompt


def _make_yaml_runner(yaml_path: Path):
    """Build an async callable that runs prompts through an agent.yaml."""
    cache: dict = {}

    async def runner(prompt: str) -> str:
        if "agent" not in cache:
            from largestack._loaders.yaml_loader import load_agent_from_yaml
            cache["agent"] = load_agent_from_yaml(yaml_path)
        resp = await cache["agent"].run(prompt)
        return getattr(resp, "content", str(resp))

    return runner


# -------------------- studio-export command --------------------

async def _run_studio_export(args: argparse.Namespace) -> int:
    """Generate an HTML visualizer from an agent.yaml + optional audit log."""
    from largestack._studio import (
        StudioBuilder, NodeSpec, EdgeSpec, ComplianceMarker,
        from_audit_log_records,
    )

    agent_yaml = Path(args.agent)
    if not agent_yaml.exists():
        print(
            f"error: agent file not found: {agent_yaml}", file=sys.stderr,
        )
        return EXIT_ERROR

    try:
        import yaml
    except ImportError:
        print("error: PyYAML required for studio-export", file=sys.stderr)
        return EXIT_ERROR

    spec = yaml.safe_load(agent_yaml.read_text(encoding="utf-8"))
    if not isinstance(spec, dict):
        print(
            f"error: agent.yaml must be a mapping: {agent_yaml}",
            file=sys.stderr,
        )
        return EXIT_ERROR

    title = str(spec.get("name", "Agent"))
    description = str(spec.get("description", spec.get("instructions", "")))[:200]

    builder = StudioBuilder(title=title, description=description)

    # Build a minimal graph from agent.yaml: start → agent → end + tools
    builder.add_node(NodeSpec(id="start", label="Start", kind="start"))
    builder.add_node(NodeSpec(
        id="agent", label=title, kind="agent",
        description=str(spec.get("model", "")),
    ))
    builder.add_edge(EdgeSpec(source="start", target="agent"))

    tools = spec.get("tools") or []
    if isinstance(tools, list):
        for i, tool in enumerate(tools):
            tool_name = (
                tool if isinstance(tool, str)
                else tool.get("name", f"tool_{i}")
            )
            tid = f"tool_{i}"
            builder.add_node(NodeSpec(
                id=tid, label=str(tool_name), kind="tool",
            ))
            builder.add_edge(EdgeSpec(
                source="agent", target=tid, label="invoke",
            ))

    builder.add_node(NodeSpec(id="end", label="End", kind="end"))
    builder.add_edge(EdgeSpec(source="agent", target="end"))

    # Compliance markers from agent.yaml
    compliance = spec.get("compliance") or []
    if isinstance(compliance, list):
        for c in compliance:
            if isinstance(c, str):
                builder.add_compliance(ComplianceMarker(name=c))
            elif isinstance(c, dict):
                builder.add_compliance(ComplianceMarker(
                    name=str(c.get("name", "")),
                    section=str(c.get("section", "")),
                    notes=str(c.get("notes", "")),
                ))

    # Audit log
    if args.audit_log:
        audit_path = Path(args.audit_log)
        if audit_path.exists():
            try:
                records = json.loads(audit_path.read_text(encoding="utf-8"))
                if isinstance(records, list):
                    for ev in from_audit_log_records(records):
                        builder.add_audit_event(
                            timestamp=ev.timestamp,
                            agent=ev.agent,
                            event=ev.event,
                            payload=ev.payload,
                            tenant_id=ev.tenant_id,
                            user_id=ev.user_id,
                            duration_ms=ev.duration_ms,
                        )
            except Exception as e:
                print(
                    f"warning: could not read audit log: {e}",
                    file=sys.stderr,
                )

    out_path = Path(args.output)
    builder.export(out_path)
    if not args.quiet:
        print(f"[studio] Wrote {out_path.resolve()}")
    return EXIT_OK


# -------------------- Argument parser --------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="largestack",
        description="Largestack AI v0.12.0 — CLI",
    )
    sub = p.add_subparsers(dest="cmd")

    # eval-block
    eb = sub.add_parser(
        "eval-block",
        help="Run eval suite; exit non-zero if pass-rate < --fail-under",
    )
    eb.add_argument("suite", help="Path to eval suite YAML")
    eb.add_argument(
        "--fail-under", type=float, default=DEFAULT_FAIL_UNDER,
        help=f"Min pass rate to succeed (default: {DEFAULT_FAIL_UNDER})",
    )
    eb.add_argument(
        "--agent", default=None,
        help="Agent spec ('module:callable' or path to agent.yaml). "
             "If omitted, uses an echo runner for smoke testing.",
    )
    eb.add_argument("--junit", default=None, help="Path for JUnit XML")
    eb.add_argument("--json-out", default=None, help="Path for JSON report")
    eb.add_argument("--quiet", action="store_true")

    # studio-export
    se = sub.add_parser(
        "studio-export",
        help="Export an HTML Studio visualizer from agent.yaml",
    )
    se.add_argument("--agent", required=True, help="Path to agent.yaml")
    se.add_argument(
        "--output", "-o", required=True, help="Path for output HTML",
    )
    se.add_argument(
        "--audit-log", default=None,
        help="Optional path to a JSON array of audit events",
    )
    se.add_argument("--quiet", action="store_true")

    # compliance-check (v0.13)
    try:
        from largestack._cli.cli_v130_compliance import (
            add_compliance_check_parser,
        )
        add_compliance_check_parser(sub)
    except ImportError:
        pass  # v0.13 module not present in older installs

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.cmd == "eval-block":
        return asyncio.run(_run_eval_block(args))
    if args.cmd == "studio-export":
        return asyncio.run(_run_studio_export(args))
    if args.cmd == "compliance-check":
        from largestack._cli.cli_v130_compliance import run_from_args
        return run_from_args(args)

    parser.print_help()
    return EXIT_USAGE


if __name__ == "__main__":
    sys.exit(main())
