"""Role-Based Access Control — real implementation with decorators and middleware."""
from __future__ import annotations
import logging
from functools import wraps
from typing import Any, Callable, Set

log = logging.getLogger("largestack.rbac")

# Built-in roles with default permissions
ROLES = {
    "admin": {"*"},  # Wildcard — covers agent.create, agent.delete, etc.  # Wildcard = all permissions
    "operator": {
        "agent.run", "agent.read", "agent.list",
        "session.read", "session.write", "session.delete",
        "tool.execute", "tool.list",
        "metrics.read", "health.read", "traces.read",
    },
    "developer": {
        "agent.run", "agent.read", "agent.list", "agent.create",
        "session.read", "session.write",
        "tool.execute", "tool.list", "tool.create",
        "metrics.read", "traces.read",
    },
    "viewer": {
        "agent.read", "agent.view", "agent.list", "session.read",
        "metrics.read", "health.read", "traces.read", "trace.view",
        "cost.view",
    },
}


class User:
    def __init__(self, user_id: str, roles: list[str] = None, custom_permissions: Set[str] = None):
        self.user_id = user_id
        self.roles = set(roles or [])
        self.custom_permissions = custom_permissions or set()
    
    def get_permissions(self) -> Set[str]:
        """Union of all permissions from roles + custom."""
        perms = set(self.custom_permissions)
        for role in self.roles:
            role_perms = ROLES.get(role, set())
            if "*" in role_perms:
                return {"*"}  # Admin wildcard
            perms.update(role_perms)
        return perms
    
    def has_permission(self, permission: str) -> bool:
        perms = self.get_permissions()
        if "*" in perms: return True
        if permission in perms: return True
        # Wildcard prefix matching (e.g., "agent.*")
        for p in perms:
            if p.endswith(".*") and permission.startswith(p[:-2] + "."):
                return True
        return False


class RBAC:
    """RBAC manager with user registry and permission checks.

        rbac = RBAC()
        rbac.add_user("alice", roles=["admin"])
        rbac.add_user("bob", roles=["viewer"])

        if rbac.check("alice", "agent.delete"):
            # Allow

    v0.4.0: optional SQLite persistence. Pass `db_path` to persist user
    records across restarts. The in-memory `_users` dict is still the
    authoritative cache for hot-path `check()` calls; mutations write
    through to disk. JSON-serialized roles + custom_permissions.

        rbac = RBAC(db_path="~/.largestack/rbac.db")
        rbac.add_user("alice", roles=["admin"])  # persisted to disk
        # ...restart...
        rbac = RBAC(db_path="~/.largestack/rbac.db")  # alice loaded from disk
        assert rbac.check("alice", "agent.delete")
    """
    def __init__(self, db_path: str | None = None):
        self._users: dict[str, User] = {}
        self._audit_log: list[dict] = []
        self._db_path: str | None = None
        if db_path:
            import os as _os
            self._db_path = _os.path.expanduser(db_path)
            self._init_db()
            self._load_users_from_db()

    # ---- v0.4.0 persistence layer ----

    def _init_db(self) -> None:
        """Create the rbac_users table if it doesn't exist."""
        import os as _os
        import sqlite3 as _sq
        d = _os.path.dirname(self._db_path)
        if d:
            _os.makedirs(d, exist_ok=True)
        with _sq.connect(self._db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS rbac_users (
                    user_id TEXT PRIMARY KEY,
                    roles TEXT NOT NULL,
                    custom_permissions TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_rbac_users_updated ON rbac_users(updated_at)")
            conn.commit()

    def _load_users_from_db(self) -> None:
        """Populate the in-memory cache from disk on startup."""
        import json as _j
        import sqlite3 as _sq
        try:
            with _sq.connect(self._db_path) as conn:
                conn.row_factory = _sq.Row
                rows = conn.execute(
                    "SELECT user_id, roles, custom_permissions FROM rbac_users"
                ).fetchall()
        except Exception as e:
            log.warning(f"RBAC: failed to load from {self._db_path}: {e}")
            return
        for r in rows:
            try:
                roles = _j.loads(r["roles"])
                perms = set(_j.loads(r["custom_permissions"]))
                self._users[r["user_id"]] = User(
                    r["user_id"], roles=roles, custom_permissions=perms
                )
            except Exception as e:
                log.warning(f"RBAC: skipping malformed row {r['user_id']}: {e}")
        log.info(f"RBAC: loaded {len(self._users)} users from {self._db_path}")

    def _persist_user(self, user: User) -> None:
        """Write a user record (insert or replace) to disk."""
        if not self._db_path:
            return
        import json as _j
        import sqlite3 as _sq
        import time as _t
        now = _t.time()
        try:
            with _sq.connect(self._db_path) as conn:
                conn.execute(
                    "INSERT INTO rbac_users (user_id, roles, custom_permissions, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?) "
                    "ON CONFLICT(user_id) DO UPDATE SET roles=excluded.roles, "
                    "custom_permissions=excluded.custom_permissions, updated_at=excluded.updated_at",
                    (
                        user.user_id,
                        _j.dumps(sorted(user.roles)),
                        _j.dumps(sorted(user.custom_permissions)),
                        now, now,
                    ),
                )
                conn.commit()
        except Exception as e:
            log.warning(f"RBAC: failed to persist {user.user_id}: {e}")

    def _delete_user(self, user_id: str) -> None:
        if not self._db_path:
            return
        import sqlite3 as _sq
        try:
            with _sq.connect(self._db_path) as conn:
                conn.execute("DELETE FROM rbac_users WHERE user_id=?", (user_id,))
                conn.commit()
        except Exception as e:
            log.warning(f"RBAC: failed to delete {user_id}: {e}")

    # ---- public API ----

    @staticmethod
    def _scoped_user_id(user_id: str, tenant_id: str | None) -> str:
        """v0.5.0: namespace user_id with tenant for multi-tenant isolation.
        
        ``tenant:user`` is the storage key. Without a tenant, the user_id
        is unchanged (backwards compat).
        """
        if tenant_id:
            return f"{tenant_id}:{user_id}"
        return user_id

    def add_user_for_tenant(self, tenant_id: str, user_id: str,
                            roles: list[str] = None,
                            custom_permissions: Set[str] = None) -> User:
        """v0.5.0: tenant-scoped add_user.
        
        Creates a user namespaced by tenant. The same user_id can exist
        across multiple tenants without collision. Use
        ``check_for_tenant(tenant_id, user_id, perm)`` to verify.
        """
        scoped = self._scoped_user_id(user_id, tenant_id)
        return self.add_user(scoped, roles, custom_permissions)

    def check_for_tenant(self, tenant_id: str, user_id: str, permission: str) -> bool:
        """v0.5.0: tenant-scoped permission check."""
        scoped = self._scoped_user_id(user_id, tenant_id)
        return self.check(scoped, permission)

    def check_for_current_tenant(self, user_id: str, permission: str) -> bool:
        """v0.5.0: scope check to current tenant from ContextVar.
        
        Raises ValueError if no tenant context. Multi-tenant SaaS deployments
        should use this to make tenant scoping the safe default — forgetting
        the tenant arg fails loud rather than silently leaking permissions
        across tenants.
        """
        from largestack._enterprise.tenant import _current_tenant_var
        tid = _current_tenant_var.get()
        if not tid:
            raise ValueError(
                "No tenant context. Set with TenantManager.set_current() "
                "or use check_for_tenant(tenant_id=..., ...) explicitly."
            )
        return self.check_for_tenant(tid, user_id, permission)

    def list_users_for_tenant(self, tenant_id: str) -> list[str]:
        """v0.5.0: list user_ids registered under a tenant."""
        prefix = f"{tenant_id}:"
        return [
            uid[len(prefix):] for uid in self._users
            if uid.startswith(prefix)
        ]

    def add_user(self, user_id: str, roles: list[str] = None,
                 custom_permissions: Set[str] = None) -> User:
        user = User(user_id, roles, custom_permissions)
        self._users[user_id] = user
        self._persist_user(user)
        log.info(f"RBAC: user {user_id} added with roles {roles}")
        return user
    
    def get_user(self, user_id: str) -> User | None:
        return self._users.get(user_id)
    
    def remove_user(self, user_id: str) -> bool:
        if user_id in self._users:
            del self._users[user_id]
            self._delete_user(user_id)
            return True
        return False
    
    def check(self, user_id: str, permission: str) -> bool:
        user = self._users.get(user_id)
        if not user:
            self._audit_log.append({"user_id": user_id, "permission": permission, "allowed": False, "reason": "unknown_user"})
            return False
        allowed = user.has_permission(permission)
        self._audit_log.append({"user_id": user_id, "permission": permission, "allowed": allowed})
        return allowed
    
    def grant_role(self, user_id: str, role: str):
        user = self._users.get(user_id)
        if not user:
            raise ValueError(f"User {user_id} not found")
        user.roles.add(role)
        self._persist_user(user)
    
    def revoke_role(self, user_id: str, role: str):
        user = self._users.get(user_id)
        if user:
            user.roles.discard(role)
            self._persist_user(user)
    

    def add_role(self, role_name: str, permissions: list[str]):
        """Define a new role with permissions."""
        ROLES[role_name] = set(permissions)
        log.info(f"RBAC: role '{role_name}' defined with {len(permissions)} permissions")
    
    def assign_role(self, user_id: str, role: str):
        """Assign a role to a user. Creates user if not exists."""
        if user_id not in self._users:
            self.add_user(user_id, roles=[role])
        else:
            self._users[user_id].roles.add(role)
            self._persist_user(self._users[user_id])
        log.info(f"RBAC: user '{user_id}' granted role '{role}'")
    
    def revoke(self, user_id: str, role: str):
        """Revoke a role from a user."""
        self.revoke_role(user_id, role)

    def require(self, permission: str):
        """Decorator: require permission to call function. User taken from kwarg 'user_id' or 'user'."""
        def decorator(fn):
            @wraps(fn)
            def wrapper(*args, **kwargs):
                user_id = kwargs.get("user_id") or kwargs.get("user")
                if not user_id:
                    raise PermissionError("No user_id provided for permission check")
                if not self.check(user_id, permission):
                    raise PermissionError(f"User '{user_id}' lacks permission: {permission}")
                return fn(*args, **kwargs)
            return wrapper
        return decorator
    
    def audit_log(self, user_id: str = None, limit: int = 100) -> list[dict]:
        logs = self._audit_log
        if user_id:
            logs = [l for l in logs if l["user_id"] == user_id]
        return logs[-limit:]


def fastapi_middleware(rbac: RBAC, permission_map: dict):
    """FastAPI middleware that checks permissions per endpoint.
    
        app.middleware("http")(fastapi_middleware(rbac, {
            "/agent/run": "agent.run",
            "/agent/delete": "agent.delete",
        }))
    """
    async def middleware(request, call_next):
        user_id = request.headers.get("X-User-Id")
        path = request.url.path
        required = permission_map.get(path)
        if required:
            from fastapi.responses import JSONResponse
            if not user_id:
                return JSONResponse(
                    {"error": "Missing X-User-Id header (authentication required)"},
                    status_code=401
                )
            if not rbac.check(user_id, required):
                return JSONResponse(
                    {"error": f"Forbidden: requires {required}"},
                    status_code=403
                )
        return await call_next(request)
    return middleware


# v0.3.6: FastAPI dependency factory — drop into per-route Depends().
try:
    from fastapi import HTTPException as _HTTPException, Request as _RBACRequest
    _FASTAPI_AVAILABLE = True
except ImportError:
    _FASTAPI_AVAILABLE = False


def require_permission(rbac: "RBAC", permission: str):
    """Returns a FastAPI dependency that enforces a permission.
    
    Usage:
        from largestack._enterprise.rbac import RBAC, require_permission
        rbac = RBAC()
        rbac.add_user("alice", roles=["admin"])
        
        @app.post("/admin/reset", dependencies=[Depends(require_permission(rbac, "admin.write"))])
        def reset(): ...
    
    Reads identity from X-User-Id header. Returns 401 if missing,
    403 if user lacks permission. The check is constant-time relative
    to the user's permission set (set lookup).
    """
    if not _FASTAPI_AVAILABLE:
        raise ImportError("FastAPI is required for require_permission. pip install fastapi")

    def _dep(request: _RBACRequest) -> str:
        user_id = request.headers.get("X-User-Id")
        if not user_id:
            raise _HTTPException(status_code=401, detail="Missing X-User-Id header")
        if not rbac.check(user_id, permission):
            raise _HTTPException(status_code=403, detail=f"Forbidden: requires {permission}")
        return user_id

    return _dep


def require_role(rbac: "RBAC", role: str):
    """FastAPI dependency that requires a specific role.
    
    Less granular than require_permission but matches simpler RBAC schemes.
    """
    if not _FASTAPI_AVAILABLE:
        raise ImportError("FastAPI is required for require_role. pip install fastapi")

    def _dep(request: _RBACRequest) -> str:
        user_id = request.headers.get("X-User-Id")
        if not user_id:
            raise _HTTPException(status_code=401, detail="Missing X-User-Id header")
        u = rbac.get_user(user_id)
        if not u or role not in u.roles:
            raise _HTTPException(status_code=403, detail=f"Forbidden: requires role={role}")
        return user_id

    return _dep


# v0.3.7: module-level default RBAC instance for serve/dashboard wiring.
_default_rbac: "RBAC | None" = None


def get_default_rbac() -> "RBAC":
    """Returns the module-level default RBAC instance, lazily initialized.
    
    Production deployments should populate this BEFORE calling create_api():
    
        from largestack._enterprise.rbac import get_default_rbac
        rbac = get_default_rbac()
        rbac.add_user("alice", roles=["admin"])
    
    Or replace it entirely:
    
        import largestack._enterprise.rbac as r
        r._default_rbac = my_custom_rbac
    
    v0.3.7: does NOT redefine existing built-in roles ("admin", "viewer", etc.)
    to avoid mutating the module-level ROLES dict in ways that surprise tests.
    The built-in admin/viewer/operator/auditor roles already cover the
    framework's permission space.
    """
    global _default_rbac
    if _default_rbac is None:
        _default_rbac = RBAC()
        # Only define roles that don't already exist in ROLES.
        # The framework's built-in admin role already has wildcard "*".
        _existing = set(ROLES.keys())
        if "operator" not in _existing:
            _default_rbac.add_role("operator", ["agent.run", "agent.read"])
    return _default_rbac


def set_default_rbac(rbac: "RBAC") -> None:
    """Replace the module-level default RBAC instance."""
    global _default_rbac
    _default_rbac = rbac
