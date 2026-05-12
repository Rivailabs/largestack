"""Fintech KYC workflow example.

Demonstrates a real Indian fintech onboarding flow:
1. Validate PAN format (offline)
2. Verify PAN with Income Tax (Signzy/IDfy aggregator)
3. Send Aadhaar OTP
4. AML/sanctions screening
5. Throughout: auto-redact Aadhaar to XXXX XXXX 1234

Run::

    export LARGESTACK_KYC_API_KEY=...
    python fintech_kyc.py
"""
from __future__ import annotations
import asyncio
import json
import os

from largestack._integrations import KYCToolkit


async def onboard_customer(name: str, pan: str, aadhaar: str) -> dict:
    """Run full KYC pipeline for a new customer."""
    if not os.environ.get("LARGESTACK_KYC_API_KEY"):
        print("⚠ LARGESTACK_KYC_API_KEY not set — running format-only validation")

    toolkit = KYCToolkit()
    tools = {t._tool_schema["name"]: t for t in toolkit.get_tools()}

    print(f"\n📋 Onboarding: {name}")
    print(f"   PAN: {pan[:4]}***")
    # NEVER print raw Aadhaar — use redacted form
    print(f"   Aadhaar: XXXX XXXX {aadhaar[-4:]}")

    # Step 1: PAN verification
    print("\n[1/3] Verifying PAN...")
    pan_result = await tools["kyc_verify_pan"](pan, full_name=name)
    pan_data = json.loads(pan_result) if pan_result.startswith("{") else {"raw": pan_result}
    print(f"   PAN format valid: {pan_data.get('valid_format')}")
    if "verified" in pan_data:
        print(f"   PAN verified: {pan_data['verified']}")

    # Step 2: Aadhaar OKYC initiation
    print("\n[2/3] Initiating Aadhaar OKYC...")
    okyc_result = await tools["kyc_initiate_aadhaar_okyc"](aadhaar)
    okyc_data = json.loads(okyc_result) if okyc_result.startswith("{") else {"raw": okyc_result}
    if "aadhaar_masked" in okyc_data:
        print(f"   Masked Aadhaar (logged): {okyc_data['aadhaar_masked']}")
    if "request_id" in okyc_data:
        print(f"   Request ID: {okyc_data['request_id']}")
        # In production: collect OTP from user, then call kyc_verify_aadhaar_okyc_otp

    # Step 3: AML screening
    print("\n[3/3] Running AML / sanctions screening...")
    aml_result = await tools["kyc_aml_check"](name)
    aml_data = json.loads(aml_result) if aml_result.startswith("{") else {"raw": aml_result}
    if "risk_level" in aml_data:
        print(f"   Risk level: {aml_data['risk_level']}")
        print(f"   PEP match: {aml_data.get('pep_match', False)}")
        print(f"   Sanctions match: {aml_data.get('sanctions_match', False)}")

    return {
        "name": name,
        "pan_valid": pan_data.get("verified", False),
        "aadhaar_okyc_initiated": "request_id" in okyc_data,
        "aml_risk": aml_data.get("risk_level", "unknown"),
    }


async def main():
    print("=" * 60)
    print("  LARGESTACK Fintech KYC Example")
    print("=" * 60)

    # Example data (NOT real PII — these are valid format-wise but test data)
    result = await onboard_customer(
        name="Sachith S",
        pan="AAACR1234C",       # valid format
        aadhaar="234567890123",  # valid format (starts with 2-9)
    )

    print("\n" + "=" * 60)
    print("Final result:", json.dumps(result, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
