# LARGESTACK Dashboard SPA

A production-quality React + Vite build of the dashboard. **Optional** — the
default dashboard is the server-rendered HTML in `largestack/_dashboard/app.py`,
which works without any build step and is the path most operators use.

This SPA is for teams who want a richer client-side experience or who need
to embed the dashboard inside another React application.

## Build

```bash
cd largestack/_dashboard/spa
npm install
npm run build
```

The output appears under `dist/` (hashed asset filenames). The FastAPI
dashboard server detects this directory at startup and, when
`LARGESTACK_DASHBOARD_SPA=1` is set, mounts it at `/spa/`.

## Develop

```bash
# In one terminal — run the LARGESTACK dashboard backend
largestack dashboard

# In another — run the Vite dev server with HMR
cd largestack/_dashboard/spa
npm run dev
```

Open <http://localhost:5173/>. Vite proxies `/api/*` to
`http://localhost:8787` so the SPA reaches the dashboard backend without
CORS configuration.

## Production deployment

After `npm run build`:

* **Same-origin deployment (recommended):** ship the `dist/` folder inside
  your Docker image; the FastAPI backend serves it from `/spa/`. No CORS
  needed; the API key is read from the `<meta name="largestack-api-key">` tag
  the server injects after authenticating.
* **Cross-origin deployment:** host `dist/` on a CDN; configure
  `LARGESTACK_CORS_ALLOWED_ORIGINS=https://your-spa.example.com` on the
  backend.

## Auth

The SPA reads the API key from `<meta name="largestack-api-key">` injected by
the backend after the initial HTML request authenticates with `X-API-Key`.
For real customer-facing UI, swap this for OIDC + same-origin session
cookies — see `largestack/_enterprise/sso.py`.

## Browser support

`browserslist` in `package.json` targets evergreen browsers (no IE11). If
you need wider support, add legacy targets and reinstall.
