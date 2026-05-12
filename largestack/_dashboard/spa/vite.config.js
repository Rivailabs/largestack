import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { resolve } from "path";

// LARGESTACK dashboard SPA — Vite build configuration.
//
// Build: `npm install && npm run build` produces `dist/` with hashed
// assets that the FastAPI dashboard serves from `/spa/*` when the SPA
// is enabled (LARGESTACK_DASHBOARD_SPA=1).
//
// Dev: `npm run dev` starts the Vite dev server on :5173 and proxies
// /api -> http://localhost:8787 so the local LARGESTACK dashboard's JSON API
// is reachable without CORS configuration.

export default defineConfig({
  plugins: [react()],
  root: __dirname,
  build: {
    outDir: "dist",
    emptyOutDir: true,
    sourcemap: true,
    target: "es2020",
    rollupOptions: {
      input: resolve(__dirname, "index.html"),
    },
  },
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://localhost:8787",
        changeOrigin: true,
      },
    },
  },
});
