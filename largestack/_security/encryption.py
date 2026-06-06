"""Encryption at rest + hashing/HMAC + key rotation."""
from __future__ import annotations
import base64, hashlib, hmac, json, logging, os, secrets, time
from typing import Any

log = logging.getLogger("largestack.security.encryption")


class EncryptionManager:
    """AES-256-GCM encryption with key rotation support.
    
    Features:
      - AES-256-GCM (authenticated encryption)
      - Key versioning for rotation
      - PBKDF2 key derivation from password
      - HMAC-SHA256 for message authentication
      - SHA-256 content hashing
    
    Usage:
        enc = EncryptionManager(key="my-master-password")
        ciphertext = enc.encrypt("sensitive data")
        plaintext = enc.decrypt(ciphertext)
        
        # Key rotation
        enc.rotate_key()
        old_plaintext = enc.decrypt(old_ciphertext)  # Still decryptable
        new_ciphertext = enc.encrypt("new data")     # Uses new key
    """
    
    def __init__(self, key: bytes | str | None = None, kdf_iterations: int = 600_000):
        """
        Args:
          key: Bytes key (32 bytes for AES-256), passphrase string, or None (random)
          kdf_iterations: PBKDF2 iterations for string keys (OWASP 2023+: 600k)
        """
        self.kdf_iterations = kdf_iterations

        # Key derivation
        if key is None:
            key = os.environ.get("LARGESTACK_ENCRYPTION_KEY", "")

        if isinstance(key, str):
            if not key:
                key = secrets.token_bytes(32)
                log.warning("EncryptionManager: no key provided, generated random (non-persistent)")
            else:
                # v1.1.1: align with vault.py — 600k PBKDF2 iterations and a
                # domain-separated salt instead of a single global constant.
                # The salt stays deterministic (the key must reproduce across
                # restarts to decrypt at-rest data); set LARGESTACK_ENCRYPTION_SALT
                # for a per-deployment salt that defeats cross-deployment key reuse.
                salt_env = os.environ.get("LARGESTACK_ENCRYPTION_SALT")
                if salt_env:
                    salt = salt_env.encode("utf-8")[:32].ljust(32, b"\x00")
                else:
                    salt = hashlib.sha256(b"largestack-encryption-v1\x00" + key.encode()).digest()
                key = self._derive_key(key.encode(), salt=salt)
        
        if not isinstance(key, bytes) or len(key) != 32:
            raise ValueError(f"Key must be 32 bytes (256 bits), got {type(key).__name__} of {len(key) if isinstance(key, bytes) else '?'}")
        
        # Key store: version → key (for rotation)
        self._keys: dict[int, bytes] = {1: key}
        self._current_version: int = 1
        self._operation_count = 0
    
    def _derive_key(self, password: bytes, salt: bytes) -> bytes:
        """PBKDF2-HMAC-SHA256 key derivation."""
        return hashlib.pbkdf2_hmac("sha256", password, salt, self.kdf_iterations, dklen=32)
    
    def derive_key_from_password(self, password: str, salt: bytes = None) -> bytes:
        """Derive a 32-byte key from a password using PBKDF2."""
        if salt is None:
            salt = secrets.token_bytes(16)
        return self._derive_key(password.encode(), salt)
    
    # Magic prefix to unambiguously identify v2 format
    MAGIC_PREFIX = b"NX\x01"
    
    def encrypt(self, plaintext: str | bytes, associated_data: bytes = None) -> str:
        """Encrypt plaintext. Returns base64 string: MAGIC(3) + version(1) + nonce(12) + ciphertext+tag."""
        self._operation_count += 1
        if isinstance(plaintext, str):
            plaintext = plaintext.encode()
        
        try:
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        except ImportError:
            raise ImportError(
                "cryptography library required for AES-256-GCM. "
                "Install: pip install cryptography>=42.0"
            )
        
        key = self._keys[self._current_version]
        nonce = os.urandom(12)
        aesgcm = AESGCM(key)
        ct = aesgcm.encrypt(nonce, plaintext, associated_data)
        # Format v2: MAGIC || version_byte || nonce || ciphertext_with_tag
        header = self.MAGIC_PREFIX + bytes([self._current_version])
        return base64.b64encode(header + nonce + ct).decode()
    
    def decrypt(self, ciphertext: str) -> str:
        """Decrypt base64-encoded ciphertext. Auto-detects v2 (magic prefix) vs legacy."""
        self._operation_count += 1
        try:
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        except ImportError:
            raise ImportError(
                "cryptography library required for AES-256-GCM decryption. "
                "Install: pip install cryptography>=42.0"
            )
        
        data = base64.b64decode(ciphertext)
        
        if len(data) < 13:
            raise ValueError("Ciphertext too short")
        
        # v2 format: starts with MAGIC_PREFIX
        if data[:3] == self.MAGIC_PREFIX:
            version = data[3]
            if version not in self._keys:
                raise ValueError(f"Unknown key version {version}; available: {list(self._keys)}")
            nonce = data[4:16]
            ct = data[16:]
            key = self._keys[version]
        else:
            # Legacy format: no magic, no version byte. Use current key.
            nonce = data[:12]
            ct = data[12:]
            key = self._keys[self._current_version]
        
        aesgcm = AESGCM(key)
        return aesgcm.decrypt(nonce, ct, None).decode()
    
    def rotate_key(self, new_key: bytes | str = None) -> int:
        """Generate a new key version. Old keys remain for decryption of legacy data.
        
        Returns new key version number.
        """
        if new_key is None:
            new_key = secrets.token_bytes(32)
        elif isinstance(new_key, str):
            new_key = self._derive_key(new_key.encode(), salt=b"largestack-default-salt")
        
        new_version = max(self._keys.keys()) + 1
        self._keys[new_version] = new_key
        self._current_version = new_version
        log.info(f"Encryption key rotated to version {new_version}")
        return new_version
    
    def retire_key(self, version: int):
        """Remove old key (can no longer decrypt data encrypted with it).
        
        Only retire old keys AFTER re-encrypting all data with newer keys.
        """
        if version == self._current_version:
            raise ValueError("Cannot retire current key version")
        if version in self._keys:
            del self._keys[version]
            log.info(f"Encryption key version {version} retired")
    
    # ═══ Hashing / HMAC / Signing ═══
    
    @staticmethod
    def hash_sha256(data: str | bytes) -> str:
        """SHA-256 hash. Returns hex string."""
        if isinstance(data, str):
            data = data.encode()
        return hashlib.sha256(data).hexdigest()
    
    @staticmethod
    def hash_sha512(data: str | bytes) -> str:
        if isinstance(data, str):
            data = data.encode()
        return hashlib.sha512(data).hexdigest()
    
    @staticmethod
    def compare_hashes(a: str, b: str) -> bool:
        """Constant-time hash comparison."""
        return hmac.compare_digest(a, b)
    
    def hmac_sign(self, message: str | bytes) -> str:
        """HMAC-SHA256 sign a message. Returns hex signature."""
        if isinstance(message, str):
            message = message.encode()
        key = self._keys[self._current_version]
        return hmac.new(key, message, hashlib.sha256).hexdigest()
    
    def hmac_verify(self, message: str | bytes, signature: str) -> bool:
        """Verify HMAC-SHA256 signature. Constant-time comparison."""
        expected = self.hmac_sign(message)
        return hmac.compare_digest(expected, signature)
    
    # ═══ Password hashing ═══
    
    def hash_password(self, password: str, salt: bytes = None) -> str:
        """Hash password with PBKDF2 + random salt. Returns salt||hash as base64."""
        if salt is None:
            salt = secrets.token_bytes(16)
        derived = self._derive_key(password.encode(), salt)
        return base64.b64encode(salt + derived).decode()
    
    def verify_password(self, password: str, hashed: str) -> bool:
        """Verify password against stored hash."""
        try:
            data = base64.b64decode(hashed)
            salt, expected = data[:16], data[16:]
            derived = self._derive_key(password.encode(), salt)
            return hmac.compare_digest(derived, expected)
        except Exception:
            return False
    
    @property
    def stats(self) -> dict:
        return {
            "key_versions": list(self._keys.keys()),
            "current_version": self._current_version,
            "operation_count": self._operation_count,
        }
