"""devagent benchmark: run real tasks, grade them with hidden tests, record cost and time.

    python -m bench.run validate                 # free: check every task is fair (no API calls)
    python -m bench.run run [--tasks 01,08]      # real runs (costs money), writes bench/results/
    python -m bench.run report bench/results/X.json

Each task gives devagent one sentence. devagent never sees ``hidden_test.py``: it is copied in only
after the run, and the task counts as solved only if the hidden tests AND the project's own tests pass.
"""

from __future__ import annotations

import argparse
import json
import shutil
import statistics
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

import tomllib

from devagent.config import Config
from devagent.tools.project_tools import run_tests

BENCH = Path(__file__).resolve().parent
PYTEST = f"{sys.executable} -m pytest -q -rf -p no:cacheprovider"
HIDDEN_NAME = "test_zz_hidden_bench.py"
DEVAGENT = Path(sys.executable).parent / "devagent"


@dataclass
class Task:
    id: str
    project: str
    category: str
    prompt: str
    dir: Path


@dataclass
class Result:
    task: str
    category: str
    solved: bool  # hidden tests + the project's own tests pass
    claimed_pass: bool | None  # what devagent's own test run said
    stage: str | None
    cost_usd: float
    duration_s: float
    debug_attempts: int
    turns: int
    hidden: str  # summary of the hidden-test run
    error: str | None = None


def load_tasks(ids: list[str] | None = None) -> list[Task]:
    tasks = []
    for tdir in sorted((BENCH / "tasks").iterdir()):
        if not (tdir / "task.toml").exists():
            continue
        if ids and not any(tdir.name.startswith(i) for i in ids):
            continue
        meta = tomllib.loads((tdir / "task.toml").read_text())
        tasks.append(Task(tdir.name, meta["project"], meta["category"], meta["prompt"], tdir))
    return tasks


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)


def prepare(task: Task, dest: Path, with_solution: bool = False) -> Path:
    """Copy the task's project to ``dest`` as a fresh git repo (optionally with the reference solution)."""
    shutil.rmtree(dest, ignore_errors=True)
    shutil.copytree(BENCH / "projects" / task.project, dest)
    if with_solution:
        shutil.copytree(task.dir / "solution", dest, dirs_exist_ok=True)
    _git(dest, "init", "-q", "-b", "main")
    _git(dest, "add", "-A")
    _git(dest, "-c", "user.name=bench", "-c", "user.email=bench@example.com", "commit", "-qm", "start")
    return dest


def grade(task: Task, repo: Path, sandbox: bool = True):
    """Add the hidden tests and run the whole suite. Agent-written code runs sandboxed."""
    shutil.copy(task.dir / "hidden_test.py", repo / "tests" / HIDDEN_NAME)
    try:
        return run_tests(repo, PYTEST, timeout=300, sandbox=sandbox)
    finally:
        (repo / "tests" / HIDDEN_NAME).unlink(missing_ok=True)


# --------------------------------------------------------------------------------------------- validate
def validate_task(task: Task, work: Path) -> list[str]:
    """A fair task: the project's tests pass, the hidden tests fail before the change, pass after."""
    problems = []
    before = prepare(task, work / f"{task.id}-before")
    if not run_tests(before, PYTEST, sandbox=False).passed:
        problems.append("the starting project's own tests fail")
    if grade(task, before, sandbox=False).passed:
        problems.append("hidden tests already pass before any change (task is trivial)")
    after = prepare(task, work / f"{task.id}-solution", with_solution=True)
    report = grade(task, after, sandbox=False)
    if not report.passed:
        problems.append(f"reference solution fails the hidden tests: {report.summary()}\n{report.raw_tail}")
    return problems


# --------------------------------------------------------------------------------------------- run
def run_task(task: Task, work: Path, max_cost: float, model: str | None, timeout: int) -> Result:
    repo = prepare(task, work / task.id)
    cmd = [str(DEVAGENT), "run", task.prompt, "--repo", str(repo), "--yes", "--no-deploy", "--max-cost", str(max_cost)]
    if model:
        cmd += ["--model", model]
    start = time.monotonic()
    error = None
    with open(work / f"{task.id}.log", "w") as log:
        try:
            proc = subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, timeout=timeout)
            if proc.returncode != 0:
                error = f"devagent exited with {proc.returncode}"
        except subprocess.TimeoutExpired:
            error = f"timed out after {timeout}s"
    duration = time.monotonic() - start

    state = {}
    states = sorted((repo / ".devagent").glob("*/state.json"))
    if states:
        state = json.loads(states[-1].read_text())
        error = state.get("error") or error
    report = grade(task, repo)
    costs = state.get("costs", [])
    return Result(
        task=task.id,
        category=task.category,
        solved=report.passed and not report.skipped,
        claimed_pass=state.get("tests_passed"),
        stage=state.get("stage"),
        cost_usd=round(sum(c.get("cost_usd", 0) for c in costs), 4),
        duration_s=round(duration, 1),
        debug_attempts=state.get("debug_attempts", 0),
        turns=sum(c.get("turns", 0) for c in costs),
        hidden=report.summary(),
        error=error,
    )


# --------------------------------------------------------------------------------------------- report
def summarize(results: list[Result], meta: dict) -> str:
    n = len(results)
    solved = sum(r.solved for r in results)
    costs = [r.cost_usd for r in results]
    times = [r.duration_s for r in results]
    false_claims = [r.task for r in results if r.claimed_pass and not r.solved]
    debugged = [r for r in results if r.debug_attempts > 0]
    lines = [
        f"# devagent benchmark: {meta['date']}",
        "",
        f"Model: `{meta['model']}` · tasks: {n} · spending limit per task: ${meta['max_cost']}",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| **Solved (hidden tests pass)** | **{solved}/{n} ({solved / n:.0%})** |",
        f"| Total cost | ${sum(costs):.2f} |",
        f"| Cost per task (median / max) | ${statistics.median(costs):.2f} / ${max(costs):.2f} |",
        f"| Time per task (median / max) | {statistics.median(times) / 60:.1f} / {max(times) / 60:.1f} min |",
        f"| Needed the debug loop | {len(debugged)}/{n}, solved after debugging: {sum(r.solved for r in debugged)} |",
        f"| False success (devagent said pass, hidden tests failed) | {len(false_claims)}"
        + (f" ({', '.join(false_claims)})" if false_claims else "")
        + " |",
        "",
        "| Task | Type | Solved | devagent's tests | Debug | Cost | Time | Hidden tests |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in results:
        claimed = {True: "pass", False: "fail", None: "–"}[r.claimed_pass]
        lines.append(
            f"| {r.task} | {r.category} | {'✅' if r.solved else '❌'} | {claimed} | {r.debug_attempts} "
            f"| ${r.cost_usd:.2f} | {r.duration_s / 60:.1f}m | {r.hidden}"
            + (f" — {r.error}" if r.error and not r.solved else "")
            + " |"
        )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m bench.run")
    sub = ap.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("validate", help="check every task is fair (no API calls)")
    v.add_argument("--tasks", help="comma-separated task id prefixes")
    r = sub.add_parser("run", help="run devagent on the tasks (costs money)")
    r.add_argument("--tasks", help="comma-separated task id prefixes, e.g. 01,08")
    r.add_argument("--max-cost", type=float, default=2.0, help="spending limit per task in USD (default 2)")
    r.add_argument("--model", help="model for every stage (default: devagent's default)")
    r.add_argument("--timeout", type=int, default=1800, help="seconds per task (default 1800)")
    p = sub.add_parser("report", help="print the summary of a results file")
    p.add_argument("file", type=Path)
    args = ap.parse_args(argv)

    if args.cmd == "report":
        data = json.loads(args.file.read_text())
        print(summarize([Result(**r) for r in data["results"]], data["meta"]))
        return 0

    tasks = load_tasks(args.tasks.split(",") if args.tasks else None)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    work = BENCH / ".work" / stamp
    work.mkdir(parents=True)

    if args.cmd == "validate":
        bad = 0
        for t in tasks:
            problems = validate_task(t, work)
            bad += bool(problems)
            print(("✅ " if not problems else "❌ ") + t.id + "".join(f"\n   - {p}" for p in problems))
        shutil.rmtree(work)
        print(f"\n{len(tasks) - bad}/{len(tasks)} tasks are valid")
        return 1 if bad else 0

    meta = {"date": stamp, "model": args.model or Config().coder.model, "max_cost": args.max_cost, "tasks": len(tasks)}
    results: list[Result] = []
    out = BENCH / "results" / f"{stamp}.json"
    out.parent.mkdir(exist_ok=True)
    for i, t in enumerate(tasks, 1):
        print(f"[{i}/{len(tasks)}] {t.id} ...", flush=True)
        res = run_task(t, work, args.max_cost, args.model, args.timeout)
        results.append(res)
        print(f"      {'✅ solved' if res.solved else '❌ not solved'} · ${res.cost_usd:.2f} · {res.duration_s / 60:.1f} min")
        out.write_text(json.dumps({"meta": meta, "results": [asdict(x) for x in results]}, indent=2))  # save as we go
    summary = summarize(results, meta)
    out.with_suffix(".md").write_text(summary)
    print("\n" + summary + f"\nSaved {out} and {out.with_suffix('.md')}. Agent work dirs and logs: {work}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
