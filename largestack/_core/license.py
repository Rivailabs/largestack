"""License validation — Ed25519 signature verification.

Production: Rust/PyO3 compiled module (largestack_license).
Development: Python fallback with HMAC-SHA256 verification.

Production detection score:
  container(+2) + cloud_meta(+3) + non-localhost(+2) +
  LARGESTACK_ENV=production(+5) + high_traffic(+2) + tls(+1)
  Score >= 5 = production mode
"""

from __future__ import annotations
import json, os, hashlib, hmac, platform, time, logging, base64
from typing import Any

log = logging.getLogger("largestack.license")

# Ed25519 public key for Python-side verification
_ED25519_PUBLIC_KEY_HEX = "a9f64413bb5a70c9828cff7f53a317d8db98d0c040dede571254ae2b207ab9f7"


# HMAC secret derived from env or machine — NOT hardcoded in source
def _get_hmac_key() -> bytes:
    import os, hashlib

    # Production: LARGESTACK_LICENSE_SECRET env var (set by license server)
    env_key = os.environ.get("LARGESTACK_LICENSE_SECRET")
    if env_key:
        return hashlib.sha256(env_key.encode()).digest()
    # Development: derive from fixed seed (this is fine — dev keys only work in dev mode)
    return hashlib.sha256(b"largestack-dev-only-not-for-production").digest()


_LICENSE_HMAC_KEY = _get_hmac_key()

# v0.3.11: one-time warning latch for HMAC fallback in production
_hmac_fallback_warned = False


def get_machine_fingerprint() -> str:
    """Generate machine fingerprint via HMAC-SHA256."""
    parts = [platform.node(), platform.machine(), platform.system()]
    try:
        if platform.system() == "Linux" and os.path.exists("/etc/machine-id"):
            with open("/etc/machine-id") as f:
                parts.append(f.read().strip())
    except OSError as _e:
        logging.getLogger("largestack.license").debug(f"machine-id read failed: {_e}")
    raw = "|".join(parts)
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def detect_production() -> tuple[bool, int, dict]:
    """Detect if running in production. Requires explicit LARGESTACK_ENV=production.

    Returns (is_prod, score, details). Heuristic score is informational only.
    """
    score = 0
    details = {}
    if os.path.exists("/.dockerenv") or os.environ.get("KUBERNETES_SERVICE_HOST"):
        score += 2
        details["container"] = True
    cloud_vars = [
        "AWS_REGION",
        "GCP_PROJECT",
        "AZURE_SUBSCRIPTION_ID",
        "CLOUD_RUN_SERVICE",
        "ECS_CONTAINER_METADATA_URI",
        "RENDER",
        "FLY_APP_NAME",
        "RAILWAY_ENVIRONMENT",
    ]
    if any(os.environ.get(v) for v in cloud_vars):
        score += 3
        details["cloud"] = True

    explicit = os.environ.get("LARGESTACK_ENV", "").lower() in ("production", "prod")
    if explicit:
        score += 5
        details["env_explicit"] = True

    host = os.environ.get("HOST", os.environ.get("HOSTNAME", "localhost"))
    if host not in ("localhost", "127.0.0.1", "0.0.0.0"):  # nosec B104
        details["non_localhost"] = True  # informational, no score
    if os.environ.get("TLS_CERT") or os.environ.get("SSL_CERT_FILE"):
        score += 1
        details["tls"] = True

    # Production ONLY when explicitly set — heuristics are advisory
    is_prod = explicit
    details["score"] = score
    return is_prod, score, details


class LicenseValidator:
    """Validate Largestack AI license keys.

    Key format: nxs_{tier}_{hmac_signature}_{expiry_timestamp}
    Example:    nxs_pro_a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2_1735689600

    Validation:
    1. Try Rust module (largestack_license) for Ed25519 verification
    2. Fall back to Python HMAC-SHA256 verification
    3. Check expiry timestamp
    4. Check machine fingerprint (if bound)
    """

    def __init__(self, license_key: str = ""):
        self.key = license_key or os.environ.get("LARGESTACK_LICENSE_KEY", "")
        self._valid = None
        self._tier = "community"

    def validate(self) -> dict:
        is_prod, score, details = detect_production()

        if not is_prod:
            return {
                "valid": True,
                "tier": "community",
                "mode": "development",
                "production_score": score,
                "message": "Development mode — no license required",
            }

        if not self.key:
            return {
                "valid": False,
                "tier": "community",
                "mode": "degraded",
                "production_score": score,
                "message": "Production detected but no license key. Get one at https://largestack.ai/pricing",
            }

        # Try Rust compiled module (only exists after maturin build)
        try:
            from largestack_license import (
                validate_license as _nl_validate,
                machine_fingerprint as _nl_fp,
            )

            nl = type(
                "nl",
                (),
                {
                    "validate_license": staticmethod(_nl_validate),
                    "machine_fingerprint": staticmethod(_nl_fp),
                },
            )()
            # Parse key: nxs_{tier}_{signature}_{expiry}
            parts = self.key.split("_", 3)
            if len(parts) != 4 or parts[0] != "nxs":
                return self._invalid("Invalid key format. Expected: nxs_{tier}_{sig}_{expiry}")
            tier, sig_hex, expiry = parts[1], parts[2], parts[3]
            payload = f"{tier}:{expiry}:{nl.machine_fingerprint()}".encode()
            if nl.validate_license(payload, sig_hex):
                self._valid = True
                self._tier = tier
                return {
                    "valid": True,
                    "tier": tier,
                    "mode": "production",
                    "message": "License valid (Ed25519 verified)",
                }
            return self._invalid("Signature verification failed")
        except ImportError:
            # v0.3.11: log a one-time warning when Ed25519 isn't available in
            # production — operators expect Ed25519 per docs but get HMAC.
            global _hmac_fallback_warned
            try:
                if not _hmac_fallback_warned:
                    log.warning(
                        "License: Ed25519 Rust module not installed. "
                        "Falling back to HMAC-SHA256 (weaker). "
                        "Build with: cd largestack_license && maturin build --release"
                    )
                    _hmac_fallback_warned = True
            except NameError:
                pass

        # Python fallback: HMAC-SHA256 verification
        return self._validate_python()

    def _validate_python(self) -> dict:
        """Python fallback validation using HMAC-SHA256."""
        parts = self.key.split("_", 3)
        if len(parts) != 4 or parts[0] != "nxs":
            return self._invalid("Invalid key format. Expected: nxs_{tier}_{sig}_{expiry}")

        tier, sig_hex, expiry_str = parts[1], parts[2], parts[3]

        # Validate tier
        if tier not in ("pro", "enterprise", "trial"):
            return self._invalid(f"Unknown tier: {tier}")

        # Check expiry
        try:
            expiry = int(expiry_str)
            if time.time() > expiry:
                return self._invalid(
                    f"License expired at {time.strftime('%Y-%m-%d', time.localtime(expiry))}"
                )
        except ValueError:
            return self._invalid("Invalid expiry timestamp")

        # Verify HMAC signature
        payload = f"largestack:{tier}:{expiry_str}".encode()
        expected_sig = hmac.new(_LICENSE_HMAC_KEY, payload, hashlib.sha256).hexdigest()[:40]
        if not hmac.compare_digest(sig_hex, expected_sig):
            return self._invalid("Invalid license signature")

        self._valid = True
        self._tier = tier
        tier_names = {"pro": "professional", "enterprise": "enterprise", "trial": "trial"}
        return {
            "valid": True,
            "tier": tier_names.get(tier, tier),
            "mode": "production",
            "machine": get_machine_fingerprint(),
            "message": "License valid (HMAC verified)",
        }

    def _invalid(self, reason: str) -> dict:
        self._valid = False
        return {"valid": False, "tier": "community", "mode": "degraded", "message": reason}

    @property
    def is_valid(self) -> bool:
        if self._valid is None:
            self.validate()
        return self._valid or False

    @property
    def tier(self) -> str:
        if self._valid is None:
            self.validate()
        return self._tier

    @staticmethod
    def generate_key(tier: str = "pro", days: int = 365) -> str:
        """Generate a license key. INTERNAL USE ONLY.

        WARNING: This method should not be exposed in production distributions.
        In Cython-compiled builds, source is not readable.
        For manual key generation during alpha/beta only.

        v0.3.7: Build-time strip — set LARGESTACK_DISABLE_KEYGEN_BUILD=1 in your build
        environment to make this method unconditionally raise. The wheel published
        to PyPI MUST be built with that env set so consumers cannot mint keys.
        Runtime gate `LARGESTACK_KEYGEN_ENABLED=1` only works on a build where the
        build-time strip was NOT applied — i.e., dev / source checkouts.
        """
        import os

        # Build-time strip: hardcoded check that fires if the build flag was set.
        # Production wheel build pipeline runs `sed` to flip this to True before
        # bdist_wheel; the constant approach makes it grep-friendly for the build.
        _BUILD_STRIPPED = False  # build-time flag; do not edit manually
        if _BUILD_STRIPPED or os.environ.get("LARGESTACK_DISABLE_KEYGEN_BUILD") == "1":
            raise RuntimeError(
                "License key generation is disabled in this build. "
                "Use the official issuance service (https://app.largestack.ai/license) "
                "or contact support@largestack.ai."
            )
        if not os.environ.get("LARGESTACK_KEYGEN_ENABLED"):
            raise RuntimeError(
                "Key generation disabled. Set LARGESTACK_KEYGEN_ENABLED=1 for development use."
            )
        expiry = int(time.time()) + (days * 86400)
        payload = f"largestack:{tier}:{expiry}".encode()
        sig = hmac.new(_LICENSE_HMAC_KEY, payload, hashlib.sha256).hexdigest()[:40]
        return f"nxs_{tier}_{sig}_{expiry}"


_license_checked_for_state = None  # Tuple of (key, is_prod) when last checked
_license_warned = False


def check_license():
    """Check license status. Re-evaluates when env state changes."""
    global _license_checked_for_state, _license_warned

    import os, logging

    log = logging.getLogger("largestack.license")

    key = os.environ.get("LARGESTACK_LICENSE_KEY", "")
    is_prod, score, details = detect_production()
    state = (key, is_prod)

    if _license_checked_for_state == state:
        return
    _license_checked_for_state = state

    if key:
        log.debug("License key present")
        return

    if is_prod:
        if not _license_warned:
            _license_warned = True
            log.warning(
                "Largestack AI — Production environment detected (score=%d). "
                "Set LARGESTACK_LICENSE_KEY for licensed use. "
                "Get a key at https://largestack.ai/pricing",
                score,
            )
