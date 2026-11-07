"""devagent CLI."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import typer
from rich.console import Console
from rich.table import Table

from . import deploy
from .config import Config
from .pipeline import Pipeline
from .runner import SDKRunner
from .state import STATE_DIR, RunState, Stage

app = typer.Typer(add_completion=False, help="Multi-agent pipeline: plan → code → test → debug → PR.")
console = Console()


def _auto_plan_gate(state, console):
    console.print(f"[dim]--yes: plan auto-approved ({state.plan_path})[/]")
    return "approve", None


def _auto_deploy_gate(state, console, status, stat):
    console.print(f"[dim]--yes: deploying\n{stat}[/]")
    return True


def _apply_safety_options(
    config: Config, max_cost: float | None, trust_project: bool, allow_network: list[str] | None, no_sandbox: bool
) -> None:
    if max_cost is not None:
        config.max_cost_usd = max_cost
    if trust_project:
        config.trust_project = True
    if allow_network:
        config.allowed_domains = [*config.allowed_domains, *allow_network]
    if no_sandbox:
        config.sandbox = config.sandbox_tests = False


def _safety_banner(config: Config) -> None:
    sandbox = "[green]on[/]" if config.sandbox else "[bold red]OFF[/]"
    net = ", ".join(config.allowed_domains) if config.allowed_domains else "blocked"
    project = "[yellow]trusted (repo settings loaded)[/]" if config.trust_project else "untrusted (repo settings ignored)"
    console.print(
        f"[dim]safety: sandbox {sandbox} · network {net} · spending limit ${config.max_cost_usd:.2f} · project {project}[/]"
    )
    if not config.sandbox:
        console.print("[bold red]⚠️  Sandbox is OFF - agents run commands with your full user permissions.[/]")


def _execute(
    state: RunState, config: Config, yes: bool, deploy_enabled: bool, verbose: bool, allow_untested: bool = False
) -> None:
    _safety_banner(config)
    runner = SDKRunner(Path(state.repo), config, console, verbose=verbose)
    kwargs: dict[str, Any] = {}
    if yes:
        kwargs = {"plan_gate": _auto_plan_gate, "deploy_gate": _auto_deploy_gate, "allow_untested_deploy": allow_untested}
    final = asyncio.run(Pipeline(state, config, runner, console, deploy_enabled=deploy_enabled, **kwargs).run())
    table = Table(title=f"Run {final.run_id}", show_header=True)
    table.add_column("stage")
    table.add_column("turns", justify="right")
    table.add_column("cost", justify="right")
    for c in final.costs:
        table.add_row(c.stage + (" [red](error)[/]" if c.is_error else ""), str(c.turns), f"${c.cost_usd:.4f}")
    table.add_row("[bold]total[/]", "", f"[bold]${final.total_cost:.4f}[/]")
    console.print(table)
    console.print(
        f"stage: [bold]{final.stage.value}[/]"
        + (f"  error: [red]{final.error}[/]" if final.error else "")
        + (f"  PR: {final.pr_url}" if final.pr_url else "")
    )
    if final.error or final.stage == Stage.ABORTED:
        if final.error:
            console.print(f"Resume with: [bold]devagent resume {final.run_id} --repo {final.repo}[/]")
        raise typer.Exit(1)


@app.command()
def run(
    task: str = typer.Argument(..., help="Feature request in plain English"),
    repo: Path = typer.Option(Path("."), "--repo", "-r", help="Target git repository"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip both approval gates (CI mode)"),
    no_deploy: bool = typer.Option(False, "--no-deploy", help="Stop after tests pass; leave changes uncommitted"),
    allow_dirty: bool = typer.Option(False, "--allow-dirty", help="Allow starting with uncommitted changes"),
    max_debug: int | None = typer.Option(None, "--max-debug", help="Max debugger attempts (default 3)"),
    base: str | None = typer.Option(None, "--base", help="PR base branch (default: current branch)"),
    test_command: str | None = typer.Option(None, "--test-command", help="Override test command"),
    model: str | None = typer.Option(None, "--model", help="Model for every stage"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Print agents' narration"),
    max_cost: float | None = typer.Option(None, "--max-cost", help="Spending limit in USD for the whole run (default 5)"),
    trust_project: bool = typer.Option(False, "--trust-project", help="Load the repo's own .claude settings / CLAUDE.md"),
    allow_network: list[str] | None = typer.Option(
        None, "--allow-network", help="Domain sandboxed commands may reach (repeatable), e.g. pypi.org"
    ),
    allow_untested: bool = typer.Option(False, "--allow-untested", help="With --yes: allow deploying when nothing was tested"),
    no_sandbox: bool = typer.Option(False, "--no-sandbox", help="DANGEROUS: run agent commands and tests unsandboxed"),
):
    """Run the full pipeline for TASK."""
    repo = repo.resolve()
    problems = deploy.preflight(repo, allow_dirty=allow_dirty, need_gh=not no_deploy)
    if problems:
        for p in problems:
            console.print(f"[red]✘[/] {p}")
        raise typer.Exit(2)
    config = Config.load(repo, max_debug=max_debug, base_branch=base, test_command=test_command)
    if model:
        for stage in ("planner", "coder", "tester", "debugger", "writer"):
            getattr(config, stage).model = model
    _apply_safety_options(config, max_cost, trust_project, allow_network, no_sandbox)
    state = RunState.new(task, repo)
    console.print(f"[bold]devagent[/] run [cyan]{state.run_id}[/] in {repo}")
    _execute(state, config, yes, not no_deploy, verbose, allow_untested)


@app.command()
def resume(
    run_id: str = typer.Argument(...),
    repo: Path = typer.Option(Path("."), "--repo", "-r"),
    yes: bool = typer.Option(False, "--yes", "-y"),
    no_deploy: bool = typer.Option(False, "--no-deploy"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
    max_cost: float | None = typer.Option(None, "--max-cost", help="New spending limit in USD (whole run, incl. earlier stages)"),
    trust_project: bool = typer.Option(False, "--trust-project"),
    allow_network: list[str] | None = typer.Option(None, "--allow-network"),
    allow_untested: bool = typer.Option(False, "--allow-untested"),
    no_sandbox: bool = typer.Option(False, "--no-sandbox"),
    test_command: str | None = typer.Option(None, "--test-command"),
):
    """Resume a run from its last completed stage (debug attempts are reset)."""
    repo = repo.resolve()
    state = RunState.load(repo, run_id)
    if state.stage in (Stage.DEPLOYED, Stage.ABORTED):
        console.print(f"Run is already {state.stage.value}.")
        raise typer.Exit(0)
    state.debug_attempts = 0
    config = Config.load(repo, test_command=test_command)
    _apply_safety_options(config, max_cost, trust_project, allow_network, no_sandbox)
    _execute(state, config, yes, not no_deploy, verbose, allow_untested)


@app.command()
def status(repo: Path = typer.Option(Path("."), "--repo", "-r")):
    """List runs in REPO."""
    root = repo.resolve() / STATE_DIR
    table = Table("run", "stage", "tests", "cost", "PR / error")
    for d in sorted(root.glob("*/state.json")) if root.exists() else []:
        s = RunState.model_validate_json(d.read_text())
        tests = "-" if s.tests_passed is None else ("pass" if s.tests_passed else "fail")
        table.add_row(s.run_id, s.stage.value, tests, f"${s.total_cost:.2f}", s.pr_url or (s.error or "")[:60])
    console.print(table)


if __name__ == "__main__":
    app()
