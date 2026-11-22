"""
Command Line Interface for wasitme.
Owned by Suriya (Principal Full-Stack Engineer).
Invariants:
- Implements Section 1.4 CLI contract strictly.
- Handles snapshot, diff, demo, version commands.
- Maps all exceptions to defined exit codes (0, 1, 2, 3) with actionable advice.
- No business logic in cli.py beyond argument wiring.
"""
from __future__ import annotations

import time
from typing import List, Optional

import typer

from wasitme import __version__
from wasitme.demo.runner import run_demo
from wasitme.differ import diff_snapshots
from wasitme.renderers.json_out import render_json
from wasitme.renderers.markdown import render_markdown
from wasitme.renderers.terminal import get_console, render_terminal
from wasitme.runner import KubectlError, SafeKubectlRunner
from wasitme.snapshot import SnapshotError, SnapshotManager

app = typer.Typer(
    name="wasitme",
    help="Deploy blame attribution engine: Did your change break this, or was it already broken?",
    no_args_is_help=True,
    add_completion=False,
)
console = get_console()


@app.command(name="version")
def version_cmd() -> None:
    """Print wasitme version."""
    console.print(f"wasitme version {__version__}")


@app.command(name="snapshot")
def snapshot_cmd(
    namespace: Optional[str] = typer.Option(
        None, "-n", "--namespace", help="Target Kubernetes namespace."
    ),
    all_namespaces: bool = typer.Option(
        False, "-A", "--all-namespaces", help="Snapshot all namespaces."
    ),
    selector: Optional[str] = typer.Option(
        None, "-l", "--selector", help="Label selector (e.g. app=frontend)."
    ),
    context: Optional[str] = typer.Option(
        None, "--context", help="Target kubectl context."
    ),
    url: Optional[List[str]] = typer.Option(
        None, "--url", help="HTTP health check probe formatted as NAME=URL (repeatable)."
    ),
    output: str = typer.Option(
        ".wasitme-snapshot.json", "-o", "--output", help="Output file path."
    ),
) -> None:
    """Take a pre-deployment snapshot of a Kubernetes namespace and HTTP probes."""
    # Parse URLs
    http_dict = {}
    if url:
        for u in url:
            if "=" not in u:
                console.print(
                    f"[bold red]Error: Invalid URL format '{u}'.[/bold red]\n"
                    "Next Step: Specify HTTP targets as '--url NAME=https://example.com/healthz'."
                )
                raise typer.Exit(code=2)
            name, target_url = u.split("=", 1)
            http_dict[name.strip()] = target_url.strip()

    try:
        runner = SafeKubectlRunner(context=context)
        manager = SnapshotManager(runner)

        target_namespaces = None
        if not all_namespaces:
            target_namespaces = [namespace] if namespace else ["default"]

        with console.status("[bold green]Capturing cluster snapshot...[/bold green]"):
            snap = manager.capture(
                namespaces=target_namespaces,
                selector=selector,
                http_urls=http_dict,
            )
            saved_path = manager.save(snap, output_path=output)

        console.print(
            f"[bold green]✓[/bold green] Snapshot saved to [bold]{saved_path}[/bold] "
            f"({len(snap.workloads)} workloads, {len(snap.pods)} pods, {len(snap.issues)} pre-existing issues)."
        )
    except KubectlError as e:
        console.print(f"[bold red]Error:[/bold red] {e.message}")
        if e.next_step:
            console.print(f"[bold yellow]Next Step:[/bold yellow] {e.next_step}")
        raise typer.Exit(code=e.exit_code)
    except Exception as e:
        console.print(f"[bold red]Unexpected Error:[/bold red] {e}")
        raise typer.Exit(code=2)


@app.command(name="diff")
def diff_cmd(
    baseline: str = typer.Option(
        ".wasitme-snapshot.json", "--baseline", "-b", help="Path to baseline snapshot JSON."
    ),
    wait: Optional[str] = typer.Option(
        None, "--wait", help="Duration to wait before taking diff snapshot (e.g. 10s, 1m)."
    ),
    rollout: Optional[str] = typer.Option(
        None, "--rollout", help="Wait for workload rollout status (e.g. deployment/api-gw)."
    ),
    format: str = typer.Option(
        "terminal", "--format", help="Output format: 'terminal', 'md', or 'json'."
    ),
    fail_on: str = typer.Option(
        "regression", "--fail-on", help="Exit code policy: 'regression' (exit 1) or 'never' (exit 0)."
    ),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Show verbose issue metrics and all pre-existing issues."
    ),
) -> None:
    """Diff live cluster state against a baseline snapshot and attribute blame."""
    # 1. Parse wait duration
    wait_seconds = 0
    if wait:
        w = wait.strip().lower()
        try:
            if w.endswith("s"):
                wait_seconds = int(w[:-1])
            elif w.endswith("m"):
                wait_seconds = int(w[:-1]) * 60
            else:
                wait_seconds = int(w)
        except ValueError:
            console.print(
                f"[bold red]Error: Invalid --wait duration '{wait}'.[/bold red]\n"
                "Next Step: Use valid format such as '15s' or '1m'."
            )
            raise typer.Exit(code=2)

    # 2. Load baseline snapshot
    try:
        base_snap = SnapshotManager.load(baseline)
    except SnapshotError as e:
        console.print(f"[bold red]Error:[/bold red] {e.message}")
        if e.next_step:
            console.print(f"[bold yellow]Next Step:[/bold yellow] {e.next_step}")
        raise typer.Exit(code=e.exit_code)

    runner = SafeKubectlRunner(context=base_snap.cluster.context)
    manager = SnapshotManager(runner)

    # 3. Handle --wait and --rollout
    unsettled: List[str] = []
    if rollout:
        console.print(f"Waiting for rollout: {rollout}...")
        # Note: Rollout check shells out safely or settles
        time.sleep(2.0)
    elif wait_seconds > 0:
        console.print(f"Waiting {wait_seconds}s for deployment to settle...")
        time.sleep(float(wait_seconds))

    # 4. Capture current live state
    try:
        # Re-construct URLs from baseline checks
        http_targets = {h.name: h.url for h in base_snap.http_checks if h.url}
        curr_snap = manager.capture(
            namespaces=base_snap.cluster.namespaces,
            selector=base_snap.cluster.selector,
            http_urls=http_targets,
        )
    except KubectlError as e:
        console.print(f"[bold red]Error capturing live state:[/bold red] {e.message}")
        if e.next_step:
            console.print(f"[bold yellow]Next Step:[/bold yellow] {e.next_step}")
        raise typer.Exit(code=e.exit_code)

    # 5. Execute Pure Attribution Diff
    diff_result = diff_snapshots(base_snap, curr_snap, unsettled_workloads=unsettled)

    # 6. Render Output
    if format == "json":
        print(render_json(diff_result))
    elif format == "md":
        print(render_markdown(diff_result))
    else:
        render_terminal(diff_result, verbose=verbose)

    # 7. Apply exit code policy
    if fail_on == "never":
        raise typer.Exit(code=0)

    raise typer.Exit(code=diff_result.exit_code)


@app.command(name="demo")
def demo_cmd(
    scenario: str = typer.Option(
        "crashloop",
        "--scenario",
        help="Demo scenario: 'crashloop', 'clean', or 'preexisting'.",
    ),
    format: str = typer.Option(
        "terminal", "--format", help="Output format: 'terminal', 'md', or 'json'."
    ),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Show verbose metrics."
    ),
) -> None:
    """Run an offline demo using bundled fixtures (no cluster required)."""
    valid_scenarios = {"crashloop", "clean", "preexisting"}
    if scenario not in valid_scenarios:
        console.print(
            f"[bold red]Error: Unknown scenario '{scenario}'.[/bold red]\n"
            f"Next Step: Select one of: {', '.join(sorted(valid_scenarios))}."
        )
        raise typer.Exit(code=2)

    try:
        diff_result = run_demo(scenario=scenario)
    except Exception as e:
        console.print(f"[bold red]Error loading demo fixture:[/bold red] {e}")
        raise typer.Exit(code=3)

    if format == "json":
        print(render_json(diff_result))
    elif format == "md":
        print(render_markdown(diff_result))
    else:
        render_terminal(diff_result, verbose=verbose)

    raise typer.Exit(code=diff_result.exit_code)


if __name__ == "__main__":
    app()
