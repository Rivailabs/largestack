# LARGESTACK Dashboard

## Architecture (v0.3.10)

The **official** LARGESTACK dashboard is **server-rendered HTML** with inline
Chart.js. It is started by:

```bash
largestack dashboard
```

…which serves on `http://127.0.0.1:8787` by default (or `0.0.0.0:8787`
when running inside a Docker container — auto-detected via `/.dockerenv`
or `LARGESTACK_IN_CONTAINER=1`).

**Why server-rendered?** The dashboard is operator-internal. It has no
authentication beyond an API key, no client-side routing needs, and the
data comes straight out of SQLite. Server-rendered HTML keeps the
deploy story to **one Python wheel** — no Node, no `npm install`, no
build step in CI, no bundle to ship.

## What's in this directory

| File | Purpose |
|---|---|
| `app.py` | The actual dashboard. FastAPI app with 10 HTML views, Chart.js, CSP. |
| `api.py` | JSON API consumed by the views (and by anyone who builds their own UI). |
| `auth.py` | X-API-Key middleware (constant-time compare; production deny-all). |
| `rate_limit.py` | Per-IP token-bucket rate limiter. |
| `frontend.jsx` | **EXPERIMENTAL** — reference React/Recharts SPA for users who want to fork. Not bundled by LARGESTACK. See header comment. |

## Authentication

- All routes except `/health` require the `X-API-Key` header.
- The expected key is read from `LARGESTACK_DASHBOARD_KEY` env var.
- In production (`LARGESTACK_ENV=production`), if `LARGESTACK_DASHBOARD_KEY` is
  unset, every protected route returns 401 — fail-secure.
- In development, if the key is unset, auth is bypassed with a single
  loud log warning. Set the key before deploying.

## Optional RBAC

Set `LARGESTACK_RBAC_ENABLED=1` and the dashboard appends a permission check
(`agent.read`) to every protected route, on top of the API-key check.

## CORS

Read from `LARGESTACK_CORS_ALLOWED_ORIGINS` (comma-separated). `*` is rejected
explicitly. Production with no value set means deny-all.

## Building your own UI

If you want a richer UI than the server-rendered HTML:

1. **Use the JSON API.** All data is exposed at `/api/*` — see `api.py`.
2. **Fork `frontend.jsx`** into your own React project. Install
   `react` + `recharts` + a bundler (Vite/Webpack/esbuild). LARGESTACK does
   not ship a bundle step for this file — it's a reference, not a
   maintained product surface.
3. **Set `LARGESTACK_CORS_ALLOWED_ORIGINS`** so your hosted UI can hit the
   API cross-origin.

We deliberately don't ship a Node toolchain in the Python package. If
that's a fit for your project, you own it.
