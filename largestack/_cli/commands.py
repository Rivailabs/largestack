"""Additional CLI commands: trace, cost, test, deploy, license, resume."""

from __future__ import annotations
import typer
from rich.console import Console
from rich.table import Table

console = Console()


def register_commands(app: typer.Typer):

    @app.command()
    def serve(
        file: str = typer.Argument("agent.py", help="Agent file"),
        port: int = typer.Option(8000, help="Port"),
    ):
        """Deploy agent as REST API server."""
        import importlib.util, sys

        spec = importlib.util.spec_from_file_location("agent_module", file)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        agent = None
        for name in dir(mod):
            obj = getattr(mod, name)
            if hasattr(obj, "run") and hasattr(obj, "name") and hasattr(obj, "instructions"):
                agent = obj
                break
        if not agent:
            console.print(f"[red]No Agent found in {file}[/red]")
            return
        console.print(f"[bold purple]Largestack AI API[/bold purple] — {agent.name} on :{port}")
        from largestack.serve import serve as do_serve

        do_serve(agent, port=port)

    @app.command()
    def owasp():
        """Show the OWASP LLM Top-10 / Agentic coverage matrix."""
        from largestack.owasp import owasp_coverage, owasp_coverage_summary

        table = Table(title="OWASP Coverage — largestack")
        table.add_column("ID", style="cyan")
        table.add_column("Risk")
        table.add_column("Status")
        table.add_column("Controls", style="dim")
        icon = {
            "covered": "[green]✅ covered[/green]",
            "partial": "[yellow]⚠️ partial[/yellow]",
            "not_covered": "[red]❌ not covered[/red]",
        }
        for c in owasp_coverage():
            table.add_row(
                c["id"],
                c["name"],
                icon.get(c["status"], c["status"]),
                "; ".join(c["controls"])[:60],
            )
        console.print(table)
        s = owasp_coverage_summary()
        console.print(
            f"[bold]{s['covered']} covered · {s['partial']} partial · "
            f"{s['not_covered']} not-covered[/bold] of {s['total']} mapped risks"
        )

    @app.command()
    def redteam():
        """Run the offline guardrail red-team eval (exits non-zero if a core attack passes through)."""
        import asyncio
        from largestack._test.redteam import RedTeamSuite

        report = asyncio.run(RedTeamSuite().run())
        console.print(report.format())
        if not report.core_passed():
            raise typer.Exit(1)

    @app.command("siem-export")
    def siem_export(
        out: str = typer.Option("audit_siem.log", help="Output file"),
        fmt: str = typer.Option("cef", help="Format: json | cef | leef"),
    ):
        """Export the audit trail to a SIEM-ingestible file (JSON-lines / CEF / LEEF)."""
        from largestack._enterprise.siem import SiemExporter

        n = SiemExporter(fmt=fmt).export_file(out)
        console.print(f"[green]Exported {n} audit rows[/green] → {out} ({fmt})")

    @app.command()
    def sbom(
        fmt: str = typer.Option("cyclonedx", help="cyclonedx | spdx"),
        out: str = typer.Option("sbom.json", help="Output path"),
    ):
        """Generate a Software Bill of Materials (OWASP LLM03 / supply-chain)."""
        from largestack._security.sbom import SBOMGenerator

        SBOMGenerator().generate(fmt, output_path=out)
        console.print(f"[green]SBOM written[/green] → {out} ({fmt})")

    """Register additional CLI commands."""

    @app.command()
    def trace(limit: int = typer.Option(20, help="Number of traces")):
        """View recent traces."""
        import sqlite3, os, json

        db_path = os.path.expanduser("~/.largestack/traces.db")
        if not os.path.exists(db_path):
            console.print("[dim]No traces yet. Run an agent first.[/dim]")
            return
        db = sqlite3.connect(db_path)
        rows = db.execute(
            "SELECT trace_id, name, start_time, end_time, attributes FROM spans ORDER BY start_time DESC LIMIT ?",
            (limit,),
        ).fetchall()
        if not rows:
            console.print("[dim]No traces found.[/dim]")
            return
        table = Table(title="Recent Traces")
        table.add_column("Trace ID", style="cyan")
        table.add_column("Name")
        table.add_column("Duration")
        table.add_column("Attributes")
        for r in rows:
            dur = f"{(r[3] - r[2]) / 1e9:.1f}s" if r[2] and r[3] else "?"
            attrs = json.loads(r[4]) if r[4] else {}
            table.add_row(r[0][:12] + "...", r[1], dur, str(attrs)[:60])
        console.print(table)

    @app.command()
    def cost(period: str = typer.Option("all", help="Period: today, week, month, all")):
        """View cost breakdown from audit trail."""
        import sqlite3, os, time
        from rich.table import Table

        db_path = os.path.expanduser("~/.largestack/audit.db")
        if not os.path.exists(db_path):
            console.print("[dim]No cost data yet. Run an agent first.[/dim]")
            return
        db = sqlite3.connect(db_path)
        db.row_factory = sqlite3.Row
        since = 0
        if period == "today":
            since = time.time() - 86400
        elif period == "week":
            since = time.time() - 604800
        elif period == "month":
            since = time.time() - 2592000
        rows = db.execute(
            "SELECT agent_name, SUM(cost) as total, COUNT(*) as runs FROM audit_log WHERE timestamp > ? GROUP BY agent_name ORDER BY total DESC",
            (since,),
        ).fetchall()
        if not rows:
            console.print("[dim]No cost data for this period.[/dim]")
            return
        table = Table(title=f"Cost Report ({period})")
        table.add_column("Agent", style="cyan")
        table.add_column("Total Cost", style="green")
        table.add_column("Runs")
        grand_total = 0
        for r in rows:
            table.add_row(r["agent_name"] or "unknown", f"${r['total']:.4f}", str(r["runs"]))
            grand_total += r["total"]
        table.add_row("[bold]TOTAL[/bold]", f"[bold]${grand_total:.4f}[/bold]", "")
        console.print(table)

    @app.command()
    def test(path: str = typer.Argument("tests/", help="Test directory")):
        """Run agent tests with statistical assertions."""
        import subprocess

        console.print(f"[bold]Running tests in {path}...[/bold]")
        result = subprocess.run(["python3", "-m", "pytest", path, "-v"], capture_output=False)

    @app.command()
    def deploy(target: str = typer.Argument("docker", help="Target: docker, k8s")):
        """Deploy LARGESTACK agent to production."""
        if target == "docker":
            console.print("[bold]Building Docker image...[/bold]")
            console.print("  docker build -t largestack-agent .")
            console.print("  docker run -p 8787:8787 largestack-agent")
        elif target == "k8s":
            console.print("[bold]Deploying to Kubernetes...[/bold]")
            console.print("  helm install largestack-agent ./deploy/helm/")

    @app.command()
    def license(key: str = typer.Argument(None, help="License key")):
        """Activate or check LARGESTACK license."""
        from largestack._core.license import LicenseValidator, detect_production

        if key:
            import os

            os.environ["LARGESTACK_LICENSE_KEY"] = key
        v = LicenseValidator(key or "")
        result = v.validate()
        is_prod, score, details = detect_production()
        console.print("\n[bold]License Status[/bold]")
        console.print(f"  Mode: {result['mode']}")
        console.print(f"  Tier: {result['tier']}")
        console.print(
            f"  Production score: {score}/5 ({'production' if is_prod else 'development'})"
        )
        console.print(f"  Message: {result['message']}")

    @app.command()
    def resume():
        """Resume after kill switch."""
        from largestack._guard.kill_switch import deactivate, is_active

        if is_active():
            deactivate()
            console.print("[green]Kill switch deactivated. Agents can resume.[/green]")
        else:
            console.print("[dim]Kill switch is not active.[/dim]")
