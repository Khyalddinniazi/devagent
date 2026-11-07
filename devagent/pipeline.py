"""Deterministic stage machine: plan -> [gate] -> code -> test -> debug loop -> [gate] -> deploy."""

from __future__ import annotations

import functools
import os
import re
import subprocess
from collections.abc import Callable
from pathlib import Path

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt

from . import deploy
from .agents import coder, debugger, planner, tester, writer
from .agents.base import AgentSpec
from .config import Config
from .runner import Runner, StageResult
from .security import scan_files
from .state import RunState, Stage, StageCost
from .tools.project_tools import NO_OP_COMMANDS, TestReport, detect_test_command, run_tests, skipped_report

INJECTION_RE = re.compile(r"^\s*INJECTION-ALERT:\s*(.+)$", re.M)

# Gate callbacks: (state, console) -> decision string
PlanGate = Callable[[RunState, Console], tuple[str, str | None]]  # ("approve"|"edit"|"revise"|"reject", feedback)
DeployGate = Callable[[RunState, Console, str, str], bool]
TestFn = Callable[[Path, str | None, int], TestReport]


class StageFailed(RuntimeError):
    pass


# ---------------------------------------------------------------------------- default interactive gates
def interactive_plan_gate(state: RunState, console: Console) -> tuple[str, str | None]:
    console.print(Panel(Markdown(state.plan_path.read_text()), title="Proposed plan", border_style="blue"))
    choice = Prompt.ask(
        "[bold]Approve plan?[/] \\[a]pprove / \\[e]dit in $EDITOR / \\[r]evise with feedback / \\[x] reject",
        choices=["a", "e", "r", "x"],
        default="a",
        console=console,
    )
    if choice == "a":
        return "approve", None
    if choice == "e":
        editor = os.environ.get("VISUAL") or os.environ.get("EDITOR") or "vi"
        subprocess.call([*editor.split(), str(state.plan_path)])
        return "edit", None
    if choice == "r":
        return "revise", Prompt.ask("Feedback for the planner", console=console)
    return "reject", None


def interactive_deploy_gate(state: RunState, console: Console, status: str, stat: str) -> bool:
    if state.security_alerts:
        console.print(
            Panel(
                "\n".join(state.security_alerts) + "\n\nAn agent saw text in your project that tried to "
                "give it instructions. Review the changes very carefully.",
                title="🚨 Possible prompt injection",
                border_style="red",
            )
        )
    if state.tests_skipped:
        console.print(
            Panel(
                "This project has no test suite, so NOTHING was checked automatically.\n"
                "Open the result and check it yourself before you send it.",
                title="⚠️  NOT TESTED",
                border_style="red",
            )
        )
        title, style = "Changes ready - NOT TESTED", "yellow"
    else:
        title, style = "Changes ready - tests PASSED", "green"
    console.print(
        Panel(f"Every file below will be committed - read the list:\n\n{status}\n\n{stat}", title=title, border_style=style)
    )
    answer = Prompt.ask(
        f"Commit to branch [bold]{state.branch}[/], push and open a PR against [bold]{state.base_branch}[/]?",
        choices=["y", "n"],
        default="n",
        console=console,
    )
    return answer == "y"


# ---------------------------------------------------------------------------- pipeline
class Pipeline:
    def __init__(
        self,
        state: RunState,
        config: Config,
        runner: Runner,
        console: Console | None = None,
        plan_gate: PlanGate = interactive_plan_gate,
        deploy_gate: DeployGate = interactive_deploy_gate,
        test_fn: TestFn | None = None,  # default: run_tests with the configured test sandbox
        deploy_enabled: bool = True,
        allow_untested_deploy: bool = True,  # False with --yes: never auto-ship code nobody verified
    ):
        self.state = state
        self.config = config
        self.runner = runner
        self.console = console or Console()
        self.plan_gate = plan_gate
        self.deploy_gate = deploy_gate
        test_sandbox = config.test_sandbox if config.sandbox_tests else "none"
        self.test_fn = test_fn or functools.partial(run_tests, sandbox=test_sandbox, image=config.test_image)
        self.deploy_enabled = deploy_enabled
        self.allow_untested_deploy = allow_untested_deploy
        self.repo = Path(state.repo)

    # -- helpers --------------------------------------------------------------
    def _log(self, msg: str) -> None:
        self.console.print(msg)

    def _remaining_budget(self) -> float:
        return self.config.max_cost_usd - self.state.total_cost

    async def _run_agent(self, spec: AgentSpec, prompt: str, label: str | None = None) -> StageResult:
        label = label or spec.name
        remaining = self._remaining_budget()
        if remaining < 0.05:
            raise StageFailed(
                f"spending limit reached (${self.state.total_cost:.2f} of ${self.config.max_cost_usd:.2f}); "
                "raise it with --max-cost to continue"
            )
        self._log(f"\n[bold magenta]▶ {label}[/] [dim](budget left ${remaining:.2f})[/]")
        res = await self.runner.run(spec, prompt, budget_usd=remaining)
        self.state.costs.append(StageCost(stage=label, cost_usd=res.cost_usd, turns=res.turns, is_error=res.is_error))
        self.state.save()
        (self.state.dir / f"{label}.out.md").write_text(res.text or "")
        self._log(f"[dim]  {label}: {res.turns} turns, ${res.cost_usd:.4f}[/]")
        alerts = INJECTION_RE.findall(res.text or "")
        if alerts:
            self.state.security_alerts.extend(f"{label}: {a.strip()}" for a in alerts)
            self.state.save()
            self._log(f"[bold red]⚠️  {label} found content that tried to give it instructions (possible prompt injection):[/]")
            for a in alerts:
                self._log(f"[red]    {a.strip()}[/]")
        if res.is_error:
            raise StageFailed(f"{label} agent failed: {res.error}")
        return res

    def _set(self, stage: Stage) -> None:
        self.state.stage = stage
        self.state.save()

    def _read(self, name: str) -> str:
        p = self.state.dir / name
        return p.read_text() if p.exists() else ""

    def _has_test_suite(self) -> bool:
        cmd = self.config.test_command
        if cmd is not None:
            return cmd.strip() not in NO_OP_COMMANDS
        return detect_test_command(self.repo) is not None

    def _record(self, report: TestReport) -> TestReport:
        self.state.test_report_path.write_text(report.to_json())
        self.state.tests_passed = report.passed
        self.state.tests_skipped = report.skipped
        self.state.test_summary = report.summary()
        self.state.save()
        color = "yellow" if report.skipped else ("green" if report.passed else "red")
        self._log(f"[{color}]  tests: {report.summary()}[/]")
        return report

    def _test(self) -> TestReport:
        if not self._has_test_suite():
            return self._record(skipped_report(self.config.test_command or "<none>"))
        return self._record(self.test_fn(self.repo, self.config.test_command, self.config.test_timeout))

    # -- stages ---------------------------------------------------------------
    async def plan(self) -> bool:
        feedback: str | None = None
        while True:
            res = await self._run_agent(planner.SPEC, planner.prompt(self.state.task, feedback))
            if not res.text.strip():
                raise StageFailed("planner returned an empty plan")
            self.state.plan_path.write_text(res.text.strip() + "\n")
            self._set(Stage.PLANNED)
            decision, feedback = self.plan_gate(self.state, self.console)
            if decision in ("approve", "edit"):
                self._set(Stage.APPROVED)
                return True
            if decision == "reject":
                self._set(Stage.ABORTED)
                return False
            # "revise": loop with feedback

    async def code(self) -> None:
        plan = self.state.plan_path.read_text()
        await self._run_agent(coder.SPEC, coder.prompt(self.state.task, plan))
        if not deploy.has_changes(self.repo):
            raise StageFailed("coder finished without changing any files")
        self._set(Stage.CODED)

    async def test(self) -> TestReport:
        if not self._has_test_suite() and not self.config.write_tests_without_framework:
            self._log(
                "\n[bold yellow]⚠️  No test suite found in this project - skipping the Tester. "
                "Nothing will be checked automatically; check the result yourself.[/]"
            )
            report = self._test()
        else:
            plan = self.state.plan_path.read_text()
            await self._run_agent(tester.SPEC, tester.prompt(self.state.task, plan, self._read("coder.out.md")))
            report = self._test()
        self._set(Stage.TESTED)
        return report

    async def debug_loop(self, report: TestReport) -> TestReport:
        plan = self.state.plan_path.read_text()
        while not report.passed and self.state.debug_attempts < self.config.max_debug:
            self.state.debug_attempts += 1
            n = self.state.debug_attempts
            history = self._read("debug_log.md")
            res = await self._run_agent(
                debugger.SPEC, debugger.prompt(self.state.task, plan, report.to_json(), n, history), label=f"debugger-{n}"
            )
            report = self._test()
            with self.state.debug_log_path.open("a") as f:
                f.write(f"### Attempt {n} -> {'PASS' if report.passed else 'FAIL'}\n{res.text.strip()}\n\n")
        return report

    def _secret_findings(self) -> str:
        findings = scan_files(self.repo, deploy.changed_files(self.repo))
        return "\n".join(f"  • {f.path}: {f.reason}" for f in findings)

    async def ship(self) -> None:
        unsafe = self._secret_findings()
        status, stat = deploy.change_summary(self.repo)
        if not self.deploy_enabled:
            self.console.print(Panel(f"{status}\n\n{stat}", title="Changes left in working tree (--no-deploy)"))
            if unsafe:
                self._log(f"[bold red]⚠️  These files look unsafe to upload - remove them before sending:[/]\n{unsafe}")
            return
        if unsafe:
            raise StageFailed(
                "refusing to commit - these files look unsafe to upload:\n"
                + unsafe
                + "\nRemove them (or add them to .gitignore), then run `devagent resume`."
            )
        if self.state.tests_skipped and not self.allow_untested_deploy:
            raise StageFailed(
                "not deploying automatically: nothing was tested. Review the changes, then run "
                "`devagent resume` without --yes (or pass --allow-untested)."
            )
        if not self.deploy_gate(self.state, self.console, status, stat):
            self._log("[yellow]Deploy declined. Changes are left uncommitted in the working tree.[/]")
            return
        branch, base = self.state.branch, self.state.base_branch
        if not branch or not base:
            raise StageFailed("internal error: branch names were not set before deploy")
        body = await self._pr_body(stat, self.state.test_summary or "")
        title = self._pr_title()
        message = f"{title}\n\n{self.state.task}\n\nGenerated by devagent run {self.state.run_id}"
        deploy.commit_branch(self.repo, branch, message)
        url = deploy.push_and_open_pr(self.repo, branch, base, title, body, self.config.remote)
        self.state.pr_url = url.splitlines()[-1] if url else None
        self._set(Stage.DEPLOYED)
        self._log(f"[bold green]✔ PR opened:[/] {self.state.pr_url}")

    def _pr_title(self) -> str:
        first = self.state.plan_path.read_text().splitlines()[0] if self.state.plan_path.exists() else ""
        title = first.removeprefix("# ").removeprefix("Plan:").strip() or self.state.task
        return title[:72]

    async def _pr_body(self, stat: str, test_summary: str) -> str:
        plan = self.state.plan_path.read_text()
        try:
            res = await self._run_agent(writer.SPEC, writer.prompt(self.state.task, plan, stat, test_summary), label="pr-writer")
            body = res.text.strip()
        except StageFailed:
            body = ""
        if not body:
            body = f"## Summary\n{self.state.task}\n\n## Plan\n{plan}\n\n## Testing\n{test_summary}\n"
        if self.state.tests_skipped:
            body = (
                "> [!WARNING]\n> This project has no automated tests, so this change was **not tested "
                "automatically**. Please check it manually before merging.\n\n"
            ) + body
        if self.config.pr_note:
            body += f"\n\n{self.config.pr_note}"
        return body + f"\n\n---\n🤖 Generated with devagent (run `{self.state.run_id}`) using the Claude Agent SDK"

    # -- driver ---------------------------------------------------------------
    async def run(self) -> RunState:
        s = self.state
        if s.base_branch is None:
            s.base_branch = self.config.base_branch or deploy.current_branch(self.repo)
        if s.branch is None:
            s.branch = self.config.branch_prefix + s.run_id
        s.error = None
        s.save()
        try:
            if s.stage in (Stage.NEW, Stage.PLANNED) and not await self.plan():
                self._log("[yellow]Plan rejected; nothing changed.[/]")
                return s
            if s.stage == Stage.APPROVED:
                await self.code()
            if s.stage == Stage.CODED:
                report = await self.test()
            elif s.stage == Stage.TESTED:  # resuming after an exhausted debug loop
                report = self._test()
            else:
                report = None
            if report is not None and report.environment_error:
                s.error = (
                    f"the test command can't run: {report.environment_error}. That's a setup problem, not a code "
                    "problem, so devagent didn't try to debug it. Fix the environment or pass --test-command."
                )
                s.save()
                self._log(f"[bold red]✘ {s.error}[/]\nChanges left uncommitted for inspection.")
                return s
            if report is not None:
                report = await self.debug_loop(report)
                if not report.passed:
                    s.error = f"tests still failing after {s.debug_attempts} debug attempt(s): {report.summary()}"
                    s.save()
                    self._log(f"[bold red]✘ {s.error}[/]\nReport: {s.test_report_path}\nChanges left uncommitted for inspection.")
                    return s
                self._set(Stage.READY)
            if s.stage == Stage.READY:
                await self.ship()
        except (StageFailed, deploy.DeployError) as e:
            s.error = str(e)
            s.save()
            self._log(f"[bold red]✘ {e}[/]")
        return s
