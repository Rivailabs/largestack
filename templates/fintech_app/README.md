# Indian Fintech Agent

A LARGESTACK template for Indian fintech (NBFCs, payment platforms, lending apps).

Built-in compliance: DPDP Act 2023, RBI PA-PG Master Directions 2024, PMLA.

## Setup
```bash
pip install largestack
export LARGESTACK_RAZORPAY_KEY_ID=rzp_test_...
export LARGESTACK_RAZORPAY_KEY_SECRET=...
export LARGESTACK_KYC_API_KEY=...   # Signzy or IDfy
export LARGESTACK_LARGESTACK_OPENAI_API_KEY=sk-...
```

## What's included

| Toolkit | What |
|---|---|
| Razorpay | Payment links, refunds, subscriptions |
| UPI | VPA validation, intent creation, status |
| KYC (PAN) | Income Tax verification + name match |
| KYC (Aadhaar OKYC) | OTP-based with auto-redaction |
| AML | Sanctions/PEP screening |

## Run
```bash
largestack run agent.yaml --task "Onboard a new customer with PAN AAACR1234C"
```

## Compliance notes
This template enforces:
- PAN+Aadhaar verification before high-value transactions
- Automatic Aadhaar masking in all logs
- AML screening on new customers
- DPDP-compliant PII handling
