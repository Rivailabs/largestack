"""Tests for payment webhook handler."""

import asyncio, json, hashlib, hmac, os, sys, tempfile

sys.path.insert(0, ".")


def tmp_db():
    return os.path.join(tempfile.mkdtemp(), "lic.db")


def test_manual_key_generation():
    from largestack._enterprise.payment import PaymentWebhook

    pw = PaymentWebhook(provider="manual", db_path=tmp_db())
    result = pw.generate_manual_key("test@example.com", "professional")
    assert result["status"] == "created"
    assert result["license_key"].startswith("nxs_professional_")
    assert result["email"] == "test@example.com"


def test_key_validation():
    from largestack._enterprise.payment import PaymentWebhook

    pw = PaymentWebhook(provider="manual", db_path=tmp_db())
    result = pw.generate_manual_key("test@example.com", "enterprise")
    info = pw.validate_key(result["license_key"])
    assert info is not None
    assert info["is_valid"] is True
    assert info["tier"] == "enterprise"


def test_invalid_key():
    from largestack._enterprise.payment import PaymentWebhook

    pw = PaymentWebhook(provider="manual", db_path=tmp_db())
    assert pw.validate_key("nxs_fake_key") is None


def test_lemonsqueezy_webhook():
    from largestack._enterprise.payment import PaymentWebhook

    secret = "test-secret"
    pw = PaymentWebhook(provider="lemonsqueezy", signing_secret=secret, db_path=tmp_db())

    payload = json.dumps(
        {
            "meta": {"event_name": "order_created"},
            "data": {
                "id": "123",
                "attributes": {
                    "user_email": "buyer@example.com",
                    "user_name": "Test Buyer",
                    "product_name": "LARGESTACK Professional",
                },
            },
        }
    ).encode()

    sig = hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()
    result = asyncio.run(pw.handle(payload, sig))
    assert result["status"] == "created"
    assert result["email"] == "buyer@example.com"


def test_bad_signature_rejected():
    from largestack._enterprise.payment import PaymentWebhook

    pw = PaymentWebhook(provider="lemonsqueezy", signing_secret="real-secret", db_path=tmp_db())
    result = asyncio.run(pw.handle(b'{"data":{}}', "wrong-sig"))
    assert result["status"] == "error"


def test_cancel_license():
    from largestack._enterprise.payment import PaymentWebhook

    pw = PaymentWebhook(provider="manual", db_path=tmp_db())
    pw.generate_manual_key("user@test.com", "professional")

    cancel_payload = json.dumps(
        {
            "meta": {"event_name": "subscription_cancelled"},
            "data": {
                "id": "1",
                "attributes": {"user_email": "user@test.com", "product_name": "pro"},
            },
        }
    ).encode()
    pw.provider = "lemonsqueezy"
    pw.signing_secret = ""
    # v1.1.1: no secret now fails closed (forged webhooks must not mint keys).
    rejected = asyncio.run(pw.handle(cancel_payload, ""))
    assert rejected["status"] == "error"
    # Explicit dev opt-in still allows the unsigned path (exercises cancel flow).
    pw.allow_unsigned = True
    result = asyncio.run(pw.handle(cancel_payload, ""))
    assert result["status"] == "cancelled"


def test_list_licenses():
    from largestack._enterprise.payment import PaymentWebhook

    pw = PaymentWebhook(provider="manual", db_path=tmp_db())
    pw.generate_manual_key("a@test.com", "professional")
    pw.generate_manual_key("b@test.com", "enterprise")
    licenses = pw.list_licenses()
    assert len(licenses) == 2


def test_stats():
    from largestack._enterprise.payment import PaymentWebhook

    pw = PaymentWebhook(provider="manual", db_path=tmp_db())
    pw.generate_manual_key("x@test.com")
    s = pw.stats
    assert s["total"] == 1
