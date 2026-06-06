"""SIEM export — stream the audit trail to a SIEM at the documented seam.

The audit trail (``_enterprise/audit.py``) is the source of truth; this reads its
rows and emits them as JSON-lines, CEF, or LEEF to a file, a syslog server, or an
HTTP webhook (Splunk HEC / generic collector). Stdlib-only except the optional
webhook path (httpx, already a dependency).

    from largestack._enterprise.siem import SiemExporter
    exp = SiemExporter(fmt="cef")
    exp.export_file("~/audit.cef")                 # batch dump
    exp.export_syslog("siem.internal", 514)        # RFC5424 over UDP
    await exp.export_webhook("https://hec.example/services/collector")

CLI: ``largestack siem-export --format cef --out audit.cef``
"""
from __future__ import annotations
import json, logging, os, socket, sqlite3, time
from typing import Any

log = logging.getLogger("largestack.siem")

_SEVERITY = {"completed": 3, "failed": 7, "denied": 8, "blocked": 8}


class SiemExporter:
    def __init__(self, audit_db: str = "~/.largestack/audit.db", fmt: str = "json",
                 product: str = "largestack"):
        self.audit_db = os.path.expanduser(audit_db)
        self.fmt = fmt
        self.product = product

    def _read(self, since: float = 0.0, limit: int = 10000) -> list[dict]:
        if not os.path.exists(self.audit_db):
            return []
        conn = sqlite3.connect(self.audit_db)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                "SELECT timestamp, event_type, agent_name, user_id, action, details, cost, trace_id "
                "FROM audit_log WHERE timestamp >= ? ORDER BY timestamp ASC LIMIT ?",
                (since, limit),
            ).fetchall()
            return [dict(r) for r in rows]
        finally:
            conn.close()

    def _severity(self, row: dict) -> int:
        return _SEVERITY.get(str(row.get("action", "")).lower(), 4)

    def format_row(self, row: dict) -> str:
        if self.fmt == "cef":
            return self._to_cef(row)
        if self.fmt == "leef":
            return self._to_leef(row)
        return json.dumps(row, default=str)

    def _to_cef(self, row: dict) -> str:
        # CEF:0|Vendor|Product|Version|SignatureID|Name|Severity|Extension
        ext = (f"rt={int(row.get('timestamp', 0) * 1000)} duser={row.get('user_id', '')} "
               f"act={row.get('action', '')} cs1={row.get('agent_name', '')} cs1Label=agent "
               f"cn1={row.get('cost', 0)} cn1Label=cost externalId={row.get('trace_id', '')}")
        name = str(row.get("event_type", "event")).replace("|", "/")
        return (f"CEF:0|Riva Labs|{self.product}|1.1.1|{row.get('event_type', 'event')}|"
                f"{name}|{self._severity(row)}|{ext}")

    def _to_leef(self, row: dict) -> str:
        return (f"LEEF:2.0|Riva Labs|{self.product}|1.1.1|{row.get('event_type', 'event')}|"
                f"devTime={int(row.get('timestamp', 0))}\tusrName={row.get('user_id', '')}\t"
                f"action={row.get('action', '')}\tagent={row.get('agent_name', '')}\t"
                f"cost={row.get('cost', 0)}\ttraceId={row.get('trace_id', '')}")

    def export_file(self, path: str, since: float = 0.0) -> int:
        rows = self._read(since)
        path = os.path.expanduser(path)
        with open(path, "w", encoding="utf-8") as f:
            for r in rows:
                f.write(self.format_row(r) + "\n")
        log.info("SIEM export: %d audit rows → %s (%s)", len(rows), path, self.fmt)
        return len(rows)

    def export_syslog(self, host: str, port: int = 514, since: float = 0.0,
                      proto: str = "udp") -> int:
        rows = self._read(since)
        sock = socket.socket(socket.AF_INET,
                             socket.SOCK_DGRAM if proto == "udp" else socket.SOCK_STREAM)
        try:
            if proto != "udp":
                sock.connect((host, port))
            for r in rows:
                # RFC5424-ish: <priority>VERSION TIMESTAMP HOST APP - - MSG
                pri = 8 + min(self._severity(r), 7)  # facility 1 (user) * 8 + severity
                msg = f"<{pri}>1 - - {self.product} - - - {self.format_row(r)}".encode()
                if proto == "udp":
                    sock.sendto(msg, (host, port))
                else:
                    sock.sendall(msg + b"\n")
            return len(rows)
        finally:
            sock.close()

    async def export_webhook(self, url: str, since: float = 0.0, headers: dict | None = None) -> int:
        import httpx
        rows = self._read(since)
        payload = ("\n".join(self.format_row(r) for r in rows)
                   if self.fmt != "json" else
                   "\n".join(json.dumps(r, default=str) for r in rows))
        async with httpx.AsyncClient(timeout=30) as c:
            resp = await c.post(url, content=payload, headers=headers or {})
            resp.raise_for_status()
        log.info("SIEM export: %d audit rows → %s", len(rows), url)
        return len(rows)
