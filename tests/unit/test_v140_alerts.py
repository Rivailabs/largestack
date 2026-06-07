"""v0.14.0: Tests for eval webhook alerts."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


def _delta_with_regression():
    from largestack._eval.pr_diff import compute_eval_delta

    return compute_eval_delta(
        {
            "summary": {"pass_rate": 0.94, "passed": 47, "total": 50},
            "cases": [
                {"name": "kyc_pan", "passed": True},
                {"name": "kyc_aadhaar", "passed": True},
            ],
        },
        {
            "summary": {"pass_rate": 0.87, "passed": 43, "total": 50},
            "cases": [
                {"name": "kyc_pan", "passed": True},
                {"name": "kyc_aadhaar", "passed": False},  # regression
            ],
        },
    )


def _delta_no_change():
    from largestack._eval.pr_diff import compute_eval_delta

    same = {
        "summary": {"pass_rate": 0.94, "passed": 47, "total": 50},
        "cases": [{"name": "c1", "passed": True}],
    }
    return compute_eval_delta(same, same)


# -------------------- build_payload --------------------


def test_slack_payload_has_blocks():
    from largestack._eval.alerts import build_payload

    p = build_payload("slack", _delta_with_regression(), "KYC")
    assert "blocks" in p
    assert "text" in p  # fallback text
    assert any(b.get("type") == "header" for b in p["blocks"])


def test_slack_payload_includes_regressions():
    from largestack._eval.alerts import build_payload

    p = build_payload("slack", _delta_with_regression(), "KYC")
    blocks = json.dumps(p) if False else p["blocks"]  # noqa
    text_dump = " ".join(str(b.get("text", {}).get("text", "")) for b in p["blocks"])
    assert "kyc_aadhaar" in text_dump


def test_teams_payload_messagecard_format():
    from largestack._eval.alerts import build_payload

    p = build_payload("teams", _delta_with_regression(), "KYC")
    assert p["@type"] == "MessageCard"
    assert "themeColor" in p
    assert "sections" in p


def test_discord_payload_embeds_format():
    from largestack._eval.alerts import build_payload

    p = build_payload("discord", _delta_with_regression(), "KYC")
    assert "embeds" in p
    assert isinstance(p["embeds"], list) and p["embeds"]
    assert "fields" in p["embeds"][0]


def test_generic_payload_machine_readable():
    from largestack._eval.alerts import build_payload

    p = build_payload("generic", _delta_with_regression(), "KYC")
    assert p["type"] == "largestack.eval.result"
    assert p["is_regression"] is True
    assert "kyc_aadhaar" in p["regressions"]
    assert "markdown_summary" in p


def test_unknown_kind_raises():
    from largestack._eval.alerts import build_payload

    with pytest.raises(ValueError, match="unknown"):
        build_payload("xmpp", _delta_with_regression(), "KYC")


# -------------------- notify_eval_result --------------------


def test_only_on_regression_skips_when_clean():
    from largestack._eval.alerts import (
        AlertChannel,
        notify_eval_result,
    )

    delta = _delta_no_change()
    ch = AlertChannel(kind="slack", url="https://hooks.slack.com/test")

    # Should NOT POST
    with patch("urllib.request.urlopen") as mock_urlopen:
        result = notify_eval_result(
            delta,
            suite_name="KYC",
            channel=ch,
            only_on_regression=True,
        )
    mock_urlopen.assert_not_called()
    assert not result.sent


def test_only_on_change_skips_when_unchanged():
    from largestack._eval.alerts import AlertChannel, notify_eval_result

    delta = _delta_no_change()
    ch = AlertChannel(kind="slack", url="https://hooks.slack.com/x")

    with patch("urllib.request.urlopen") as mock_urlopen:
        result = notify_eval_result(
            delta,
            suite_name="KYC",
            channel=ch,
            only_on_change=True,
        )
    mock_urlopen.assert_not_called()
    assert not result.sent


def test_post_invoked_for_regression():
    from largestack._eval.alerts import AlertChannel, notify_eval_result

    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.__enter__ = lambda self: self
    mock_response.__exit__ = lambda *a: None

    delta = _delta_with_regression()
    ch = AlertChannel(kind="slack", url="https://hooks.slack.com/x")

    with patch("urllib.request.urlopen", return_value=mock_response) as m:
        result = notify_eval_result(
            delta,
            suite_name="KYC",
            channel=ch,
            only_on_regression=True,
        )

    assert result.sent
    assert result.status_code == 200
    m.assert_called_once()


def test_post_handles_http_error():
    import urllib.error
    from largestack._eval.alerts import AlertChannel, notify_eval_result

    delta = _delta_with_regression()
    ch = AlertChannel(kind="slack", url="https://hooks.slack.com/bad")

    err = urllib.error.HTTPError(
        ch.url,
        500,
        "server err",
        {},
        None,
    )
    with patch("urllib.request.urlopen", side_effect=err):
        result = notify_eval_result(
            delta,
            suite_name="KYC",
            channel=ch,
        )

    assert not result.sent
    assert result.status_code == 500


def test_post_handles_network_error():
    import urllib.error
    from largestack._eval.alerts import AlertChannel, notify_eval_result

    delta = _delta_with_regression()
    ch = AlertChannel(kind="slack", url="https://nope.invalid/x")

    with patch(
        "urllib.request.urlopen",
        side_effect=urllib.error.URLError("connection refused"),
    ):
        result = notify_eval_result(
            delta,
            suite_name="KYC",
            channel=ch,
        )
    assert not result.sent
    assert "refused" in result.error


# -------------------- notify_eval_result_async --------------------


@pytest.mark.asyncio
async def test_async_notify_uses_thread_when_aiohttp_unavailable():
    """Falls back to sync POST in a thread if aiohttp not installed."""
    from largestack._eval.alerts import (
        AlertChannel,
        notify_eval_result_async,
    )

    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.__enter__ = lambda self: self
    mock_response.__exit__ = lambda *a: None

    delta = _delta_with_regression()
    ch = AlertChannel(kind="slack", url="https://hooks.slack.com/x")

    with patch.dict("sys.modules", {"aiohttp": None}):
        with patch("urllib.request.urlopen", return_value=mock_response):
            result = await notify_eval_result_async(
                delta,
                suite_name="KYC",
                channel=ch,
            )
    assert result.sent
    assert result.status_code == 200


# -------------------- Headers --------------------


def test_custom_headers_passed_through():
    from largestack._eval.alerts import AlertChannel, notify_eval_result

    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.__enter__ = lambda self: self
    mock_response.__exit__ = lambda *a: None

    delta = _delta_with_regression()
    ch = AlertChannel(
        kind="generic",
        url="https://my-hook.example/x",
        headers={"X-Auth-Token": "secret"},
    )

    with patch("urllib.request.urlopen", return_value=mock_response) as m:
        notify_eval_result(delta, suite_name="X", channel=ch)

    req_obj = m.call_args[0][0]
    # Verify our custom header is in the Request
    assert req_obj.get_header("X-auth-token") == "secret"


import json  # noqa
