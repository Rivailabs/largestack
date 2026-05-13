# AML Policy

## High-Risk Indicators
- Transactions to/from sanctioned countries (e.g., Iran, North Korea, Syria, Cuba).
- Amount spikes exceeding 5x the customer's average monthly volume.
- Keywords: 'terrorism', 'money laundering', 'sanctions evasion', 'illicit', 'bribe'.
- High-risk KYC profile (kyc_risk = 'high').

## SAR Filing
- All high-risk screenings require approval before filing.
- SARs are never filed externally by this system.

## Policy Q&A
- Use token-overlap retrieval to answer questions.
- If insufficient evidence, return 'Insufficient evidence to answer.'
