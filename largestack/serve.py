"""REST API server — deploy any agent as HTTP API.

    from largestack import Agent
    from largestack.serve import serve
    agent = Agent(name="api", llm="openai/gpt-4o-mini")
    serve(agent, port=8000)
    # POST /run, POST /stream, GET /health, GET /tools, GET /cost

Authentication (v0.5.0):
    - **X-API-Key header** (primary, machine-to-machine)
    - **session cookie** (browser-friendly, set via POST /login with X-API-Key
      then retained by the browser; revoked via POST /logout)

Both methods are accepted. Cookie-auth requires LARGESTACK_SESSION_BACKEND to be
configured for multi-worker deployments; defaults to in-memory.
"""
# v0.3.6: do NOT use `from __future__ import annotations` here. It turns all
# annotations into strings, which breaks FastAPI's request-body detection for
# Pydantic models defined inside create_api(). We use Python 3.11+ native
# union syntax (`str | None`) directly.
import asyncio, json, os, secrets, time, logging
from typing import Any
from fastapi import Request, HTTPException, Response

log = logging.getLogger("largestack.serve")

# Module-level auth dep so FastAPI can resolve the Request annotation reliably.
# Tests + runtime read LARGESTACK_API_KEY at call time.
_warned_no_key = [False]

# v0.5.0: Cookie session config
_SESSION_COOKIE = "largestack_session"
_SESSION_TTL = int(os.environ.get("LARGESTACK_SESSION_TTL_SECONDS", "3600"))


def _get_session_store():
    """Lazy-init session store at first use."""
    if not hasattr(_get_session_store, "_store"):
        from largestack._enterprise.session_store import create_session_store
        _get_session_store._store = create_session_store()
    return _get_session_store._store


def _verify_api_key_module(request: Request) -> None:
    """Auth — accepts X-API-Key header OR session cookie (v0.5.0).

    - If LARGESTACK_API_KEY is set:
        - If X-API-Key header matches → OK
        - Else if session cookie is valid → OK
        - Else → 401
    - If unset and LARGESTACK_ENV=production → 401.
    - If unset in dev → allow with one-time warning.
    """
    expected = os.environ.get("LARGESTACK_API_KEY")

    # 1. X-API-Key path (machine-to-machine, primary)
    if expected:
        provided = request.headers.get("X-API-Key", "")
        if provided and secrets.compare_digest(provided, expected):
            return

        # 2. Cookie-session path (browsers, v0.5.0)
        cookie = request.cookies.get(_SESSION_COOKIE)
        if cookie:
            store = _get_session_store()
            session = store.get(cookie)
            if session is not None and not session.is_expired:
                # Touch (extends last_active in store)
                session.touch()
                store.put(session)
                return

        raise HTTPException(
            status_code=401,
            detail="Invalid or missing X-API-Key / session cookie",
        )

    # No API key configured — dev mode behavior (unchanged)
    if os.environ.get("LARGESTACK_ENV", "development").lower() == "production":
        raise HTTPException(
            status_code=401,
            detail="Serve endpoint requires authentication. Set LARGESTACK_API_KEY env var.",
        )
    if not _warned_no_key[0]:
        log.warning(
            "LARGESTACK_API_KEY is not set. Serve endpoints are unauthenticated in development. "
            "Set LARGESTACK_API_KEY before deploying."
        )
        _warned_no_key[0] = True


def serve(agent, host: str = "127.0.0.1", port: int = 8000, **kw):
    """Start HTTP API server for an agent."""
    import uvicorn
    app = create_api(agent)
    uvicorn.run(app, host=host, port=port, **kw)


def create_app(agent: Any | None = None) -> Any:
    """Create a FastAPI app for an agent.

    Compatibility wrapper for docs/checklists and FastAPI test clients. If no
    agent is supplied, a lightweight default Agent is created for health,
    metrics, and basic API smoke tests; real deployments should pass their
    configured Agent to ``create_api(agent)`` or ``serve(agent)``.
    """
    if agent is None:
        from largestack import Agent
        agent = Agent(
            name=os.environ.get("LARGESTACK_SERVE_AGENT_NAME", "serve"),
            llm=os.environ.get("LARGESTACK_DEFAULT_LLM", "openai/gpt-4o-mini"),
        )
    return create_api(agent)


def create_api(agent) -> Any:
    """Create FastAPI app for an agent.

    Auth: /run, /stream, /tools, /cost are protected via X-API-Key header
    matching the LARGESTACK_API_KEY env var. Health/liveness/readiness probes
    are always public for deployment infrastructure.

    In dev mode (LARGESTACK_ENV != "production"), if LARGESTACK_API_KEY is unset,
    auth is bypassed with a one-time warning. In production, missing key
    means all protected routes return 401.
    """
    from fastapi import FastAPI, Depends
    from fastapi.responses import StreamingResponse, JSONResponse
    from pydantic import BaseModel
    try:
        from sse_starlette.sse import EventSourceResponse
    except ImportError:
        # Fallback: plain StreamingResponse with SSE format
        from fastapi.responses import StreamingResponse as EventSourceResponse

    app = FastAPI(title=f"Largestack AI — {agent.name}", version="1.0.0")
    
    # v0.3.7: CORS middleware on serve API. Reuses dashboard's resolver so the
    # same allowlist policy applies (LARGESTACK_CORS_ALLOWED_ORIGINS env, no '*' silently,
    # production deny-by-default).
    from fastapi.middleware.cors import CORSMiddleware
    from largestack._dashboard.api import _resolve_cors_origins
    _origins = _resolve_cors_origins()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "Authorization", "X-API-Key", "X-User-Id"],
        max_age=600,
    )
    
    verify_api_key = _verify_api_key_module
    
    # Rate limiting on all auth-protected routes
    from largestack._dashboard.rate_limit import rate_limit_dependency
    
    # v0.3.7: optional RBAC wiring on mutation routes. Activate via
    # LARGESTACK_RBAC_ENABLED=1 + supply an RBAC instance via LARGESTACK_RBAC_INSTANCE
    # (or by patching largestack._enterprise.rbac._default_rbac before create_api).
    _rbac_deps_run = [Depends(verify_api_key), Depends(rate_limit_dependency)]
    _rbac_deps_read = [Depends(verify_api_key), Depends(rate_limit_dependency)]
    if os.environ.get("LARGESTACK_RBAC_ENABLED", "").lower() in ("1", "true", "yes"):
        try:
            from largestack._enterprise.rbac import require_permission, get_default_rbac
            _rbac_inst = get_default_rbac()
            _rbac_deps_run.append(Depends(require_permission(_rbac_inst, "agent.run")))
            _rbac_deps_read.append(Depends(require_permission(_rbac_inst, "agent.read")))
            log.info("Serve: RBAC enforcement enabled (LARGESTACK_RBAC_ENABLED=1)")
        except Exception as e:
            log.warning(f"Serve: LARGESTACK_RBAC_ENABLED set but RBAC wiring failed: {e}. Continuing without RBAC.")
    
    _protected_deps = _rbac_deps_run  # legacy alias
    _protected_read_deps = _rbac_deps_read

    from pydantic import Field
    
    # v0.3.6: bound user-input length to prevent body-size DoS / token bombs.
    # Read at create_api() time. Tunable via LARGESTACK_MAX_TASK_LENGTH env
    # (default 64KB — generous for prompts but not unbounded).
    _MAX_TASK_LEN = int(os.environ.get("LARGESTACK_MAX_TASK_LENGTH", "65536"))
    
    class RunRequest(BaseModel):
        task: str = Field(..., min_length=1, max_length=_MAX_TASK_LEN)
        cost_budget: float | None = Field(None, ge=0, le=10000)
        max_turns: int | None = Field(None, ge=1, le=200)
    
    # Stash on the app for tests/introspection
    app.state.max_task_len = _MAX_TASK_LEN

    class RunResponse(BaseModel):
        content: str
        agent_name: str
        total_cost: float
        turns: int
        trace_id: str
        duration_ms: float
        tool_calls_made: list[str]
        status: str

    @app.get("/health")
    async def health():
        return {"status": "ok", "agent": agent.name, "llm": agent.llm}

    @app.get("/metrics")
    async def metrics():
        """Prometheus-compatible metrics endpoint.

        Uses prometheus_client when installed. Falls back to a minimal text
        exposition so the default Compose/Prometheus stack can still scrape
        liveness and basic cost gauges in minimal deployments.
        """
        try:
            from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
            return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
        except Exception:
            total_cost = 0.0
            run_cost = 0.0
            try:
                total_cost = float(agent._gw.cost_tracker.total_cost)
                run_cost = float(agent._gw.cost_tracker.run_cost)
            except Exception:
                pass
            body = (
                "# HELP largestack_up LARGESTACK app liveness\n"
                "# TYPE largestack_up gauge\n"
                "largestack_up 1\n"
                "# HELP largestack_total_cost_usd Total observed LLM cost in USD\n"
                "# TYPE largestack_total_cost_usd gauge\n"
                f"largestack_total_cost_usd {total_cost}\n"
                "# HELP largestack_run_cost_usd Last/current run LLM cost in USD\n"
                "# TYPE largestack_run_cost_usd gauge\n"
                f"largestack_run_cost_usd {run_cost}\n"
            )
            return Response(content=body, media_type="text/plain; version=0.0.4")

    # v0.5.0: cookie-based session auth endpoints.
    @app.post("/login")
    async def login(request: Request, response: Response):
        """Exchange X-API-Key for a session cookie.
        
        After this, browser-style clients can use the cookie for subsequent
        requests instead of sending X-API-Key on every call. Sessions persist
        in the configured backend (in-memory by default, Redis if
        LARGESTACK_SESSION_BACKEND=redis).
        
        Returns 401 if X-API-Key invalid. On success, sets `largestack_session`
        cookie (HttpOnly, SameSite=Lax, Secure if LARGESTACK_ENV=production)
        and returns ``{"session_id": "..."}`` (informational only).
        """
        expected = os.environ.get("LARGESTACK_API_KEY")
        if not expected:
            raise HTTPException(
                status_code=503,
                detail="LARGESTACK_API_KEY not set; cannot create sessions",
            )
        provided = request.headers.get("X-API-Key", "")
        if not provided or not secrets.compare_digest(provided, expected):
            raise HTTPException(status_code=401, detail="Invalid X-API-Key")

        # Create a session
        from largestack._enterprise.sso import Session
        import uuid
        sid = str(uuid.uuid4())
        session = Session(
            session_id=sid,
            user_info={"user_id": "api_key_user", "auth": "x-api-key"},
            ttl=_SESSION_TTL,
        )
        _get_session_store().put(session)

        # Set the cookie. Secure=True in production.
        is_prod = os.environ.get("LARGESTACK_ENV", "").lower() == "production"
        response.set_cookie(
            key=_SESSION_COOKIE,
            value=sid,
            max_age=_SESSION_TTL,
            httponly=True,
            secure=is_prod,
            samesite="lax",
            path="/",
        )
        return {"session_id": sid, "ttl_seconds": _SESSION_TTL}

    @app.post("/logout")
    async def logout(request: Request, response: Response):
        """Revoke session and clear cookie."""
        cookie = request.cookies.get(_SESSION_COOKIE)
        if cookie:
            _get_session_store().delete(cookie)
        response.delete_cookie(_SESSION_COOKIE, path="/")
        return {"status": "ok"}

    @app.get("/tools", dependencies=_protected_read_deps)
    async def tools():
        return {"tools": agent._reg.get_all_schemas()}

    @app.post("/run", response_model=RunResponse, dependencies=_protected_deps)
    async def run(req: RunRequest):
        kw = {}
        if req.cost_budget is not None: kw["cost_budget"] = req.cost_budget
        if req.max_turns is not None: kw["max_turns"] = req.max_turns
        result = await agent.run(req.task, **kw)
        return RunResponse(
            content=result.content, agent_name=result.agent_name,
            total_cost=result.total_cost, turns=result.turns,
            trace_id=result.trace_id, duration_ms=result.duration_ms,
            tool_calls_made=result.tool_calls_made, status=result.status)

    @app.post("/stream", dependencies=_protected_deps)
    async def stream(req: RunRequest):
        async def generate():
            async for token in agent.stream(req.task):
                yield {"event": "token", "data": json.dumps({"content": token})}
            yield {"event": "done", "data": "{}"}
        return EventSourceResponse(generate())

    @app.get("/cost", dependencies=_protected_read_deps)
    async def cost():
        return {"run_cost": agent._gw.cost_tracker.run_cost,
                "total_cost": agent._gw.cost_tracker.total_cost}

    
    @app.get("/readyz")
    async def readyz():
        """Kubernetes readiness probe — checks circuit breaker state."""
        cb_states = {}
        try:
            for name, cb in agent._gw._breakers.items():
                cb_states[name] = cb.state.value
        except Exception as _e:
            logging.getLogger("largestack.serve").debug(f"breaker readiness check failed: {_e}")
        all_open = all(s == "open" for s in cb_states.values()) if cb_states else False
        ready = not all_open
        return {"ready": ready, "agent": agent.name, "circuit_breakers": cb_states}

    @app.get("/livez")
    async def livez():
        """Kubernetes liveness probe."""
        return {"alive": True}

    # Graceful shutdown handled by uvicorn signal handlers
    # Agent gateway closes automatically when process exits

    return app
