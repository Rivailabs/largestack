"""v0.14.0: Tests for DPDP §8 breach notification flow."""

from __future__ import annotations

import time

import pytest


# -------------------- BreachDetector --------------------


def test_detector_emits_no_indicators_below_threshold():
    from largestack._compliance.dpdp_breach import (
        BreachDetector,
        BreachDetectorConfig,
    )

    detector = BreachDetector(
        BreachDetectorConfig(
            mass_read_threshold=100,
            mass_read_window_seconds=300.0,
        )
    )
    for _ in range(50):
        detector.observe_read(tenant_id="t1", user_id="u1")
    assert detector.flush() == []


def test_detector_emits_mass_read_indicator():
    from largestack._compliance.dpdp_breach import (
        BreachDetector,
        BreachDetectorConfig,
    )

    detector = BreachDetector(
        BreachDetectorConfig(
            mass_read_threshold=10,
            mass_read_window_seconds=300.0,
        )
    )
    for _ in range(15):
        detector.observe_read(tenant_id="t1", user_id="u1")
    indicators = detector.flush()
    assert any(i.kind == "mass_read" for i in indicators)


def test_detector_isolates_tenants_in_mass_read_window():
    """A different tenant's reads must not contribute to t1's window."""
    from largestack._compliance.dpdp_breach import (
        BreachDetector,
        BreachDetectorConfig,
    )

    detector = BreachDetector(
        BreachDetectorConfig(
            mass_read_threshold=10,
        )
    )
    for _ in range(8):
        detector.observe_read(tenant_id="t1", user_id="u1")
    for _ in range(8):
        detector.observe_read(tenant_id="t2", user_id="u2")
    assert detector.flush() == []  # neither hit threshold alone


def test_detector_drops_old_window_entries():
    from largestack._compliance.dpdp_breach import (
        BreachDetector,
        BreachDetectorConfig,
    )

    detector = BreachDetector(
        BreachDetectorConfig(
            mass_read_threshold=20,
            mass_read_window_seconds=10.0,
        )
    )
    # Old reads (way before window)
    old_ts = time.time() - 1000.0
    for _ in range(15):
        detector.observe_read(
            tenant_id="t1",
            user_id="u1",
            timestamp=old_ts,
        )
    # New reads
    for _ in range(15):
        detector.observe_read(
            tenant_id="t1",
            user_id="u1",
            timestamp=time.time(),
        )
    indicators = detector.flush()
    # 15 new + 0 old = 15, below threshold of 20
    assert not any(i.kind == "mass_read" for i in indicators)


def test_detector_flags_cross_tenant_attempt():
    from largestack._compliance.dpdp_breach import BreachDetector

    detector = BreachDetector()
    detector.observe_cross_tenant_attempt(
        actor_tenant="t1",
        target_tenant="t2",
        user_id="u1",
    )
    indicators = detector.flush()
    assert len(indicators) == 1
    assert indicators[0].kind == "cross_tenant"
    assert indicators[0].metadata["target_tenant"] == "t2"


def test_detector_ignores_same_tenant_as_cross_tenant():
    from largestack._compliance.dpdp_breach import BreachDetector

    detector = BreachDetector()
    detector.observe_cross_tenant_attempt(
        actor_tenant="t1",
        target_tenant="t1",
    )
    assert detector.flush() == []


def test_detector_flags_unauthorized_export():
    from largestack._compliance.dpdp_breach import BreachDetector

    detector = BreachDetector()
    detector.observe_unauthorized_export(
        tenant_id="t1",
        user_id="u1",
        export_tool="audit-export",
        record_count=5000,
    )
    indicators = detector.flush()
    assert indicators[0].kind == "unauthorized_export"


def test_detector_flush_clears_queue():
    from largestack._compliance.dpdp_breach import BreachDetector

    detector = BreachDetector()
    detector.observe_cross_tenant_attempt(
        actor_tenant="t1",
        target_tenant="t2",
    )
    first = detector.flush()
    second = detector.flush()
    assert len(first) == 1
    assert len(second) == 0


# -------------------- BreachClassifier --------------------


def test_classifier_marks_cross_tenant_as_breach():
    from largestack._compliance.dpdp_breach import (
        BreachClassifier,
        BreachIndicator,
    )

    cls = BreachClassifier()
    ind = BreachIndicator(
        kind="cross_tenant",
        detected_at=time.time(),
        tenant_id="t1",
        record_count=10,
    )
    result = cls.classify(ind)
    assert result.is_personal_data_breach is True
    assert result.severity == "high"
    assert result.must_notify_dpb is True
    assert result.must_notify_principals is True


def test_classifier_marks_system_intrusion_as_critical():
    from largestack._compliance.dpdp_breach import (
        BreachClassifier,
        BreachIndicator,
    )

    cls = BreachClassifier()
    ind = BreachIndicator(
        kind="system_intrusion",
        detected_at=time.time(),
        tenant_id="t1",
    )
    result = cls.classify(ind)
    assert result.severity == "critical"
    assert result.must_notify_dpb is True


def test_classifier_after_hours_alone_not_a_breach():
    """After-hours bulk access is suspicious but not a breach by itself."""
    from largestack._compliance.dpdp_breach import (
        BreachClassifier,
        BreachIndicator,
    )

    cls = BreachClassifier()
    ind = BreachIndicator(
        kind="after_hours",
        detected_at=time.time(),
        tenant_id="t1",
        record_count=200,
    )
    result = cls.classify(ind)
    assert result.is_personal_data_breach is False
    assert result.must_notify_dpb is False


def test_classifier_mass_read_severity_scales_with_records():
    from largestack._compliance.dpdp_breach import (
        BreachClassifier,
        BreachIndicator,
    )

    cls = BreachClassifier()
    small = cls.classify(
        BreachIndicator(
            kind="mass_read",
            detected_at=time.time(),
            tenant_id="t1",
            record_count=2000,
        )
    )
    huge = cls.classify(
        BreachIndicator(
            kind="mass_read",
            detected_at=time.time(),
            tenant_id="t1",
            record_count=200_000,
        )
    )
    assert huge.severity == "critical"
    assert small.severity == "medium"


# -------------------- Notification rendering --------------------


def test_dpb_notification_includes_required_fields():
    from largestack._compliance.dpdp_breach import (
        BreachClassifier,
        BreachIndicator,
        render_dpb_notification,
    )

    cls = BreachClassifier()
    ind = BreachIndicator(
        kind="cross_tenant",
        detected_at=time.time(),
        tenant_id="t1",
        record_count=500,
        description="actor tenant t1 attempted access on target tenant t2",
    )
    classification = cls.classify(ind)
    notif = render_dpb_notification(
        classification,
        organisation_name="Sri Rajeshwari NBFC",
        contact_email="dpo@srirajeshwari.in",
    )
    assert notif.target == "dpb"
    assert "Section 8(6)" in notif.body
    assert "Sri Rajeshwari NBFC" in notif.body
    assert "dpo@srirajeshwari.in" in notif.body
    assert "cross_tenant" in notif.body
    assert "high" in notif.body  # severity


def test_principal_notification_uses_plain_language():
    from largestack._compliance.dpdp_breach import (
        BreachClassifier,
        BreachIndicator,
        render_principal_notification,
    )

    cls = BreachClassifier()
    classification = cls.classify(
        BreachIndicator(
            kind="unauthorized_export",
            detected_at=time.time(),
            tenant_id="t1",
            record_count=5000,
            description="export via audit-export without recorded purpose",
        )
    )
    notif = render_principal_notification(
        classification,
        organisation_name="Sri Rajeshwari NBFC",
        contact_email="grievance@srirajeshwari.in",
        principal_name="Sachith",
        remediation_steps=["Reset password", "Enable 2FA"],
    )
    assert "Sachith" in notif.body
    assert "Reset password" in notif.body
    # Principal-facing must NOT contain regulator-only jargon
    assert "Section 8(6)" not in notif.body


def test_dpb_deadline_is_72_hours():
    from largestack._compliance.dpdp_breach import (
        DPB_NOTIFICATION_DEADLINE_SECONDS,
    )

    assert DPB_NOTIFICATION_DEADLINE_SECONDS == 72 * 3600


# -------------------- LoggingNotifier --------------------


@pytest.mark.asyncio
async def test_logging_notifier_records_sends():
    from largestack._compliance.dpdp_breach import (
        BreachClassifier,
        BreachIndicator,
        LoggingNotifier,
        render_dpb_notification,
    )

    cls = BreachClassifier()
    classification = cls.classify(
        BreachIndicator(
            kind="cross_tenant",
            detected_at=time.time(),
            tenant_id="t1",
        )
    )
    notif = render_dpb_notification(
        classification,
        organisation_name="X",
        contact_email="x@x.in",
    )
    notifier = LoggingNotifier()
    ok = await notifier.send(notif)
    assert ok
    assert len(notifier.sent) == 1


# -------------------- Classification dict serialization --------------------


def test_classification_to_dict_serializable():
    import json
    from largestack._compliance.dpdp_breach import (
        BreachClassifier,
        BreachIndicator,
    )

    cls = BreachClassifier()
    classification = cls.classify(
        BreachIndicator(
            kind="cross_tenant",
            detected_at=time.time(),
            tenant_id="t1",
        )
    )
    json.dumps(classification.to_dict())  # must not raise
