"""Payment webhook handler — LemonSqueezy + Stripe → automatic license key issuance.

Supports:
  - LemonSqueezy (primary, recommended for indie)
  - Stripe (enterprise fallback)
  - Manual key generation (admin CLI)

Flow:
  1. Customer pays on LemonSqueezy/Stripe checkout
  2. Webhook fires → POST /api/webhooks/payment
  3. Verify signature → extract customer email + plan
  4. Generate Ed25519-signed license key
  5. Email key to customer (or return in API)
  6. Key stored in license DB for validation
"""

from __future__ import annotations
import base64, hashlib, hmac, json, logging, os, secrets, sqlite3, time, uuid
from typing import Any, Callable

log = logging.getLogger("largestack.payment")


class PaymentWebhook:
    """Handle payment webhooks from LemonSqueezy or Stripe.

    Usage:
        webhook = PaymentWebhook(
            provider="lemonsqueezy",
            signing_secret=os.environ["LEMONSQUEEZY_WEBHOOK_SECRET"],
            on_license_created=send_email_fn,
        )

        # In FastAPI:
        @app.post("/api/webhooks/payment")
        async def handle(request: Request):
            body = await request.body()
            sig = request.headers.get("X-Signature", "")
            result = await webhook.handle(body, sig)
            return {"status": result["status"]}
    """

    PROVIDERS = ("lemonsqueezy", "stripe", "manual")
    PLANS = {
        "community": {"tier": "community", "max_agents": 3, "price": 0, "duration_days": 36500},
        "professional": {
            "tier": "professional",
            "max_agents": 25,
            "price": 299,
            "duration_days": 365,
        },
        "enterprise": {"tier": "enterprise", "max_agents": 999, "price": 999, "duration_days": 365},
    }

    def __init__(
        self,
        provider: str = "lemonsqueezy",
        signing_secret: str = None,
        db_path: str = "~/.largestack/licenses.db",
        on_license_created: Callable = None,
        allow_unsigned: bool = False,
    ):
        if provider not in self.PROVIDERS:
            raise ValueError(f"Provider must be one of {self.PROVIDERS}")

        self.provider = provider
        self.signing_secret = signing_secret or os.environ.get(
            "LARGESTACK_WEBHOOK_SECRET", os.environ.get("LEMONSQUEEZY_WEBHOOK_SECRET", "")
        )
        # v1.1.1: fail closed. Without a signing secret, webhooks are REJECTED
        # unless the operator explicitly opts in (dev only) — a missing secret
        # must never silently mint real license keys for forged payloads.
        self.allow_unsigned = allow_unsigned
        self.on_license_created = on_license_created

        self.db_path = os.path.expanduser(db_path)
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        # v1.1.1: real Ed25519 signing key (the docstring's long-standing claim).
        # After db_path — the sidecar key file lives next to the license DB.
        self._signing_key = self._load_signing_key()
        self.db = sqlite3.connect(self.db_path, check_same_thread=False)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("""CREATE TABLE IF NOT EXISTS licenses (
            id TEXT PRIMARY KEY,
            key TEXT UNIQUE NOT NULL,
            email TEXT NOT NULL,
            plan TEXT NOT NULL,
            tier TEXT NOT NULL,
            status TEXT DEFAULT 'active',
            max_agents INTEGER DEFAULT 3,
            created_at REAL NOT NULL,
            expires_at REAL NOT NULL,
            payment_provider TEXT,
            payment_id TEXT,
            metadata TEXT
        )""")
        self.db.execute("CREATE INDEX IF NOT EXISTS idx_lic_email ON licenses(email)")
        self.db.execute("CREATE INDEX IF NOT EXISTS idx_lic_key ON licenses(key)")
        self.db.commit()

    def _load_signing_key(self):
        """Load (or create) the Ed25519 license-signing private key.

        Precedence: ``LARGESTACK_LICENSE_SIGNING_KEY`` (32-byte seed, hex or
        base64) > 0600 sidecar file next to the license DB. Returns None only if
        the cryptography backend is unavailable (→ legacy unsigned keys).
        """
        try:
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        except Exception as e:  # pragma: no cover - cryptography is a core dep
            log.warning("cryptography unavailable (%s); license keys will be unsigned.", e)
            return None
        seed = None
        env = os.environ.get("LARGESTACK_LICENSE_SIGNING_KEY")
        if env:
            try:
                seed = (
                    bytes.fromhex(env) if len(env) == 64 else base64.urlsafe_b64decode(env + "==")
                )
            except Exception:
                seed = None
        if seed is None:
            key_path = os.path.join(os.path.dirname(self.db_path), ".license_signing_key")
            try:
                if os.path.exists(key_path):
                    with open(key_path, "rb") as f:
                        seed = f.read().strip()
                if not seed:
                    seed = secrets.token_bytes(32)
                    fd = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                    with os.fdopen(fd, "wb") as f:
                        f.write(seed)
            except OSError as e:
                log.warning("could not establish license signing key (%s); unsigned.", e)
                return None
        try:
            return Ed25519PrivateKey.from_private_bytes(seed[:32])
        except Exception:
            return None

    def public_key_hex(self) -> str | None:
        """Raw Ed25519 public key (hex) for offline license verification."""
        if self._signing_key is None:
            return None
        from cryptography.hazmat.primitives import serialization

        raw = self._signing_key.public_key().public_bytes(
            serialization.Encoding.Raw, serialization.PublicFormat.Raw
        )
        return raw.hex()

    def verify_key_signature(self, key: str) -> bool:
        """Offline-verify a key's Ed25519 signature. Legacy unsigned keys → False."""
        if self._signing_key is None or "." not in key:
            return False
        payload, _, sig_b64 = key.rpartition(".")
        try:
            sig = base64.urlsafe_b64decode(sig_b64 + "=" * (-len(sig_b64) % 4))
            self._signing_key.public_key().verify(sig, payload.encode())
            return True
        except Exception:
            return False

    def verify_signature(self, payload: bytes, signature: str) -> bool:
        """Verify webhook signature. Fails closed when no secret is configured."""
        if not self.signing_secret:
            if self.allow_unsigned:
                log.warning(
                    "No signing secret configured and allow_unsigned=True — "
                    "accepting webhook WITHOUT verification (DEV ONLY)."
                )
                return True
            log.error(
                "Payment webhook rejected: no signing secret configured. "
                "Set LARGESTACK_WEBHOOK_SECRET (or pass allow_unsigned=True for dev)."
            )
            return False

        if self.provider == "lemonsqueezy":
            expected = hmac.new(self.signing_secret.encode(), payload, hashlib.sha256).hexdigest()
            return hmac.compare_digest(expected, signature)

        if self.provider == "stripe":
            # Stripe uses timestamp + payload signing
            try:
                parts = dict(p.split("=", 1) for p in signature.split(","))
                timestamp = parts.get("t", "")
                sig = parts.get("v1", "")
                signed_payload = f"{timestamp}.{payload.decode()}".encode()
                expected = hmac.new(
                    self.signing_secret.encode(), signed_payload, hashlib.sha256
                ).hexdigest()
                return hmac.compare_digest(expected, sig)
            except Exception:
                return False

        return True

    async def handle(self, payload: bytes, signature: str = "") -> dict:
        """Handle incoming webhook. Returns {status, license_key?, error?}."""
        # Verify signature
        if not self.verify_signature(payload, signature):
            log.warning("Payment webhook: signature verification failed")
            return {"status": "error", "error": "Invalid signature"}

        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            return {"status": "error", "error": "Invalid JSON"}

        # Extract payment info based on provider
        if self.provider == "lemonsqueezy":
            info = self._parse_lemonsqueezy(data)
        elif self.provider == "stripe":
            info = self._parse_stripe(data)
        else:
            return {"status": "error", "error": f"Unknown provider: {self.provider}"}

        if not info:
            return {"status": "ignored", "reason": "Not a relevant event"}

        # Handle based on event type
        if info["event"] == "subscription_created":
            return await self._create_license(info)
        elif info["event"] == "subscription_cancelled":
            return await self._cancel_license(info)
        elif info["event"] == "subscription_renewed":
            return await self._renew_license(info)

        return {"status": "ignored", "reason": f"Unhandled event: {info['event']}"}

    def _parse_lemonsqueezy(self, data: dict) -> dict | None:
        """Parse LemonSqueezy webhook payload."""
        meta = data.get("meta", {})
        event_name = meta.get("event_name", "")
        attrs = data.get("data", {}).get("attributes", {})

        event_map = {
            "subscription_created": "subscription_created",
            "subscription_updated": "subscription_renewed",
            "subscription_cancelled": "subscription_cancelled",
            "order_created": "subscription_created",
        }

        event = event_map.get(event_name)
        if not event:
            return None

        # Extract plan from variant/product name
        product_name = attrs.get("product_name", "").lower()
        plan = "community"
        for p in ("enterprise", "professional"):
            if p in product_name:
                plan = p
                break

        return {
            "event": event,
            "email": attrs.get("user_email", ""),
            "name": attrs.get("user_name", ""),
            "plan": plan,
            "payment_id": str(data.get("data", {}).get("id", "")),
            "provider": "lemonsqueezy",
        }

    def _parse_stripe(self, data: dict) -> dict | None:
        """Parse Stripe webhook payload."""
        event_type = data.get("type", "")
        obj = data.get("data", {}).get("object", {})

        event_map = {
            "checkout.session.completed": "subscription_created",
            "customer.subscription.updated": "subscription_renewed",
            "customer.subscription.deleted": "subscription_cancelled",
        }

        event = event_map.get(event_type)
        if not event:
            return None

        # Extract plan from metadata or price
        metadata = obj.get("metadata", {})
        plan = metadata.get("plan", "professional")

        return {
            "event": event,
            "email": obj.get("customer_email", obj.get("customer_details", {}).get("email", "")),
            "name": obj.get("customer_name", ""),
            "plan": plan,
            "payment_id": obj.get("id", ""),
            "provider": "stripe",
        }

    async def _create_license(self, info: dict) -> dict:
        """Generate and store a new license key."""
        plan_config = self.PLANS.get(info["plan"], self.PLANS["professional"])

        license_id = str(uuid.uuid4())
        now = time.time()
        expires = now + (plan_config["duration_days"] * 86400)

        # Generate license key format: nxs_{tier}_{random}_{expiry_hex}
        key = self._generate_key(plan_config["tier"], expires)

        self.db.execute(
            "INSERT INTO licenses (id, key, email, plan, tier, status, max_agents, "
            "created_at, expires_at, payment_provider, payment_id, metadata) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                license_id,
                key,
                info["email"],
                info["plan"],
                plan_config["tier"],
                "active",
                plan_config["max_agents"],
                now,
                expires,
                info["provider"],
                info["payment_id"],
                json.dumps({"name": info.get("name", "")}, default=str),
            ),
        )
        self.db.commit()

        log.info(f"License created: {info['email']} → {info['plan']} (key: {key[:20]}...)")

        # Fire callback
        if self.on_license_created:
            try:
                result = {
                    "license_key": key,
                    "email": info["email"],
                    "plan": info["plan"],
                    "tier": plan_config["tier"],
                    "expires_at": expires,
                    "max_agents": plan_config["max_agents"],
                }
                if hasattr(self.on_license_created, "__call__"):
                    import asyncio

                    if asyncio.iscoroutinefunction(self.on_license_created):
                        await self.on_license_created(result)
                    else:
                        self.on_license_created(result)
            except Exception as e:
                log.error(f"License callback failed: {e}")

        return {
            "status": "created",
            "license_key": key,
            "email": info["email"],
            "plan": info["plan"],
            "expires_at": expires,
        }

    async def _cancel_license(self, info: dict) -> dict:
        """Mark license as cancelled."""
        self.db.execute(
            "UPDATE licenses SET status='cancelled' WHERE email=? AND status='active'",
            (info["email"],),
        )
        self.db.commit()
        log.info(f"License cancelled: {info['email']}")
        return {"status": "cancelled", "email": info["email"]}

    async def _renew_license(self, info: dict) -> dict:
        """Extend license expiry."""
        plan_config = self.PLANS.get(info["plan"], self.PLANS["professional"])
        new_expiry = time.time() + (plan_config["duration_days"] * 86400)

        self.db.execute(
            "UPDATE licenses SET expires_at=?, status='active' WHERE email=? AND status='active'",
            (new_expiry, info["email"]),
        )
        self.db.commit()
        log.info(f"License renewed: {info['email']} → expires {new_expiry}")
        return {"status": "renewed", "email": info["email"], "expires_at": new_expiry}

    def _generate_key(self, tier: str, expires: float) -> str:
        """Generate a license key, Ed25519-signed when a signing key is available.

        Format: ``nxs_{tier}_{random}_{expiry_hex}.{base64url(signature)}``. The
        signature makes the key offline-verifiable (``verify_key_signature``);
        if no signing key could be established, a legacy unsigned key is issued.
        """
        random_part = secrets.token_hex(16)
        expiry_hex = hex(int(expires))[2:]
        payload = f"nxs_{tier}_{random_part}_{expiry_hex}"
        if self._signing_key is not None:
            sig = self._signing_key.sign(payload.encode())
            return f"{payload}.{base64.urlsafe_b64encode(sig).decode().rstrip('=')}"
        return payload

    def validate_key(self, key: str) -> dict | None:
        """Validate a license key against the database."""
        row = self.db.execute(
            "SELECT id, email, plan, tier, status, max_agents, expires_at "
            "FROM licenses WHERE key=?",
            (key,),
        ).fetchone()
        if not row:
            return None

        now = time.time()
        return {
            "id": row[0],
            "email": row[1],
            "plan": row[2],
            "tier": row[3],
            "status": row[4],
            "max_agents": row[5],
            "expires_at": row[6],
            "is_valid": row[4] == "active" and row[6] > now,
            "is_expired": row[6] <= now,
        }

    def list_licenses(self, email: str = None, status: str = None, limit: int = 100) -> list[dict]:
        """List licenses with optional filters."""
        where = []
        params = []
        if email:
            where.append("email=?")
            params.append(email)
        if status:
            where.append("status=?")
            params.append(status)

        sql = "SELECT id, key, email, plan, tier, status, max_agents, created_at, expires_at FROM licenses"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        self.db.row_factory = sqlite3.Row
        return [dict(r) for r in self.db.execute(sql, params).fetchall()]

    def generate_manual_key(self, email: str, plan: str = "professional") -> dict:
        """Generate a license key manually (admin use)."""
        import asyncio

        info = {
            "event": "subscription_created",
            "email": email,
            "plan": plan,
            "name": "",
            "payment_id": f"manual_{uuid.uuid4().hex[:8]}",
            "provider": "manual",
        }
        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(self._create_license(info))
        loop.close()
        return result

    @property
    def stats(self) -> dict:
        rows = self.db.execute(
            "SELECT status, COUNT(*), tier FROM licenses GROUP BY status, tier"
        ).fetchall()
        return {
            "total": sum(r[1] for r in rows),
            "breakdown": [{"status": r[0], "count": r[1], "tier": r[2]} for r in rows],
            "provider": self.provider,
        }
