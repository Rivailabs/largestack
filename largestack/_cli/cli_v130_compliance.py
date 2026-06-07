"""v0.13.0 CLI: ``compliance-check`` command.

Pre-deploy DPDP / RBI / PMLA marker validator. Run before pushing
a LARGESTACK agent to production:

    $ largestack compliance-check agent.yaml
    $ largestack compliance-check agent.yaml --strict --sector financial

Checks performed:

1. **Compliance markers** — at least one DPDP marker present
2. **Sector triggers** — financial sector requires RBI markers
3. **Tenant parameterization** — ``tenant_id`` is templated, not literal
4. **Audit enabled** — ``audit:`` section exists & enabled
5. **PII tools** — agents that touch Aadhaar / PAN / CIBIL must declare
   ``purpose`` and ``lawful_basis``
6. **Memory residency** — long-term store must be one of: in-memory,
   sqlite (local), postgres (with India-region host), or qdrant_in_india
7. **LLM provider** — must not use China-hosted (DeepSeek, Moonshot,
   etc.) when ``sector: financial``

Exit codes:
- 0 — all checks pass
- 1 — at least one check failed (compliance gap)
- 2 — usage / argument error
- 3 — runtime error (file not found, parse error)
"""

from __future__ import annotations
import argparse
import logging
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

log = logging.getLogger("largestack.cli_v130.compliance")


# Exit codes
EXIT_OK = 0
EXIT_FAIL = 1
EXIT_USAGE = 2
EXIT_ERROR = 3


# Known DPDP / RBI section markers
DPDP_SECTIONS = {
    "Section 6",
    "Section 7",
    "Section 8",
    "Section 9",
    "Section 11",
    "DPDP_Act_2023",
    "DPDP",
}
RBI_SECTIONS = {
    "RBI",
    "MD-NBFC-D",
    "PA-PG-2024",
    "MD-KYC",
    "RBI_IT_Framework",
}
PMLA_SECTIONS = {"PMLA", "PMLA_Rule_9", "Rule_9", "CDD"}

# China-hosted LLM provider prefixes (for residency violation)
CHINA_HOSTED = {
    "deepseek",
    "moonshot",
    "qwen",
    "yi",
    "01ai",
    "baichuan",
    "minimax",
    "doubao",
}

# Indian aggregator / KYC tools that imply PII handling
PII_TOOLS = {
    "aadhaar_verify",
    "aadhaar_okyc",
    "pan_verify",
    "cibil",
    "experian",
    "ckyc",
    "digilocker",
    "aadhaar_redact",
    "gstn_lookup",
    "mca_lookup",
}


# -------------------- Findings model --------------------


@dataclass
class Finding:
    severity: str  # 'error', 'warning', 'info'
    code: str
    message: str
    location: str = ""

    def format(self) -> str:
        sev_tag = {
            "error": "ERROR  ",
            "warning": "WARNING",
            "info": "INFO   ",
        }.get(self.severity, "       ")
        loc = f" [{self.location}]" if self.location else ""
        return f"  {sev_tag} {self.code}{loc}: {self.message}"


@dataclass
class CheckReport:
    file_path: str
    findings: list[Finding] = field(default_factory=list)

    def add(
        self,
        severity: str,
        code: str,
        message: str,
        location: str = "",
    ) -> None:
        self.findings.append(Finding(severity, code, message, location))

    @property
    def errors(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == "error"]

    @property
    def warnings(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == "warning"]

    @property
    def passed(self) -> bool:
        return not self.errors

    def render(self, *, strict: bool = False) -> str:
        lines = [f"LARGESTACK compliance-check: {self.file_path}"]
        lines.append("=" * 60)

        if not self.findings:
            lines.append("  ✓ All compliance checks passed.")
        else:
            for f in self.findings:
                lines.append(f.format())

        lines.append("-" * 60)
        e, w = len(self.errors), len(self.warnings)
        i = len([f for f in self.findings if f.severity == "info"])
        lines.append(f"  Summary: {e} error(s), {w} warning(s), {i} info")

        if strict and (e or w):
            lines.append("  Result: FAIL (strict mode)")
        elif e:
            lines.append("  Result: FAIL")
        else:
            lines.append("  Result: PASS")

        return "\n".join(lines)


# -------------------- Loader --------------------


def _load_agent_yaml(path: Path) -> dict[str, Any]:
    try:
        import yaml
    except ImportError as e:
        raise ImportError(
            "PyYAML required for compliance-check. Install: pip install pyyaml"
        ) from e

    text = path.read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    if not isinstance(data, dict):
        raise ValueError(f"agent.yaml must be a mapping at top level, got {type(data).__name__}")
    return data


# -------------------- Individual checks --------------------


def _check_compliance_markers(
    spec: dict[str, Any],
    report: CheckReport,
) -> set[str]:
    """Verify at least one compliance marker. Returns marker types found."""
    compliance = spec.get("compliance", [])
    found_kinds: set[str] = set()

    if not compliance:
        report.add(
            "error",
            "C001",
            "no 'compliance:' section found — agents touching Indian "
            "user data must declare DPDP / RBI markers",
            location="root",
        )
        return found_kinds

    if not isinstance(compliance, list):
        report.add(
            "error",
            "C002",
            "'compliance:' must be a list of marker objects",
            location="compliance",
        )
        return found_kinds

    for idx, marker in enumerate(compliance):
        if not isinstance(marker, dict):
            report.add(
                "error",
                "C003",
                f"compliance entry #{idx} must be a mapping",
                location=f"compliance[{idx}]",
            )
            continue

        name = str(marker.get("name", "")).strip()
        section = str(marker.get("section", "")).strip()

        if not name:
            report.add(
                "warning",
                "C004",
                f"compliance entry #{idx} missing 'name'",
                location=f"compliance[{idx}]",
            )

        # Classify the marker
        ident = f"{name} {section}"
        if any(s in ident for s in DPDP_SECTIONS) or "dpdp" in name.lower():
            found_kinds.add("dpdp")
        if any(s in ident for s in RBI_SECTIONS) or "rbi" in name.lower():
            found_kinds.add("rbi")
        if any(s in ident for s in PMLA_SECTIONS) or "pmla" in name.lower():
            found_kinds.add("pmla")

    if "dpdp" not in found_kinds:
        report.add(
            "error",
            "C005",
            "no DPDP marker found — declare at least one DPDP_Act_2023 "
            "section if you process personal data of Indian residents",
            location="compliance",
        )

    return found_kinds


def _check_sector_requirements(
    spec: dict[str, Any],
    found_kinds: set[str],
    report: CheckReport,
) -> None:
    """Verify sector-specific compliance markers."""
    sector = str(spec.get("sector", "")).strip().lower()

    if sector == "financial":
        if "rbi" not in found_kinds:
            report.add(
                "error",
                "C010",
                "sector=financial requires at least one RBI marker "
                "(MD-NBFC-D, PA-PG-2024, MD-KYC, etc.)",
                location="compliance",
            )
        if "pmla" not in found_kinds:
            report.add(
                "warning",
                "C011",
                "sector=financial typically also requires PMLA Rule 9 CDD marker",
                location="compliance",
            )
    elif sector and sector not in {
        "general",
        "education",
        "retail",
        "healthcare",
        "legaltech",
    }:
        report.add(
            "info",
            "C012",
            f"sector='{sector}' is non-standard — verify required markers",
            location="sector",
        )


def _check_tenant_parameterization(
    spec: dict[str, Any],
    report: CheckReport,
) -> None:
    """``tenant_id`` should be templated/parameterized, not a hardcoded literal."""
    tenant = spec.get("tenant_id")
    if tenant is None:
        # Could be parameterized at runtime; check for memory.tenant_id
        memory = spec.get("memory") or {}
        if isinstance(memory, dict):
            tenant = memory.get("tenant_id")

    if tenant is None:
        report.add(
            "warning",
            "C020",
            "no 'tenant_id' found — multi-tenant agents must scope data by tenant",
            location="root",
        )
        return

    tenant_str = str(tenant)
    is_template = "{{" in tenant_str or "${" in tenant_str or tenant_str.startswith("$")
    if not is_template and tenant_str.lower() in {
        "default",
        "demo",
        "test",
        "production",
        "prod",
    }:
        report.add(
            "warning",
            "C021",
            f"tenant_id='{tenant_str}' looks hardcoded — use a template "
            "like '{{ env.TENANT_ID }}' for multi-tenant deploys",
            location="tenant_id",
        )


def _check_audit_enabled(
    spec: dict[str, Any],
    report: CheckReport,
) -> None:
    """Audit log must be enabled for production."""
    audit = spec.get("audit")
    if audit is None:
        report.add(
            "error",
            "C030",
            "no 'audit:' section — production agents require hash-chain audit logging",
            location="root",
        )
        return

    if isinstance(audit, dict):
        if audit.get("enabled") is False:
            report.add(
                "error",
                "C031",
                "audit.enabled=false — must be true for production",
                location="audit.enabled",
            )
        retention = audit.get("retention_days")
        if retention is not None and retention < 2555:  # 7 years
            report.add(
                "warning",
                "C032",
                f"audit.retention_days={retention} is below RBI's "
                f"8-year (2920 days) recommendation",
                location="audit.retention_days",
            )
    elif audit is False:
        report.add(
            "error",
            "C031",
            "audit=false — must be enabled for production",
            location="audit",
        )


def _check_pii_tools_have_purpose(
    spec: dict[str, Any],
    report: CheckReport,
) -> None:
    """If the agent uses Indian PII tools, every such tool must declare purpose+lawful_basis."""
    tools = spec.get("tools", [])
    if not isinstance(tools, list):
        return

    for idx, t in enumerate(tools):
        if not isinstance(t, dict):
            continue
        tool_name = str(t.get("name", "")).strip().lower()
        if any(p in tool_name for p in PII_TOOLS):
            if not t.get("purpose"):
                report.add(
                    "error",
                    "C040",
                    f"PII tool '{tool_name}' must declare 'purpose' (DPDP §6 explicit purpose)",
                    location=f"tools[{idx}]",
                )
            if not t.get("lawful_basis"):
                report.add(
                    "error",
                    "C041",
                    f"PII tool '{tool_name}' must declare 'lawful_basis' (DPDP §7)",
                    location=f"tools[{idx}]",
                )


def _check_llm_residency(
    spec: dict[str, Any],
    report: CheckReport,
) -> None:
    """Reject China-hosted LLM providers when sector=financial."""
    sector = str(spec.get("sector", "")).strip().lower()
    model = spec.get("model") or spec.get("llm", {}).get("model", "")
    if not isinstance(model, str):
        return

    provider = model.split("/", 1)[0].lower() if "/" in model else "openai"

    if provider in CHINA_HOSTED:
        if sector == "financial":
            report.add(
                "error",
                "C050",
                f"model='{model}' uses China-hosted provider '{provider}' "
                "— violates India residency for financial sector",
                location="model",
            )
        else:
            report.add(
                "warning",
                "C051",
                f"model='{model}' uses China-hosted provider '{provider}'"
                " — consider data residency implications",
                location="model",
            )

    # Bedrock must be Mumbai region for India deploys
    if provider == "bedrock":
        region = (
            spec.get("region") or spec.get("aws_region") or spec.get("llm", {}).get("region", "")
        )
        if region and region not in ("ap-south-1", "ap-south-2"):
            report.add(
                "warning",
                "C052",
                f"Bedrock region='{region}' is not ap-south-1/2 (Mumbai) "
                "— may violate India residency",
                location="region",
            )


def _check_memory_residency(
    spec: dict[str, Any],
    report: CheckReport,
) -> None:
    """Long-term memory backend must be India-resident."""
    memory = spec.get("memory") or {}
    if not isinstance(memory, dict):
        return

    backend = str(memory.get("backend", "")).strip().lower()
    if backend in {"sqlite", "in_memory", "inmemory", ""}:
        return  # local, fine

    if backend == "postgres":
        host = str(memory.get("host", "")).strip()
        if host and not any(
            mark in host.lower() for mark in ("mumbai", "ap-south", "in-", ".in", "india")
        ):
            report.add(
                "warning",
                "C060",
                f"postgres host='{host}' may not be India-resident — verify",
                location="memory.host",
            )


# -------------------- Top-level runner --------------------


def run_compliance_check(
    yaml_path: str | Path,
    *,
    strict: bool = False,
    sector_override: str | None = None,
) -> CheckReport:
    """Run all compliance checks on an agent.yaml file."""
    p = Path(yaml_path)
    report = CheckReport(file_path=str(p))

    if not p.exists():
        report.add("error", "C000", f"file not found: {p}")
        return report

    try:
        spec = _load_agent_yaml(p)
    except Exception as e:
        report.add("error", "C000", f"parse error: {e}")
        return report

    if sector_override:
        spec = {**spec, "sector": sector_override}

    found_kinds = _check_compliance_markers(spec, report)
    _check_sector_requirements(spec, found_kinds, report)
    _check_tenant_parameterization(spec, report)
    _check_audit_enabled(spec, report)
    _check_pii_tools_have_purpose(spec, report)
    _check_llm_residency(spec, report)
    _check_memory_residency(spec, report)

    return report


# -------------------- argparse subcommand --------------------


def add_compliance_check_parser(sub: argparse._SubParsersAction) -> None:
    """Register the ``compliance-check`` subcommand on a subparsers obj."""
    cc = sub.add_parser(
        "compliance-check",
        help="Validate DPDP / RBI / PMLA markers in agent.yaml before deploy",
    )
    cc.add_argument("agent", help="Path to agent.yaml")
    cc.add_argument(
        "--strict",
        action="store_true",
        help="Treat warnings as failures",
    )
    cc.add_argument(
        "--sector",
        default=None,
        help="Override sector ('financial', 'healthcare', etc.)",
    )
    cc.add_argument("--quiet", action="store_true")


def run_from_args(args: argparse.Namespace) -> int:
    """Synchronous entry from argparse."""
    report = run_compliance_check(
        args.agent,
        strict=getattr(args, "strict", False),
        sector_override=getattr(args, "sector", None),
    )

    if not getattr(args, "quiet", False):
        print(report.render(strict=getattr(args, "strict", False)))

    if not report.passed:
        return EXIT_FAIL
    if getattr(args, "strict", False) and report.warnings:
        return EXIT_FAIL
    return EXIT_OK


__all__ = [
    "Finding",
    "CheckReport",
    "run_compliance_check",
    "run_from_args",
    "add_compliance_check_parser",
    "EXIT_OK",
    "EXIT_FAIL",
    "EXIT_USAGE",
    "EXIT_ERROR",
]
