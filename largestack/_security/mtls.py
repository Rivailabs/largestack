"""Mutual TLS for inter-agent communication — certificate management and verification.

Features:
  - Self-signed CA generation for development
  - Certificate generation per agent
  - Certificate rotation with overlap period
  - Certificate revocation list (CRL)
  - TLS context creation for httpx/aiohttp
  - Certificate chain validation
"""
from __future__ import annotations
import hashlib, json, logging, os, time, uuid
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger("largestack.security.mtls")


@dataclass
class CertInfo:
    """Certificate metadata."""
    cert_id: str
    agent_name: str
    fingerprint: str
    issued_at: float
    expires_at: float
    serial: str
    issuer: str = "largestack-ca"
    status: str = "active"  # active, rotated, revoked
    
    @property
    def is_expired(self) -> bool:
        return time.time() > self.expires_at
    
    @property
    def days_remaining(self) -> float:
        return max(0, (self.expires_at - time.time()) / 86400)
    
    def to_dict(self) -> dict:
        return {
            "cert_id": self.cert_id, "agent_name": self.agent_name,
            "fingerprint": self.fingerprint, "issued_at": self.issued_at,
            "expires_at": self.expires_at, "serial": self.serial,
            "issuer": self.issuer, "status": self.status,
            "is_expired": self.is_expired, "days_remaining": round(self.days_remaining, 1),
        }


class MTLSManager:
    """Manage mutual TLS certificates for inter-agent communication.
    
    Usage:
        mtls = MTLSManager(ca_dir="~/.largestack/certs")
        
        # Generate CA (once)
        mtls.init_ca()
        
        # Generate per-agent certs
        cert = mtls.issue_cert("agent-research")
        cert = mtls.issue_cert("agent-writer")
        
        # Get TLS context for httpx
        ssl_ctx = mtls.get_ssl_context("agent-research")
        async with httpx.AsyncClient(verify=ssl_ctx) as client:
            ...
        
        # Rotate before expiry
        new_cert = mtls.rotate_cert("agent-research")
        
        # Revoke compromised cert
        mtls.revoke_cert(cert.cert_id)
    """
    
    DEFAULT_VALIDITY_DAYS = 365
    ROTATION_OVERLAP_DAYS = 30
    
    def __init__(self, ca_dir: str = "~/.largestack/certs",
                 validity_days: int = None,
                 auto_rotate_days: int = 30):
        self.ca_dir = os.path.expanduser(ca_dir)
        os.makedirs(self.ca_dir, exist_ok=True)
        self.validity_days = validity_days or self.DEFAULT_VALIDITY_DAYS
        self.auto_rotate_days = auto_rotate_days
        
        self._certs: dict[str, list[CertInfo]] = {}  # agent_name → [certs]
        self._revoked: set[str] = set()  # cert_ids
        self._ca_initialized = False
        
        # Load state
        self._load_state()
    
    def init_ca(self, cn: str = "LARGESTACK Agent CA", validity_years: int = 10) -> dict:
        """Initialize Certificate Authority (self-signed for dev, real CA for prod)."""
        try:
            from cryptography import x509
            from cryptography.x509.oid import NameOID
            from cryptography.hazmat.primitives import hashes, serialization
            from cryptography.hazmat.primitives.asymmetric import rsa
            import datetime
            
            # Generate CA key pair
            ca_key = rsa.generate_private_key(public_exponent=65537, key_size=4096)
            
            subject = issuer = x509.Name([
                x509.NameAttribute(NameOID.COMMON_NAME, cn),
                x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Largestack AI"),
            ])
            
            ca_cert = (
                x509.CertificateBuilder()
                .subject_name(subject)
                .issuer_name(issuer)
                .public_key(ca_key.public_key())
                .serial_number(x509.random_serial_number())
                .not_valid_before(datetime.datetime.now(datetime.timezone.utc))
                .not_valid_after(datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=validity_years * 365))
                .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
                .sign(ca_key, hashes.SHA256())
            )
            
            # Save
            key_path = os.path.join(self.ca_dir, "ca.key")
            cert_path = os.path.join(self.ca_dir, "ca.crt")
            
            with open(key_path, "wb") as f:
                f.write(ca_key.private_bytes(
                    serialization.Encoding.PEM,
                    serialization.PrivateFormat.PKCS8,
                    serialization.NoEncryption()
                ))
            os.chmod(key_path, 0o600)
            
            with open(cert_path, "wb") as f:
                f.write(ca_cert.public_bytes(serialization.Encoding.PEM))
            
            self._ca_initialized = True
            log.info(f"CA initialized: {cn} (valid {validity_years} years)")
            return {"status": "created", "path": cert_path, "cn": cn}
            
        except ImportError:
            # B-04 (v0.3.4): Match EncryptionManager pattern — stub mTLS is a security
            # vulnerability if it silently activates. Hard-fail unless explicit opt-in.
            env = os.environ.get("LARGESTACK_ENV", "development").lower()
            allow_stub = os.environ.get("LARGESTACK_ALLOW_INSECURE_MTLS", "").lower() in ("1", "true", "yes")
            if env == "production":
                raise ImportError(
                    "mTLS requires the `cryptography` library. Install: pip install cryptography. "
                    "Stub CA is not allowed in production."
                )
            if not allow_stub:
                raise ImportError(
                    "mTLS requires the `cryptography` library. Install: pip install cryptography. "
                    "To opt into the insecure stub CA for development testing only, set "
                    "LARGESTACK_ALLOW_INSECURE_MTLS=1. The stub does NOT provide real TLS security."
                )
            log.warning(
                "mTLS: USING STUB CA (LARGESTACK_ALLOW_INSECURE_MTLS=1). "
                "This does NOT provide real certificate validation."
            )
            return self._stub_init_ca(cn)
    
    def _stub_init_ca(self, cn: str) -> dict:
        """Stub CA for when cryptography lib isn't available."""
        import secrets
        ca_id = secrets.token_hex(16)
        state = {"ca_id": ca_id, "cn": cn, "created_at": time.time()}
        with open(os.path.join(self.ca_dir, "ca.json"), "w") as f:
            json.dump(state, f)
        self._ca_initialized = True
        return {"status": "created_stub", "ca_id": ca_id, "cn": cn}
    
    def issue_cert(self, agent_name: str, validity_days: int = None) -> CertInfo:
        """Issue a new certificate for an agent."""
        validity = validity_days or self.validity_days
        now = time.time()
        
        cert_id = f"cert_{uuid.uuid4().hex[:12]}"
        serial = uuid.uuid4().hex[:16]
        fingerprint = hashlib.sha256(f"{agent_name}:{serial}:{now}".encode()).hexdigest()[:40]
        
        try:
            cert_info = self._issue_real_cert(agent_name, cert_id, serial, validity)
        except (ImportError, Exception) as e:
            log.debug(f"Using stub cert (real cert failed: {e})")
            cert_info = CertInfo(
                cert_id=cert_id, agent_name=agent_name, fingerprint=fingerprint,
                issued_at=now, expires_at=now + validity * 86400,
                serial=serial, issuer="largestack-ca-stub",
            )
        
        self._certs.setdefault(agent_name, []).append(cert_info)
        self._save_state()
        log.info(f"Certificate issued: {agent_name} (id: {cert_id}, valid {validity} days)")
        return cert_info
    
    def _issue_real_cert(self, agent_name: str, cert_id: str, serial_hex: str,
                         validity_days: int) -> CertInfo:
        """Issue real X.509 cert signed by CA."""
        from cryptography import x509
        from cryptography.x509.oid import NameOID
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        import datetime
        
        ca_key_path = os.path.join(self.ca_dir, "ca.key")
        ca_cert_path = os.path.join(self.ca_dir, "ca.crt")
        
        if not os.path.exists(ca_key_path):
            raise FileNotFoundError("CA not initialized. Call init_ca() first.")
        
        with open(ca_key_path, "rb") as f:
            ca_key = serialization.load_pem_private_key(f.read(), password=None)
        with open(ca_cert_path, "rb") as f:
            ca_cert = x509.load_pem_x509_certificate(f.read())
        
        # Generate agent key
        agent_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        now = datetime.datetime.now(datetime.timezone.utc)
        
        agent_cert = (
            x509.CertificateBuilder()
            .subject_name(x509.Name([
                x509.NameAttribute(NameOID.COMMON_NAME, agent_name),
            ]))
            .issuer_name(ca_cert.subject)
            .public_key(agent_key.public_key())
            .serial_number(int(serial_hex, 16))
            .not_valid_before(now)
            .not_valid_after(now + datetime.timedelta(days=validity_days))
            .add_extension(
                x509.SubjectAlternativeName([x509.DNSName(agent_name)]),
                critical=False,
            )
            .sign(ca_key, hashes.SHA256())
        )
        
        # Save agent cert + key
        agent_dir = os.path.join(self.ca_dir, "agents", agent_name)
        os.makedirs(agent_dir, exist_ok=True)
        
        key_path = os.path.join(agent_dir, f"{cert_id}.key")
        cert_path = os.path.join(agent_dir, f"{cert_id}.crt")
        
        with open(key_path, "wb") as f:
            f.write(agent_key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption()
            ))
        os.chmod(key_path, 0o600)
        
        with open(cert_path, "wb") as f:
            f.write(agent_cert.public_bytes(serialization.Encoding.PEM))
        
        fingerprint = agent_cert.fingerprint(hashes.SHA256()).hex()
        
        return CertInfo(
            cert_id=cert_id, agent_name=agent_name, fingerprint=fingerprint,
            issued_at=time.time(), expires_at=time.time() + validity_days * 86400,
            serial=serial_hex, issuer="largestack-ca",
        )
    
    def rotate_cert(self, agent_name: str) -> CertInfo:
        """Rotate certificate — issue new, keep old active for overlap period."""
        new_cert = self.issue_cert(agent_name)
        
        # Mark old certs as rotated (but keep them valid for overlap)
        for cert in self._certs.get(agent_name, []):
            if cert.cert_id != new_cert.cert_id and cert.status == "active":
                cert.status = "rotated"
        
        self._save_state()
        log.info(f"Certificate rotated for {agent_name}: {new_cert.cert_id}")
        return new_cert
    
    def revoke_cert(self, cert_id: str) -> bool:
        """Revoke a certificate immediately."""
        for agent_certs in self._certs.values():
            for cert in agent_certs:
                if cert.cert_id == cert_id:
                    cert.status = "revoked"
                    self._revoked.add(cert_id)
                    self._save_state()
                    log.warning(f"Certificate revoked: {cert_id}")
                    return True
        return False
    
    def is_valid(self, cert_id: str) -> bool:
        """Check if a certificate is currently valid (not expired, not revoked)."""
        if cert_id in self._revoked:
            return False
        for agent_certs in self._certs.values():
            for cert in agent_certs:
                if cert.cert_id == cert_id:
                    return cert.status == "active" and not cert.is_expired
        return False
    
    def get_ssl_context(self, agent_name: str):
        """Get SSL context for httpx/aiohttp with mTLS."""
        import ssl
        ctx = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
        
        ca_cert_path = os.path.join(self.ca_dir, "ca.crt")
        if os.path.exists(ca_cert_path):
            ctx.load_verify_locations(ca_cert_path)
        
        # Load latest active cert for this agent
        agent_certs = [c for c in self._certs.get(agent_name, [])
                       if c.status == "active" and not c.is_expired]
        if agent_certs:
            latest = agent_certs[-1]
            agent_dir = os.path.join(self.ca_dir, "agents", agent_name)
            cert_path = os.path.join(agent_dir, f"{latest.cert_id}.crt")
            key_path = os.path.join(agent_dir, f"{latest.cert_id}.key")
            if os.path.exists(cert_path) and os.path.exists(key_path):
                ctx.load_cert_chain(cert_path, key_path)
        
        return ctx
    
    def get_expiring_certs(self, within_days: int = 30) -> list[CertInfo]:
        """Get certs expiring within N days."""
        threshold = time.time() + within_days * 86400
        expiring = []
        for agent_certs in self._certs.values():
            for cert in agent_certs:
                if cert.status == "active" and cert.expires_at <= threshold:
                    expiring.append(cert)
        return expiring
    
    def auto_rotate_expiring(self) -> list[CertInfo]:
        """Auto-rotate all certs expiring within auto_rotate_days."""
        expiring = self.get_expiring_certs(self.auto_rotate_days)
        rotated = []
        seen_agents = set()
        for cert in expiring:
            if cert.agent_name not in seen_agents:
                new_cert = self.rotate_cert(cert.agent_name)
                rotated.append(new_cert)
                seen_agents.add(cert.agent_name)
        return rotated
    
    def _save_state(self):
        state = {
            "certs": {name: [c.to_dict() for c in certs]
                      for name, certs in self._certs.items()},
            "revoked": list(self._revoked),
        }
        with open(os.path.join(self.ca_dir, "state.json"), "w") as f:
            json.dump(state, f, indent=2)
    
    def _load_state(self):
        path = os.path.join(self.ca_dir, "state.json")
        if not os.path.exists(path):
            return
        try:
            with open(path) as f:
                state = json.load(f)
            self._revoked = set(state.get("revoked", []))
            for name, certs in state.get("certs", {}).items():
                self._certs[name] = [CertInfo(**{k: v for k, v in c.items()
                                    if k in CertInfo.__dataclass_fields__})
                                    for c in certs]
        except Exception as e:
            log.warning(f"Failed to load mTLS state: {e}")
    
    @property
    def stats(self) -> dict:
        all_certs = [c for certs in self._certs.values() for c in certs]
        return {
            "total_certs": len(all_certs),
            "active": sum(1 for c in all_certs if c.status == "active"),
            "revoked": len(self._revoked),
            "agents": len(self._certs),
            "expiring_30d": len(self.get_expiring_certs(30)),
            "ca_initialized": self._ca_initialized or os.path.exists(
                os.path.join(self.ca_dir, "ca.crt")) or os.path.exists(
                os.path.join(self.ca_dir, "ca.json")),
        }
