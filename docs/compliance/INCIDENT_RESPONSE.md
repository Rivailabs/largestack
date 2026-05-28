# Largestack AI — Incident Response Plan

## Severity Levels

| Level | Definition | Response Time | Examples |
|---|---|---|---|
| P0 Critical | Data breach, system compromise | 15 min | API key leak, unauthorized data access |
| P1 High | Service outage, security vulnerability | 1 hour | All providers down, guardrail bypass |
| P2 Medium | Degraded performance, partial outage | 4 hours | Single provider failure, high error rate |
| P3 Low | Minor issue, no user impact | 24 hours | Dashboard bug, non-critical log error |

## Response Procedures

### P0 — Critical
1. **Activate kill switch** — `largestack._guard.kill_switch.activate("incident")`
2. **Assess scope** — check audit trail: `audit.query(event_type="agent.error")`
3. **Contain** — revoke compromised credentials, rotate keys
4. **Notify** — affected customers within 72 hours (DPDP Act requirement)
5. **Remediate** — deploy fix via canary deployment
6. **Post-mortem** — document root cause, timeline, corrective actions

### P1 — High  
1. **Check circuit breakers** — `largestack dashboard`
2. **Failover** — circuit breaker auto-routes to healthy providers
3. **Investigate** — review traces and anomaly detection alerts
4. **Fix** — deploy via canary with monitoring

### P2/P3 — Medium/Low
1. **Log** — create issue tracker entry
2. **Fix** — standard development cycle
3. **Deploy** — via CI/CD with quality gates

## Communication Templates

### Data Breach Notification (DPDP Act §8)
```
Subject: Security Incident Notification — [Date]

Dear [Customer],

We are writing to inform you of a data security incident affecting 
your account on the Largestack AI platform.

What happened: [Description]
When: [Date/time discovered]  
What data was affected: [Specific data types]
What we're doing: [Remediation steps]
What you should do: [Customer actions]

Contact: security@largestack.ai
```

## Recovery Procedures
- **Event replay**: `EventStore.reconstruct_state()` — rebuild from event log
- **Saga rollback**: Automatic compensation via `SagaOrchestrator`
- **Checkpoint resume**: `largestack resume` — restart from last checkpoint
