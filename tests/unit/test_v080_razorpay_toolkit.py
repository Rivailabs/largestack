"""v0.8.0: Razorpay Toolkit tests."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import pytest

respx = pytest.importorskip("respx")


def test_toolkit_exposes_8_tools(monkeypatch):
    monkeypatch.setenv("LARGESTACK_RAZORPAY_KEY_ID", "rzp_test_x")
    monkeypatch.setenv("LARGESTACK_RAZORPAY_KEY_SECRET", "secret_x")
    from largestack._integrations.razorpay_toolkit import RazorpayToolkit

    tk = RazorpayToolkit()
    tools = tk.get_tools()
    assert len(tools) == 8
    assert len(tk) == 8


def test_no_creds_warning():
    """Without key_id/secret, calls return a clear error string."""
    from largestack._integrations.razorpay_toolkit import RazorpayToolkit
    import os

    os.environ.pop("LARGESTACK_RAZORPAY_KEY_ID", None)
    os.environ.pop("LARGESTACK_RAZORPAY_KEY_SECRET", None)
    tk = RazorpayToolkit(key_id="", key_secret="")
    assert tk._auth_header == {}


# -------------------- Create order --------------------


@pytest.mark.asyncio
async def test_create_order_success(monkeypatch):
    monkeypatch.setenv("LARGESTACK_RAZORPAY_KEY_ID", "k")
    monkeypatch.setenv("LARGESTACK_RAZORPAY_KEY_SECRET", "s")
    from largestack._integrations.razorpay_toolkit import RazorpayToolkit

    tk = RazorpayToolkit()
    create_order = next(
        t for t in tk.get_tools() if t._tool_schema["name"] == "razorpay_create_order"
    )

    fake_resp = {
        "id": "order_abc123",
        "amount": 50000,
        "currency": "INR",
        "status": "created",
    }
    with respx.mock() as mock:
        route = mock.post("https://api.razorpay.com/v1/orders").respond(200, json=fake_resp)
        out = await create_order(amount_paise=50000, receipt="rcpt_001")

    body = json.loads(route.calls.last.request.content)
    assert body["amount"] == 50000
    assert body["currency"] == "INR"
    assert body["receipt"] == "rcpt_001"

    assert json.loads(out)["id"] == "order_abc123"


@pytest.mark.asyncio
async def test_create_order_validates_amount(monkeypatch):
    monkeypatch.setenv("LARGESTACK_RAZORPAY_KEY_ID", "k")
    monkeypatch.setenv("LARGESTACK_RAZORPAY_KEY_SECRET", "s")
    from largestack._integrations.razorpay_toolkit import RazorpayToolkit

    tk = RazorpayToolkit()
    create_order = next(
        t for t in tk.get_tools() if t._tool_schema["name"] == "razorpay_create_order"
    )
    out = await create_order(amount_paise=-100)
    assert "positive integer" in out
    out = await create_order(amount_paise=0)
    assert "positive integer" in out


@pytest.mark.asyncio
async def test_create_order_validates_receipt(monkeypatch):
    monkeypatch.setenv("LARGESTACK_RAZORPAY_KEY_ID", "k")
    monkeypatch.setenv("LARGESTACK_RAZORPAY_KEY_SECRET", "s")
    from largestack._integrations.razorpay_toolkit import RazorpayToolkit

    tk = RazorpayToolkit()
    create_order = next(
        t for t in tk.get_tools() if t._tool_schema["name"] == "razorpay_create_order"
    )
    # Whitespace is invalid
    out = await create_order(amount_paise=100, receipt="bad receipt!")
    assert "alphanumeric" in out


@pytest.mark.asyncio
async def test_create_order_no_creds_returns_error():
    """Without env vars, the tool returns a clear error string."""
    import os

    os.environ.pop("LARGESTACK_RAZORPAY_KEY_ID", None)
    os.environ.pop("LARGESTACK_RAZORPAY_KEY_SECRET", None)
    from largestack._integrations.razorpay_toolkit import RazorpayToolkit

    tk = RazorpayToolkit(key_id="", key_secret="")
    create_order = next(
        t for t in tk.get_tools() if t._tool_schema["name"] == "razorpay_create_order"
    )
    out = await create_order(amount_paise=100)
    assert "credentials not set" in out


# -------------------- Fetch order/payment --------------------


@pytest.mark.asyncio
async def test_fetch_order(monkeypatch):
    monkeypatch.setenv("LARGESTACK_RAZORPAY_KEY_ID", "k")
    monkeypatch.setenv("LARGESTACK_RAZORPAY_KEY_SECRET", "s")
    from largestack._integrations.razorpay_toolkit import RazorpayToolkit

    tk = RazorpayToolkit()
    fetch_order = next(
        t for t in tk.get_tools() if t._tool_schema["name"] == "razorpay_fetch_order"
    )
    with respx.mock() as mock:
        mock.get("https://api.razorpay.com/v1/orders/order_xyz").respond(
            200, json={"id": "order_xyz", "status": "paid"}
        )
        out = await fetch_order(order_id="order_xyz")
    assert json.loads(out)["status"] == "paid"


@pytest.mark.asyncio
async def test_fetch_order_validates_id(monkeypatch):
    monkeypatch.setenv("LARGESTACK_RAZORPAY_KEY_ID", "k")
    monkeypatch.setenv("LARGESTACK_RAZORPAY_KEY_SECRET", "s")
    from largestack._integrations.razorpay_toolkit import RazorpayToolkit

    tk = RazorpayToolkit()
    fetch_order = next(
        t for t in tk.get_tools() if t._tool_schema["name"] == "razorpay_fetch_order"
    )
    out = await fetch_order(order_id="not_an_order")
    assert "must start with" in out


@pytest.mark.asyncio
async def test_fetch_payment(monkeypatch):
    monkeypatch.setenv("LARGESTACK_RAZORPAY_KEY_ID", "k")
    monkeypatch.setenv("LARGESTACK_RAZORPAY_KEY_SECRET", "s")
    from largestack._integrations.razorpay_toolkit import RazorpayToolkit

    tk = RazorpayToolkit()
    fetch_payment = next(
        t for t in tk.get_tools() if t._tool_schema["name"] == "razorpay_fetch_payment"
    )
    with respx.mock() as mock:
        mock.get("https://api.razorpay.com/v1/payments/pay_abc").respond(
            200, json={"id": "pay_abc", "status": "captured", "amount": 50000}
        )
        out = await fetch_payment(payment_id="pay_abc")
    assert json.loads(out)["status"] == "captured"


# -------------------- Refund --------------------


@pytest.mark.asyncio
async def test_refund_payment_partial(monkeypatch):
    monkeypatch.setenv("LARGESTACK_RAZORPAY_KEY_ID", "k")
    monkeypatch.setenv("LARGESTACK_RAZORPAY_KEY_SECRET", "s")
    from largestack._integrations.razorpay_toolkit import RazorpayToolkit

    tk = RazorpayToolkit()
    refund = next(t for t in tk.get_tools() if t._tool_schema["name"] == "razorpay_refund_payment")
    with respx.mock() as mock:
        route = mock.post("https://api.razorpay.com/v1/payments/pay_x/refund").respond(
            200, json={"id": "rfnd_y", "status": "processed", "amount": 25000}
        )
        out = await refund(payment_id="pay_x", amount_paise=25000)
    body = json.loads(route.calls.last.request.content)
    assert body["amount"] == 25000
    assert body["speed"] == "normal"
    assert json.loads(out)["status"] == "processed"


@pytest.mark.asyncio
async def test_refund_payment_full(monkeypatch):
    """No amount → full refund (don't include amount in body)."""
    monkeypatch.setenv("LARGESTACK_RAZORPAY_KEY_ID", "k")
    monkeypatch.setenv("LARGESTACK_RAZORPAY_KEY_SECRET", "s")
    from largestack._integrations.razorpay_toolkit import RazorpayToolkit

    tk = RazorpayToolkit()
    refund = next(t for t in tk.get_tools() if t._tool_schema["name"] == "razorpay_refund_payment")
    with respx.mock() as mock:
        route = mock.post("https://api.razorpay.com/v1/payments/pay_x/refund").respond(
            200, json={"id": "rfnd_y", "status": "processed"}
        )
        await refund(payment_id="pay_x")
    body = json.loads(route.calls.last.request.content)
    assert "amount" not in body  # full refund — no amount specified


@pytest.mark.asyncio
async def test_refund_validates_speed(monkeypatch):
    monkeypatch.setenv("LARGESTACK_RAZORPAY_KEY_ID", "k")
    monkeypatch.setenv("LARGESTACK_RAZORPAY_KEY_SECRET", "s")
    from largestack._integrations.razorpay_toolkit import RazorpayToolkit

    tk = RazorpayToolkit()
    refund = next(t for t in tk.get_tools() if t._tool_schema["name"] == "razorpay_refund_payment")
    out = await refund(payment_id="pay_x", speed="instant")
    assert "speed" in out


# -------------------- Payment Link --------------------


@pytest.mark.asyncio
async def test_create_payment_link(monkeypatch):
    monkeypatch.setenv("LARGESTACK_RAZORPAY_KEY_ID", "k")
    monkeypatch.setenv("LARGESTACK_RAZORPAY_KEY_SECRET", "s")
    from largestack._integrations.razorpay_toolkit import RazorpayToolkit

    tk = RazorpayToolkit()
    create_link = next(
        t for t in tk.get_tools() if t._tool_schema["name"] == "razorpay_create_payment_link"
    )
    with respx.mock() as mock:
        route = mock.post("https://api.razorpay.com/v1/payment_links").respond(
            200,
            json={"id": "plink_abc", "short_url": "https://rzp.io/l/abc"},
        )
        out = await create_link(
            amount_paise=10000,
            description="Invoice #001",
            customer_email="user@test.in",
            notify_email=True,
        )
    body = json.loads(route.calls.last.request.content)
    assert body["amount"] == 10000
    assert body["description"] == "Invoice #001"
    assert body["customer"]["email"] == "user@test.in"
    assert body["notify"]["email"] is True
    assert json.loads(out)["short_url"].startswith("https://")


# -------------------- Signature verification --------------------


@pytest.mark.asyncio
async def test_verify_payment_signature_valid(monkeypatch):
    monkeypatch.setenv("LARGESTACK_RAZORPAY_KEY_ID", "k")
    monkeypatch.setenv("LARGESTACK_RAZORPAY_KEY_SECRET", "secret_test")
    from largestack._integrations.razorpay_toolkit import RazorpayToolkit

    tk = RazorpayToolkit()
    verify = next(
        t for t in tk.get_tools() if t._tool_schema["name"] == "razorpay_verify_payment_signature"
    )
    # Compute correct signature
    payload = "order_x|pay_x".encode()
    correct_sig = hmac.new(b"secret_test", payload, hashlib.sha256).hexdigest()
    out = await verify(order_id="order_x", payment_id="pay_x", signature=correct_sig)
    assert out == "valid"


@pytest.mark.asyncio
async def test_verify_payment_signature_invalid(monkeypatch):
    monkeypatch.setenv("LARGESTACK_RAZORPAY_KEY_ID", "k")
    monkeypatch.setenv("LARGESTACK_RAZORPAY_KEY_SECRET", "secret_test")
    from largestack._integrations.razorpay_toolkit import RazorpayToolkit

    tk = RazorpayToolkit()
    verify = next(
        t for t in tk.get_tools() if t._tool_schema["name"] == "razorpay_verify_payment_signature"
    )
    out = await verify(order_id="order_x", payment_id="pay_x", signature="badsig")
    assert out == "invalid"


@pytest.mark.asyncio
async def test_verify_webhook_signature_valid(monkeypatch):
    monkeypatch.setenv("LARGESTACK_RAZORPAY_KEY_ID", "k")
    monkeypatch.setenv("LARGESTACK_RAZORPAY_KEY_SECRET", "x")
    from largestack._integrations.razorpay_toolkit import RazorpayToolkit

    tk = RazorpayToolkit()
    verify = next(
        t for t in tk.get_tools() if t._tool_schema["name"] == "razorpay_verify_webhook_signature"
    )
    body = '{"event":"payment.captured"}'
    secret = "wh_secret_xyz"
    correct = hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()
    out = await verify(body=body, signature=correct, webhook_secret=secret)
    assert out == "valid"


@pytest.mark.asyncio
async def test_verify_webhook_signature_invalid(monkeypatch):
    monkeypatch.setenv("LARGESTACK_RAZORPAY_KEY_ID", "k")
    monkeypatch.setenv("LARGESTACK_RAZORPAY_KEY_SECRET", "x")
    from largestack._integrations.razorpay_toolkit import RazorpayToolkit

    tk = RazorpayToolkit()
    verify = next(
        t for t in tk.get_tools() if t._tool_schema["name"] == "razorpay_verify_webhook_signature"
    )
    out = await verify(body="x", signature="wrong", webhook_secret="s")
    assert out == "invalid"


# -------------------- List payments --------------------


@pytest.mark.asyncio
async def test_list_payments(monkeypatch):
    monkeypatch.setenv("LARGESTACK_RAZORPAY_KEY_ID", "k")
    monkeypatch.setenv("LARGESTACK_RAZORPAY_KEY_SECRET", "s")
    from largestack._integrations.razorpay_toolkit import RazorpayToolkit

    tk = RazorpayToolkit()
    list_p = next(t for t in tk.get_tools() if t._tool_schema["name"] == "razorpay_list_payments")
    with respx.mock() as mock:
        route = mock.get("https://api.razorpay.com/v1/payments").respond(
            200, json={"items": [], "count": 0}
        )
        await list_p(count=5, skip=10)
    url = str(route.calls.last.request.url)
    assert "count=5" in url
    assert "skip=10" in url


@pytest.mark.asyncio
async def test_list_payments_validates(monkeypatch):
    monkeypatch.setenv("LARGESTACK_RAZORPAY_KEY_ID", "k")
    monkeypatch.setenv("LARGESTACK_RAZORPAY_KEY_SECRET", "s")
    from largestack._integrations.razorpay_toolkit import RazorpayToolkit

    tk = RazorpayToolkit()
    list_p = next(t for t in tk.get_tools() if t._tool_schema["name"] == "razorpay_list_payments")
    out = await list_p(count=200)
    assert "count" in out
    out = await list_p(skip=-1)
    assert "skip" in out


# -------------------- Auth header --------------------


def test_auth_header_uses_basic_auth(monkeypatch):
    monkeypatch.setenv("LARGESTACK_RAZORPAY_KEY_ID", "rzp_test_xyz")
    monkeypatch.setenv("LARGESTACK_RAZORPAY_KEY_SECRET", "secret_value")
    from largestack._integrations.razorpay_toolkit import RazorpayToolkit

    tk = RazorpayToolkit()
    expected = "Basic " + base64.b64encode(b"rzp_test_xyz:secret_value").decode()
    assert tk._auth_header["Authorization"] == expected
