from pathlib import Path

import pytest
from rich.console import Console

from devagent import deploy
from devagent.config import Config
from devagent.pipeline import Pipeline
from devagent.runner import StageResult
from devagent.state import RunState, Stage
from devagent.tools.project_tools import Failure, TestReport

PLAN = "# Plan: Change f\n## Steps\n1. return 2\n"


class FakeRunner:
    """Scripted stand-in for SDKRunner. Handlers may edit the repo to simulate agent work."""

    def __init__(self, repo: Path, handlers: dict):
        self.repo, self.handlers, self.calls = repo, handlers, []

    async def run(self, spec, prompt, budget_usd=None):
        self.calls.append((spec.name, prompt))
        self.budgets = getattr(self, "budgets", []) + [budget_usd]
        h = self.handlers.get(spec.name)
        res = h(self.repo, prompt) if h else None
        return res or StageResult(text=f"{spec.name} done", cost_usd=0.01, turns=2)


def edit_code(repo, prompt):
    (repo / "app.py").write_text("def f():\n    return 2\n")


def scripted_tests(*passes):
    seq = list(passes)

    def fn(repo, cmd, timeout):
        ok = seq.pop(0) if seq else seq_last[0]
        seq_last[0] = ok
        return TestReport(
            command="pytest",
            passed=ok,
            exit_code=0 if ok else 1,
            num_passed=1,
            num_failed=0 if ok else 1,
            failures=[] if ok else [Failure("t::x", "boom")],
        )

    seq_last = [passes[-1]]
    return fn


def make(
    git_repo,
    handlers,
    tests,
    plan_decisions=("approve",),
    deploy_ok=False,
    deploy_enabled=True,
    allow_untested_deploy=True,
    **cfg,
):
    cfg.setdefault("test_command", "pytest")  # pretend the repo has a test suite unless a test says otherwise
    deploy.exclude_state_dir(git_repo)
    state = RunState.new("make f return 2", git_repo)
    decisions = list(plan_decisions)
    gates = {"plan": 0, "deploy": 0}

    def plan_gate(s, c):
        gates["plan"] += 1
        d = decisions.pop(0)
        return (d, "more detail") if d == "revise" else (d, None)

    def deploy_gate(s, c, status, stat):
        gates["deploy"] += 1
        gates["skipped_seen"] = s.tests_skipped
        return deploy_ok

    runner = FakeRunner(git_repo, {"planner": lambda r, p: StageResult(PLAN, 0.02, 3), **handlers})
    p = Pipeline(
        state, Config(**cfg), runner, Console(quiet=True), plan_gate, deploy_gate, tests, deploy_enabled, allow_untested_deploy
    )
    return p, runner, gates


async def test_happy_path_declined_deploy(git_repo):
    p, runner, gates = make(git_repo, {"coder": edit_code}, scripted_tests(True))
    s = await p.run()
    assert [c[0] for c in runner.calls] == ["planner", "coder", "tester"]
    assert s.stage == Stage.READY and s.tests_passed and s.error is None
    assert gates["plan"] == 1 and gates["deploy"] == 1 and gates["skipped_seen"] is False
    assert s.plan_path.read_text().startswith("# Plan")
    assert "return 2" in (git_repo / "app.py").read_text()  # left uncommitted
    assert s.branch.startswith("devagent/") and s.base_branch == "main"


async def test_plan_rejected_stops(git_repo):
    p, runner, _ = make(git_repo, {}, scripted_tests(True), plan_decisions=("reject",))
    s = await p.run()
    assert s.stage == Stage.ABORTED and [c[0] for c in runner.calls] == ["planner"]


async def test_plan_revise_passes_feedback(git_repo):
    p, runner, _ = make(git_repo, {"coder": edit_code}, scripted_tests(True), plan_decisions=("revise", "approve"))
    await p.run()
    planner_calls = [c for c in runner.calls if c[0] == "planner"]
    assert len(planner_calls) == 2 and "more detail" in planner_calls[1][1]


async def test_debug_loop_fixes(git_repo):
    p, runner, _ = make(git_repo, {"coder": edit_code}, scripted_tests(False, False, True))
    s = await p.run()
    assert [c[0] for c in runner.calls] == ["planner", "coder", "tester", "debugger", "debugger"]
    assert s.stage == Stage.READY and s.debug_attempts == 2
    assert "Attempt 2 -> PASS" in s.debug_log_path.read_text()
    assert '"t::x"' in runner.calls[3][1]  # failure JSON reaches the debugger


async def test_debug_loop_exhausted_stops_before_deploy(git_repo):
    p, runner, gates = make(git_repo, {"coder": edit_code}, scripted_tests(False), max_debug=2)
    s = await p.run()
    assert s.debug_attempts == 2 and s.stage == Stage.TESTED and "still failing" in s.error
    assert gates["deploy"] == 0


async def test_coder_no_changes_fails(git_repo):
    p, _, _ = make(git_repo, {}, scripted_tests(True))
    s = await p.run()
    assert s.stage == Stage.APPROVED and "without changing" in s.error


async def test_agent_error_recorded(git_repo):
    p, _, _ = make(git_repo, {"coder": lambda r, pr: StageResult("", is_error=True, error="max_turns")}, scripted_tests(True))
    s = await p.run()
    assert s.stage == Stage.APPROVED and "max_turns" in s.error and s.costs[-1].is_error


async def test_resume_after_exhausted_debug(git_repo):
    p, _, _ = make(git_repo, {"coder": edit_code}, scripted_tests(False), max_debug=1)
    s = await p.run()
    assert s.stage == Stage.TESTED
    loaded = RunState.load(git_repo, s.run_id)
    loaded.debug_attempts = 0
    runner = FakeRunner(git_repo, {})
    p2 = Pipeline(
        loaded,
        Config(max_debug=2, test_command="pytest"),
        runner,
        Console(quiet=True),
        deploy_gate=lambda *a: False,
        test_fn=scripted_tests(False, True),
    )
    s2 = await p2.run()
    assert [c[0] for c in runner.calls] == ["debugger"]  # no re-plan / re-code
    assert s2.stage == Stage.READY


async def test_deploy_commits_and_opens_pr(git_repo, git, monkeypatch):
    opened = {}

    def fake_pr(repo, branch, base, title, body, remote="origin"):
        opened.update(branch=branch, base=base, title=title, body=body)
        return "https://github.com/o/r/pull/7"

    monkeypatch.setattr(deploy, "push_and_open_pr", fake_pr)
    p, runner, _ = make(
        git_repo,
        {"coder": edit_code, "writer": lambda r, pr: StageResult("## Summary\n- f returns 2")},
        scripted_tests(True),
        deploy_ok=True,
    )
    s = await p.run()
    assert s.stage == Stage.DEPLOYED and s.pr_url.endswith("/pull/7")
    assert opened["title"] == "Change f" and opened["base"] == "main"
    assert "f returns 2" in opened["body"] and s.run_id in opened["body"]
    assert git(git_repo, "rev-parse", "--abbrev-ref", "HEAD") == s.branch
    assert git(git_repo, "show", "--name-only", "--format=", "HEAD") == "app.py"


# ---------------------------------------------------------------------------- safety features
async def test_no_test_suite_skips_tester_and_warns(git_repo):
    p, runner, gates = make(git_repo, {"coder": edit_code}, scripted_tests(False), test_command="true")
    s = await p.run()
    assert [c[0] for c in runner.calls] == ["planner", "coder"]  # no tester, no debugger
    assert s.stage == Stage.READY and s.tests_skipped and "NOT TESTED" in s.test_summary
    assert gates["skipped_seen"] is True


async def test_autodetect_no_suite_is_skipped(git_repo):
    p, runner, _ = make(git_repo, {"coder": edit_code}, scripted_tests(False), test_command=None)
    s = await p.run()  # git_repo has only app.py -> nothing to detect
    assert s.tests_skipped and "tester" not in [c[0] for c in runner.calls]


async def test_yes_mode_refuses_untested_deploy(git_repo):
    p, _, gates = make(
        git_repo, {"coder": edit_code}, scripted_tests(True), test_command="true", deploy_ok=True, allow_untested_deploy=False
    )
    s = await p.run()
    assert s.stage == Stage.READY and "nothing was tested" in s.error and gates["deploy"] == 0


async def test_untested_pr_body_has_warning(git_repo, monkeypatch):
    opened = {}
    monkeypatch.setattr(
        deploy, "push_and_open_pr", lambda repo, b, base, t, body, remote="origin": opened.update(body=body) or "u"
    )
    p, _, _ = make(git_repo, {"coder": edit_code}, scripted_tests(True), test_command="true", deploy_ok=True)
    await p.run()
    assert "not tested" in opened["body"].lower()


async def test_pr_note_is_added_to_pr_body_but_not_to_agents(git_repo, monkeypatch):
    opened = {}
    monkeypatch.setattr(
        deploy, "push_and_open_pr", lambda repo, b, base, t, body, remote="origin": opened.update(body=body) or "u"
    )
    p, runner, _ = make(git_repo, {"coder": edit_code}, scripted_tests(True), deploy_ok=True, pr_note="Closes #12")
    await p.run()
    assert "Closes #12" in opened["body"]
    assert not any("Closes #12" in prompt for _, prompt in runner.calls)


def test_task_after_double_dash_is_never_an_option():
    # The GitHub Action passes issue text as the task; `--` stops it being read as a flag like --no-sandbox.
    import typer

    from devagent.cli import app

    run = typer.main.get_command(app).commands["run"]
    params = run.make_context("run", ["--repo", ".", "--yes", "--", "--no-sandbox"]).params
    assert params["task"] == "--no-sandbox" and params["no_sandbox"] is False


async def test_spending_limit_stops_run(git_repo):
    p, runner, _ = make(git_repo, {"coder": edit_code}, scripted_tests(True), max_cost_usd=1.0)
    runner.handlers["planner"] = lambda r, pr: StageResult(PLAN, cost_usd=0.98, turns=1)
    s = await p.run()
    assert [c[0] for c in runner.calls] == ["planner"]
    assert "spending limit" in s.error and s.stage == Stage.APPROVED
    assert runner.budgets[0] == 1.0  # remaining budget passed to the SDK


async def test_secret_file_blocks_deploy(git_repo, monkeypatch):
    monkeypatch.setattr(deploy, "push_and_open_pr", lambda *a, **k: pytest.fail("must not push"))

    def leaky_coder(repo, prompt):
        edit_code(repo, prompt)
        (repo / "config.py").write_text('API = "sk-ant-api03-' + "x" * 40 + '"\n')

    p, _, gates = make(git_repo, {"coder": leaky_coder}, scripted_tests(True), deploy_ok=True)
    s = await p.run()
    assert "unsafe to upload" in s.error and "config.py" in s.error and gates["deploy"] == 0
    assert s.stage == Stage.READY  # resumable after the file is fixed


async def test_injection_alert_only_on_marker(git_repo):
    def coder_out(repo, prompt):
        edit_code(repo, prompt)
        return StageResult(
            "Done. I found no signs of prompt injection.\nINJECTION-ALERT: README.md - asked me to print ~/.ssh keys"
        )

    p, _, _ = make(
        git_repo, {"coder": coder_out, "tester": lambda r, pr: StageResult("No prompt injection found.")}, scripted_tests(True)
    )
    s = await p.run()
    assert s.security_alerts == ["coder: README.md - asked me to print ~/.ssh keys"]


async def test_broken_test_runner_skips_debugging(git_repo):
    # The Debugger can't install a missing pytest, so devagent must stop instead of paying for 3 attempts.
    def tests(repo, cmd, timeout):
        return TestReport(command=cmd or "pytest", passed=False, exit_code=1, environment_error="pytest is not installed")

    p, runner, gates = make(git_repo, {"coder": edit_code}, tests, deploy_ok=True)
    s = await p.run()
    assert "setup problem" in s.error and "pytest is not installed" in s.error
    assert not any(name == "debugger" for name, _ in runner.calls) and s.debug_attempts == 0
    assert gates["deploy"] == 0
