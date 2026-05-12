from largestack._guard.config import GuardrailConfig
from largestack._guard.policy import GuardrailAction, GuardrailMode
from largestack._guard.tool_policy import decide_tool_action


def test_read_tool_allowed():
    decision = decide_tool_action("read_document", {"path": "policy.md"})

    assert decision.allowed is True
    assert decision.action == GuardrailAction.ALLOW


def test_file_write_requires_approval():
    decision = decide_tool_action("write_file", {"path": "out.txt", "content": "ok"})

    assert decision.allowed is True
    assert decision.action == GuardrailAction.REQUIRE_APPROVAL


def test_delete_requires_approval_in_protect():
    decision = decide_tool_action(
        "delete_file",
        {"path": "out.txt"},
        config=GuardrailConfig(mode=GuardrailMode.PROTECT),
    )

    assert decision.action == GuardrailAction.REQUIRE_APPROVAL


def test_delete_blocks_in_strict():
    decision = decide_tool_action(
        "delete_file",
        {"path": "out.txt"},
        config=GuardrailConfig(mode=GuardrailMode.STRICT),
    )

    assert decision.allowed is False
    assert decision.action == GuardrailAction.BLOCK


def test_external_upload_of_secrets_blocks():
    decision = decide_tool_action(
        "upload_to_api",
        {"payload": {"api_key": "test_secret_value_1234567890"}},
    )

    assert decision.allowed is False
    assert decision.action == GuardrailAction.BLOCK


def test_payment_requires_maker_checker_in_strict_bfsi():
    decision = decide_tool_action(
        "payment_transfer",
        {"amount": 1000, "to": "acct"},
        config=GuardrailConfig(mode=GuardrailMode.STRICT, context="bfsi"),
    )

    assert decision.action == GuardrailAction.REQUIRE_APPROVAL
    assert decision.metadata["maker_checker"] is True
