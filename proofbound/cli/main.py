import argparse
import sys
import uvicorn
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.markdown import Markdown
from proofbound.core.agent import ProofboundAgent
from proofbound.core.approval_gate import ApprovalGate
from proofbound.core.ledger import ActionLedger
from proofbound.memory.engine import MemoryEngine
from proofbound.benchmark.suite import BenchmarkSuite
from proofbound.config import settings

console = Console()

def cmd_serve(args):
    console.print(f"[bold cyan]Starting Proofbound Server on http://{args.host}:{args.port}[/bold cyan]")
    uvicorn.run("proofbound.web.app:app", host=args.host, port=args.port, reload=args.reload)

def cmd_run(args):
    agent = ProofboundAgent()
    console.print(f"[bold green]>> Submitting Intent:[/bold green] [white]{args.intent}[/white]")
    
    run = agent.create_run(args.intent)
    console.print(f"[cyan]Run ID:[/cyan] {run.id}")
    console.print(f"[yellow]Risk Level:[/yellow] {run.risk_level.value} | [magenta]Approval State:[/magenta] {run.approval_state.value}")

    if run.approval_state.value == "PENDING":
        if args.yes:
            ApprovalGate.grant_approval(run, approver="cli-user")
            agent.ledger.save_run(run)
            console.print("[green][OK] Auto-approving per --yes flag[/green]")
        else:
            console.print(Panel(f"Policy Gate requires confirmation for risk level: [bold]{run.risk_level.value}[/bold]\nScopes: {', '.join(run.requested_scopes)}", title="Approval Gate"))
            ans = input("Approve execution? (y/N): ").strip().lower()
            if ans == 'y':
                ApprovalGate.grant_approval(run, approver="cli-user")
                agent.ledger.save_run(run)
            else:
                ApprovalGate.reject_approval(run, approver="cli-user", reason="Rejected in CLI")
                agent.ledger.save_run(run)
                console.print("[red]Execution rejected.[/red]")
                return

    if run.approval_state.value in ["APPROVED", "AUTO_APPROVED"]:
        console.print("[cyan]Executing plan steps...[/cyan]")
        completed_run = agent.execute_run(run.id)
        
        table = Table(title=f"ActionRun Summary: {completed_run.id}")
        table.add_column("Step", style="cyan")
        table.add_column("Title", style="white")
        table.add_column("Tool", style="yellow")
        table.add_column("Status", style="green")
        for s in completed_run.plan_steps:
            table.add_row(str(s.step_index), s.title, s.tool_name, s.status.value)
        console.print(table)

        if completed_run.citations:
            console.print(f"[bold green][*] Citations Captured ({len(completed_run.citations)}):[/bold green]")
            for cit in completed_run.citations:
                console.print(f"  * [{cit.source_uri}] {cit.snippet[:100]}...")

        if any(s.status.value == "failed" for s in completed_run.plan_steps):
            raise SystemExit(1)
    elif run.approval_state.value == "REJECTED":
        raise SystemExit(1)

def cmd_audit(args):
    ledger = ActionLedger()
    if args.action == "list":
        runs = ledger.list_runs(limit=args.limit)
        table = Table(title="Proofbound Verifiable Action Ledger")
        table.add_column("Run ID", style="cyan")
        table.add_column("Intent", style="white")
        table.add_column("Risk", style="yellow")
        table.add_column("Approval", style="magenta")
        table.add_column("Started At", style="dim")
        for r in runs:
            table.add_row(r["id"], r["intent"][:40] + "...", r["risk_level"], r["approval_state"], r["started_at"])
        console.print(table)
    elif args.action == "show":
        if not args.run_id:
            console.print("[red]Error: --run-id required for audit show[/red]")
            return
        md = ledger.export_markdown(args.run_id)
        console.print(Markdown(md))
    elif args.action == "replay":
        if not args.run_id:
            console.print("[red]Error: --run-id required for audit replay[/red]")
            return
        rep = ledger.replay_run(args.run_id)
        console.print(f"[bold cyan]Replay for Run {rep.run_id}:[/bold cyan] {'[green]100% IDENTICAL[/green]' if rep.is_identical else '[red]DIVERGENCE DETECTED[/red]'}")
        console.print(f"Replayed {rep.replayed_events}/{rep.total_events} events (Match Rate: {rep.match_rate*100:.1f}%)")

def cmd_memory(args):
    memory = MemoryEngine()
    if args.action == "list":
        facts = memory.storage.list_facts()
        table = Table(title="Source-Linked Memory Bank")
        table.add_column("ID", style="cyan")
        table.add_column("Category", style="yellow")
        table.add_column("Content", style="white")
        table.add_column("Provenance Run", style="dim")
        table.add_column("Confidence", style="green")
        for f in facts:
            table.add_row(f.id, f.category.value, f.content[:50] + "...", f.provenance_run_id, f"{f.confidence*100:.0f}%")
        console.print(table)
    elif args.action == "rollback":
        if not args.fact_id:
            console.print("[red]Error: --fact-id required for rollback[/red]")
            return
        rolled = memory.rollback_fact(args.fact_id, args.revision_id)
        console.print(f"[green][OK] Memory '{rolled.id}' reverted to: {rolled.content}[/green]")

def cmd_benchmark(args):
    console.print("[bold cyan]Running Proofbound 10-Task Verification Benchmark Suite...[/bold cyan]")
    suite = BenchmarkSuite()
    res = suite.run_all()

    table = Table(title=f"Benchmark Verification Results ({res.pass_rate}% Pass Rate)")
    table.add_column("Task ID", style="cyan")
    table.add_column("Name", style="white")
    table.add_column("Category", style="yellow")
    table.add_column("Status", style="bold")
    table.add_column("Duration", style="dim")
    table.add_column("Details", style="dim white")

    for r in res.results:
        status_str = "[green]PASS[/green]" if r.passed else "[red]FAIL[/red]"
        table.add_row(str(r.task_id), r.name, r.category, status_str, f"{r.duration_ms}ms", r.details)

    console.print(table)
    console.print(f"[bold green]Summary: {res.passed_tasks}/{res.total_tasks} passed in {res.total_duration_ms}ms[/bold green]")

    if res.failed_tasks:
        raise SystemExit(1)

def main():
    parser = argparse.ArgumentParser(prog="proofbound", description="Proofbound: Evidence-First Personal Operations Agent")
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    p_serve = subparsers.add_parser("serve", help="Start web dashboard & API server")
    p_serve.add_argument("--host", default=settings.host, help="Host interface")
    p_serve.add_argument("--port", type=int, default=settings.port, help="Port number")
    p_serve.add_argument("--reload", action="store_true", help="Enable live reload")

    p_run = subparsers.add_parser("run", help="Execute an intent")
    p_run.add_argument("intent", help="Task description or goal")
    p_run.add_argument("-y", "--yes", action="store_true", help="Auto-approve pending risk boundaries")

    p_audit = subparsers.add_parser("audit", help="Audit ledger inspection & replay")
    p_audit.add_argument("action", choices=["list", "show", "replay"], default="list", nargs="?")
    p_audit.add_argument("--run-id", help="ActionRun ID")
    p_audit.add_argument("--limit", type=int, default=20, help="Number of records to show")

    p_mem = subparsers.add_parser("memory", help="Inspect and manage source-linked memory")
    p_mem.add_argument("action", choices=["list", "rollback"], default="list", nargs="?")
    p_mem.add_argument("--fact-id", help="Fact ID to inspect or rollback")
    p_mem.add_argument("--revision-id", help="Target revision ID for rollback")

    p_bench = subparsers.add_parser("benchmark", help="Execute the 10-task verification benchmark")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(0)

    if args.command == "serve":
        cmd_serve(args)
    elif args.command == "run":
        cmd_run(args)
    elif args.command == "audit":
        cmd_audit(args)
    elif args.command == "memory":
        cmd_memory(args)
    elif args.command == "benchmark":
        cmd_benchmark(args)

if __name__ == "__main__":
    main()
