"""Stripe Toolkit (v0.9.0) — global payment processing.

Companion to Razorpay (Indian) for the rest of the world.

Tools:
- ``stripe_create_payment_link`` — generate a hosted payment link
- ``stripe_fetch_payment_intent`` — get PaymentIntent details
- ``stripe_list_charges`` — paginated charges list
- ``stripe_create_refund`` — full or partial refund
- ``stripe_create_customer`` — create customer
- ``stripe_list_subscriptions`` — list subscriptions
- ``stripe_create_invoice`` — invoice creation

Auth via LARGESTACK_STRIPE_API_KEY (Stripe secret key, sk_live_... or sk_test_...).
Uses Stripe REST API directly via httpx — no SDK required.
"""
from __future__ import annotations
import json
import logging
import os
from typing import Any, Callable

import httpx

from largestack._core.tools import tool

log = logging.getLogger("largestack.stripe_toolkit")


class StripeToolkit:
    """Toolkit for Stripe payment operations.

    Args:
        api_key: Stripe secret key (or LARGESTACK_STRIPE_API_KEY env var).
        api_version: Stripe API version header.
    """

    def __init__(
        self,
        api_key: str | None = None,
        *,
        api_version: str = "2024-06-20",
    ):
        self.api_key = api_key or os.environ.get(
            "LARGESTACK_STRIPE_API_KEY"
        ) or os.environ.get("STRIPE_API_KEY", "")
        self.api_version = api_version
        self.base_url = "https://api.stripe.com/v1"
        self._tools: list[Callable] = self._build_tools()

    @property
    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Stripe-Version": self.api_version,
        }

    async def _post(self, path: str, data: dict) -> dict:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(
                f"{self.base_url}{path}",
                headers=self._headers, data=data,
            )
            try:
                return r.json()
            except Exception:
                return {"error": {"message": r.text[:500]}}

    async def _get(self, path: str, params: dict | None = None) -> dict:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.get(
                f"{self.base_url}{path}",
                headers=self._headers, params=params or {},
            )
            try:
                return r.json()
            except Exception:
                return {"error": {"message": r.text[:500]}}

    def _check_auth(self) -> str | None:
        if not self.api_key:
            return "error: LARGESTACK_STRIPE_API_KEY not set"
        return None

    def _build_tools(self) -> list[Callable]:
        tk = self

        @tool(
            name="stripe_create_payment_link",
            description="Create a hosted Stripe payment link for a one-off charge",
            timeout=30,
        )
        async def create_payment_link(
            amount_cents: int,
            currency: str = "usd",
            description: str = "",
        ) -> str:
            err = tk._check_auth()
            if err:
                return err
            try:
                # First create a price + product
                product_resp = await tk._post(
                    "/products", {"name": description or "Payment"}
                )
                if "error" in product_resp:
                    return f"error: {product_resp['error'].get('message', 'product create failed')}"
                product_id = product_resp.get("id")
                price_resp = await tk._post(
                    "/prices", {
                        "product": product_id,
                        "unit_amount": int(amount_cents),
                        "currency": currency,
                    }
                )
                if "error" in price_resp:
                    return f"error: {price_resp['error'].get('message')}"
                price_id = price_resp.get("id")
                # Now create payment link
                link_resp = await tk._post(
                    "/payment_links", {
                        "line_items[0][price]": price_id,
                        "line_items[0][quantity]": 1,
                    }
                )
                if "error" in link_resp:
                    return f"error: {link_resp['error'].get('message')}"
                return json.dumps({
                    "id": link_resp.get("id"),
                    "url": link_resp.get("url"),
                    "amount_cents": amount_cents,
                    "currency": currency,
                })
            except Exception as e:
                return f"error: {e}"

        @tool(
            name="stripe_fetch_payment_intent",
            description="Get PaymentIntent details by ID",
        )
        async def fetch_payment_intent(payment_intent_id: str) -> str:
            err = tk._check_auth()
            if err:
                return err
            try:
                resp = await tk._get(f"/payment_intents/{payment_intent_id}")
                if "error" in resp:
                    return f"error: {resp['error'].get('message')}"
                return json.dumps({
                    "id": resp.get("id"),
                    "status": resp.get("status"),
                    "amount": resp.get("amount"),
                    "currency": resp.get("currency"),
                    "customer": resp.get("customer"),
                    "created": resp.get("created"),
                })
            except Exception as e:
                return f"error: {e}"

        @tool(
            name="stripe_list_charges",
            description="List recent charges. limit defaults to 10, max 100.",
        )
        async def list_charges(limit: int = 10) -> str:
            err = tk._check_auth()
            if err:
                return err
            try:
                resp = await tk._get(
                    "/charges", params={"limit": min(int(limit), 100)}
                )
                if "error" in resp:
                    return f"error: {resp['error'].get('message')}"
                charges = [
                    {
                        "id": c.get("id"),
                        "amount": c.get("amount"),
                        "currency": c.get("currency"),
                        "status": c.get("status"),
                        "created": c.get("created"),
                        "customer": c.get("customer"),
                    }
                    for c in resp.get("data", [])
                ]
                return json.dumps({"charges": charges, "has_more": resp.get("has_more")})
            except Exception as e:
                return f"error: {e}"

        @tool(
            name="stripe_create_refund",
            description="Refund a charge. amount_cents optional; if omitted, full refund.",
            timeout=30,
        )
        async def create_refund(
            charge_id: str,
            amount_cents: int | None = None,
            reason: str = "requested_by_customer",
        ) -> str:
            err = tk._check_auth()
            if err:
                return err
            try:
                data: dict = {"charge": charge_id, "reason": reason}
                if amount_cents is not None:
                    data["amount"] = int(amount_cents)
                resp = await tk._post("/refunds", data)
                if "error" in resp:
                    return f"error: {resp['error'].get('message')}"
                return json.dumps({
                    "id": resp.get("id"),
                    "amount": resp.get("amount"),
                    "status": resp.get("status"),
                    "charge": resp.get("charge"),
                })
            except Exception as e:
                return f"error: {e}"

        @tool(
            name="stripe_create_customer",
            description="Create a new Stripe customer with email + optional name",
        )
        async def create_customer(email: str, name: str = "") -> str:
            err = tk._check_auth()
            if err:
                return err
            try:
                data = {"email": email}
                if name:
                    data["name"] = name
                resp = await tk._post("/customers", data)
                if "error" in resp:
                    return f"error: {resp['error'].get('message')}"
                return json.dumps({
                    "id": resp.get("id"),
                    "email": resp.get("email"),
                    "name": resp.get("name"),
                })
            except Exception as e:
                return f"error: {e}"

        @tool(
            name="stripe_list_subscriptions",
            description="List active Stripe subscriptions, optionally for a specific customer",
        )
        async def list_subscriptions(
            customer_id: str = "", limit: int = 10
        ) -> str:
            err = tk._check_auth()
            if err:
                return err
            try:
                params: dict = {"limit": min(int(limit), 100)}
                if customer_id:
                    params["customer"] = customer_id
                resp = await tk._get("/subscriptions", params=params)
                if "error" in resp:
                    return f"error: {resp['error'].get('message')}"
                subs = [
                    {
                        "id": s.get("id"),
                        "status": s.get("status"),
                        "customer": s.get("customer"),
                        "current_period_end": s.get("current_period_end"),
                    }
                    for s in resp.get("data", [])
                ]
                return json.dumps({"subscriptions": subs})
            except Exception as e:
                return f"error: {e}"

        return [
            create_payment_link, fetch_payment_intent, list_charges,
            create_refund, create_customer, list_subscriptions,
        ]

    def get_tools(self) -> list[Callable]:
        return list(self._tools)
