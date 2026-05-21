"""CLI entry point — typer-based command interface.

Commands:
  analyze  — read-only directory analysis (markdown report)
  plan     — dry-run showing what would be moved (DEFAULT)
  apply    — execute moves (requires --confirm)
  undo     — reverse a previous session from log
  history  — list recent session logs
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel

from . import __version__
from .analyzer import analyze_scope, format_report
from .executor import execute_plan
from .logger import cleanup_old_logs, list_sessions, load_session
from .planner import format_plan, generate_plan
from .rules import load_rules
from .undo import undo_session

app = typer.Typer(
    name="organizer",
    help="Directory file organization automation tool. Safety-first design: dry-run is the default.",
    add_completion=False,
)
console = Console()

DEFAULT_RULES = Path(__file__).resolve().parent.parent / "config" / "default_rules.yaml"


def _load_ruleset(rule_file: Path | None) -> ...:
    """Load ruleset from file, falling back to default_rules.yaml."""
    path = rule_file or DEFAULT_RULES
    if not path.exists():
        console.print(f"[red]Rule file not found: {path}[/red]")
        raise typer.Exit(1)
    return load_rules(path)


def _resolve_scopes(
    scope: list[str] | None, ruleset_scopes: list[Path]
) -> list[Path]:
    """Determine which directories to scan."""
    if scope:
        return [Path(s).expanduser().resolve() for s in scope]
    return [s.resolve() for s in ruleset_scopes]


@app.command()
def analyze(
    scope: Optional[list[str]] = typer.Option(
        None, "--scope", "-s", help="Directory to analyze (repeatable)"
    ),
    rule_file: Optional[Path] = typer.Option(
        None, "--rule-file", "-r", help="YAML rules file"
    ),
) -> None:
    """Read-only analysis of target directories. No files are moved."""
    ruleset = _load_ruleset(rule_file)
    scopes = _resolve_scopes(scope, ruleset.settings.scopes)

    if not scopes:
        console.print("[yellow]No scopes configured. Use --scope or configure in YAML.[/yellow]")
        raise typer.Exit(1)

    results = [analyze_scope(s, ruleset) for s in scopes]
    report = format_report(results)
    console.print(report)


@app.command()
def plan(
    scope: Optional[list[str]] = typer.Option(
        None, "--scope", "-s", help="Directory to scan (repeatable)"
    ),
    rule_file: Optional[Path] = typer.Option(
        None, "--rule-file", "-r", help="YAML rules file"
    ),
) -> None:
    """Dry-run: show what would be moved without changing anything."""
    ruleset = _load_ruleset(rule_file)
    scopes = _resolve_scopes(scope, ruleset.settings.scopes)

    if not scopes:
        console.print("[yellow]No scopes configured. Use --scope or configure in YAML.[/yellow]")
        raise typer.Exit(1)

    p = generate_plan(scopes, ruleset)
    output = format_plan(p)
    console.print(output)

    if p.actions:
        console.print(
            "\n[bold yellow]To apply these changes:[/bold yellow] "
            "[cyan]organizer apply --confirm[/cyan]"
        )


@app.command()
def apply(
    scope: Optional[list[str]] = typer.Option(
        None, "--scope", "-s", help="Directory to scan (repeatable)"
    ),
    rule_file: Optional[Path] = typer.Option(
        None, "--rule-file", "-r", help="YAML rules file"
    ),
    confirm: bool = typer.Option(
        False, "--confirm", help="Required flag to actually execute moves"
    ),
) -> None:
    """Execute file organization. Requires --confirm to proceed."""
    if not confirm:
        console.print(
            Panel(
                "[bold red]Safety gate:[/bold red] "
                "The --confirm flag is required to execute file moves.\n\n"
                "Run [cyan]organizer plan[/cyan] first to preview changes,\n"
                "then [cyan]organizer apply --confirm[/cyan] to proceed.",
                title="Confirmation Required",
            )
        )
        raise typer.Exit(1)

    ruleset = _load_ruleset(rule_file)
    scopes = _resolve_scopes(scope, ruleset.settings.scopes)

    if not scopes:
        console.print("[yellow]No scopes configured.[/yellow]")
        raise typer.Exit(1)

    # Generate and show plan first
    p = generate_plan(scopes, ruleset)

    if not p.actions:
        console.print("[green]Nothing to do. All files are already organized or unmatched.[/green]")
        return

    console.print(f"[bold]Executing {len(p.actions)} actions...[/bold]\n")

    session, log_path = execute_plan(p)

    # Summary
    console.print(f"\n[bold green]Done.[/bold green]")
    console.print(f"  Moves:  {session.total_moves}")
    console.print(f"  Trash:  {session.total_trash}")
    console.print(f"  Errors: {session.total_errors}")
    console.print(f"  Log:    {log_path}")

    if session.total_errors > 0:
        console.print("\n[yellow]Some operations failed. Check the log for details.[/yellow]")

    console.print(f"\n[dim]To undo: organizer undo {log_path}[/dim]")

    # Cleanup old logs
    cleaned = cleanup_old_logs(ruleset.settings.log_retention_days)
    if cleaned:
        console.print(f"[dim]Cleaned {cleaned} old log(s).[/dim]")


@app.command()
def undo(
    log_file: Path = typer.Argument(
        ..., help="Path to the session log JSON to reverse"
    ),
) -> None:
    """Reverse all operations from a previous session log."""
    if not log_file.exists():
        console.print(f"[red]Log file not found: {log_file}[/red]")
        raise typer.Exit(1)

    console.print(f"[bold]Undoing session from: {log_file}[/bold]\n")

    session, undo_path = undo_session(log_file)

    console.print(f"[bold green]Undo complete.[/bold green]")
    console.print(f"  Reversed:  {session.total_moves}")
    console.print(f"  Errors:    {session.total_errors}")
    console.print(f"  Undo log:  {undo_path}")


@app.command()
def history(
    limit: int = typer.Option(20, "--limit", "-n", help="Number of sessions to show"),
) -> None:
    """List recent session logs."""
    logs = list_sessions(limit=limit)

    if not logs:
        console.print("[dim]No session logs found.[/dim]")
        return

    console.print("[bold]Recent sessions:[/bold]\n")
    for log_path in logs:
        try:
            session = load_session(log_path)
            moves = session.total_moves
            trash = session.total_trash
            errors = session.total_errors
            console.print(
                f"  {session.session_id}  "
                f"moves={moves} trash={trash} errors={errors}  "
                f"[dim]{log_path}[/dim]"
            )
        except Exception:
            console.print(f"  [dim]{log_path.name} (corrupt)[/dim]")


@app.command()
def version() -> None:
    """Show version."""
    console.print(f"organizer {__version__}")


def main() -> None:
    """Entry point for the CLI."""
    app()


if __name__ == "__main__":
    main()
