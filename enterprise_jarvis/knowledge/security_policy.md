# Security Policy

Production data and production logs must never be deleted by an individual; such
actions require a change request and human approval from the security team.

Customer PII must not be pasted into external tools. Access to systems follows
least-privilege: roles are `admin`, `agent`, and `viewer`. Viewers have read-only
access. All privileged actions are recorded in an immutable audit log.
