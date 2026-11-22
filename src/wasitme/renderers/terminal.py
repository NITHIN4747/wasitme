"""
Rich terminal renderer implementing docs/DESIGN.md exactly.
Owned by Suriya (Principal Full-Stack Engineer).
Invariants:
- Verdict banner displayed first with counts.
- BROKE AFTER YOUR CHANGE printed first, ALREADY BROKEN second, FIXED third.
- Meaning is never carried by color alone (bracket symbols [!], [~], [+] used everywhere).
- Full NO_COLOR and non-TTY support.
- Responsive to 80-column and 120-column viewports.
"""
from __future__ import annotations

import os

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from wasitme.models import DiffResult


def get_console() -> Console:
    """Returns a Rich console respecting NO_COLOR and TTY detection."""
    no_color = bool(os.environ.get("NO_COLOR"))
    return Console(
        no_color=no_color,
        color_system=None if no_color else "auto",
        force_terminal=None if no_color else None,
        width=min(120, max(80, shutil_terminal_width())),
    )


def shutil_terminal_width() -> int:
    try:
        import shutil
        return shutil.get_terminal_size((80, 24)).columns
    except Exception:
        return 80


def render_terminal(diff_result: DiffResult, verbose: bool = False) -> None:
    """Renders formatted attribution diff to stdout using Rich."""
    console = get_console()

    broke_count = len(diff_result.broke_after)
    already_count = len(diff_result.already_broken)
    fixed_count = len(diff_result.fixed)

    # 1. Verdict Banner
    if diff_result.verdict == "REGRESSION_DETECTED":
        verdict_text = Text(
            f"[FAIL] VERDICT: REGRESSION DETECTED ({broke_count} regressions, {already_count} pre-existing, {fixed_count} fixed)",
            style="bold white on red" if not console.no_color else "bold",
        )
    elif diff_result.verdict == "PREEXISTING_ISSUES_ONLY":
        verdict_text = Text(
            f"[OK] VERDICT: CLEAN ({broke_count} regressions, {already_count} pre-existing, {fixed_count} fixed)",
            style="bold yellow" if not console.no_color else "bold",
        )
    else:
        verdict_text = Text(
            f"[OK] VERDICT: CLEAN ({broke_count} regressions, {already_count} pre-existing, {fixed_count} fixed)",
            style="bold green" if not console.no_color else "bold",
        )

    console.print()
    console.print(Panel(verdict_text, expand=False))

    console.print(
        f"[dim]Baseline: {diff_result.baseline_taken_at} | Current: {diff_result.current_taken_at}[/dim]\n"
    )

    # 2. Unsettled Workloads Warning if present
    if diff_result.unsettled:
        console.print("[bold magenta][?] UNSETTLED WORKLOADS ACTIVE:[/bold magenta]")
        for u in diff_result.unsettled:
            console.print(f"  • {u} [dim](still rolling out or pending)[/dim]")
        console.print(
            "[dim]Tip: Use --wait DURATION or --rollout KIND/NAME to let resources settle.[/dim]\n"
        )

    # 3. 🔴 BROKE AFTER YOUR CHANGE
    if broke_count > 0:
        console.print(
            f"[bold red]🔴 BROKE AFTER YOUR CHANGE ({broke_count})[/bold red]"
            if not console.no_color
            else f"[!] BROKE AFTER YOUR CHANGE ({broke_count})"
        )
        for issue in diff_result.broke_after:
            severity_tag = "[ERROR]" if issue.severity == "error" else "[WARN]"
            console.print(f"  • [bold]{issue.kind.value}[/bold] {severity_tag} [dim]({issue.key})[/dim]")
            console.print(f"    {issue.detail}")
            if verbose and issue.metrics:
                console.print(f"    [dim]Metrics: {issue.metrics}[/dim]")
        console.print()

    # 4. 🟡 ALREADY BROKEN
    if already_count > 0:
        console.print(
            f"[bold yellow]🟡 ALREADY BROKEN ({already_count})[/bold yellow]"
            if not console.no_color
            else f"[~] ALREADY BROKEN ({already_count})"
        )
        items_to_show = diff_result.already_broken if verbose else diff_result.already_broken[:3]
        for issue in items_to_show:
            console.print(f"  • [bold]{issue.kind.value}[/bold] [dim]({issue.key})[/dim]")
            console.print(f"    {issue.detail}")

        if not verbose and already_count > 3:
            console.print(
                f"  [dim]... and {already_count - 3} more pre-existing issues (use --verbose to view all)[/dim]"
            )
        console.print()

    # 5. 🟢 FIXED
    if fixed_count > 0:
        console.print(
            f"[bold green]🟢 FIXED ({fixed_count})[/bold green]"
            if not console.no_color
            else f"[+] FIXED ({fixed_count})"
        )
        for issue in diff_result.fixed:
            console.print(f"  • [bold]{issue.kind.value}[/bold] [dim]({issue.key})[/dim]")
            console.print(f"    {issue.detail}")
        console.print()

    # Footer note
    if diff_result.verdict == "REGRESSION_DETECTED":
        console.print(
            "[bold red]Action Required:[/bold red] Review the regressions above. Your deployment introduced new failures.\n"
        )
    elif diff_result.verdict == "PREEXISTING_ISSUES_ONLY":
        console.print(
            "[dim]Note: Issues were detected, but all were pre-existing prior to your change. No new regressions.[/dim]\n"
        )
    else:
        console.print("[bold green]Deploy verification successful. No regressions detected.[/bold green]\n")
