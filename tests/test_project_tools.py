import shutil
import sys
from pathlib import Path

from devagent.tools.project_tools import _parse, detect_test_command, run_tests

SAMPLE = Path(__file__).parent.parent / "examples" / "sample_repo"


def test_detect(tmp_path):
    assert detect_test_command(tmp_path) is None
    (tmp_path / "package.json").write_text('{"scripts": {"test": "jest"}}')
    assert detect_test_command(tmp_path) == "npm test --silent"
    (tmp_path / "pyproject.toml").write_text("")
    assert "pytest" in detect_test_command(tmp_path)


def test_parse_pytest_failure():
    out = "FAILED tests/test_a.py::test_x - AssertionError: 1 != 2\n==== 1 failed, 3 passed in 0.1s ===="
    r = _parse("python -m pytest -q -rf", 1, out)
    assert not r.passed and r.num_failed == 1 and r.num_passed == 3
    assert r.failures[0].test == "tests/test_a.py::test_x"
    assert "AssertionError" in r.failures[0].message


def test_no_tests_collected_is_failure():
    assert not _parse("pytest", 5, "no tests ran").passed


def test_run_sample_repo(tmp_path):
    repo = tmp_path / "s"
    shutil.copytree(SAMPLE, repo)
    report = run_tests(repo, f"{sys.executable} -m pytest -q -rf")
    assert report.passed, report.raw_tail
    (repo / "tests" / "test_bad.py").write_text("def test_bad():\n    assert 1 == 2\n")
    report = run_tests(repo, f"{sys.executable} -m pytest -q -rf")
    assert not report.passed and report.failures[0].test.endswith("test_bad")
