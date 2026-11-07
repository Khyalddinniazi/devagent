"""Test detection/execution, usable directly by the pipeline and as an in-process SDK tool."""

from __future__ import annotations

import json
import re
import shlex
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from claude_agent_sdk import McpSdkServerConfig, create_sdk_mcp_server, tool

from ..security import (
    DEFAULT_TEST_IMAGE,
    docker_available,
    docker_image_exists,
    os_sandbox_available,
    pick_test_sandbox,
    scrubbed_env,
    wrap_in_docker,
    wrap_in_sandbox,
)

TOOL_SERVER_NAME = "devagent"
RUN_TESTS_TOOL = f"mcp__{TOOL_SERVER_NAME}__run_tests"
NO_OP_COMMANDS = {"true", ":", "/usr/bin/true", "exit 0"}
TAIL_CHARS = 6000


@dataclass
class Failure:
    test: str
    message: str = ""


@dataclass
class TestReport:
    __test__ = False  # not a pytest test class
    command: str
    passed: bool
    exit_code: int
    num_passed: int | None = None
    num_failed: int | None = None
    failures: list[Failure] = field(default_factory=list)
    raw_tail: str = ""
    skipped: bool = False  # no real test suite was run - nothing was verified
    sandboxed: bool = False
    sandbox_kind: str = "none"  # sandbox-exec | docker | none
    environment_error: str | None = None  # the test runner itself couldn't start (not a code problem)

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2)

    def summary(self) -> str:
        if self.skipped:
            return "NOT TESTED (no test suite found) - check the result yourself"
        if self.environment_error:
            return f"TEST RUNNER BROKEN ({self.environment_error}) via `{self.command}`"
        if self.passed:
            counts = f" ({self.num_passed} passed)" if self.num_passed is not None else ""
            return f"PASSED{counts} via `{self.command}`"
        names = ", ".join(f.test for f in self.failures[:5]) or "see output"
        return f"FAILED (exit {self.exit_code}, {self.num_failed or '?'} failed: {names}) via `{self.command}`"


def detect_test_command(repo: Path) -> str | None:
    if (
        (repo / "pyproject.toml").exists()
        or (repo / "pytest.ini").exists()
        or (repo / "setup.py").exists()
        or (repo / "tests").is_dir()
    ):
        venv_py = next((p for p in (repo / ".venv/bin/python", repo / "venv/bin/python") if p.exists()), None)
        py = str(venv_py) if venv_py else sys.executable
        return f"{shlex.quote(py)} -m pytest -q -rf"
    if (repo / "package.json").exists():
        try:
            if "test" in json.loads((repo / "package.json").read_text()).get("scripts", {}):
                return "npm test --silent"
        except json.JSONDecodeError:
            pass
    if (repo / "go.mod").exists():
        return "go test ./..."
    if (repo / "Cargo.toml").exists():
        return "cargo test"
    if (repo / "Makefile").exists() and re.search(r"^test:", (repo / "Makefile").read_text(), re.M):
        return "make test"
    return None


_PYTEST_FAILED = re.compile(r"^(?:FAILED|ERROR) (\S+)(?: - (.*))?$", re.M)
_PYTEST_COUNTS = re.compile(r"(\d+) (passed|failed|error|errors)\b")


def _environment_error(command: str, code: int, output: str) -> str | None:
    """Detect a test runner that can't start at all. Changing the code can't fix that, so don't debug it."""
    runner = re.search(r"-m\s+([\w.]+)", command)
    if runner and re.search(rf"No module named '?{re.escape(runner.group(1))}'?(\s|$)", output):
        return f"{runner.group(1)} is not installed"
    if code == 127 or "command not found" in output:
        return "test command not found"
    return None


def _parse(command: str, code: int, output: str) -> TestReport:
    report = TestReport(command=command, passed=code == 0, exit_code=code, raw_tail=output[-TAIL_CHARS:])
    report.environment_error = None if code == 0 else _environment_error(command, code, output)
    if "pytest" in command:
        counts: dict[str, int] = {}
        for n, kind in _PYTEST_COUNTS.findall(output):
            counts[kind.rstrip("s") if kind != "passed" else kind] = int(n)
        report.num_passed = counts.get("passed", 0)
        report.num_failed = counts.get("failed", 0) + counts.get("error", 0)
        report.failures = [Failure(t, (m or "").strip()) for t, m in _PYTEST_FAILED.findall(output)]
        if code == 5:  # pytest: no tests collected
            report.passed = False
            report.failures = [Failure("<collection>", "no tests were collected")]
    elif not report.passed:
        report.failures = [Failure("<suite>", "non-zero exit; see raw_tail")]
    return report


def skipped_report(command: str = "<none>") -> TestReport:
    return TestReport(command=command, passed=True, exit_code=0, skipped=True)


def _setup_error(command: str, message: str) -> TestReport:
    return TestReport(command=command, passed=False, exit_code=-1, environment_error=message)


def run_tests(
    repo: Path,
    command: str | None = None,
    timeout: int = 900,
    sandbox: bool | str = True,
    image: str = DEFAULT_TEST_IMAGE,
) -> TestReport:
    """Run the test suite. `sandbox`: True/"auto" picks the strongest available, or name one explicitly."""
    command = command or detect_test_command(repo)
    if not command or command.strip() in NO_OP_COMMANDS:
        return skipped_report(command or "<none>")
    kind = pick_test_sandbox(sandbox)
    if kind == "sandbox-exec":
        if not os_sandbox_available():
            return _setup_error(command, "sandbox-exec is only available on macOS")
        to_run = wrap_in_sandbox(command, repo)
    elif kind == "docker":
        if not docker_available():
            return _setup_error(command, "Docker is not installed or not running")
        if not docker_image_exists(image):
            return _setup_error(command, f"test image {image} not found; build it with `make docker-image`")
        to_run = wrap_in_docker(command, repo, image)
    else:
        to_run = command
    try:
        # Tests are code an agent may have written: they never see the host's tokens and keys.
        env = {**scrubbed_env(), "PYTHONDONTWRITEBYTECODE": "1"}
        proc = subprocess.run(to_run, shell=True, cwd=repo, capture_output=True, text=True, timeout=timeout, env=env)
    except subprocess.TimeoutExpired as e:
        out = (e.stdout or "") if isinstance(e.stdout, str) else ""
        return TestReport(
            command=command,
            passed=False,
            exit_code=-1,
            raw_tail=out[-TAIL_CHARS:],
            failures=[Failure("<timeout>", f"tests exceeded {timeout}s")],
        )
    report = _parse(command, proc.returncode, proc.stdout + "\n" + proc.stderr)
    report.sandboxed = kind != "none"
    report.sandbox_kind = kind
    return report


def build_tool_server(
    repo: Path, command: str | None, timeout: int, sandbox: bool | str = True, image: str = DEFAULT_TEST_IMAGE
) -> McpSdkServerConfig:
    @tool(
        "run_tests",
        "Run the project's test suite and return structured JSON: passed, counts, failures[{test,message}], "
        "raw_tail. Optionally pass `args` (e.g. a test file path or -k expression) to run a subset.",
        {"type": "object", "properties": {"args": {"type": "string", "description": "extra args appended to the test command"}}},
    )
    async def _run_tests(args: dict[str, Any]) -> dict[str, Any]:
        base = command or detect_test_command(repo)
        extra = (args or {}).get("args") or ""
        report = run_tests(repo, f"{base} {extra}".strip() if base else None, timeout, sandbox, image)
        return {"content": [{"type": "text", "text": report.to_json()}]}

    return create_sdk_mcp_server(TOOL_SERVER_NAME, tools=[_run_tests])
