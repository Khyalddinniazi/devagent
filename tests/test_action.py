"""The GitHub Action's run script, executed for real with a fake devagent and hostile issue text."""

import os
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
FAKE_DEVAGENT = """#!/bin/bash
printf '%s\\0' "$@" > "$RUNNER_TEMP/argv"
mkdir -p .devagent/r1
echo '{"stage":"deployed","pr_url":"https://github.com/o/r/pull/7","costs":[{"cost_usd":0.4123},{"cost_usd":0.1}]}' \\
  > .devagent/r1/state.json
exit ${FAKE_EXIT:-0}
"""
EVIL_TASK = 'Fix login --no-sandbox\n\n$(touch PWNED) `touch PWNED2` "; touch PWNED3; echo "\n--trust-project'

pytestmark = pytest.mark.skipif(not (shutil.which("bash") and shutil.which("jq")), reason="needs bash and jq")


def run_step(tmp_path: Path, task: str, **env_overrides: str) -> tuple[subprocess.CompletedProcess, list[str], Path]:
    action = yaml.safe_load((ROOT / "action.yml").read_text())
    script = next(s for s in action["runs"]["steps"] if s.get("id") == "run")["run"]
    runner = tmp_path / "runner"
    (runner / "devagent-venv" / "bin").mkdir(parents=True)
    fake = runner / "devagent-venv" / "bin" / "devagent"
    fake.write_text(FAKE_DEVAGENT)
    fake.chmod(0o755)
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    out = tmp_path / "out.txt"
    env = {
        **os.environ,
        "RUNNER_TEMP": str(runner),
        "GITHUB_OUTPUT": str(out),
        "TASK": task,
        "MAX_COST": "3",
        "MODEL": "",
        "PR_NOTE": "Closes #12",
        "ALLOW_UNTESTED": "false",
        "ANTHROPIC_API_KEY": "",
        "CLAUDE_CODE_OAUTH_TOKEN": "",
        "GH_TOKEN": "x",
        **env_overrides,
    }
    # GitHub runs composite `shell: bash` steps exactly like this
    r = subprocess.run(["bash", "--noprofile", "--norc", "-eo", "pipefail", "-c", script], cwd=repo, env=env, text=True)
    argv = (runner / "argv").read_text().split("\0")[:-1]
    return r, argv, repo


def test_issue_text_cannot_inject_commands_or_flags(tmp_path):
    r, argv, repo = run_step(tmp_path, EVIL_TASK)
    assert r.returncode == 0
    assert not list(repo.glob("PWNED*"))  # no shell injection
    assert argv[-2:] == ["--", EVIL_TASK]  # whole text arrives as the task, after `--`
    assert "--no-sandbox" not in argv[:-1] and "--trust-project" not in argv[:-1]
    assert argv[argv.index("--pr-note") : argv.index("--pr-note") + 2] == ["--pr-note", "Closes #12"]


def test_outputs_and_exit_code(tmp_path):
    r, _, _ = run_step(tmp_path, "add a thing", FAKE_EXIT="1")
    assert r.returncode == 1  # a failed run fails the job
    out = (tmp_path / "out.txt").read_text().split()
    assert out == ["pr-url=https://github.com/o/r/pull/7", "stage=deployed", "cost=0.51"]


def test_example_workflow_is_locked_down():
    wf = yaml.safe_load((ROOT / "examples/workflows/devagent.yml").read_text())
    job = wf["jobs"]["devagent"]
    assert wf[True] == {"issues": {"types": ["labeled"]}}  # `on:` parses as True in YAML 1.1
    assert job["if"] == "github.event.label.name == 'devagent'"
    assert "write access" in job["steps"][0]["name"]  # permission check runs first
    assert set(wf["permissions"]) == {"contents", "pull-requests", "issues"}
    for step in job["steps"]:  # issue text must never be interpolated into a shell script
        assert "github.event.issue" not in step.get("run", "")
