from devagent import deploy


def test_preflight_clean_and_dirty(git_repo, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    assert deploy.preflight(git_repo, need_gh=False) == []
    assert "/.devagent/" in (git_repo / ".git" / "info" / "exclude").read_text()
    (git_repo / "new.py").write_text("x = 1\n")
    assert any("not clean" in p for p in deploy.preflight(git_repo, need_gh=False))
    assert deploy.preflight(git_repo, allow_dirty=True, need_gh=False) == []


def test_preflight_not_repo(tmp_path):
    assert "not a git repository" in deploy.preflight(tmp_path, need_gh=False)[0]


def test_commit_branch_excludes_state_dir(git_repo, git, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    deploy.preflight(git_repo, need_gh=False)
    (git_repo / ".devagent" / "run1").mkdir(parents=True)
    (git_repo / ".devagent" / "run1" / "state.json").write_text("{}")
    (git_repo / "app.py").write_text("def f():\n    return 2\n")
    (git_repo / "new.py").write_text("y = 1\n")
    status, stat = deploy.change_summary(git_repo)
    assert "new.py" in stat and "app.py" in stat and ".devagent" not in status
    deploy.commit_branch(git_repo, "devagent/run1", "feat: thing")
    assert git(git_repo, "rev-parse", "--abbrev-ref", "HEAD") == "devagent/run1"
    files = git(git_repo, "show", "--name-only", "--format=", "HEAD").split()
    assert sorted(files) == ["app.py", "new.py"]
    assert not deploy.has_changes(git_repo)


def test_push_and_pr_uses_gh(git_repo, monkeypatch):
    calls = []
    monkeypatch.setattr(deploy, "git", lambda repo, *a, check=True: calls.append(("git", a)) or "")
    monkeypatch.setattr(deploy, "gh", lambda repo, *a: calls.append(("gh", a)) or "https://github.com/o/r/pull/1")
    url = deploy.push_and_open_pr(git_repo, "devagent/x", "main", "T", "B")
    assert url.endswith("/pull/1")
    assert calls[0] == ("git", ("push", "-u", "origin", "devagent/x"))
    assert calls[1][1][:2] == ("pr", "create") and "--base" in calls[1][1]
