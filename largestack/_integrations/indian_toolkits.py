"""Indian wedge toolkits (v0.9.0).

Six LARGESTACK-unique toolkits for Indian fintech / legaltech / RegTech.
Nobody else builds these. Direct support for Sachith's Sri Rajeshwari
NBFC, LegalDocs.in, and CA Practice Management projects.

- ``UPIToolkit`` — UPI VPA validation, payment intents, status checks
- ``GSTToolkit`` — GST verification, return filing helpers
- ``MCAToolkit`` — Ministry of Corporate Affairs company lookup
- ``DigiLockerToolkit`` — issued docs fetch
- ``eSignToolkit`` — Aadhaar-based eSign workflows
- ``KYCToolkit`` — PAN, Aadhaar OKYC verification
"""
from __future__ import annotations
import json
import logging
import os
import re
from typing import Any, Callable

import httpx

from largestack._core.tools import tool

log = logging.getLogger("largestack.indian_toolkits")


# Patterns for Indian identifiers
PAN_PATTERN = re.compile(r"^[A-Z]{5}[0-9]{4}[A-Z]$")
AADHAAR_PATTERN = re.compile(r"^[2-9][0-9]{11}$")
GSTIN_PATTERN = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z][Z][0-9A-Z]$")
CIN_PATTERN = re.compile(r"^[LU][0-9]{5}[A-Z]{2}[0-9]{4}[A-Z]{3}[0-9]{6}$")


def _aadhaar_redact(aadhaar: str) -> str:
    """Mask Aadhaar to 'XXXX XXXX 1234' format."""
    if isinstance(aadhaar, str) and len(aadhaar) == 12:
        return f"XXXX XXXX {aadhaar[-4:]}"
    return "XXXX"


# -------------------- UPI Toolkit --------------------

class UPIToolkit:
    """UPI integration via Razorpay (the canonical Indian aggregator).

    NPCI itself doesn't expose a public REST API for VPA validation —
    you go through a PSP. Razorpay is reused (Sachith already has it
    live from v0.8 Razorpay toolkit).

    Tools:
    - ``upi_validate_vpa`` — check if a UPI VPA exists
    - ``upi_create_payment_intent`` — generate a UPI payment request
    - ``upi_check_payment_status`` — poll for payment completion
    """

    def __init__(
        self,
        key_id: str | None = None,
        key_secret: str | None = None,
    ):
        self.key_id = key_id or os.environ.get("LARGESTACK_RAZORPAY_KEY_ID", "")
        self.key_secret = key_secret or os.environ.get(
            "LARGESTACK_RAZORPAY_KEY_SECRET", ""
        )
        self.base_url = "https://api.razorpay.com/v1"
        self._tools = self._build_tools()

    def _check_auth(self) -> str | None:
        if not self.key_id or not self.key_secret:
            return "error: LARGESTACK_RAZORPAY_KEY_ID + LARGESTACK_RAZORPAY_KEY_SECRET required"
        return None

    def _build_tools(self) -> list[Callable]:
        tk = self

        @tool(
            name="upi_validate_vpa",
            description="Validate a UPI VPA (Virtual Payment Address) like 'name@bank'",
            timeout=30,
        )
        async def validate_vpa(vpa: str) -> str:
            err = tk._check_auth()
            if err:
                return err
            if "@" not in vpa or len(vpa) < 5:
                return json.dumps({
                    "vpa": vpa, "valid": False,
                    "reason": "invalid VPA format",
                })
            try:
                async with httpx.AsyncClient(
                    timeout=30, auth=(tk.key_id, tk.key_secret)
                ) as client:
                    r = await client.post(
                        f"{tk.base_url}/payments/validate/vpa",
                        json={"vpa": vpa},
                    )
                    if r.status_code == 200:
                        data = r.json()
                        return json.dumps({
                            "vpa": vpa, "valid": True,
                            "customer_name": data.get("customer_name", ""),
                        })
                    if r.status_code == 400:
                        return json.dumps({
                            "vpa": vpa, "valid": False,
                            "reason": "invalid VPA",
                        })
                    return f"error: HTTP {r.status_code}: {r.text[:200]}"
            except Exception as e:
                return f"error: {e}"

        @tool(
            name="upi_create_payment_intent",
            description=(
                "Create a UPI payment request. Returns payment_id + UPI intent."
            ),
            timeout=30,
        )
        async def create_upi_payment_intent(
            amount_paise: int, vpa: str, description: str = "Payment",
            currency: str = "INR",
        ) -> str:
            err = tk._check_auth()
            if err:
                return err
            try:
                async with httpx.AsyncClient(
                    timeout=30, auth=(tk.key_id, tk.key_secret)
                ) as client:
                    order_r = await client.post(
                        f"{tk.base_url}/orders",
                        json={
                            "amount": int(amount_paise),
                            "currency": currency,
                            "payment_capture": 1,
                        },
                    )
                    if order_r.status_code >= 400:
                        return f"error: order create HTTP {order_r.status_code}"
                    order = order_r.json()
                    pay_r = await client.post(
                        f"{tk.base_url}/payments/create/upi",
                        json={
                            "amount": int(amount_paise), "currency": currency,
                            "order_id": order.get("id"), "method": "upi",
                            "vpa": vpa, "description": description,
                        },
                    )
                    if pay_r.status_code >= 400:
                        return f"error: UPI HTTP {pay_r.status_code}"
                    pay = pay_r.json()
                    return json.dumps({
                        "order_id": order.get("id"),
                        "payment_id": pay.get("razorpay_payment_id", pay.get("id")),
                        "amount_paise": amount_paise, "vpa": vpa,
                        "status": pay.get("status", "created"),
                    })
            except Exception as e:
                return f"error: {e}"

        @tool(
            name="upi_check_payment_status",
            description="Poll status of UPI payment by payment_id",
        )
        async def check_payment_status(payment_id: str) -> str:
            err = tk._check_auth()
            if err:
                return err
            try:
                async with httpx.AsyncClient(
                    timeout=30, auth=(tk.key_id, tk.key_secret)
                ) as client:
                    r = await client.get(f"{tk.base_url}/payments/{payment_id}")
                    if r.status_code >= 400:
                        return f"error: HTTP {r.status_code}"
                    p = r.json()
                    return json.dumps({
                        "payment_id": payment_id,
                        "status": p.get("status"),
                        "amount": p.get("amount"),
                        "method": p.get("method"),
                        "vpa": p.get("vpa"),
                        "captured": p.get("captured"),
                    })
            except Exception as e:
                return f"error: {e}"

        return [validate_vpa, create_upi_payment_intent, check_payment_status]

    def get_tools(self) -> list[Callable]:
        return list(self._tools)


# -------------------- GST Toolkit --------------------

class GSTToolkit:
    """GST gov.in lookup + verification toolkit (via MasterGST aggregator)."""

    def __init__(
        self, api_key: str | None = None, *, provider: str = "mastergst",
    ):
        self.api_key = api_key or os.environ.get(
            "LARGESTACK_GST_API_KEY"
        ) or os.environ.get("MASTERGST_API_KEY", "")
        self.provider = provider
        self.base_urls = {
            "mastergst": "https://api.mastergst.com/public/search",
            "cleartax": "https://api.cleartax.in/gst/v1",
        }
        self._tools = self._build_tools()

    def _check_auth(self) -> str | None:
        if not self.api_key:
            return "error: LARGESTACK_GST_API_KEY required"
        return None

    def _build_tools(self) -> list[Callable]:
        tk = self

        @tool(
            name="gst_validate_gstin",
            description="Validate GSTIN format and look up basic taxpayer info",
            timeout=30,
        )
        async def validate_gstin(gstin: str) -> str:
            gstin = gstin.upper().strip()
            if not GSTIN_PATTERN.match(gstin):
                return json.dumps({
                    "gstin": gstin, "valid_format": False,
                    "reason": "invalid GSTIN format",
                })
            err = tk._check_auth()
            if err:
                return json.dumps({
                    "gstin": gstin, "valid_format": True,
                    "lookup": "skipped", "error": err,
                })
            base = tk.base_urls[tk.provider]
            try:
                async with httpx.AsyncClient(timeout=30) as client:
                    r = await client.get(
                        base, params={"gstin": gstin},
                        headers={"x-api-key": tk.api_key},
                    )
                    if r.status_code != 200:
                        return f"error: GST HTTP {r.status_code}"
                    data = r.json()
                    return json.dumps({
                        "gstin": gstin, "valid_format": True,
                        "legal_name": data.get("lgnm") or data.get("legal_name"),
                        "trade_name": data.get("tradeNam") or data.get("trade_name"),
                        "status": data.get("sts") or data.get("status"),
                        "registration_date": data.get("rgdt"),
                        "constitution": data.get("ctb"),
                    })
            except Exception as e:
                return f"error: {e}"

        @tool(
            name="gst_check_return_status",
            description="Check GSTR return filing status",
            timeout=30,
        )
        async def check_return_status(
            gstin: str, financial_year: str, return_type: str = "GSTR3B",
        ) -> str:
            gstin = gstin.upper().strip()
            if not GSTIN_PATTERN.match(gstin):
                return f"error: invalid GSTIN: {gstin}"
            err = tk._check_auth()
            if err:
                return err
            try:
                async with httpx.AsyncClient(timeout=30) as client:
                    r = await client.get(
                        f"{tk.base_urls[tk.provider]}/returns",
                        params={"gstin": gstin, "fy": financial_year, "type": return_type},
                        headers={"x-api-key": tk.api_key},
                    )
                    if r.status_code != 200:
                        return f"error: HTTP {r.status_code}"
                    return json.dumps({
                        "gstin": gstin, "fy": financial_year,
                        "return_type": return_type,
                        "filings": r.json().get("filings", []),
                    })
            except Exception as e:
                return f"error: {e}"

        return [validate_gstin, check_return_status]

    def get_tools(self) -> list[Callable]:
        return list(self._tools)


# -------------------- MCA Toolkit --------------------

class MCAToolkit:
    """Ministry of Corporate Affairs lookup (via Probe42 aggregator)."""

    def __init__(self, api_key: str | None = None, *, base_url: str | None = None):
        self.api_key = api_key or os.environ.get("LARGESTACK_MCA_API_KEY", "")
        self.base_url = base_url or "https://api.probe42.in/v1"
        self._tools = self._build_tools()

    def _check_auth(self) -> str | None:
        if not self.api_key:
            return "error: LARGESTACK_MCA_API_KEY required"
        return None

    def _build_tools(self) -> list[Callable]:
        tk = self

        @tool(
            name="mca_lookup_company",
            description="Look up Indian company by CIN",
            timeout=30,
        )
        async def lookup_company(cin: str) -> str:
            cin = cin.upper().strip()
            if not CIN_PATTERN.match(cin):
                return json.dumps({
                    "cin": cin, "valid_format": False,
                    "reason": "CIN must be 21 chars",
                })
            err = tk._check_auth()
            if err:
                return err
            try:
                async with httpx.AsyncClient(timeout=30) as client:
                    r = await client.get(
                        f"{tk.base_url}/companies/{cin}",
                        headers={"x-api-key": tk.api_key},
                    )
                    if r.status_code == 404:
                        return json.dumps({"cin": cin, "found": False})
                    if r.status_code != 200:
                        return f"error: HTTP {r.status_code}"
                    data = r.json()
                    return json.dumps({
                        "cin": cin, "found": True,
                        "company_name": data.get("company_name"),
                        "incorporation_date": data.get("date_of_incorporation"),
                        "status": data.get("company_status"),
                        "category": data.get("company_category"),
                        "paid_up_capital": data.get("paid_up_capital"),
                    })
            except Exception as e:
                return f"error: {e}"

        @tool(
            name="mca_check_director",
            description="Check Director Identification Number (DIN)",
            timeout=30,
        )
        async def check_director(din: str) -> str:
            din = din.strip()
            if not re.match(r"^[0-9]{8}$", din):
                return json.dumps({
                    "din": din, "valid_format": False,
                    "reason": "DIN must be 8 digits",
                })
            err = tk._check_auth()
            if err:
                return err
            try:
                async with httpx.AsyncClient(timeout=30) as client:
                    r = await client.get(
                        f"{tk.base_url}/directors/{din}",
                        headers={"x-api-key": tk.api_key},
                    )
                    if r.status_code == 404:
                        return json.dumps({"din": din, "found": False})
                    if r.status_code != 200:
                        return f"error: HTTP {r.status_code}"
                    data = r.json()
                    return json.dumps({
                        "din": din, "found": True,
                        "name": data.get("director_name"),
                        "status": data.get("status"),
                        "associated_companies": data.get("companies", []),
                    })
            except Exception as e:
                return f"error: {e}"

        return [lookup_company, check_director]

    def get_tools(self) -> list[Callable]:
        return list(self._tools)


# -------------------- DigiLocker Toolkit --------------------

class DigiLockerToolkit:
    """DigiLocker integration scaffold."""

    def __init__(
        self, client_id: str | None = None, client_secret: str | None = None,
        *, sandbox: bool = True,
    ):
        self.client_id = client_id or os.environ.get(
            "LARGESTACK_DIGILOCKER_CLIENT_ID", ""
        )
        self.client_secret = client_secret or os.environ.get(
            "LARGESTACK_DIGILOCKER_CLIENT_SECRET", ""
        )
        self.sandbox = sandbox
        self.base_url = (
            "https://api-sandbox.digitallocker.gov.in/public/oauth2/1"
            if sandbox else
            "https://api.digitallocker.gov.in/public/oauth2/1"
        )
        self._tools = self._build_tools()

    def _check_auth(self) -> str | None:
        if not self.client_id or not self.client_secret:
            return "error: LARGESTACK_DIGILOCKER_CLIENT_ID + SECRET required"
        return None

    def _build_tools(self) -> list[Callable]:
        tk = self

        @tool(
            name="digilocker_list_issued_documents",
            description="List documents in user's DigiLocker (requires user access_token)",
            timeout=30,
        )
        async def list_documents(access_token: str) -> str:
            err = tk._check_auth()
            if err:
                return err
            try:
                async with httpx.AsyncClient(timeout=30) as client:
                    r = await client.get(
                        f"{tk.base_url}/files/issued",
                        headers={"Authorization": f"Bearer {access_token}"},
                    )
                    if r.status_code == 401:
                        return "error: invalid or expired access_token"
                    if r.status_code != 200:
                        return f"error: HTTP {r.status_code}"
                    data = r.json()
                    items = data.get("items", []) if isinstance(data, dict) else data
                    return json.dumps({
                        "documents": [
                            {
                                "uri": d.get("uri"), "name": d.get("name"),
                                "doctype": d.get("doctype"),
                                "issuer": d.get("issuer"),
                                "date": d.get("date"),
                            } for d in (items or [])
                        ]
                    })
            except Exception as e:
                return f"error: {e}"

        @tool(
            name="digilocker_download_document",
            description="Download document from DigiLocker by URI",
            timeout=60,
        )
        async def download_document(access_token: str, uri: str) -> str:
            err = tk._check_auth()
            if err:
                return err
            import base64 as _b64
            try:
                async with httpx.AsyncClient(timeout=60) as client:
                    r = await client.get(
                        f"{tk.base_url}/file/{uri}",
                        headers={"Authorization": f"Bearer {access_token}"},
                    )
                    if r.status_code != 200:
                        return f"error: HTTP {r.status_code}"
                    return json.dumps({
                        "uri": uri, "size_bytes": len(r.content),
                        "content_type": r.headers.get("content-type"),
                        "content_b64": _b64.b64encode(r.content).decode(),
                    })
            except Exception as e:
                return f"error: {e}"

        return [list_documents, download_document]

    def get_tools(self) -> list[Callable]:
        return list(self._tools)


# -------------------- eSign Toolkit --------------------

class eSignToolkit:
    """Aadhaar-based eSign integration (eMudhra / NSDL)."""

    def __init__(
        self,
        client_id: str | None = None,
        client_secret: str | None = None,
        *, provider: str = "emudhra",
    ):
        self.client_id = client_id or os.environ.get("LARGESTACK_ESIGN_CLIENT_ID", "")
        self.client_secret = client_secret or os.environ.get(
            "LARGESTACK_ESIGN_CLIENT_SECRET", ""
        )
        self.provider = provider
        self.base_urls = {
            "emudhra": "https://esign.emudhra.com/v3",
            "nsdl": "https://esign.nsdl.com/v3",
        }
        self._tools = self._build_tools()

    def _check_auth(self) -> str | None:
        if not self.client_id or not self.client_secret:
            return "error: LARGESTACK_ESIGN_CLIENT_ID + SECRET required"
        return None

    def _build_tools(self) -> list[Callable]:
        tk = self

        @tool(
            name="esign_initiate",
            description=(
                "Initiate eSign for a document. Returns signing URL for user to "
                "authenticate via Aadhaar OTP."
            ),
            timeout=30,
        )
        async def initiate_esign(
            document_url: str, signer_name: str, signer_email: str,
            callback_url: str = "",
        ) -> str:
            err = tk._check_auth()
            if err:
                return err
            base = tk.base_urls.get(tk.provider, tk.base_urls["emudhra"])
            try:
                async with httpx.AsyncClient(timeout=30) as client:
                    r = await client.post(
                        f"{base}/esign/init",
                        headers={
                            "X-Client-Id": tk.client_id,
                            "X-Client-Secret": tk.client_secret,
                            "Content-Type": "application/json",
                        },
                        json={
                            "document_url": document_url,
                            "signer_name": signer_name,
                            "signer_email": signer_email,
                            "callback_url": callback_url,
                        },
                    )
                    if r.status_code >= 400:
                        return f"error: eSign HTTP {r.status_code}: {r.text[:200]}"
                    data = r.json()
                    return json.dumps({
                        "request_id": data.get("request_id"),
                        "signing_url": data.get("url"),
                        "expires_at": data.get("expires_at"),
                    })
            except Exception as e:
                return f"error: {e}"

        @tool(
            name="esign_check_status",
            description="Check status of an eSign request",
        )
        async def check_status(request_id: str) -> str:
            err = tk._check_auth()
            if err:
                return err
            base = tk.base_urls.get(tk.provider, tk.base_urls["emudhra"])
            try:
                async with httpx.AsyncClient(timeout=30) as client:
                    r = await client.get(
                        f"{base}/esign/status/{request_id}",
                        headers={
                            "X-Client-Id": tk.client_id,
                            "X-Client-Secret": tk.client_secret,
                        },
                    )
                    if r.status_code >= 400:
                        return f"error: HTTP {r.status_code}"
                    data = r.json()
                    return json.dumps({
                        "request_id": request_id,
                        "status": data.get("status"),
                        "signed_document_url": data.get("signed_document_url"),
                        "signed_at": data.get("signed_at"),
                    })
            except Exception as e:
                return f"error: {e}"

        return [initiate_esign, check_status]

    def get_tools(self) -> list[Callable]:
        return list(self._tools)


# -------------------- KYC Toolkit (PAN + Aadhaar OKYC + AML) --------------------

class KYCToolkit:
    """Indian KYC + AML toolkit (PAN + Aadhaar OKYC).

    Uses Signzy or IDfy aggregator. Critical for fintech / NBFC / lending.
    """

    def __init__(
        self, api_key: str | None = None, *, provider: str = "signzy",
    ):
        self.api_key = api_key or os.environ.get("LARGESTACK_KYC_API_KEY", "")
        self.provider = provider
        self.base_urls = {
            "signzy": "https://preproduction.signzy.tech/api/v3",
            "idfy": "https://eve.idfy.com/v3",
        }
        self._tools = self._build_tools()

    def _check_auth(self) -> str | None:
        if not self.api_key:
            return "error: LARGESTACK_KYC_API_KEY required"
        return None

    def _build_tools(self) -> list[Callable]:
        tk = self

        @tool(
            name="kyc_verify_pan",
            description="Verify PAN against Income Tax Dept records",
            timeout=30,
        )
        async def verify_pan(pan: str, full_name: str = "") -> str:
            pan = pan.upper().strip()
            if not PAN_PATTERN.match(pan):
                return json.dumps({
                    "pan": pan, "valid_format": False,
                    "reason": "PAN must be 10 chars: 5 letters + 4 digits + 1 letter",
                })
            err = tk._check_auth()
            if err:
                return json.dumps({
                    "pan": pan, "valid_format": True, "verified": False,
                    "error": err,
                })
            base = tk.base_urls.get(tk.provider, tk.base_urls["signzy"])
            try:
                async with httpx.AsyncClient(timeout=30) as client:
                    r = await client.post(
                        f"{base}/pan/verification",
                        headers={
                            "Authorization": tk.api_key,
                            "Content-Type": "application/json",
                        },
                        json={"pan": pan, "name_to_match": full_name},
                    )
                    if r.status_code >= 400:
                        return f"error: HTTP {r.status_code}: {r.text[:200]}"
                    data = r.json()
                    return json.dumps({
                        "pan": pan, "valid_format": True,
                        "verified": data.get("status") == "valid",
                        "name_on_pan": data.get("name", ""),
                        "name_match": data.get("name_match", False),
                    })
            except Exception as e:
                return f"error: {e}"

        @tool(
            name="kyc_initiate_aadhaar_okyc",
            description=(
                "Send OTP to Aadhaar-linked phone for OKYC. "
                "Aadhaar number is automatically redacted in logs/storage. "
                "Returns request_id needed for OTP verification step."
            ),
            timeout=30,
        )
        async def initiate_aadhaar_okyc(aadhaar: str) -> str:
            aadhaar = aadhaar.replace(" ", "").strip()
            if not AADHAAR_PATTERN.match(aadhaar):
                return json.dumps({
                    "valid_format": False,
                    "reason": "Aadhaar must be 12 digits, first digit 2-9",
                })
            err = tk._check_auth()
            if err:
                return err
            base = tk.base_urls.get(tk.provider, tk.base_urls["signzy"])
            try:
                async with httpx.AsyncClient(timeout=30) as client:
                    r = await client.post(
                        f"{base}/aadhaar/okyc/init",
                        headers={
                            "Authorization": tk.api_key,
                            "Content-Type": "application/json",
                        },
                        json={"aadhaar": aadhaar},
                    )
                    if r.status_code >= 400:
                        return f"error: HTTP {r.status_code}"
                    data = r.json()
                    # NEVER log raw aadhaar
                    log.info(
                        f"OKYC initiated for Aadhaar {_aadhaar_redact(aadhaar)}, "
                        f"request_id={data.get('request_id', 'unknown')}"
                    )
                    return json.dumps({
                        "request_id": data.get("request_id"),
                        "aadhaar_masked": _aadhaar_redact(aadhaar),
                        "otp_sent": data.get("otp_sent", True),
                        "expires_in_seconds": data.get("expires_in", 300),
                    })
            except Exception as e:
                return f"error: {e}"

        @tool(
            name="kyc_verify_aadhaar_okyc_otp",
            description="Submit OTP from Aadhaar OKYC. Returns masked Aadhaar response.",
            timeout=30,
        )
        async def verify_aadhaar_okyc_otp(request_id: str, otp: str) -> str:
            if not re.match(r"^[0-9]{4,6}$", otp):
                return "error: OTP must be 4-6 digits"
            err = tk._check_auth()
            if err:
                return err
            base = tk.base_urls.get(tk.provider, tk.base_urls["signzy"])
            try:
                async with httpx.AsyncClient(timeout=30) as client:
                    r = await client.post(
                        f"{base}/aadhaar/okyc/verify",
                        headers={
                            "Authorization": tk.api_key,
                            "Content-Type": "application/json",
                        },
                        json={"request_id": request_id, "otp": otp},
                    )
                    if r.status_code >= 400:
                        return f"error: HTTP {r.status_code}"
                    data = r.json()
                    # Return data with Aadhaar masked
                    return json.dumps({
                        "request_id": request_id,
                        "verified": data.get("status") == "success",
                        "name": data.get("name"),
                        "dob": data.get("dob"),
                        "gender": data.get("gender"),
                        "aadhaar_masked": _aadhaar_redact(data.get("aadhaar", "")),
                        "address": data.get("address"),
                    })
            except Exception as e:
                return f"error: {e}"

        @tool(
            name="kyc_aml_check",
            description=(
                "AML/sanctions screening for an individual or entity. "
                "Checks against PEP, sanctions, adverse media databases."
            ),
            timeout=30,
        )
        async def aml_check(name: str, dob: str = "") -> str:
            err = tk._check_auth()
            if err:
                return err
            base = tk.base_urls.get(tk.provider, tk.base_urls["signzy"])
            try:
                async with httpx.AsyncClient(timeout=30) as client:
                    r = await client.post(
                        f"{base}/aml/screen",
                        headers={
                            "Authorization": tk.api_key,
                            "Content-Type": "application/json",
                        },
                        json={"name": name, "dob": dob},
                    )
                    if r.status_code >= 400:
                        return f"error: HTTP {r.status_code}"
                    data = r.json()
                    return json.dumps({
                        "name": name,
                        "matches_found": data.get("matches", 0),
                        "pep_match": data.get("pep_match", False),
                        "sanctions_match": data.get("sanctions_match", False),
                        "adverse_media_match": data.get("adverse_media", False),
                        "risk_level": data.get("risk_level", "low"),
                    })
            except Exception as e:
                return f"error: {e}"

        return [
            verify_pan, initiate_aadhaar_okyc, verify_aadhaar_okyc_otp, aml_check,
        ]

    def get_tools(self) -> list[Callable]:
        return list(self._tools)
