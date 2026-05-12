// =====================================================================
// EXPERIMENTAL — Reference React SPA for the LARGESTACK dashboard.
// =====================================================================
//
// As of v0.3.10, the OFFICIAL dashboard is the server-rendered HTML in
// `largestack/_dashboard/app.py` (started via `largestack dashboard`). That path is
// fully working: 10 views, real Chart.js visualizations on real DB data,
// X-API-Key auth, CSP headers, no build step required.
//
// THIS FILE is shipped as JSX SOURCE for users who want to fork the
// dashboard into their own React app. LARGESTACK does not ship a Vite/esbuild
// build pipeline for it. To use this file:
//
//   1. Copy it into your own React project.
//   2. Install: `npm install react recharts`.
//   3. Bundle with Vite/Webpack/esbuild as you normally would.
//   4. Serve the resulting bundle behind any static HTTP server; have it
//      hit the LARGESTACK dashboard JSON API at `/api/*` (CORS allowlist
//      controlled by `LARGESTACK_CORS_ALLOWED_ORIGINS`).
//
// The SPA reads the API key from a `<meta name="largestack-api-key">` tag that
// the LARGESTACK server injects into its own HTML pages after the request
// authenticates. If you embed this SPA in your own page, set that meta
// tag yourself, OR rewrite `getApiKey()` to read from your auth flow.
//
// See `largestack/_dashboard/README.md` for the full architecture overview.
// =====================================================================

import { useState, useEffect, useCallback } from "react";
import { LineChart, Line, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, PieChart, Pie, Cell } from "recharts";

const COLORS = {
  bg: "#0B0B12", surface: "#12121D", surfaceHover: "#181828",
  border: "#1E1E32", borderLight: "#2A2A44",
  primary: "#6C5CE7", primaryLight: "#A29BFE",
  success: "#00D68F", successBg: "rgba(0,214,143,0.12)",
  warning: "#FFB347", warningBg: "rgba(255,179,71,0.12)",
  error: "#FF6B6B", errorBg: "rgba(255,107,107,0.12)",
  text: "#E8E8F0", textMuted: "#6B6B8D", textDim: "#44446A",
};

const CHART_COLORS = ["#6C5CE7", "#00D68F", "#FFB347", "#FF6B6B", "#61DAFB", "#C77DFF", "#64DFDF"];

const API = "/api";

// v0.3.9: read API key from <meta name="largestack-api-key" content="..."> tag.
// The dashboard HTML server (in `_dashboard/app.py`) injects this meta tag
// only after the browser session has already authenticated via the
// `X-API-Key` header on the initial `/` GET (the FastAPI dependency runs
// before the HTML response). This means: by the time the React bundle is
// served, we know auth is good — and we can safely surface the key to the
// SPA so its background `/api/*` fetches succeed.
//
// SECURITY NOTE: this trades secrecy for usability — the key is in the DOM,
// reachable by any script on the same page. That's acceptable here because
// (a) the dashboard is operator-internal, (b) we already require the key to
// load the page at all, and (c) we set strict CSP `default-src 'self'` so
// no XHR exfiltration is possible without bypassing CSP. For real
// customer-facing UI, swap this for OIDC + same-origin session cookies.
function getApiKey() {
  if (typeof document === "undefined") return null;
  const meta = document.querySelector('meta[name="largestack-api-key"]');
  return meta ? meta.getAttribute("content") : null;
}

function authHeaders() {
  const key = getApiKey();
  return key ? { "X-API-Key": key } : {};
}

function useFetch(endpoint) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const refresh = useCallback(() => {
    setLoading(true); setError(null);
    fetch(`${API}${endpoint}`, { headers: authHeaders() })
      .then(r => {
        if (!r.ok) {
          const msg = r.status === 401 ? "Unauthorized — refresh and re-auth"
                    : r.status === 403 ? "Forbidden — RBAC denied"
                    : r.status === 429 ? "Rate-limited — slow down"
                    : `HTTP ${r.status}`;
          throw new Error(msg);
        }
        return r.json();
      })
      .then(d => { setData(d); setLoading(false); })
      .catch(e => { setError(e.message || String(e)); setData(null); setLoading(false); });
  }, [endpoint]);
  useEffect(() => { refresh(); const i = setInterval(refresh, 30000); return () => clearInterval(i); }, [refresh]);
  return { data, loading, error, refresh };
}

function StatCard({ label, value, sub, color = COLORS.success }) {
  return (
    <div style={{ background: COLORS.surface, border: `1px solid ${COLORS.border}`, borderRadius: 10, padding: "18px 20px" }}>
      <div style={{ fontSize: 11, color: COLORS.textMuted, textTransform: "uppercase", letterSpacing: 1, marginBottom: 6 }}>{label}</div>
      <div style={{ fontSize: 28, fontWeight: 700, color, fontFamily: "'JetBrains Mono', monospace" }}>{value}</div>
      {sub && <div style={{ fontSize: 11, color: COLORS.textDim, marginTop: 4 }}>{sub}</div>}
    </div>
  );
}

function EmptyState({ message }) {
  return (
    <div style={{ padding: 48, textAlign: "center", color: COLORS.textMuted, fontStyle: "italic", background: COLORS.surface, borderRadius: 10, border: `1px solid ${COLORS.border}` }}>
      {message}
    </div>
  );
}

function Tag({ children, color = COLORS.success }) {
  return (
    <span style={{ display: "inline-block", padding: "2px 10px", borderRadius: 12, fontSize: 10, fontWeight: 700, background: `${color}18`, color, letterSpacing: 0.5 }}>
      {children}
    </span>
  );
}

// ═══ PAGES ═══

function OverviewPage() {
  const { data } = useFetch("/overview");
  if (!data) return <EmptyState message="Loading overview..." />;
  
  const costData = (data.cost_hourly || []).map(r => ({
    hour: `${23 - (r.hour || 0)}h ago`,
    cost: r.cost,
    runs: r.count,
  }));
  
  return (
    <div>
      <h2 style={{ color: COLORS.text, fontSize: 16, marginBottom: 16 }}>Last 24 Hours</h2>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12, marginBottom: 24 }}>
        <StatCard label="Agent Runs" value={data.traces_24h} />
        <StatCard label="Audit Events" value={data.audit_events_24h} />
        <StatCard label="Total Cost" value={`$${data.total_cost_24h.toFixed(4)}`} color={COLORS.warning} />
        <StatCard label="Avg Cost/Run" value={`$${(data.total_cost_24h / Math.max(data.traces_24h, 1)).toFixed(5)}`} color={COLORS.primaryLight} />
      </div>
      
      {costData.length > 0 ? (
        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
          <div style={{ background: COLORS.surface, border: `1px solid ${COLORS.border}`, borderRadius: 10, padding: 20 }}>
            <div style={{ fontSize: 11, color: COLORS.textMuted, textTransform: "uppercase", letterSpacing: 1, marginBottom: 16 }}>Cost Trend</div>
            <ResponsiveContainer width="100%" height={240}>
              <LineChart data={costData}>
                <CartesianGrid strokeDasharray="3 3" stroke={COLORS.border} />
                <XAxis dataKey="hour" tick={{ fill: COLORS.textDim, fontSize: 10 }} />
                <YAxis tick={{ fill: COLORS.textDim, fontSize: 10 }} />
                <Tooltip contentStyle={{ background: COLORS.surface, border: `1px solid ${COLORS.border}`, borderRadius: 8, fontSize: 12, color: COLORS.text }} />
                <Line type="monotone" dataKey="cost" stroke={COLORS.success} strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
          <div style={{ background: COLORS.surface, border: `1px solid ${COLORS.border}`, borderRadius: 10, padding: 20 }}>
            <div style={{ fontSize: 11, color: COLORS.textMuted, textTransform: "uppercase", letterSpacing: 1, marginBottom: 16 }}>Runs by Hour</div>
            <ResponsiveContainer width="100%" height={240}>
              <BarChart data={costData}>
                <CartesianGrid strokeDasharray="3 3" stroke={COLORS.border} />
                <XAxis dataKey="hour" tick={{ fill: COLORS.textDim, fontSize: 10 }} />
                <YAxis tick={{ fill: COLORS.textDim, fontSize: 10 }} />
                <Tooltip contentStyle={{ background: COLORS.surface, border: `1px solid ${COLORS.border}`, borderRadius: 8, fontSize: 12, color: COLORS.text }} />
                <Bar dataKey="runs" fill={COLORS.primary} radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      ) : <EmptyState message="No activity yet. Run an agent to see data here." />}
    </div>
  );
}

function TracesPage() {
  const { data } = useFetch("/traces");
  const traces = data?.traces || [];
  if (traces.length === 0) return <EmptyState message="No traces yet. Run an agent to see data here." />;
  
  return (
    <div style={{ background: COLORS.surface, border: `1px solid ${COLORS.border}`, borderRadius: 10, overflow: "hidden" }}>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
        <thead>
          <tr style={{ borderBottom: `1px solid ${COLORS.border}` }}>
            {["Time", "Agent", "Task", "Duration", "Cost", "Turns"].map(h => (
              <th key={h} style={{ textAlign: "left", padding: "10px 12px", color: COLORS.textMuted, fontWeight: 600, fontSize: 11, textTransform: "uppercase", letterSpacing: 0.5 }}>{h}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {traces.map((t, i) => (
            <tr key={i} style={{ borderBottom: `1px solid ${COLORS.border}08` }}>
              <td style={{ padding: "8px 12px", color: COLORS.textDim, fontFamily: "monospace" }}>
                {new Date((t.timestamp || 0) * 1000).toLocaleTimeString()}
              </td>
              <td style={{ padding: "8px 12px", color: COLORS.primaryLight, fontWeight: 600 }}>{t.agent || "—"}</td>
              <td style={{ padding: "8px 12px", color: COLORS.text, maxWidth: 300, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{(t.task || "").slice(0, 60)}</td>
              <td style={{ padding: "8px 12px", color: COLORS.textMuted, fontFamily: "monospace" }}>{(t.duration_ms || 0).toFixed(0)}ms</td>
              <td style={{ padding: "8px 12px", color: COLORS.success, fontFamily: "monospace" }}>${(t.cost || 0).toFixed(5)}</td>
              <td style={{ padding: "8px 12px", color: COLORS.textMuted }}>{t.turns || "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function CostsPage() {
  const { data } = useFetch("/costs");
  const models = data?.by_model || [];
  if (models.length === 0) return <EmptyState message="No cost data. Run some agents first." />;
  
  const pieData = models.map((m, i) => ({ name: m.model || "unknown", value: Math.round((m.cost || 0) * 10000) / 10000 }));
  
  return (
    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
      <div style={{ background: COLORS.surface, border: `1px solid ${COLORS.border}`, borderRadius: 10, padding: 20 }}>
        <div style={{ fontSize: 11, color: COLORS.textMuted, textTransform: "uppercase", letterSpacing: 1, marginBottom: 16 }}>Cost by Model</div>
        <ResponsiveContainer width="100%" height={280}>
          <PieChart>
            <Pie data={pieData} cx="50%" cy="50%" outerRadius={100} dataKey="value" label={({ name, value }) => `${name}: $${value}`} labelLine={{ stroke: COLORS.textDim }}>
              {pieData.map((_, i) => <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />)}
            </Pie>
            <Tooltip contentStyle={{ background: COLORS.surface, border: `1px solid ${COLORS.border}`, borderRadius: 8, fontSize: 12, color: COLORS.text }} />
          </PieChart>
        </ResponsiveContainer>
      </div>
      <div style={{ background: COLORS.surface, border: `1px solid ${COLORS.border}`, borderRadius: 10, padding: 20 }}>
        <div style={{ fontSize: 11, color: COLORS.textMuted, textTransform: "uppercase", letterSpacing: 1, marginBottom: 16 }}>Breakdown</div>
        <table style={{ width: "100%", fontSize: 12 }}>
          <thead><tr>{["Model", "Calls", "Total Cost"].map(h => <th key={h} style={{ textAlign: "left", padding: 8, color: COLORS.textMuted, borderBottom: `1px solid ${COLORS.border}`, fontSize: 11 }}>{h}</th>)}</tr></thead>
          <tbody>
            {models.map((m, i) => (
              <tr key={i}>
                <td style={{ padding: 8, color: COLORS.text }}>{m.model}</td>
                <td style={{ padding: 8, color: COLORS.textMuted, fontFamily: "monospace" }}>{m.calls}</td>
                <td style={{ padding: 8, color: COLORS.success, fontFamily: "monospace" }}>${(m.cost || 0).toFixed(4)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function AgentsPage() {
  const { data } = useFetch("/agents");
  const agents = data?.agents || [];
  if (agents.length === 0) return <EmptyState message="No agent activity yet." />;
  
  const chartData = agents.map(a => ({ name: a.agent || "unknown", runs: a.runs, latency: Math.round(a.avg_latency || 0) }));
  
  return (
    <div>
      <div style={{ background: COLORS.surface, border: `1px solid ${COLORS.border}`, borderRadius: 10, padding: 20, marginBottom: 12 }}>
        <div style={{ fontSize: 11, color: COLORS.textMuted, textTransform: "uppercase", letterSpacing: 1, marginBottom: 16 }}>Agent Performance</div>
        <ResponsiveContainer width="100%" height={240}>
          <BarChart data={chartData} layout="vertical">
            <CartesianGrid strokeDasharray="3 3" stroke={COLORS.border} />
            <XAxis type="number" tick={{ fill: COLORS.textDim, fontSize: 10 }} />
            <YAxis dataKey="name" type="category" tick={{ fill: COLORS.text, fontSize: 11 }} width={120} />
            <Tooltip contentStyle={{ background: COLORS.surface, border: `1px solid ${COLORS.border}`, borderRadius: 8, fontSize: 12, color: COLORS.text }} />
            <Bar dataKey="runs" fill={COLORS.primary} radius={[0, 4, 4, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
      <div style={{ background: COLORS.surface, border: `1px solid ${COLORS.border}`, borderRadius: 10, overflow: "hidden" }}>
        <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
          <thead><tr>{["Agent", "Runs", "Avg Latency", "Total Cost"].map(h => <th key={h} style={{ textAlign: "left", padding: "10px 12px", color: COLORS.textMuted, fontWeight: 600, fontSize: 11, borderBottom: `1px solid ${COLORS.border}` }}>{h}</th>)}</tr></thead>
          <tbody>
            {agents.map((a, i) => (
              <tr key={i}><td style={{ padding: "8px 12px", color: COLORS.primaryLight, fontWeight: 600 }}>{a.agent}</td><td style={{ padding: "8px 12px", fontFamily: "monospace", color: COLORS.text }}>{a.runs}</td><td style={{ padding: "8px 12px", fontFamily: "monospace", color: COLORS.textMuted }}>{Math.round(a.avg_latency || 0)}ms</td><td style={{ padding: "8px 12px", fontFamily: "monospace", color: COLORS.success }}>${(a.total_cost || 0).toFixed(4)}</td></tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function GuardsPage() {
  const { data } = useFetch("/guards");
  const events = data?.events || [];
  if (events.length === 0) return <EmptyState message="No guardrail events. All requests passed cleanly." />;
  
  return (
    <div style={{ background: COLORS.surface, border: `1px solid ${COLORS.border}`, borderRadius: 10, overflow: "hidden" }}>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 12 }}>
        <thead><tr><th style={{ textAlign: "left", padding: "10px 12px", color: COLORS.textMuted, borderBottom: `1px solid ${COLORS.border}` }}>Guard Event</th><th style={{ textAlign: "left", padding: "10px 12px", color: COLORS.textMuted, borderBottom: `1px solid ${COLORS.border}` }}>Count</th></tr></thead>
        <tbody>
          {events.map((e, i) => (
            <tr key={i}><td style={{ padding: "8px 12px", color: COLORS.text }}>{e.event}</td><td style={{ padding: "8px 12px" }}><Tag color={COLORS.warning}>{e.count}</Tag></td></tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function MetricsPage() {
  const { data } = useFetch("/metrics");
  if (!data || data.count === 0) return <EmptyState message="No metrics yet." />;
  
  return (
    <div>
      <h2 style={{ color: COLORS.text, fontSize: 16, marginBottom: 16 }}>Latency Percentiles (24h)</h2>
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12 }}>
        <StatCard label="p50" value={`${data.p50_ms}ms`} />
        <StatCard label="p95" value={`${data.p95_ms}ms`} color={COLORS.warning} />
        <StatCard label="p99" value={`${data.p99_ms}ms`} color={COLORS.error} />
        <StatCard label="Total Requests" value={data.count} color={COLORS.primaryLight} />
      </div>
    </div>
  );
}

function AlertsPage() {
  const { data } = useFetch("/alerts");
  const alerts = data?.alerts || [];
  if (alerts.length === 0) return <EmptyState message="No active alerts. All systems operational." />;
  
  return (
    <div style={{ display: "grid", gap: 8 }}>
      {alerts.map((a, i) => (
        <div key={i} style={{ background: COLORS.surface, border: `1px solid ${a.level === "error" ? COLORS.error : COLORS.warning}40`, borderRadius: 10, padding: 16, display: "flex", alignItems: "center", gap: 12 }}>
          <Tag color={a.level === "error" ? COLORS.error : COLORS.warning}>{a.level.toUpperCase()}</Tag>
          <span style={{ color: COLORS.text, fontSize: 13 }}>{a.message}</span>
        </div>
      ))}
    </div>
  );
}

function MemoryPage() {
  const types = [
    { name: "Buffer (conversation)", status: "Active" },
    { name: "Episodic (event scoring)", status: "Active" },
    { name: "Semantic (vector)", status: "Active" },
    { name: "Graph (entity/relation)", status: "Active" },
    { name: "Procedural (skills)", status: "Active" },
    { name: "Observational (Observer+Reflector)", status: "Active" },
    { name: "Compression (LLMLingua)", status: "Active" },
    { name: "Shared (cross-agent)", status: "Active" },
  ];
  
  return (
    <div style={{ background: COLORS.surface, border: `1px solid ${COLORS.border}`, borderRadius: 10, overflow: "hidden" }}>
      <div style={{ padding: "16px 20px", borderBottom: `1px solid ${COLORS.border}` }}>
        <span style={{ fontSize: 11, color: COLORS.textMuted, textTransform: "uppercase", letterSpacing: 1 }}>Memory Types</span>
      </div>
      {types.map((t, i) => (
        <div key={i} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "10px 20px", borderBottom: `1px solid ${COLORS.border}08` }}>
          <span style={{ color: COLORS.text, fontSize: 13 }}>{t.name}</span>
          <Tag color={COLORS.success}>{t.status}</Tag>
        </div>
      ))}
    </div>
  );
}

// ═══ MAIN APP ═══

const NAV_ITEMS = [
  { id: "overview", label: "Overview", icon: "◉" },
  { id: "traces", label: "Traces", icon: "◈" },
  { id: "costs", label: "Costs", icon: "$" },
  { id: "agents", label: "Agents", icon: "◎" },
  { id: "guards", label: "Guards", icon: "◆" },
  { id: "memory", label: "Memory", icon: "◇" },
  { id: "metrics", label: "Metrics", icon: "◐" },
  { id: "alerts", label: "Alerts", icon: "!" },
];

const PAGES = {
  overview: OverviewPage,
  traces: TracesPage,
  costs: CostsPage,
  agents: AgentsPage,
  guards: GuardsPage,
  memory: MemoryPage,
  metrics: MetricsPage,
  alerts: AlertsPage,
};

export default function App() {
  const [page, setPage] = useState("overview");
  const PageComponent = PAGES[page] || OverviewPage;
  const { data: health } = useFetch("/health");
  
  return (
    <div style={{ display: "flex", minHeight: "100vh", background: COLORS.bg, fontFamily: "'Outfit', 'Segoe UI', sans-serif", color: COLORS.text }}>
      {/* Sidebar */}
      <div style={{ width: 220, background: COLORS.surface, borderRight: `1px solid ${COLORS.border}`, display: "flex", flexDirection: "column", flexShrink: 0 }}>
        <div style={{ padding: "20px 16px 16px", borderBottom: `1px solid ${COLORS.border}` }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <div style={{ width: 28, height: 28, borderRadius: 6, background: `linear-gradient(135deg, ${COLORS.primary}, ${COLORS.success})`, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 14, fontWeight: 900, color: "#fff" }}>N</div>
            <div>
              <div style={{ fontSize: 14, fontWeight: 700, color: COLORS.text, lineHeight: 1.2 }}>LARGESTACK</div>
              <div style={{ fontSize: 9, color: COLORS.textDim, letterSpacing: 1.5, textTransform: "uppercase" }}>Multi-Agent AI</div>
            </div>
          </div>
        </div>
        
        <nav style={{ padding: "8px 8px", flex: 1 }}>
          {NAV_ITEMS.map(item => (
            <button
              key={item.id}
              onClick={() => setPage(item.id)}
              style={{
                display: "flex", alignItems: "center", gap: 10, width: "100%",
                padding: "9px 12px", marginBottom: 2, border: "none", borderRadius: 8, cursor: "pointer",
                background: page === item.id ? `${COLORS.primary}20` : "transparent",
                color: page === item.id ? COLORS.primaryLight : COLORS.textMuted,
                fontSize: 13, fontWeight: page === item.id ? 600 : 400,
                transition: "all 0.15s", textAlign: "left",
              }}
            >
              <span style={{ fontSize: 14, width: 20, textAlign: "center", opacity: page === item.id ? 1 : 0.5 }}>{item.icon}</span>
              {item.label}
            </button>
          ))}
        </nav>
        
        <div style={{ padding: 16, borderTop: `1px solid ${COLORS.border}`, fontSize: 10, color: COLORS.textDim }}>
          <div style={{ display: "flex", alignItems: "center", gap: 6, marginBottom: 4 }}>
            <div style={{ width: 6, height: 6, borderRadius: "50%", background: health ? COLORS.success : COLORS.error }} />
            {health ? "Connected" : "Disconnected"}
          </div>
          v0.1.1 • RivaiLabs
        </div>
      </div>
      
      {/* Main */}
      <div style={{ flex: 1, padding: 24, overflow: "auto" }}>
        <div style={{ maxWidth: 1200, margin: "0 auto" }}>
          <h1 style={{ fontSize: 20, fontWeight: 700, color: COLORS.text, marginBottom: 20 }}>
            {NAV_ITEMS.find(n => n.id === page)?.label}
          </h1>
          <PageComponent />
        </div>
      </div>
    </div>
  );
}
