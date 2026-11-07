"""Git / GitHub operations. Plain code, never driven by the model."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from .state import STATE_DIR


class DeployError(RuntimeError):
    pass


def git(repo: Path, *args: str, check: bool = True) -> str:
    proc = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True)
    if check and proc.returncode != 0:
        raise DeployError(f"git {' '.join(args)} failed: {proc.stderr.strip() or proc.stdout.strip()}")
    return proc.stdout.strip()


def gh(repo: Path, *args: str) -> str:
    proc = subprocess.run(["gh", *args], cwd=repo, capture_output=True, text=True)
    if proc.returncode != 0:
        raise DeployError(f"gh {' '.join(args)} failed: {proc.stderr.strip() or proc.stdout.strip()}")
    return proc.stdout.strip()


def exclude_state_dir(repo: Path) -> None:
    """Keep .devagent/ out of commits without touching the repo's tracked .gitignore."""
    exclude = Path(git(repo, "rev-parse", "--git-path", "info/exclude"))
    exclude = exclude if exclude.is_absolute() else repo / exclude
    exclude.parent.mkdir(parents=True, exist_ok=True)
    lines = exclude.read_text().splitlines() if exclude.exists() else []
    if f"/{STATE_DIR}/" not in lines:
        exclude.write_text("\n".join([*lines, f"/{STATE_DIR}/"]) + "\n")


def preflight(repo: Path, allow_dirty: bool = False, need_gh: bool = True) -> list[str]:
    """Return a list of problems (empty = ready)."""
    problems: list[str] = []
    if shutil.which("git") is None:
        return ["git is not installed"]
    if git(repo, "rev-parse", "--is-inside-work-tree", check=False) != "true":
        return [f"{repo} is not a git repository"]
    if not git(repo, "rev-parse", "--verify", "HEAD", check=False):
        problems.append("repository has no commits yet")
    exclude_state_dir(repo)
    if not allow_dirty and git(repo, "status", "--porcelain"):
        problems.append("working tree is not clean (commit/stash first, or pass --allow-dirty)")
    if need_gh:
        if shutil.which("gh") is None:
            problems.append("GitHub CLI `gh` is not installed (needed for deploy; or pass --no-deploy)")
        elif subprocess.run(["gh", "auth", "status"], cwd=repo, capture_output=True).returncode != 0:
            problems.append("`gh` is not authenticated - run `gh auth login`")
    if not (
        os.environ.get("ANTHROPIC_API_KEY")
        or os.environ.get("ANTHROPIC_AUTH_TOKEN")
        or os.environ.get("CLAUDE_CODE_OAUTH_TOKEN")
        or (Path.home() / ".claude").is_dir()
    ):
        # The SDK's bundled CLI also reuses an existing Claude Code login (~/.claude / keychain).
        problems.append("no Anthropic credentials found (set ANTHROPIC_API_KEY or log in to Claude Code)")
    return problems


def current_branch(repo: Path) -> str:
    return git(repo, "rev-parse", "--abbrev-ref", "HEAD")


def change_summary(repo: Path) -> tuple[str, str]:
    """(status --short, diff --stat vs HEAD including untracked files)."""
    status = git(repo, "status", "--short")
    git(repo, "add", "-A", "--intent-to-add")
    stat = git(repo, "diff", "--stat", "HEAD")
    return status, stat


def changed_files(repo: Path) -> list[str]:
    """Added/modified files (incl. untracked, minus ignored) that a commit would include."""
    git(repo, "add", "-A", "--intent-to-add")
    out = git(repo, "diff", "--name-only", "--diff-filter=d", "HEAD")
    return [line for line in out.splitlines() if line.strip()]


def has_changes(repo: Path) -> bool:
    return bool(git(repo, "status", "--porcelain"))


def commit_branch(repo: Path, branch: str, message: str) -> str:
    """Create/switch to `branch`, commit all changes. Returns commit sha."""
    existing = git(repo, "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}", check=False)
    if current_branch(repo) != branch:
        git(repo, "checkout", *(["-b"] if not existing else []), branch)
    git(repo, "add", "-A")
    git(repo, "commit", "-m", message)
    return git(repo, "rev-parse", "HEAD")


def push_and_open_pr(repo: Path, branch: str, base: str, title: str, body: str, remote: str = "origin") -> str:
    git(repo, "push", "-u", remote, branch)
    return gh(repo, "pr", "create", "--base", base, "--head", branch, "--title", title, "--body", body)
