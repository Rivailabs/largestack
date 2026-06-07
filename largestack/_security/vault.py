"""Secret management with multiple backends and automatic redaction."""

from __future__ import annotations
import os, json, time, logging, hashlib
from typing import Any

log = logging.getLogger("largestack.vault")


class SecretStore:
    """Manage secrets with auto-redaction from traces.

    Backends:
      - env (default): OS environment variables
      - vault: HashiCorp Vault (requires hvac)
      - aws-sm: AWS Secrets Manager (requires boto3)
      - file: Encrypted local file
      - memory: In-memory only (testing)

    Features:
      - Automatic secret redaction from traces/logs
      - TTL-based caching
      - Key rotation support
      - Encryption at rest (file backend)

        store = SecretStore(backend="env")
        api_key = store.get("OPENAI_API_KEY")
        redacted_text = store.redact(log_message)
    """

    def __init__(
        self, backend: str = "env", ttl_seconds: int = 3600, encryption_key: str = None, **config
    ):
        self.backend = backend
        self.ttl_seconds = ttl_seconds
        self._config = config
        self._cache: dict[str, tuple[str, float]] = {}  # key → (value, expires_at)
        self._redact_patterns: set[str] = set()
        self._encryption_key = encryption_key
        self._fernet = None
        if encryption_key:
            try:
                from cryptography.fernet import Fernet
                from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
                from cryptography.hazmat.primitives import hashes as _hashes

                # P0-3 (v0.3.5): real KDF instead of single-iteration SHA-256.
                # PBKDF2-HMAC-SHA256 with 600k iterations (OWASP 2023+ recommendation for SHA-256).
                # Salt is derived from a deterministic transform of the passphrase to keep
                # the key stable across restarts (vault is persistent secret-store, not
                # per-session encryption). For per-session encryption use EncryptionManager.
                # If you want random per-vault salts, set LARGESTACK_VAULT_SALT env var.
                salt_env = os.environ.get("LARGESTACK_VAULT_SALT")
                if salt_env:
                    salt = salt_env.encode("utf-8")[:32].ljust(32, b"\x00")
                else:
                    # Domain-separated deterministic salt: SHA-256("largestack-vault-v1" || passphrase)
                    # This is NOT a cryptographic random salt, but it's strictly better than
                    # single-iteration SHA-256 because the 600k PBKDF2 iterations dominate.
                    salt = hashlib.sha256(
                        b"largestack-vault-v1\x00" + encryption_key.encode()
                    ).digest()
                kdf = PBKDF2HMAC(
                    algorithm=_hashes.SHA256(),
                    length=32,
                    salt=salt,
                    iterations=600_000,
                )
                derived = kdf.derive(encryption_key.encode())
                import base64

                self._fernet = Fernet(base64.urlsafe_b64encode(derived))
            except ImportError:
                log.warning("cryptography not installed — file backend will be plaintext")

    def get(self, key: str, default: str = "") -> str:
        """Get secret with TTL caching."""
        now = time.time()
        # Check cache
        if key in self._cache:
            value, expires = self._cache[key]
            if expires > now:
                return value
            del self._cache[key]

        # Fetch from backend
        value = self._fetch(key, default)

        # Cache with TTL
        if value:
            self._cache[key] = (value, now + self.ttl_seconds)
            self._redact_patterns.add(value)

        return value

    def _fetch(self, key: str, default: str) -> str:
        """Fetch from the configured backend."""
        if self.backend == "env":
            return os.environ.get(key, default)

        if self.backend == "vault":
            return self._vault_fetch(key, default)

        if self.backend == "aws-sm":
            return self._aws_fetch(key, default)

        # v0.5.0: Azure Key Vault + GCP Secret Manager
        if self.backend == "azure-kv":
            return self._azure_kv_fetch(key, default)

        if self.backend == "gcp-sm":
            return self._gcp_sm_fetch(key, default)

        if self.backend == "file":
            return self._file_fetch(key, default)

        if self.backend == "memory":
            return default  # memory backend uses set() only

        return default

    def _vault_fetch(self, key: str, default: str) -> str:
        try:
            import hvac

            client = hvac.Client(
                url=self._config.get("url", os.environ.get("VAULT_ADDR")),
                token=self._config.get("token", os.environ.get("VAULT_TOKEN")),
            )
            mount = self._config.get("mount_point", "secret")
            path = self._config.get("path", "largestack")
            response = client.secrets.kv.v2.read_secret_version(path=path, mount_point=mount)
            return response["data"]["data"].get(key, default)
        except ImportError:
            log.warning("hvac not installed for Vault backend")
            return default
        except Exception as e:
            log.error(f"Vault fetch failed for {key}: {e}")
            return default

    def _aws_fetch(self, key: str, default: str) -> str:
        try:
            import boto3

            client = boto3.client(
                "secretsmanager", region_name=self._config.get("region", "us-east-1")
            )
            response = client.get_secret_value(SecretId=key)
            return response.get("SecretString", default)
        except ImportError:
            log.warning("boto3 not installed for AWS Secrets Manager")
            return default
        except Exception as e:
            log.error(f"AWS SM fetch failed for {key}: {e}")
            return default

    def _azure_kv_fetch(self, key: str, default: str) -> str:
        """Fetch from Azure Key Vault.

        v0.5.0: requires `pip install azure-keyvault-secrets azure-identity`.
        Vault URL from config['vault_url'] or env AZURE_KEYVAULT_URL.
        Uses DefaultAzureCredential (env vars, managed identity, az login, etc.)
        """
        try:
            from azure.keyvault.secrets import SecretClient
            from azure.identity import DefaultAzureCredential
        except ImportError:
            log.warning(
                "Azure Key Vault backend needs: pip install azure-keyvault-secrets azure-identity"
            )
            return default

        vault_url = self._config.get("vault_url") or os.environ.get("AZURE_KEYVAULT_URL", "")
        if not vault_url:
            log.error("Azure KV: vault_url config / AZURE_KEYVAULT_URL env not set")
            return default

        try:
            credential = DefaultAzureCredential()
            client = SecretClient(vault_url=vault_url, credential=credential)
            # Azure secret names can't contain underscores; map common conventions
            azure_key = key.replace("_", "-").lower()
            secret = client.get_secret(azure_key)
            return secret.value if secret.value else default
        except Exception as e:
            log.error(f"Azure KV fetch failed for {key}: {e}")
            return default

    def _gcp_sm_fetch(self, key: str, default: str) -> str:
        """Fetch from GCP Secret Manager.

        v0.5.0: requires `pip install google-cloud-secret-manager`.
        Project from config['project_id'] or env GOOGLE_CLOUD_PROJECT.
        Uses Application Default Credentials.
        """
        try:
            from google.cloud import secretmanager
        except ImportError:
            log.warning("GCP Secret Manager backend needs: pip install google-cloud-secret-manager")
            return default

        project_id = self._config.get("project_id") or os.environ.get("GOOGLE_CLOUD_PROJECT", "")
        if not project_id:
            log.error("GCP SM: project_id config / GOOGLE_CLOUD_PROJECT env not set")
            return default

        try:
            client = secretmanager.SecretManagerServiceClient()
            version = self._config.get("version", "latest")
            name = f"projects/{project_id}/secrets/{key}/versions/{version}"
            response = client.access_secret_version(request={"name": name})
            return response.payload.data.decode("UTF-8")
        except Exception as e:
            log.error(f"GCP SM fetch failed for {key}: {e}")
            return default

    def _file_fetch(self, key: str, default: str) -> str:
        path = self._config.get("path", os.path.expanduser("~/.largestack/secrets.enc"))
        if not os.path.exists(path):
            return default
        try:
            with open(path, "rb") as f:
                data = f.read()
            if self._fernet:
                data = self._fernet.decrypt(data)
            secrets = json.loads(data)
            return secrets.get(key, default)
        except Exception as e:
            log.error(f"File secret fetch failed: {e}")
            return default

    def set(self, key: str, value: str, persist: bool = False):
        """Set a secret. Optionally persist to backend."""
        now = time.time()
        self._cache[key] = (value, now + self.ttl_seconds)
        if value:
            self._redact_patterns.add(value)

        if persist and self.backend == "file":
            self._file_persist(key, value)

    def _file_persist(self, key: str, value: str):
        path = self._config.get("path", os.path.expanduser("~/.largestack/secrets.enc"))
        os.makedirs(os.path.dirname(path), exist_ok=True)

        # Read existing
        secrets = {}
        if os.path.exists(path):
            try:
                with open(path, "rb") as f:
                    data = f.read()
                if self._fernet:
                    data = self._fernet.decrypt(data)
                secrets = json.loads(data)
            except Exception:
                pass

        secrets[key] = value
        data = json.dumps(secrets).encode()
        if self._fernet:
            data = self._fernet.encrypt(data)

        with open(path, "wb") as f:
            f.write(data)

    def rotate(self, key: str, new_value: str):
        """Rotate a secret — new value replaces old, old value stays in redact list."""
        old = self._cache.get(key, (None, 0))[0]
        self.set(key, new_value)
        if old and old in self._redact_patterns:
            # Keep old in redact patterns so any logs still get it redacted
            pass
        log.info(f"Secret rotated: {key}")

    def redact(self, text: str) -> str:
        """Redact all known secrets from text."""
        if not isinstance(text, str):
            text = str(text)
        for secret in self._redact_patterns:
            if len(secret) < 4:
                continue  # Skip very short "secrets" to avoid false positives
            if secret in text:
                if len(secret) <= 4:
                    masked = "*" * len(secret)
                else:
                    masked = secret[:2] + "*" * (len(secret) - 4) + secret[-2:]
                text = text.replace(secret, masked)
        return text

    def clear_cache(self):
        """Clear cached secrets (forces re-fetch on next access)."""
        self._cache.clear()

    def add_redact_pattern(self, pattern: str):
        """Manually add a pattern to always redact."""
        self._redact_patterns.add(pattern)

    @property
    def patterns(self) -> list[str]:
        return list(self._redact_patterns)

    @property
    def cache_size(self) -> int:
        return len(self._cache)
