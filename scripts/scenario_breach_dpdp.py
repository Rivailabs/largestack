"""LARGESTACK v0.14.0 — DPDP §8 breach detection scenario.

Simulates an insider-threat scenario where a rogue employee tries to
exfiltrate customer data. LARGESTACK should:

  1. Detect the mass-read pattern
  2. Detect the cross-tenant access attempt
  3. Detect the unauthorized export
  4. Classify each as a breach
  5. Generate the DPB notification template
  6. Generate principal-facing notifications
  7. Track the 72-hour DPDP §8(6) deadline
"""
from __future__ import annotations

# Ensure repo root is importable when this script is launched by path from CI or shell.
import sys as _ls_sys
from pathlib import Path as _LSPath
_LS_ROOT = _LSPath(__file__).resolve().parents[1]
if str(_LS_ROOT) not in _ls_sys.path:
    _ls_sys.path.insert(0, str(_LS_ROOT))

import asyncio
import time

from largestack._compliance.dpdp_breach import (
    BreachDetector, BreachClassifier, BreachDetectorConfig,
    render_dpb_notification, render_principal_notification,
    LoggingNotifier,
    DPB_NOTIFICATION_DEADLINE_SECONDS,
    PRINCIPAL_NOTIFICATION_DEADLINE_SECONDS,
)


async def main():
    print("=" * 70)
    print("  SCENARIO: DPDP §8 Insider Breach Detection")
    print("=" * 70)

    # ---- Setup detector ----
    detector = BreachDetector(BreachDetectorConfig(
        mass_read_threshold=1000,
        mass_read_window_seconds=300.0,
    ))
    classifier = BreachClassifier()
    notifier = LoggingNotifier()

    # ---- Phase 1: Normal traffic baseline ----
    print("\n--- Phase 1: Normal traffic (5 mins) ---")
    for i in range(50):
        detector.observe_read(
            tenant_id="bank_a", user_id=f"normal_user_{i % 5}",
            record_count=1,
        )
    indicators = detector.flush()
    print(f"  Indicators: {len(indicators)} (expected: 0)")
    assert len(indicators) == 0, "false positive on normal traffic"
    print("  ✓ no false positives on normal load")

    # ---- Phase 2: Rogue employee exfiltration ----
    print("\n--- Phase 2: Rogue employee mass-read attempt ---")
    print("  Simulating: rogue user reads 1500 customer records...")
    for _ in range(1500):
        detector.observe_read(
            tenant_id="bank_a", user_id="rogue_employee",
            record_count=1,
        )
    indicators = detector.flush()
    mass_reads = [i for i in indicators if i.kind == "mass_read"]
    print(f"  ✓ Mass-read indicators: {len(mass_reads)}")
    assert len(mass_reads) >= 1

    # Classify
    cls = classifier.classify(mass_reads[0])
    print(f"  ✓ Classification: {cls.severity}")
    print(f"    Records affected:    {cls.affected_principal_count}")
    print(f"    Personal data breach: {cls.is_personal_data_breach}")
    print(f"    Notify DPB:           {cls.must_notify_dpb}")

    # ---- Phase 3: Cross-tenant attempt ----
    print("\n--- Phase 3: Cross-tenant access attempt ---")
    detector.observe_cross_tenant_attempt(
        actor_tenant="bank_a",
        target_tenant="bank_b",
        user_id="rogue_employee",
    )
    indicators = detector.flush()
    cross_tenant = [i for i in indicators if i.kind == "cross_tenant"]
    assert len(cross_tenant) == 1
    print("  ✓ Cross-tenant indicator detected")

    cls = classifier.classify(cross_tenant[0])
    print(f"    Severity:     {cls.severity}")
    print(f"    Notify DPB:   {cls.must_notify_dpb}")
    print(f"    Notify principals: {cls.must_notify_principals}")
    assert cls.severity == "high"

    # ---- Phase 4: Unauthorized export ----
    print("\n--- Phase 4: Unauthorized data export ---")
    detector.observe_unauthorized_export(
        tenant_id="bank_a",
        user_id="rogue_employee",
        export_tool="pii-scan",
        record_count=5000,
    )
    indicators = detector.flush()
    exports = [i for i in indicators if i.kind == "unauthorized_export"]
    assert len(exports) == 1

    cls = classifier.classify(exports[0])
    print(f"  ✓ Unauthorized export indicator")
    print(f"    Records:     {cls.affected_principal_count}")
    print(f"    Severity:    {cls.severity}")
    assert cls.severity == "high"  # 1000-9999 records

    # ---- Phase 5: Generate DPB notification ----
    print("\n--- Phase 5: Generate DPB notification (DPDP §8(6)) ---")
    notif = render_dpb_notification(
        cls,
        organisation_name="Sri Rajeshwari NBFC Pvt Ltd",
        contact_email="dpo@srirajeshwari.in",
        description_supplement=(
            "Internal investigation initiated. Affected user accounts "
            "have been temporarily suspended pending forensic review."
        ),
    )

    print(f"  Subject: {notif.subject}")
    print(f"  Deadline: {notif.deadline_seconds/3600:.0f} hours")
    print(f"  Body length: {len(notif.body)} chars")
    print(f"\n  --- Notification body preview ---")
    for line in notif.body.split("\n")[:10]:
        print(f"    {line}")
    print(f"    ... [truncated]")
    assert "Section 8(6)" in notif.body
    assert notif.deadline_seconds == DPB_NOTIFICATION_DEADLINE_SECONDS

    # ---- Phase 6: Principal-facing notification ----
    print("\n--- Phase 6: Principal notification (plain language) ---")
    principal_notif = render_principal_notification(
        cls,
        organisation_name="Sri Rajeshwari NBFC",
        contact_email="grievance@srirajeshwari.in",
        principal_name="Sachith I A",
        remediation_steps=[
            "Reset your account password using the secure link sent to "
            "your registered email",
            "Enable two-factor authentication via your account settings",
            "Review your recent transactions and report any unrecognized "
            "activity to grievance@srirajeshwari.in",
            "Contact CIBIL/Experian to set a fraud alert on your credit file",
        ],
    )
    print(f"  Subject: {principal_notif.subject}")
    print(f"  Deadline: "
          f"{PRINCIPAL_NOTIFICATION_DEADLINE_SECONDS/3600:.0f} hours")

    # Verify principal notification doesn't have regulator jargon
    assert "Section 8(6)" not in principal_notif.body, \
        "principal notification should not have §8(6) jargon"
    assert "Sachith I A" in principal_notif.body
    print("  ✓ plain language (no §8(6) jargon)")

    # ---- Phase 7: Send via notifier ----
    print("\n--- Phase 7: Deliver notifications ---")
    await notifier.send(notif)
    await notifier.send(principal_notif)
    print(f"  ✓ {len(notifier.sent)} notification(s) queued")

    # ---- Final scorecard ----
    print("\n" + "=" * 70)
    print("  BREACH SCENARIO RESULTS")
    print("=" * 70)
    print(f"  Mass-read detected:       ✓")
    print(f"  Cross-tenant detected:    ✓")
    print(f"  Unauthorized export:      ✓")
    print(f"  DPB notification ready:   ✓")
    print(f"  Principal notification:   ✓ (plain language)")
    print(f"  72hr deadline tracked:    ✓")
    print("\n  ✅ DPDP §8 BREACH FLOW: scenario smoke test passed (beta)")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(asyncio.run(main()))
