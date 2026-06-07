"""v0.9.0: Tests for 6 Indian wedge toolkits (LARGESTACK-unique)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

respx = pytest.importorskip("respx")


# -------------------- UPI Toolkit --------------------


@pytest.mark.asyncio
async def test_upi_no_creds(monkeypatch):
    monkeypatch.delenv("LARGESTACK_RAZORPAY_KEY_ID", raising=False)
    monkeypatch.delenv("LARGESTACK_RAZORPAY_KEY_SECRET", raising=False)
    from largestack._integrations import UPIToolkit

    tk = UPIToolkit()
    validate = next(t for t in tk.get_tools() if t._tool_schema["name"] == "upi_validate_vpa")
    result = await validate("test@upi")
    assert "RAZORPAY" in result


@pytest.mark.asyncio
async def test_upi_validate_vpa_invalid_format():
    from largestack._integrations import UPIToolkit

    tk = UPIToolkit(key_id="kid", key_secret="ks")
    validate = next(t for t in tk.get_tools() if t._tool_schema["name"] == "upi_validate_vpa")
    result = await validate("nope")
    data = json.loads(result)
    assert data["valid"] is False


@pytest.mark.asyncio
async def test_upi_validate_vpa_success():
    from largestack._integrations import UPIToolkit

    tk = UPIToolkit(key_id="kid", key_secret="ks")
    validate = next(t for t in tk.get_tools() if t._tool_schema["name"] == "upi_validate_vpa")
    with respx.mock() as mock:
        mock.post("https://api.razorpay.com/v1/payments/validate/vpa").respond(
            200, json={"customer_name": "Sachith S", "success": True}
        )
        result = await validate("sachith@oksbi")
    data = json.loads(result)
    assert data["valid"] is True
    assert data["customer_name"] == "Sachith S"


@pytest.mark.asyncio
async def test_upi_check_payment_status():
    from largestack._integrations import UPIToolkit

    tk = UPIToolkit(key_id="kid", key_secret="ks")
    check = next(t for t in tk.get_tools() if t._tool_schema["name"] == "upi_check_payment_status")
    with respx.mock() as mock:
        mock.get("https://api.razorpay.com/v1/payments/pay_x").respond(
            200,
            json={
                "status": "captured",
                "amount": 50000,
                "method": "upi",
                "vpa": "x@ybl",
                "captured": True,
            },
        )
        result = await check("pay_x")
    data = json.loads(result)
    assert data["status"] == "captured"
    assert data["amount"] == 50000


# -------------------- GST Toolkit --------------------


@pytest.mark.asyncio
async def test_gst_validates_format():
    from largestack._integrations import GSTToolkit

    tk = GSTToolkit(api_key="x")
    validate = next(t for t in tk.get_tools() if t._tool_schema["name"] == "gst_validate_gstin")
    # Invalid format
    result = await validate("INVALID123")
    data = json.loads(result)
    assert data["valid_format"] is False


@pytest.mark.asyncio
async def test_gst_validates_real_gstin_format():
    from largestack._integrations import GSTToolkit

    tk = GSTToolkit(api_key="api_key_test")
    validate = next(t for t in tk.get_tools() if t._tool_schema["name"] == "gst_validate_gstin")
    # Valid format GSTIN (Karnataka prefix 29)
    valid_gstin = "29AAACR5055K1Z5"
    with respx.mock() as mock:
        mock.get("https://api.mastergst.com/public/search").respond(
            200,
            json={
                "lgnm": "Test Pvt Ltd",
                "tradeNam": "Test",
                "sts": "Active",
                "rgdt": "01/04/2017",
                "ctb": "Private Limited",
            },
        )
        result = await validate(valid_gstin)
    data = json.loads(result)
    assert data["valid_format"] is True
    assert data["status"] == "Active"


@pytest.mark.asyncio
async def test_gst_no_api_key_returns_format_only(monkeypatch):
    monkeypatch.delenv("LARGESTACK_GST_API_KEY", raising=False)
    monkeypatch.delenv("MASTERGST_API_KEY", raising=False)
    from largestack._integrations import GSTToolkit

    tk = GSTToolkit()
    validate = next(t for t in tk.get_tools() if t._tool_schema["name"] == "gst_validate_gstin")
    result = await validate("29AAACR5055K1Z5")
    data = json.loads(result)
    assert data["valid_format"] is True
    assert data["lookup"] == "skipped"


# -------------------- MCA Toolkit --------------------


@pytest.mark.asyncio
async def test_mca_validates_cin_format():
    from largestack._integrations import MCAToolkit

    tk = MCAToolkit(api_key="x")
    lookup = next(t for t in tk.get_tools() if t._tool_schema["name"] == "mca_lookup_company")
    result = await lookup("BAD_CIN")
    data = json.loads(result)
    assert data["valid_format"] is False


@pytest.mark.asyncio
async def test_mca_lookup_real_cin():
    from largestack._integrations import MCAToolkit

    tk = MCAToolkit(api_key="x")
    lookup = next(t for t in tk.get_tools() if t._tool_schema["name"] == "mca_lookup_company")
    valid_cin = "U72200KA2010PTC012345"  # Karnataka private ltd, valid format
    with respx.mock() as mock:
        mock.get(f"https://api.probe42.in/v1/companies/{valid_cin}").respond(
            200,
            json={
                "company_name": "Test Pvt Ltd",
                "company_status": "Active",
                "date_of_incorporation": "2010-04-01",
                "company_category": "Company limited by Shares",
                "paid_up_capital": 1000000,
            },
        )
        result = await lookup(valid_cin)
    data = json.loads(result)
    assert data["found"] is True
    assert data["status"] == "Active"


@pytest.mark.asyncio
async def test_mca_director_din_validation():
    from largestack._integrations import MCAToolkit

    tk = MCAToolkit(api_key="x")
    check = next(t for t in tk.get_tools() if t._tool_schema["name"] == "mca_check_director")
    # Invalid (not 8 digits)
    result = await check("123")
    data = json.loads(result)
    assert data["valid_format"] is False


# -------------------- DigiLocker Toolkit --------------------


@pytest.mark.asyncio
async def test_digilocker_no_creds(monkeypatch):
    for v in ["LARGESTACK_DIGILOCKER_CLIENT_ID", "LARGESTACK_DIGILOCKER_CLIENT_SECRET"]:
        monkeypatch.delenv(v, raising=False)
    from largestack._integrations import DigiLockerToolkit

    tk = DigiLockerToolkit()
    list_tool = next(
        t for t in tk.get_tools() if t._tool_schema["name"] == "digilocker_list_issued_documents"
    )
    result = await list_tool("user_token")
    assert "DIGILOCKER" in result


@pytest.mark.asyncio
async def test_digilocker_invalid_token():
    from largestack._integrations import DigiLockerToolkit

    tk = DigiLockerToolkit(client_id="cid", client_secret="cs")
    list_tool = next(
        t for t in tk.get_tools() if t._tool_schema["name"] == "digilocker_list_issued_documents"
    )
    with respx.mock() as mock:
        mock.get(f"{tk.base_url}/files/issued").respond(401)
        result = await list_tool("expired_token")
    assert "expired" in result.lower() or "invalid" in result.lower()


@pytest.mark.asyncio
async def test_digilocker_list_documents():
    from largestack._integrations import DigiLockerToolkit

    tk = DigiLockerToolkit(client_id="c", client_secret="s")
    list_tool = next(
        t for t in tk.get_tools() if t._tool_schema["name"] == "digilocker_list_issued_documents"
    )
    with respx.mock() as mock:
        mock.get(f"{tk.base_url}/files/issued").respond(
            200,
            json={
                "items": [
                    {
                        "uri": "in.gov.uidai-AADHAAR-1234",
                        "name": "Aadhaar Card",
                        "doctype": "AADHAAR",
                        "issuer": "UIDAI",
                        "date": "2024-01-01",
                    }
                ]
            },
        )
        result = await list_tool("valid_token")
    data = json.loads(result)
    assert len(data["documents"]) == 1
    assert data["documents"][0]["doctype"] == "AADHAAR"


# -------------------- eSign Toolkit --------------------


@pytest.mark.asyncio
async def test_esign_no_creds(monkeypatch):
    for v in ["LARGESTACK_ESIGN_CLIENT_ID", "LARGESTACK_ESIGN_CLIENT_SECRET"]:
        monkeypatch.delenv(v, raising=False)
    from largestack._integrations import eSignToolkit

    tk = eSignToolkit()
    init = next(t for t in tk.get_tools() if t._tool_schema["name"] == "esign_initiate")
    result = await init("https://x.com/doc.pdf", "Sachith", "s@x.com")
    assert "ESIGN" in result or "esign" in result.lower()


@pytest.mark.asyncio
async def test_esign_initiate_success():
    from largestack._integrations import eSignToolkit

    tk = eSignToolkit(client_id="cid", client_secret="cs")
    init = next(t for t in tk.get_tools() if t._tool_schema["name"] == "esign_initiate")
    with respx.mock() as mock:
        mock.post("https://esign.emudhra.com/v3/esign/init").respond(
            200,
            json={
                "request_id": "req_123",
                "url": "https://esign.emudhra.com/sign/req_123",
                "expires_at": "2026-05-03T12:00:00Z",
            },
        )
        result = await init("https://x.com/doc.pdf", "Sachith S", "s@x.com")
    data = json.loads(result)
    assert data["request_id"] == "req_123"
    assert "sign" in data["signing_url"]


# -------------------- KYC Toolkit --------------------


@pytest.mark.asyncio
async def test_kyc_pan_invalid_format():
    from largestack._integrations import KYCToolkit

    tk = KYCToolkit(api_key="x")
    verify_pan = next(t for t in tk.get_tools() if t._tool_schema["name"] == "kyc_verify_pan")
    result = await verify_pan("BADPAN")
    data = json.loads(result)
    assert data["valid_format"] is False


@pytest.mark.asyncio
async def test_kyc_pan_verify_success():
    from largestack._integrations import KYCToolkit

    tk = KYCToolkit(api_key="signzy_key")
    verify_pan = next(t for t in tk.get_tools() if t._tool_schema["name"] == "kyc_verify_pan")
    valid_pan = "AAACR1234C"
    with respx.mock() as mock:
        mock.post("https://preproduction.signzy.tech/api/v3/pan/verification").respond(
            200, json={"status": "valid", "name": "SACHITH S", "name_match": True}
        )
        result = await verify_pan(valid_pan, "Sachith S")
    data = json.loads(result)
    assert data["verified"] is True
    assert data["name_match"] is True


@pytest.mark.asyncio
async def test_kyc_aadhaar_okyc_invalid_format():
    from largestack._integrations import KYCToolkit

    tk = KYCToolkit(api_key="x")
    init = next(t for t in tk.get_tools() if t._tool_schema["name"] == "kyc_initiate_aadhaar_okyc")
    result = await init("123")
    data = json.loads(result)
    assert data["valid_format"] is False


@pytest.mark.asyncio
async def test_kyc_aadhaar_okyc_redacts():
    """Verify Aadhaar number is masked in response."""
    from largestack._integrations import KYCToolkit

    tk = KYCToolkit(api_key="signzy_key")
    init = next(t for t in tk.get_tools() if t._tool_schema["name"] == "kyc_initiate_aadhaar_okyc")
    valid_aadhaar = "234567890123"  # starts with 2, 12 digits
    with respx.mock() as mock:
        mock.post("https://preproduction.signzy.tech/api/v3/aadhaar/okyc/init").respond(
            200, json={"request_id": "req_x", "otp_sent": True, "expires_in": 300}
        )
        result = await init(valid_aadhaar)
    data = json.loads(result)
    # Raw aadhaar should NOT appear in response
    assert valid_aadhaar not in result
    # Masked version should be present
    assert data["aadhaar_masked"] == "XXXX XXXX 0123"


@pytest.mark.asyncio
async def test_kyc_aml_check_runs():
    from largestack._integrations import KYCToolkit

    tk = KYCToolkit(api_key="x")
    aml = next(t for t in tk.get_tools() if t._tool_schema["name"] == "kyc_aml_check")
    with respx.mock() as mock:
        mock.post("https://preproduction.signzy.tech/api/v3/aml/screen").respond(
            200,
            json={
                "matches": 0,
                "pep_match": False,
                "sanctions_match": False,
                "adverse_media": False,
                "risk_level": "low",
            },
        )
        result = await aml("Sachith S", "1994-11-20")
    data = json.loads(result)
    assert data["matches_found"] == 0
    assert data["risk_level"] == "low"


@pytest.mark.asyncio
async def test_kyc_aadhaar_otp_format():
    from largestack._integrations import KYCToolkit

    tk = KYCToolkit(api_key="x")
    verify = next(
        t for t in tk.get_tools() if t._tool_schema["name"] == "kyc_verify_aadhaar_okyc_otp"
    )
    # Bad OTP format
    result = await verify("req_x", "abc")
    assert "OTP" in result or "otp" in result.lower()


# -------------------- Aadhaar redaction --------------------


def test_aadhaar_redact_masks_correctly():
    from largestack._integrations.indian_toolkits import _aadhaar_redact

    assert _aadhaar_redact("234567890123") == "XXXX XXXX 0123"
    assert _aadhaar_redact("123") == "XXXX"  # too short → fully masked
    assert _aadhaar_redact("") == "XXXX"
