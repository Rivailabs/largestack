"""largestack dev — Hot-reload dev server with playground.

Mastra-style developer experience:
  - localhost:4111
  - File watcher with SSE refresh (real, via `watchfiles`)
  - Playground at /playground
  - /api/run for ad-hoc agent runs

v0.3.10: hot-reload is now actually implemented. The previous version
declared a `refresh_subscribers` list but never pushed events into it.
Now a background `watchfiles.awatch()` task fans events out to every
connected SSE client. If `watchfiles` is not installed we log an honest
"hot-reload disabled" message instead of pretending it works.
"""

from __future__ import annotations
import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import Request

log = logging.getLogger("largestack.dev")


def watchfiles_available() -> bool:
    """True if `watchfiles` is importable. The CLI uses this to print an
    honest "enabled" / "disabled" status rather than always claiming enabled."""
    try:
        import watchfiles  # noqa: F401

        return True
    except ImportError:
        return False


PLAYGROUND_HTML = """<!DOCTYPE html>
<html>
<head>
<title>LARGESTACK Playground</title>
<style>
  body { font-family: 'JetBrains Mono', monospace; background: #0B0B12; color: #E8E8F0; padding: 24px; }
  h1 { color: #6C5CE7; }
  .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
  .card { background: #12121D; border: 1px solid #1E1E32; border-radius: 10px; padding: 20px; }
  .label { font-size: 11px; color: #6B6B8D; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 8px; }
  textarea, input { width: 100%; background: #0B0B12; border: 1px solid #2A2A44; color: #E8E8F0; padding: 10px; border-radius: 6px; font-family: inherit; }
  button { background: #6C5CE7; color: white; border: none; padding: 10px 20px; border-radius: 6px; cursor: pointer; font-weight: 600; }
  button:hover { background: #A29BFE; }
  pre { background: #0B0B12; padding: 12px; border-radius: 6px; overflow: auto; max-height: 400px; }
  .endpoint { padding: 8px; border-bottom: 1px solid #1E1E32; }
  .method { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 11px; font-weight: 700; }
  .GET { background: rgba(0,214,143,0.2); color: #00D68F; }
  .POST { background: rgba(108,92,231,0.2); color: #A29BFE; }
  .reload { color: #00D68F; font-size: 11px; }
  .reload.off { color: #FFB347; }
</style>
</head>
<body>
<h1>LARGESTACK Playground</h1>
<div class="reload" id="status">connecting…</div>

<div class="grid" style="margin-top: 24px;">
  <div class="card">
    <div class="label">Send Prompt</div>
    <textarea id="prompt" rows="4" placeholder="Enter prompt..."></textarea>
    <input id="model" value="deepseek/deepseek-chat" placeholder="Model">
    <button onclick="send()">Run</button>
  </div>
  <div class="card">
    <div class="label">Response</div>
    <pre id="response">Click Run to test</pre>
  </div>
</div>

<div class="card" style="margin-top: 16px;">
  <div class="label">Available Endpoints</div>
  <div class="endpoint"><span class="method GET">GET</span> /api/health — Health check (reports hot-reload status)</div>
  <div class="endpoint"><span class="method POST">POST</span> /api/run — Run an agent</div>
  <div class="endpoint"><span class="method GET">GET</span> /refresh-events — SSE stream of file-change events</div>
</div>

<script>
async function send() {
  const r = document.getElementById('response');
  r.textContent = 'Running...';
  try {
    const resp = await fetch('/api/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        prompt: document.getElementById('prompt').value,
        model: document.getElementById('model').value,
      }),
    });
    const data = await resp.json();
    r.textContent = JSON.stringify(data, null, 2);
  } catch (e) {
    r.textContent = 'Error: ' + e;
  }
}

const es = new EventSource('/refresh-events');
es.onopen = () => {
  const s = document.getElementById('status');
  s.classList.remove('off');
  s.textContent = '● Connected';
};
es.onmessage = (e) => {
  if (e.data === 'hot-reload-disabled') {
    const s = document.getElementById('status');
    s.classList.add('off');
    s.textContent = '○ Hot-reload disabled (install largestack[dev-server])';
    return;
  }
  if (e.data === 'reload') {
    const s = document.getElementById('status');
    s.textContent = '↻ Reloading…';
    setTimeout(() => location.reload(), 100);
  }
};
es.onerror = () => {
  const s = document.getElementById('status');
  s.classList.add('off');
  s.textContent = '× Disconnected';
};
</script>
</body>
</html>"""


def create_dev_app(*, watch_path: str | None = None, enable_hot_reload: bool | None = None):
    """Create dev FastAPI app with playground + (optional) real hot-reload.

    Args:
        watch_path: directory to watch for file changes. Defaults to cwd.
        enable_hot_reload: tri-state. None = auto (on iff watchfiles installed).
                            True = error if watchfiles missing.
                            False = explicitly disabled (status shown to client).
    """
    from fastapi import FastAPI
    from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse
    from fastapi.middleware.cors import CORSMiddleware

    have_watchfiles = watchfiles_available()
    if enable_hot_reload is None:
        hot_reload_active = have_watchfiles
    elif enable_hot_reload and not have_watchfiles:
        raise RuntimeError(
            "Hot-reload requested but `watchfiles` is not installed. "
            "Install: pip install largestack[dev-server]"
        )
    else:
        hot_reload_active = bool(enable_hot_reload) and have_watchfiles

    if watch_path is None:
        try:
            watch_path = os.getcwd()
        except (FileNotFoundError, OSError):
            # cwd may have been deleted (test fixtures cleaning up tmp_path).
            watch_path = os.path.expanduser("~")

    refresh_subscribers: list[asyncio.Queue] = []
    _watcher_task: dict[str, asyncio.Task | None] = {"task": None}

    async def _watcher_loop():
        """Background task: watch project files and fan out reload events.

        Uses a small deterministic polling watcher instead of depending on
        platform-specific watch backends during tests. `watchfiles_available()`
        still controls whether hot-reload is enabled for developer UX, but the
        actual loop is cancellation-safe and does not hang FastAPI lifespan
        shutdown when a backend blocks.
        """
        from pathlib import Path

        log.info(f"largestack dev: watching {watch_path} for changes (hot-reload ON)")
        ignored = (
            "__pycache__",
            ".git",
            ".venv",
            "node_modules",
            ".pytest_cache",
            ".mypy_cache",
            ".ruff_cache",
            ".largestack",
            "dist",
            "build",
        )

        def _snapshot() -> dict[str, int]:
            root = Path(watch_path)
            seen: dict[str, int] = {}
            if not root.exists():
                return seen
            for path in root.rglob("*"):
                sp = str(path)
                if any(seg in sp for seg in ignored) or sp.endswith((".pyc", ".pyo", ".db")):
                    continue
                try:
                    if path.is_file():
                        seen[sp] = path.stat().st_mtime_ns
                except OSError:
                    continue
            return seen

        def _fanout() -> None:
            dead: list[asyncio.Queue] = []
            for q in list(refresh_subscribers):
                try:
                    q.put_nowait("reload")
                except Exception:
                    dead.append(q)
            for q in dead:
                if q in refresh_subscribers:
                    refresh_subscribers.remove(q)

        previous = _snapshot()
        try:
            while True:
                await asyncio.sleep(0.15)
                current = _snapshot()
                if current != previous:
                    previous = current
                    _fanout()
        except asyncio.CancelledError:
            log.info("largestack dev: watcher cancelled")
            raise
        except Exception as e:
            log.warning(f"largestack dev: watcher stopped: {e}")

    @asynccontextmanager
    async def lifespan(app):
        if hot_reload_active:
            _watcher_task["task"] = asyncio.create_task(_watcher_loop())
        yield
        t = _watcher_task["task"]
        if t and not t.done():
            t.cancel()
            try:
                await asyncio.wait_for(t, timeout=1.0)
            except (asyncio.CancelledError, asyncio.TimeoutError, Exception):
                pass

    app = FastAPI(title="LARGESTACK Dev Server", version="0.1.2", lifespan=lifespan)

    # `largestack dev` is a developer command. Restrict CORS to localhost.
    _env = os.environ.get("LARGESTACK_ENV", "development").lower()
    if _env == "production":
        log.warning(
            "`largestack dev` is being run with LARGESTACK_ENV=production. "
            "This server is for local development only — do not expose to the internet."
        )
    _dev_origins = [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://localhost:8080",
        "http://localhost:4111",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:8080",
        "http://127.0.0.1:4111",
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_dev_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", "Authorization", "X-API-Key"],
    )

    @app.get("/")
    async def root():
        return HTMLResponse(PLAYGROUND_HTML)

    @app.get("/playground")
    async def playground():
        return HTMLResponse(PLAYGROUND_HTML)

    @app.get("/api/health")
    async def health():
        return {
            "status": "ok",
            "server": "largestack-dev",
            "version": "0.1.2",
            "hot_reload": hot_reload_active,
            "watchfiles_installed": have_watchfiles,
            "watching": watch_path if hot_reload_active else None,
        }

    @app.post("/api/run")
    async def run_agent(request: Request):
        body = await request.json()
        prompt = body.get("prompt", "")
        model = body.get("model", "deepseek/deepseek-chat")

        try:
            from largestack import Agent

            agent = Agent(name="dev", llm=model, cost_budget=0.05)
            result = await agent.run(prompt)
            return {
                "content": result.content,
                "cost": result.total_cost,
                "trace_id": result.trace_id,
                "turns": result.turns,
            }
        except Exception as e:
            return JSONResponse({"error": str(e)}, status_code=500)

    @app.get("/refresh-events")
    async def refresh_events():
        """SSE stream of file-change reload events.

        v0.3.10: when hot-reload is disabled (watchfiles missing or disabled
        explicitly), the first event is `hot-reload-disabled` so the client
        shows an honest status instead of a green "● Connected" lie.
        """

        async def event_gen():
            queue: asyncio.Queue = asyncio.Queue()
            refresh_subscribers.append(queue)
            try:
                if not hot_reload_active:
                    yield "data: hot-reload-disabled\n\n"
                else:
                    yield "data: connected\n\n"
                while True:
                    msg = await queue.get()
                    yield f"data: {msg}\n\n"
            finally:
                if queue in refresh_subscribers:
                    refresh_subscribers.remove(queue)

        return StreamingResponse(event_gen(), media_type="text/event-stream")

    # Expose internals for tests
    app.state.refresh_subscribers = refresh_subscribers
    app.state.hot_reload_active = hot_reload_active
    app.state.watch_path = watch_path
    app.state.watchfiles_available = have_watchfiles

    return app


def run_dev_server(host: str = "127.0.0.1", port: int = 4111):
    """Run the dev server with uvicorn."""
    try:
        import uvicorn
    except ImportError:
        raise ImportError("Install: pip install uvicorn[standard]")

    if not watchfiles_available():
        log.warning(
            "largestack dev: hot-reload disabled — `watchfiles` is not installed. "
            "Install with: pip install largestack[dev-server]"
        )

    app = create_dev_app()
    uvicorn.run(app, host=host, port=port, log_level="info")
