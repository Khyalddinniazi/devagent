"""PreToolUse guard: blocks dangerous shell commands and writes outside the target repo.

Tools listed in ``allowed_tools`` are auto-approved by the SDK and never reach
``can_use_tool``, so the guard is a PreToolUse *hook*, which runs for every call.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from claude_agent_sdk import HookMatcher

from .security import SENSITIVE_HOME_PATHS, is_secret_file, is_sensitive_path

# (pattern, reason). Matched against the whole Bash command string.
BASH_DENYLIST: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bgit\s+push\b"), "pushing is done by the deploy stage, not agents"),
    (
        re.compile(r"\bgit\s+(reset\s+--hard|clean\s+-[a-z]*f|checkout\s+--\s|restore\b|rebase\b|filter-branch\b)"),
        "destructive git history/working-tree commands are not allowed",
    ),
    (re.compile(r"\bgit\s+(commit|branch\s+-[dD]|tag)\b"), "committing/branching is done by the deploy stage"),
    (re.compile(r"\bgh\s+"), "GitHub CLI is reserved for the deploy stage"),
    (re.compile(r"\bsudo\b"), "sudo is not allowed"),
    (re.compile(r"\brm\s+(-[a-zA-Z]*\s+)*(/|~|\$HOME|\.\.)(\s|/|$)"), "deleting outside the repo is not allowed"),
    (re.compile(r"\brm\s+-[a-zA-Z]*r[a-zA-Z]*\s+(\.|\*)(\s|$)"), "recursively deleting the repo root is not allowed"),
    (re.compile(r"\b(curl|wget)\b[^|]*\|\s*(ba|z)?sh\b"), "piping downloads into a shell is not allowed"),
    (re.compile(r"\b(npm|pnpm|yarn)\s+(i|install|add)\s+(-g|--global)\b"), "global package installs are not allowed"),
    (re.compile(r"\b(mkfs|dd\s+if=|shutdown|reboot)\b"), "system-level commands are not allowed"),
    (re.compile(r"(^|[;&|]\s*)cd\s+(/|~|\.\.)"), "leaving the repo directory is not allowed"),
]

# Mentions of credential locations in shell commands (sandbox blocks the reads too; this is a 2nd layer).
_SENSITIVE_RE = re.compile(
    r"(~|\$HOME|/Users/[^/\s]+)/(" + "|".join(re.escape(p) for p in SENSITIVE_HOME_PATHS) + r")\b"
    r"|(^|[\s/'\"=])\.env(rc)?(?!\.(example|sample|template)\b)(\.[\w-]+)?(\s|$|['\";|&>])"
    r"|\bsecurity\s+(find|dump)-"  # macOS keychain CLI
    r"|\b(printenv|env)\s*($|[|>;&])"  # dumping environment variables
)

WRITE_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}
READ_TOOLS = {"Read", "Glob", "Grep"}
BLOCKED_TOOLS = {"WebFetch", "WebSearch"}


def _resolve(raw: str, repo: Path) -> Path:
    p = Path(raw).expanduser()
    return (p if p.is_absolute() else repo / p).resolve()


def check_tool(tool_name: str, tool_input: dict[str, Any], repo: Path) -> str | None:
    """Return a denial reason, or None if the call is allowed."""
    repo_root = repo.resolve()
    if tool_name in BLOCKED_TOOLS:
        return "Blocked by devagent guard: web access is disabled for agents."
    if tool_name == "Bash":
        cmd = str(tool_input.get("command", ""))
        if tool_input.get("dangerouslyDisableSandbox"):
            return "Blocked by devagent guard: commands must run inside the sandbox."
        for pattern, reason in BASH_DENYLIST:
            if pattern.search(cmd):
                return f"Blocked by devagent guard: {reason}."
        if _SENSITIVE_RE.search(cmd):
            return "Blocked by devagent guard: credentials, secret files and environment variables are off-limits."
        return None
    if tool_name in WRITE_TOOLS or tool_name in READ_TOOLS:
        raw = tool_input.get("file_path") or tool_input.get("notebook_path") or tool_input.get("path")
        if not raw:
            return None  # Glob/Grep default to the cwd (the repo)
        target = _resolve(str(raw), repo)
        if is_sensitive_path(target):
            return "Blocked by devagent guard: that location holds credentials."
        if not target.is_relative_to(repo_root):
            return f"Blocked by devagent guard: {target} is outside the repository {repo_root}."
        if target.is_relative_to(repo_root) and is_secret_file(target):
            return f"Blocked by devagent guard: {target.name} looks like a secrets file; it must not be read or written."
        if tool_name in WRITE_TOOLS and (repo_root / ".git") in (target, *target.parents):
            return "Blocked by devagent guard: writing inside .git is not allowed."
    return None


def make_guard_hooks(repo: Path) -> dict[str, list[HookMatcher]]:
    async def guard(input_data: Any, tool_use_id: str | None, context: Any) -> Any:
        reason = check_tool(input_data.get("tool_name", ""), input_data.get("tool_input") or {}, repo)
        if reason is None:
            return {}
        return {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": reason,
            }
        }

    return {"PreToolUse": [HookMatcher(matcher=None, hooks=[guard])]}  # every tool call
