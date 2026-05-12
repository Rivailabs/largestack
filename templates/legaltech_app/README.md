# Indian LegalTech Agent

LARGESTACK template for Indian legal document drafting and analysis.

Built for: lawyers, legal-tech platforms, contract review tools.

## Setup
```bash
pip install largestack-agentic-ai
export LARGESTACK_ESIGN_CLIENT_ID=...      # eMudhra or NSDL
export LARGESTACK_ESIGN_CLIENT_SECRET=...
export LARGESTACK_MCA_API_KEY=...          # Probe42 for company lookup
export LARGESTACK_LARGESTACK_OPENAI_API_KEY=sk-...
```

## Capabilities
- Drafts Indian legal documents with proper Act citations
- Looks up Indian companies by CIN before drafting MoUs
- Initiates Aadhaar-based eSign workflows
- Flags non-enforceable clauses

## Run
```bash
largestack run agent.yaml --task "Draft a service agreement between XYZ Pvt Ltd and ABC Services"
```

## Compliance notes
This template enforces:
- Citation of specific Indian Acts and sections
- Indian English usage
- Stamp duty + registration awareness
- Hallucination guardrail (critical for legal accuracy)
- DPDP-compliant client data handling
