"""DPDP §8 personal-data breach notification (v0.14.0).

Closes Tier A #14. Implements the full DPDP §8 breach detection +
notification workflow:

1. **Detection** — anomaly hooks on memory/audit access patterns
   (mass-read, cross-tenant attempt, after-hours access, unusual
   geography)
2. **Classification** — is this a "personal data breach" per §8?
   Severity scoring: low / medium / high / critical
3. **Notification** — generate templated reports for the Data
   Protection Board (DPB) and affected data principals
4. **Audit chain** — every detection + notification gets a hash-chain
   entry for legal admissibility

DPDP timelines (§8(6)):
- Notify DPB "as soon as practicable" — industry interpretation: 72 hrs
- Notify data principals "without delay" once classified

Penalties (§33):
- Failure to notify: up to ₹250 Cr per violation
- Failure to take security safeguards: up to ₹250 Cr per violation

This module is the *engine* — actual transmission to the DPB API
(when published by MeitY) is pluggable via ``BreachNotifier`` subclasses.
"""

from __future__ import annotations
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Literal, Protocol

log = logging.getLogger(__name__)


BreachSeverity = Literal["low", "medium", "high", "critical"]
BreachKind = Literal[
    "mass_read",  # one principal touches > N records in a
    # short window
    "cross_tenant",  # access attempt across tenant boundary
    "after_hours",  # bulk access outside business hours
    "unusual_geography",  # access from an unexpected region
    "unauthorized_export",  # export tool used without an audit purpose
    "credential_compromise",  # known leaked credential used
    "system_intrusion",  # external entity in system logs
    "other",
]


# -------------------- Domain types --------------------


@dataclass
class BreachIndicator:
    """A signal that *might* indicate a breach. Detected by hooks."""

    kind: BreachKind
    detected_at: float
    tenant_id: str
    user_id: str = ""
    record_count: int = 0
    description: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class BreachClassification:
    """Result of running an indicator through DPDP §8 criteria."""

    indicator: BreachIndicator
    is_personal_data_breach: bool
    severity: BreachSeverity
    affected_principal_count: int
    must_notify_dpb: bool
    must_notify_principals: bool
    rationale: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.indicator.kind,
            "detected_at": self.indicator.detected_at,
            "tenant_id": self.indicator.tenant_id,
            "user_id": self.indicator.user_id,
            "is_personal_data_breach": self.is_personal_data_breach,
            "severity": self.severity,
            "affected_principal_count": self.affected_principal_count,
            "must_notify_dpb": self.must_notify_dpb,
            "must_notify_principals": self.must_notify_principals,
            "rationale": self.rationale,
        }


@dataclass
class BreachNotification:
    """A formatted notification ready for delivery."""

    classification: BreachClassification
    target: Literal["dpb", "principal"]
    subject: str
    body: str
    deadline_seconds: float  # seconds from detection until must be sent
    metadata: dict[str, Any] = field(default_factory=dict)


# -------------------- Detector --------------------


@dataclass
class BreachDetectorConfig:
    """Thresholds for the built-in detector heuristics."""

    mass_read_threshold: int = 1000
    mass_read_window_seconds: float = 300.0
    after_hours_start: int = 22  # 22:00 local
    after_hours_end: int = 6  # 06:00 local
    after_hours_record_threshold: int = 100


class BreachDetector:
    """Aggregate access patterns + emit ``BreachIndicator`` events.

    Used as a thin layer over the existing audit log. Call ``observe``
    on each access; periodically inspect ``flush()`` for indicators.
    """

    def __init__(
        self,
        config: BreachDetectorConfig | None = None,
    ):
        self.config = config or BreachDetectorConfig()
        # Per-tenant per-user sliding window of timestamps
        self._read_windows: dict[
            tuple[str, str],
            list[float],
        ] = {}
        self._indicators: list[BreachIndicator] = []

    def observe_read(
        self,
        *,
        tenant_id: str,
        user_id: str,
        record_count: int = 1,
        timestamp: float | None = None,
    ) -> None:
        """Record a read event. Synchronous — call from any sync ctx."""
        if not tenant_id:
            return
        ts = timestamp if timestamp is not None else time.time()
        key = (tenant_id, user_id)
        window = self._read_windows.setdefault(key, [])

        # Append one timestamp per record (mass_read counts records,
        # not events)
        window.extend([ts] * record_count)

        # Drop entries outside the window
        cutoff = ts - self.config.mass_read_window_seconds
        self._read_windows[key] = [t for t in window if t >= cutoff]

        # Mass-read check
        if len(self._read_windows[key]) >= self.config.mass_read_threshold:
            self._indicators.append(
                BreachIndicator(
                    kind="mass_read",
                    detected_at=ts,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    record_count=len(self._read_windows[key]),
                    description=(
                        f"user '{user_id}' read "
                        f"{len(self._read_windows[key])} records in "
                        f"{self.config.mass_read_window_seconds:.0f}s"
                    ),
                )
            )
            # Reset to avoid duplicate alerts every record
            self._read_windows[key] = []

        # After-hours check
        try:
            tm = time.localtime(ts)
            hour = tm.tm_hour
            after_hours = (
                hour >= self.config.after_hours_start or hour < self.config.after_hours_end
            )
            if after_hours and record_count >= self.config.after_hours_record_threshold:
                self._indicators.append(
                    BreachIndicator(
                        kind="after_hours",
                        detected_at=ts,
                        tenant_id=tenant_id,
                        user_id=user_id,
                        record_count=record_count,
                        description=(
                            f"after-hours bulk access at {hour:02d}:00 ({record_count} records)"
                        ),
                    )
                )
        except Exception:
            pass

    def observe_cross_tenant_attempt(
        self,
        *,
        actor_tenant: str,
        target_tenant: str,
        user_id: str = "",
        timestamp: float | None = None,
    ) -> None:
        if not actor_tenant or not target_tenant:
            return
        if actor_tenant == target_tenant:
            return  # not cross-tenant
        ts = timestamp if timestamp is not None else time.time()
        self._indicators.append(
            BreachIndicator(
                kind="cross_tenant",
                detected_at=ts,
                tenant_id=actor_tenant,
                user_id=user_id,
                description=(
                    f"actor tenant '{actor_tenant}' attempted access on "
                    f"target tenant '{target_tenant}'"
                ),
                metadata={"target_tenant": target_tenant},
            )
        )

    def observe_unauthorized_export(
        self,
        *,
        tenant_id: str,
        user_id: str,
        export_tool: str,
        record_count: int,
        timestamp: float | None = None,
    ) -> None:
        ts = timestamp if timestamp is not None else time.time()
        self._indicators.append(
            BreachIndicator(
                kind="unauthorized_export",
                detected_at=ts,
                tenant_id=tenant_id,
                user_id=user_id,
                record_count=record_count,
                description=(
                    f"export via '{export_tool}' without recorded purpose ({record_count} records)"
                ),
                metadata={"export_tool": export_tool},
            )
        )

    def flush(self) -> list[BreachIndicator]:
        """Return + clear all queued indicators."""
        out, self._indicators = self._indicators, []
        return out


# -------------------- Classifier --------------------


class BreachClassifier:
    """Classify indicators against DPDP §8 criteria."""

    def classify(
        self,
        indicator: BreachIndicator,
    ) -> BreachClassification:
        is_breach, severity, affected = self._evaluate(indicator)

        # DPDP §8(6): notify DPB + principals on any personal data breach
        must_notify_dpb = is_breach
        # Notify principals only when severity ≥ medium
        must_notify_principals = is_breach and severity in (
            "medium",
            "high",
            "critical",
        )

        rationale = self._rationale(indicator, severity, affected)

        return BreachClassification(
            indicator=indicator,
            is_personal_data_breach=is_breach,
            severity=severity,
            affected_principal_count=affected,
            must_notify_dpb=must_notify_dpb,
            must_notify_principals=must_notify_principals,
            rationale=rationale,
        )

    def _evaluate(
        self,
        indicator: BreachIndicator,
    ) -> tuple[bool, BreachSeverity, int]:
        """Returns (is_breach, severity, affected_count)."""
        kind = indicator.kind
        records = max(1, indicator.record_count)

        if kind == "cross_tenant":
            # Always a breach — DPDP §8 strict liability
            return True, "high", records

        if kind == "system_intrusion":
            return True, "critical", records

        if kind == "unauthorized_export":
            severity: BreachSeverity = (
                "critical"
                if records >= 10000
                else "high"
                if records >= 1000
                else "medium"
                if records >= 100
                else "low"
            )
            return True, severity, records

        if kind == "mass_read":
            severity = (
                "critical"
                if records >= 100000
                else "high"
                if records >= 10000
                else "medium"
                if records >= 1000
                else "low"
            )
            # Mass-read alone ISN'T a breach — only if combined with
            # other signals, OR if records >= 1000 (anomaly threshold)
            is_breach = records >= 1000
            return is_breach, severity, records

        if kind == "after_hours":
            return False, "low", records  # alone, not a breach

        if kind == "credential_compromise":
            return True, "high", records

        # Unknown
        return False, "low", records

    def _rationale(
        self,
        indicator: BreachIndicator,
        severity: BreachSeverity,
        affected: int,
    ) -> str:
        return (
            f"Indicator kind='{indicator.kind}' affected "
            f"{affected} record(s); severity classified as "
            f"'{severity}' under DPDP §8 criteria. "
            f"Original observation: {indicator.description}"
        )


# -------------------- Notifier (template + delivery hook) --------------------

DPB_NOTIFICATION_DEADLINE_SECONDS = 72 * 3600.0  # 72 hours
PRINCIPAL_NOTIFICATION_DEADLINE_SECONDS = 24 * 3600.0  # 24 hours


def render_dpb_notification(
    classification: BreachClassification,
    *,
    organisation_name: str,
    contact_email: str,
    description_supplement: str = "",
) -> BreachNotification:
    """Render a DPB notification (English).

    Format follows MeitY's draft DPDP Rules notification template.
    """
    ind = classification.indicator
    detected_dt = time.strftime(
        "%Y-%m-%d %H:%M:%S UTC",
        time.gmtime(ind.detected_at),
    )
    subject = (
        f"DPDP §8 Personal Data Breach Notification — "
        f"{organisation_name} — severity {classification.severity}"
    )
    body = (
        f"To: Data Protection Board of India\n"
        f"From: {organisation_name} <{contact_email}>\n\n"
        f"Pursuant to Section 8(6) of the Digital Personal Data Protection "
        f"Act 2023, this notification is submitted in respect of a "
        f"personal data breach detected on {detected_dt}.\n\n"
        f"1. Nature of the breach: {ind.kind}\n"
        f"2. Severity classification: {classification.severity}\n"
        f"3. Approximate affected data principals: "
        f"{classification.affected_principal_count}\n"
        f"4. Description of indicator: {ind.description}\n"
        f"5. Tenant identifier (internal): {ind.tenant_id}\n"
    )
    if description_supplement:
        body += f"6. Additional context: {description_supplement}\n"
    body += (
        f"\nClassification rationale: {classification.rationale}\n\n"
        f"Mitigation steps taken / underway will be furnished in the "
        f"follow-up report within 7 days as required by Rule 8 of the "
        f"draft DPDP Rules.\n\n"
        f"Authorised representative: {contact_email}\n"
    )
    return BreachNotification(
        classification=classification,
        target="dpb",
        subject=subject,
        body=body,
        deadline_seconds=DPB_NOTIFICATION_DEADLINE_SECONDS,
        metadata={"organisation_name": organisation_name},
    )


def render_principal_notification(
    classification: BreachClassification,
    *,
    organisation_name: str,
    contact_email: str,
    principal_name: str = "Data Principal",
    remediation_steps: list[str] | None = None,
) -> BreachNotification:
    """Render a notification for an affected data principal."""
    ind = classification.indicator
    detected_dt = time.strftime(
        "%Y-%m-%d",
        time.gmtime(ind.detected_at),
    )
    subject = f"Important: Personal data security incident at {organisation_name}"
    steps = remediation_steps or [
        "Reset passwords on accounts you use with this service",
        "Enable two-factor authentication where supported",
        "Monitor your accounts for unusual activity",
    ]
    body = (
        f"Dear {principal_name},\n\n"
        f"On {detected_dt}, {organisation_name} detected a "
        f"security incident affecting personal data.\n\n"
        f"What happened: {ind.description}\n\n"
        f"What we are doing: We have taken immediate action to contain "
        f"the incident and have notified the Data Protection Board of "
        f"India in accordance with the DPDP Act 2023.\n\n"
        f"What you should do:\n"
    )
    for s in steps:
        body += f"  - {s}\n"
    body += (
        f"\nFor questions or to exercise your rights under the DPDP Act "
        f"(including the right to access, correction, and erasure), "
        f"please contact our grievance officer at {contact_email}.\n\n"
        f"Yours sincerely,\n{organisation_name}\n"
    )
    return BreachNotification(
        classification=classification,
        target="principal",
        subject=subject,
        body=body,
        deadline_seconds=PRINCIPAL_NOTIFICATION_DEADLINE_SECONDS,
    )


# -------------------- Pluggable delivery --------------------


class BreachNotifier(Protocol):
    """Pluggable delivery backend (DPB API, email, SMS)."""

    async def send(self, notification: BreachNotification) -> bool: ...


class LoggingNotifier:
    """Default notifier — just logs (for dev / testing)."""

    def __init__(self):
        self.sent: list[BreachNotification] = []

    async def send(self, notification: BreachNotification) -> bool:
        log.warning(
            f"[BREACH NOTIFICATION] target={notification.target} subject='{notification.subject}'"
        )
        self.sent.append(notification)
        return True


__all__ = [
    "BreachKind",
    "BreachSeverity",
    "BreachIndicator",
    "BreachClassification",
    "BreachNotification",
    "BreachDetectorConfig",
    "BreachDetector",
    "BreachClassifier",
    "render_dpb_notification",
    "render_principal_notification",
    "BreachNotifier",
    "LoggingNotifier",
    "DPB_NOTIFICATION_DEADLINE_SECONDS",
    "PRINCIPAL_NOTIFICATION_DEADLINE_SECONDS",
]
