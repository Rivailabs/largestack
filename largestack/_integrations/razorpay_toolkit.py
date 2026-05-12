"""Razorpay Toolkit — Indian payment gateway tools (v0.8.0).

The first LARGESTACK-unique India-wedge toolkit. Razorpay is the dominant
payment gateway in India (used by ~60% of online merchants). This
toolkit gives an agent the ability to:

- Create payment orders (the standard checkout flow)
- Fetch payment / order status
- Refund payments
- Verify payment signatures (cryptographic check after callback)
- Verify webhook signatures (cryptographic check on incoming events)
- Create + fetch payment links (for invoice flows)

Auth: ``LARGESTACK_RAZORPAY_KEY_ID`` and ``LARGESTACK_RAZORPAY_KEY_SECRET``
env vars (or pass when constructing the toolkit).

Implementation: direct httpx calls to ``https://api.razorpay.com/v1``
with HTTP Basic Auth. No razorpay SDK dependency — keeps LARGESTACK lean.

The signature verifications use stdlib hmac/hashlib — no extra deps.

Usage:

    from largestack._integrations.razorpay_toolkit import RazorpayToolkit
    from largestack import Agent

    rzp = RazorpayToolkit()  # reads env vars
    agent = Agent(name="payments", llm="...", tools=rzp.get_tools())
"""
from __future__ import annotations
import base64
import hashlib
import hmac
import json
import logging
import os
import re
from typing import Any, Callable

import httpx

from largestack._core.tools import tool

log = logging.getLogger("largestack.razorpay_toolkit")

_RAZORPAY_BASE = "https://api.razorpay.com/v1"

# Razorpay receipt IDs are alphanumeric, max 40 chars
_RECEIPT_RE = re.compile(r"^[A-Za-z0-9_-]{1,40}$")


class RazorpayToolkit:
    """Bundle of Razorpay tools for use with LARGESTACK agents.

    Args:
        key_id: Razorpay Key ID. Reads ``LARGESTACK_RAZORPAY_KEY_ID`` if None.
        key_secret: Razorpay Key Secret. Reads ``LARGESTACK_RAZORPAY_KEY_SECRET``.
        timeout: per-request HTTP timeout (default 20s).
    """

    def __init__(
        self,
        key_id: str | None = None,
        key_secret: str | None = None,
        timeout: float = 20.0,
    ):
        self.key_id = key_id or os.environ.get("LARGESTACK_RAZORPAY_KEY_ID", "")
        self.key_secret = key_secret or os.environ.get(
            "LARGESTACK_RAZORPAY_KEY_SECRET", ""
        )
        self.timeout = timeout
        self._tools: list[Callable] = self._build_tools()

    @property
    def _auth_header(self) -> dict[str, str]:
        if not (self.key_id and self.key_secret):
            return {}
        creds = f"{self.key_id}:{self.key_secret}".encode()
        return {"Authorization": "Basic " + base64.b64encode(creds).decode()}

    def _no_creds_msg(self) -> str:
        return (
            "error: Razorpay credentials not set. "
            "Set LARGESTACK_RAZORPAY_KEY_ID and LARGESTACK_RAZORPAY_KEY_SECRET."
        )

    async def _request(
        self,
        method: str,
        endpoint: str,
        *,
        json_body: dict | None = None,
        params: dict | None = None,
    ) -> str:
        """Run a Razorpay API request. Returns JSON-string output."""
        if not (self.key_id and self.key_secret):
            return self._no_creds_msg()
        url = f"{_RAZORPAY_BASE}{endpoint}"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                r = await client.request(
                    method,
                    url,
                    headers={**self._auth_header, "Content-Type": "application/json"},
                    json=json_body,
                    params=params,
                )
        except httpx.TimeoutException:
            return "error: Razorpay request timed out"
        except Exception as e:
            return f"error: Razorpay request failed: {e}"

        # Razorpay returns JSON for both success and errors
        try:
            data = r.json()
        except Exception:
            return f"error: Razorpay HTTP {r.status_code}: {r.text[:200]}"

        if r.status_code >= 400:
            err_desc = ""
            if isinstance(data, dict):
                err = data.get("error") or {}
                err_desc = err.get("description") or err.get("code") or str(err)
            return f"error: Razorpay HTTP {r.status_code}: {err_desc}"
        return json.dumps(data)

    def _build_tools(self) -> list[Callable]:
        tk = self  # for closures

        @tool(timeout=int(self.timeout) + 5)
        async def razorpay_create_order(
            amount_paise: int,
            currency: str = "INR",
            receipt: str = "",
            notes: dict | None = None,
        ) -> str:
            """Create a Razorpay payment order.

            Args:
                amount_paise: amount in paise (₹100 = 10000 paise).
                    Razorpay always works in the smallest currency unit.
                currency: 3-letter ISO code, default ``INR``.
                receipt: merchant-side receipt ID (alphanumeric, max 40 chars).
                notes: optional dict of metadata, max 15 keys × 256 chars each.

            Returns:
                JSON string with the new order details, or error string.
            """
            if not isinstance(amount_paise, int) or amount_paise <= 0:
                return "error: amount_paise must be a positive integer"
            if amount_paise > 50_000_000_00:  # ₹50 crore upper sanity limit
                return "error: amount_paise exceeds reasonable limit"
            if not isinstance(currency, str) or len(currency) != 3:
                return "error: currency must be a 3-letter code"
            if receipt and not _RECEIPT_RE.match(receipt):
                return "error: receipt must be alphanumeric, max 40 chars"
            body: dict[str, Any] = {
                "amount": amount_paise,
                "currency": currency.upper(),
            }
            if receipt:
                body["receipt"] = receipt
            if notes:
                if not isinstance(notes, dict):
                    return "error: notes must be a dict"
                if len(notes) > 15:
                    return "error: notes may have at most 15 keys"
                body["notes"] = notes
            return await tk._request("POST", "/orders", json_body=body)

        @tool(timeout=int(self.timeout) + 5)
        async def razorpay_fetch_order(order_id: str) -> str:
            """Fetch a Razorpay order by ID.

            Args:
                order_id: order ID like ``order_xxx``.

            Returns:
                JSON string with order details, or error string.
            """
            if not order_id or not order_id.startswith("order_"):
                return "error: order_id must start with 'order_'"
            return await tk._request("GET", f"/orders/{order_id}")

        @tool(timeout=int(self.timeout) + 5)
        async def razorpay_fetch_payment(payment_id: str) -> str:
            """Fetch a Razorpay payment by ID.

            Args:
                payment_id: payment ID like ``pay_xxx``.

            Returns:
                JSON string with payment details, or error string.
            """
            if not payment_id or not payment_id.startswith("pay_"):
                return "error: payment_id must start with 'pay_'"
            return await tk._request("GET", f"/payments/{payment_id}")

        @tool(timeout=int(self.timeout) + 5)
        async def razorpay_refund_payment(
            payment_id: str,
            amount_paise: int | None = None,
            notes: dict | None = None,
            speed: str = "normal",
        ) -> str:
            """Refund a payment.

            Args:
                payment_id: ``pay_xxx`` to refund.
                amount_paise: amount in paise. If None, refunds full amount.
                notes: optional metadata.
                speed: ``normal`` (1-5 days) or ``optimum`` (instant if eligible).

            Returns:
                JSON string with refund details, or error string.
            """
            if not payment_id or not payment_id.startswith("pay_"):
                return "error: payment_id must start with 'pay_'"
            if speed not in {"normal", "optimum"}:
                return "error: speed must be 'normal' or 'optimum'"
            body: dict[str, Any] = {"speed": speed}
            if amount_paise is not None:
                if not isinstance(amount_paise, int) or amount_paise <= 0:
                    return "error: amount_paise must be a positive integer if given"
                body["amount"] = amount_paise
            if notes:
                body["notes"] = notes
            return await tk._request(
                "POST", f"/payments/{payment_id}/refund", json_body=body
            )

        @tool(timeout=int(self.timeout) + 5)
        async def razorpay_create_payment_link(
            amount_paise: int,
            currency: str = "INR",
            description: str = "",
            customer_name: str = "",
            customer_email: str = "",
            customer_contact: str = "",
            notify_sms: bool = False,
            notify_email: bool = False,
        ) -> str:
            """Create a Razorpay payment link (for invoice / share flows).

            Args:
                amount_paise: amount in paise.
                currency: 3-letter ISO code.
                description: invoice description.
                customer_name/email/contact: customer details for prefill.
                notify_sms: ask Razorpay to send SMS notification.
                notify_email: ask Razorpay to send email notification.

            Returns:
                JSON string with payment link incl. ``short_url``, or error.
            """
            if not isinstance(amount_paise, int) or amount_paise <= 0:
                return "error: amount_paise must be a positive integer"
            body: dict[str, Any] = {
                "amount": amount_paise,
                "currency": currency.upper(),
                "accept_partial": False,
            }
            if description:
                body["description"] = description
            customer: dict = {}
            if customer_name:
                customer["name"] = customer_name
            if customer_email:
                customer["email"] = customer_email
            if customer_contact:
                customer["contact"] = customer_contact
            if customer:
                body["customer"] = customer
            body["notify"] = {"sms": notify_sms, "email": notify_email}
            return await tk._request("POST", "/payment_links", json_body=body)

        @tool
        async def razorpay_verify_payment_signature(
            order_id: str, payment_id: str, signature: str
        ) -> str:
            """Verify a payment signature (after the checkout callback).

            Razorpay signs ``order_id|payment_id`` with the key secret;
            this tool checks the HMAC-SHA256 matches. Returns ``"valid"``
            or ``"invalid"`` (or an error string for missing creds).

            This is a CRITICAL security check — never trust a payment_id
            from the frontend without verifying its signature.

            Args:
                order_id: ``order_xxx`` from checkout.
                payment_id: ``pay_xxx`` from checkout.
                signature: ``razorpay_signature`` from checkout callback.
            """
            if not tk.key_secret:
                return tk._no_creds_msg()
            if not (order_id and payment_id and signature):
                return "error: order_id, payment_id, signature all required"
            payload = f"{order_id}|{payment_id}".encode()
            expected = hmac.new(
                tk.key_secret.encode(), payload, hashlib.sha256
            ).hexdigest()
            ok = hmac.compare_digest(expected, signature)
            return "valid" if ok else "invalid"

        @tool
        async def razorpay_verify_webhook_signature(
            body: str, signature: str, webhook_secret: str
        ) -> str:
            """Verify a Razorpay webhook signature.

            Args:
                body: raw HTTP request body (bytes/str — exactly as received).
                signature: value from ``X-Razorpay-Signature`` header.
                webhook_secret: the secret you configured on the dashboard
                    (NOT the API key secret).

            Returns:
                ``"valid"`` if signature matches, ``"invalid"`` otherwise.
            """
            if not (body and signature and webhook_secret):
                return "error: body, signature, webhook_secret all required"
            payload = body.encode() if isinstance(body, str) else body
            expected = hmac.new(
                webhook_secret.encode(), payload, hashlib.sha256
            ).hexdigest()
            ok = hmac.compare_digest(expected, signature)
            return "valid" if ok else "invalid"

        @tool(timeout=int(self.timeout) + 5)
        async def razorpay_list_payments(count: int = 10, skip: int = 0) -> str:
            """List recent payments.

            Args:
                count: how many to return (1-100, default 10).
                skip: pagination offset.

            Returns:
                JSON string with payments list, or error string.
            """
            if not (1 <= count <= 100):
                return "error: count must be in [1, 100]"
            if skip < 0:
                return "error: skip must be >= 0"
            return await tk._request(
                "GET", "/payments", params={"count": count, "skip": skip}
            )

        return [
            razorpay_create_order,
            razorpay_fetch_order,
            razorpay_fetch_payment,
            razorpay_refund_payment,
            razorpay_create_payment_link,
            razorpay_verify_payment_signature,
            razorpay_verify_webhook_signature,
            razorpay_list_payments,
        ]

    def get_tools(self) -> list[Callable]:
        """Return all 8 Razorpay tools as a list."""
        return list(self._tools)

    def __len__(self) -> int:
        return len(self._tools)
