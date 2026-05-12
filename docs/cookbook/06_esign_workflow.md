# Recipe 06 — eSign Workflow

**Use case:** Customer signs a loan agreement digitally using
Aadhaar-OTP-based eSign (no physical signature required).

**Compliance:** IT Act 2000 §3A (electronic signature), MCA notification
on Aadhaar-eSign as legally equivalent to wet signature.

## Architecture

```
1. Customer reviews PDF
2. Click "Sign with Aadhaar"
3. Enter Aadhaar number → OTP sent to Aadhaar-linked phone
4. Customer enters OTP → eSign provider (Signzy/Leegality/eMudhra) signs the PDF
5. Signed PDF + Aadhaar XML response stored
6. Audit log entry with hash
```

## Full code

```python
import asyncio
from largestack._india_kyc import esign_initiate, esign_verify_otp
from largestack._compliance import AuditLogger
from largestack._memory.long_term import LongTermMemoryManager

async def esign_loan_agreement(
    *,
    tenant_id: str,
    customer_id: str,
    document_path: str,
    aadhaar_number: str,
    consent_token: str,
):
    audit = AuditLogger(tenant_id=tenant_id)
    memory = LongTermMemoryManager(
        tenant_id=tenant_id, user_id=customer_id,
    )

    # 1) Initiate eSign — returns request_id + sends OTP
    init = await esign_initiate(
        document_path=document_path,
        aadhaar_number=aadhaar_number,
        purpose="loan_agreement_signing",
        consent_token=consent_token,
    )
    if not init.success:
        return {"status": "fail", "stage": "initiate"}

    await audit.log({
        "event": "esign_initiated",
        "customer_id": customer_id,
        "request_id": init.request_id,
        "document_hash": init.document_hash,
    })

    # 2) Get OTP from customer (UI/IVR/SMS reply) — pass back here
    otp = await get_otp_from_customer(customer_id)  # your UI

    # 3) Verify OTP and sign
    signed = await esign_verify_otp(
        request_id=init.request_id, otp=otp,
    )
    if not signed.success:
        return {"status": "fail", "stage": "otp_verify"}

    # 4) Log the signed event with the signature hash
    await audit.log({
        "event": "esign_completed",
        "customer_id": customer_id,
        "request_id": init.request_id,
        "signed_document_hash": signed.signed_pdf_hash,
        "aadhaar_xml_hash": signed.aadhaar_xml_hash,
        "signature_timestamp": signed.timestamp,
    })

    # 5) Store signed-document reference in archival memory
    await memory.add_archival(
        f"signed_loan_agreement: doc_hash={signed.signed_pdf_hash} "
        f"timestamp={signed.timestamp}",
        tag="signed_agreement",
        purpose="loan_contract_record",
        lawful_basis="contract",
        ttl_seconds=10 * 365 * 24 * 3600,  # 10-year contract retention
    )

    return {
        "status": "signed",
        "signed_path": signed.signed_pdf_path,
        "signature_id": signed.signature_id,
    }


async def get_otp_from_customer(customer_id: str) -> str:
    """Stub — replace with your UI / IVR / SMS-back integration."""
    raise NotImplementedError
```

## Provider compatibility

LARGESTACK's `esign_initiate` / `esign_verify_otp` work with these providers
(via adapter):

| Provider | Adapter | Pricing (per signature) |
|---|---|---|
| Signzy | built-in | ₹15–25 |
| Leegality | built-in | ₹10–20 |
| eMudhra | built-in | ₹25–40 |
| Digio | built-in | ₹20–30 |
| ZoopSign | built-in | ₹15 |

Switch providers by changing one config:

```yaml
# agent.yaml
esign:
  provider: signzy  # or leegality, emudhra, digio, zoopsign
  api_key_env: SIGNZY_API_KEY
```

## Compliance retention

- **Contract documents (loan agreement, NOC)**: 10 years post-closure (RBI MD-IRACP)
- **Aadhaar XML response**: 5 years (UIDAI auth log retention guideline)
- **Signature metadata**: forever (for any future fraud claim)

## Why this matters

- **No printer/scanner**: rural customers can sign on a feature phone via SMS-based OTP
- **Legally equivalent to wet signature**: IT Act §3A
- **Tamper-proof**: every signature has a hash chain entry — modify the PDF and the hash mismatch is provable
