# Roadmap

Largestack is already a serious release-candidate framework. The next work is not more random features; it is platform hardening.

---

## P0 — Runtime hardening

| Item | Why |
|---|---|
| Queue/backpressure | Prevent overload under high traffic |
| Distributed workers | Scale agent runs beyond one process |
| Durable checkpoints/replay | Resume workflows after crash |
| Concurrency limits | Avoid event loop and memory pressure |
| Load/concurrency evidence | Extend completed 24h soak evidence with traffic pressure |

---

## P1 — Deployment and operations

| Item | Why |
|---|---|
| Real Kubernetes install | Enterprise deployment proof |
| HPA/autoscaling test | Scale validation |
| Postgres/Redis production profile | Durable runtime proof |
| Dashboard polish | Better operator experience |
| Replay debugger | Production incident analysis |

---

## P2 — Developer adoption

| Item | Why |
|---|---|
| Public docs website | Easier onboarding |
| More polished examples | Improve trust |
| 3 flagship demos | Sales/support/RAG/BFSI clarity |
| Template gallery | Faster developer start |
| GitHub issue templates | Community readiness |

---

## P3 — Enterprise and ecosystem

| Item | Why |
|---|---|
| External VAPT | Enterprise trust |
| SOC2/ISO preparation | Regulated customer trust |
| Plugin ecosystem | Compete with larger frameworks |
| More connectors | Enterprise workflows |
| Case studies | Investor/client credibility |
