"""The benchmark must be fair: checked in CI so a broken task or grader can't produce fake numbers."""

import pytest

from bench.run import HIDDEN_NAME, Result, grade, load_tasks, prepare, summarize, validate_task

TASKS = load_tasks()


def test_there_are_tasks():
    assert len(TASKS) >= 15
    assert {t.project for t in TASKS} == {"textkit", "shop"}


@pytest.mark.parametrize("task", TASKS, ids=[t.id for t in TASKS])
def test_task_is_fair(task, tmp_path):
    # starting tests pass, hidden tests fail before the change and pass with the reference solution
    assert validate_task(task, tmp_path) == []


def test_hidden_tests_are_not_left_in_the_repo(tmp_path):
    task = TASKS[0]
    repo = prepare(task, tmp_path / "r")
    grade(task, repo, sandbox=False)
    assert not (repo / "tests" / HIDDEN_NAME).exists()
    assert task.prompt and "hidden" not in task.prompt.lower()


def _r(task, solved, claimed, cost, debug=0):
    return Result(task, "feature", solved, claimed, "ready", cost, 60.0, debug, 10, "ok")


def test_summary_counts_false_success():
    results = [_r("a", True, True, 0.5), _r("b", False, True, 1.0, debug=2), _r("c", False, False, 1.5, debug=3)]
    md = summarize(results, {"date": "x", "model": "m", "max_cost": 2})
    assert "**1/3 (33%)**" in md
    assert "| Total cost | $3.00 |" in md
    assert "False success (devagent said pass, hidden tests failed) | 1 (b)" in md
    assert "Needed the debug loop | 2/3, solved after debugging: 0" in md
