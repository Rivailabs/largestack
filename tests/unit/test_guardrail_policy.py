from largestack._guard.policy import (
    GuardrailAction,
    GuardrailMode,
    GuardrailRiskType,
    GuardrailSeverity,
    allow,
    block,
    isolate,
    redact,
    require_approval,
    warn,
)


def test_guardrail_enum_values():
    assert [m.value for m in GuardrailMode] == [
        "observe",
        "warn",
        "protect",
        "strict",
        "custom",
    ]
    assert [a.value for a in GuardrailAction] == [
        "allow",
        "warn",
        "redact",
        "isolate",
        "require_approval",
        "block",
    ]
    assert [s.value for s in GuardrailSeverity] == [
        "low",
        "medium",
        "high",
        "critical",
    ]
    assert [r.value for r in GuardrailRiskType] == [
        "pii",
        "secret",
        "financial_data",
        "prompt_injection",
        "unsafe_tool",
        "external_exfiltration",
        "malware",
        "credential_theft",
        "illegal_abuse",
        "provider_routing_violation",
        "unknown",
    ]


def test_decision_constructor_allowed_semantics():
    decisions = [
        allow(),
        warn("warned"),
        redact("redacted", redacted_text="[REDACTED]"),
        isolate("isolated"),
        require_approval("approval needed"),
    ]

    assert all(d.allowed for d in decisions)
    assert decisions[0].action == GuardrailAction.ALLOW
    assert decisions[1].action == GuardrailAction.WARN
    assert decisions[2].action == GuardrailAction.REDACT
    assert decisions[2].redacted_text == "[REDACTED]"
    assert decisions[3].action == GuardrailAction.ISOLATE
    assert decisions[4].action == GuardrailAction.REQUIRE_APPROVAL


def test_block_constructor_disallows():
    decision = block(
        "blocked",
        risk_type=GuardrailRiskType.MALWARE,
        severity=GuardrailSeverity.CRITICAL,
    )

    assert decision.allowed is False
    assert decision.action == GuardrailAction.BLOCK
    assert decision.risk_type == GuardrailRiskType.MALWARE
    assert decision.severity == GuardrailSeverity.CRITICAL


def test_metadata_defaults_are_independent_empty_dicts():
    first = allow()
    second = warn("warned")

    assert first.metadata == {}
    assert second.metadata == {}
    first.metadata["x"] = 1
    assert second.metadata == {}
