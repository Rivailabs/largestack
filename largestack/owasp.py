"""OWASP coverage matrix — how largestack maps to the OWASP LLM Top 10 (2025) and
the OWASP Agentic-AI (ASI) threat categories.

This is an HONEST, machine-readable self-assessment of which framework controls
address which OWASP risk, including the gaps. It is documentation/inspection only —
not a runtime component. Pair it with the red-team eval (``largestack._test.redteam``)
which actually exercises the guardrails.

    from largestack.owasp import owasp_coverage, owasp_coverage_summary
    for item in owasp_coverage():
        print(item["id"], item["status"], item["controls"])
    print(owasp_coverage_summary())   # {"covered": .., "partial": .., "not_covered": ..}

Status values:
  covered     — a real largestack control directly addresses this risk
  partial     — partially addressed / heuristic / requires the caller to wire it
  not_covered — out of the framework's scope (caller/ops responsibility), stated plainly
"""

from __future__ import annotations
from dataclasses import dataclass, asdict

COVERED = "covered"
PARTIAL = "partial"
NOT_COVERED = "not_covered"

LLM_TOP_10 = "OWASP LLM Top 10 (2025)"
AGENTIC = "OWASP Agentic-AI (ASI) threats"


@dataclass(frozen=True)
class OwaspControl:
    id: str
    name: str
    category: str
    status: str
    controls: tuple[str, ...]  # largestack features that address it
    modules: tuple[str, ...]  # where they live
    notes: str


OWASP_COVERAGE: tuple[OwaspControl, ...] = (
    # ---- OWASP LLM Top 10 (2025) ----
    OwaspControl(
        "LLM01",
        "Prompt Injection",
        LLM_TOP_10,
        COVERED,
        (
            "InjectionGuard (pattern)",
            "PromptGuard 2 (optional ML)",
            "SecureRAGAgent pre-retrieval input guard",
        ),
        ("_guard/injection.py", "_guard/prompt_guard.py", "secure_rag.py"),
        "Regex/heuristic by default (PROTECT blocks on a single high-confidence pattern, or "
        ">=2 patterns); enable the 86M ML model via LARGESTACK_ENABLE_PROMPT_GUARD_ML=1 for stronger recall.",
    ),
    OwaspControl(
        "LLM02",
        "Sensitive Information Disclosure",
        LLM_TOP_10,
        COVERED,
        ("PIIGuard (input+output redact)", "trace-content redaction", "secret/key patterns"),
        ("_guard/pii.py", "_observe/traces_db.py", "_observe/log_redaction.py"),
        "PII + API-key/secret redaction on inputs, outputs and persisted traces. "
        "Separator-free numerics (bare SSN/account) need Presidio (LARGESTACK_ENABLE_PRESIDIO_PII=1).",
    ),
    OwaspControl(
        "LLM03",
        "Supply Chain",
        LLM_TOP_10,
        PARTIAL,
        (
            "SBOM generation (CycloneDX/SPDX, `largestack sbom`)",
            "CI: pip-audit + bandit + trivy + SBOM artifact",
            "PyPI Trusted Publishing (OIDC, attested)",
        ),
        (
            "_security/sbom.py",
            "_cli/commands.py",
            ".github/workflows/security.yml",
            ".github/workflows/release.yml",
        ),
        "SBOM + CVE/SAST/container scans run in CI and releases publish via Trusted Publishing "
        "(signed/attested). Remaining for 'covered': full hash-pinned lockfile + enabling the "
        "PyPI trusted-publisher (a one-time account setting). Build-time pin: constraints-release.txt.",
    ),
    OwaspControl(
        "LLM04",
        "Data and Model Poisoning",
        LLM_TOP_10,
        PARTIAL,
        ("MemoryIntegrityChecker", "RBAC/tenant-scoped memory"),
        ("_guard/memory_integrity.py", "_memory/long_term.py"),
        "Memory/context-poisoning checks exist; RAG ingestion is caller-controlled — validate "
        "your corpus upstream. Training-data poisoning is out of scope.",
    ),
    OwaspControl(
        "LLM05",
        "Improper Output Handling",
        LLM_TOP_10,
        PARTIAL,
        (
            "OutputSanitizer (opt-in helper)",
            "Output guardrails (check_output)",
            "CodeSandbox for generated code",
            "typed/structured output",
        ),
        (
            "_guard/output_sanitizer.py",
            "_core/engine.py",
            "_security/code_sandbox.py",
            "_core/structured.py",
        ),
        "`OutputSanitizer` neutralizes XSS/script/JS-URI/SQL/shell-meta but is OPT-IN: it is NOT in "
        "create_guardrails or the default Agent output path; it is applied automatically only by "
        "SecureRAGAgent (sanitize_output=True) or when you call it yourself. Output guardrails + typed "
        "validation do run on responses, and CodeSandbox isolates generated code. You must apply "
        "context-appropriate escaping at the final sink.",
    ),
    OwaspControl(
        "LLM06",
        "Excessive Agency",
        LLM_TOP_10,
        COVERED,
        (
            "tool_permissions allow/deny",
            "ToolAccessPolicy (rate+param)",
            "HITL approval",
            "max_turns",
            "cost_budget",
            "kill-switch",
        ),
        (
            "_core/tools.py",
            "_guard/tool_access.py",
            "_core/hitl.py",
            "_core/loop_guard.py",
            "_guard/kill_switch.py",
        ),
        "Tool gating is enforced in the run loop; HITL approval, turn caps, budgets and a "
        "kill-switch bound autonomy. The agentic ASI02/ASI03 controls below reinforce this.",
    ),
    OwaspControl(
        "LLM07",
        "System Prompt Leakage",
        LLM_TOP_10,
        PARTIAL,
        ("InjectionGuard (reveal-system-prompt patterns)", "output redaction"),
        ("_guard/injection.py", "_guard/pii.py"),
        "Injection patterns catch common 'reveal your system prompt' attacks and secrets are "
        "redacted from output; do not place secrets in the system prompt regardless.",
    ),
    OwaspControl(
        "LLM08",
        "Vector and Embedding Weaknesses",
        LLM_TOP_10,
        PARTIAL,
        ("RBAC/tenant isolation on stores", "vector-store filter-injection escaping"),
        ("_vectorstores/__init__.py", "_memory/vector_store.py", "_enterprise/rbac.py"),
        "Per-tenant scoping + escaped metadata filters (Redis/Milvus). Embedding-inversion / "
        "cross-tenant leakage hardening beyond access control is the deployment's responsibility.",
    ),
    OwaspControl(
        "LLM09",
        "Misinformation",
        LLM_TOP_10,
        COVERED,
        (
            "HallucinationGuard (groundedness)",
            "CitationEngine",
            "SecureRAGAgent grounded+cited answers",
        ),
        ("_guard/hallucination.py", "_core/citation_sandbox.py", "secure_rag.py"),
        "Groundedness scoring + citations against retrieved sources. Default 'fast' mode is a "
        "heuristic; NLI (DeBERTa) is opt-in via LARGESTACK_ENABLE_NLI_GUARD=1.",
    ),
    OwaspControl(
        "LLM10",
        "Unbounded Consumption",
        LLM_TOP_10,
        COVERED,
        (
            "cost_budget + BudgetExceededError",
            "LoopGuard (max_turns/fingerprint/timeout)",
            "rate limiting",
        ),
        ("_core/loop_guard.py", "_core/budget.py", "_ratelimit/__init__.py"),
        "Per-run cost ceiling, 5-layer loop termination, and token-bucket rate limiting bound "
        "cost/compute. (Cost-budget double-count was fixed in v1.1.1.)",
    ),
    # ---- OWASP Agentic-AI (ASI) threats ----
    OwaspControl(
        "ASI02",
        "Tool / Function Misuse",
        AGENTIC,
        COVERED,
        (
            "ToolAccessPolicy (allow/deny + rate + fullmatch param validation)",
            "tool_permissions",
            "approval gating",
        ),
        ("_guard/tool_access.py", "_core/tools.py"),
        "Now enforced in ToolExecutor (v1.1.1); parameter rules use re.fullmatch to stop "
        "argument injection. Treat tool args as untrusted — never pass to a shell.",
    ),
    OwaspControl(
        "ASI03",
        "Identity & Privilege Abuse",
        AGENTIC,
        COVERED,
        ("RBAC (roles/permissions, wildcard, tenant)", "AgentIdentityManager", "audit of denials"),
        ("_enterprise/rbac.py", "_guard/agent_identity.py", "_enterprise/audit.py"),
        "RBAC enforces (401/403, behavioral bypass test); SecureRAGAgent gates queries by permission.",
    ),
    OwaspControl(
        "ASI06",
        "Memory & Context Poisoning",
        AGENTIC,
        PARTIAL,
        ("MemoryIntegrityChecker (validate + hash)",),
        ("_guard/memory_integrity.py",),
        "Heuristic injection/length checks + content hashing on memory writes; not a complete "
        "provenance system.",
    ),
    OwaspControl(
        "ASI07",
        "Insecure Inter-Agent Communication",
        AGENTIC,
        PARTIAL,
        ("InterAgentAuth (HMAC-signed messages, nonce replay-protection) — OPT-IN primitive",),
        ("_guard/inter_agent_auth.py",),
        "HMAC-SHA256 message signing is available (public default secret removed, nonce set bounded), "
        "but it is NOT wired into the default multi-agent handoff path (Team/Swarm pass plain "
        "messages) — you must adopt it explicitly and set LARGESTACK_INTER_AGENT_SECRET. Partial "
        "until it's the default transport.",
    ),
    OwaspControl(
        "ASI-SSRF",
        "Server-Side Request Forgery (agent tools)",
        AGENTIC,
        COVERED,
        ("NetworkPolicy (name + resolved-IP deny, public_only preset)",),
        ("_security/network.py",),
        "v1.1.1: blocks internal hosts by name (localhost/*.internal/*.local) and validates "
        "resolved IPs against deny ranges (defeats DNS-rebinding to metadata endpoints).",
    ),
    OwaspControl(
        "ASI-AUDIT",
        "Repudiation / Insufficient Audit",
        AGENTIC,
        COVERED,
        ("AuditTrail (HMAC-keyed hash chain)", "per-run trace + audit row", "OTel spans"),
        ("_enterprise/audit.py", "_enterprise/siem.py", "_core/engine.py", "_observe/*"),
        "v1.1.1: audit chain is HMAC-keyed (key held outside the DB) so DB-only tampering is "
        "detected, and `SiemExporter` (`largestack siem-export`) streams it to syslog/CEF/LEEF/"
        "webhook for your SIEM.",
    ),
    OwaspControl(
        "ASI-SANDBOX",
        "Unsafe Code Execution",
        AGENTIC,
        PARTIAL,
        (
            "CodeSandbox (env-scrubbed subprocess + AST import allowlist)",
            "E2B backend for real isolation",
        ),
        ("_security/code_sandbox.py", "_core/e2b_sandbox.py"),
        "v1.1.1: default subprocess scrubs the parent env and uses AST-based import control. "
        "It has NO kernel isolation — use backend='e2b' (Firecracker microVMs) for untrusted code.",
    ),
)


def owasp_coverage() -> list[dict]:
    """Return the coverage matrix as a list of plain dicts (JSON-serializable)."""
    return [asdict(c) for c in OWASP_COVERAGE]


def owasp_coverage_summary() -> dict:
    """Counts by status + by category."""
    summary = {COVERED: 0, PARTIAL: 0, NOT_COVERED: 0, "total": len(OWASP_COVERAGE)}
    for c in OWASP_COVERAGE:
        summary[c.status] = summary.get(c.status, 0) + 1
    return summary


def render_markdown() -> str:
    """Render the matrix as a Markdown table (used to keep the docs page honest)."""
    icon = {COVERED: "✅ covered", PARTIAL: "⚠️ partial", NOT_COVERED: "❌ not covered"}
    lines = ["| ID | Risk | Status | largestack controls | Notes |", "|---|---|---|---|---|"]
    cat = None
    for c in OWASP_COVERAGE:
        if c.category != cat:
            cat = c.category
            lines.append(f"| | **{cat}** | | | |")
        controls = "; ".join(c.controls)
        lines.append(
            f"| {c.id} | {c.name} | {icon.get(c.status, c.status)} | {controls} | {c.notes} |"
        )
    s = owasp_coverage_summary()
    lines.append("")
    lines.append(
        f"_Summary: {s[COVERED]} covered, {s[PARTIAL]} partial, "
        f"{s[NOT_COVERED]} not-covered, of {s['total']} mapped risks._"
    )
    return "\n".join(lines)


if __name__ == "__main__":
    print(render_markdown())
