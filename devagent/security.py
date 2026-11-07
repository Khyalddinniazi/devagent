"""Security layer: OS sandboxing, sensitive-path rules and secret scanning.

Defense in depth, one layer per risk:
  1. Agent Bash runs inside the Claude Code sandbox (filesystem + network isolation, no escape hatch).
  2. Test commands run inside macOS `sandbox-exec` (no network, writes only to repo/tmp/caches).
  3. Sensitive files (SSH keys, cloud creds, .env ...) are unreadable by agent tools and sandboxed Bash,
     so they are never sent to the model.
  4. Before anything is committed, changed files are scanned for secrets and oversized files.
"""

from __future__ import annotations

import fnmatch
import functools
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

HOME = Path.home()

# Home-relative paths holding credentials. Agents may never read these.
SENSITIVE_HOME_PATHS = [
    ".ssh",
    ".aws",
    ".gnupg",
    ".kube",
    ".docker",
    ".azure",
    ".config/gcloud",
    ".config/gh",
    ".config/anthropic",
    ".claude",
    ".netrc",
    ".git-credentials",
    ".npmrc",
    ".pypirc",
    "Library/Keychains",
    "Library/Cookies",
]

# Secret-looking files inside the repo: never readable by agents, never committed.
SECRET_FILE_GLOBS = [
    ".env",
    ".env.*",
    ".envrc",
    "*.pem",
    "*.key",
    "*.p12",
    "*.pfx",
    "*.keystore",
    "*.jks",
    "id_rsa*",
    "id_dsa*",
    "id_ecdsa*",
    "id_ed25519*",
    ".npmrc",
    ".pypirc",
    ".netrc",
    "credentials.json",
    "service-account*.json",
    "*.tfstate",
    "*.tfvars",
]
SAFE_FILE_GLOBS = [".env.example", ".env.sample", ".env.template", "*.pub"]

SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("private key", re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP |ENCRYPTED )?PRIVATE KEY-----")),
    ("AWS access key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("GitHub token", re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{60,})\b")),
    ("Anthropic API key", re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{20,}")),
    ("OpenAI API key", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9]{32,}\b")),
    ("Slack token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}")),
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b")),
    ("Stripe live key", re.compile(r"\b[sr]k_live_[0-9a-zA-Z]{20,}")),
]

MAX_FILE_BYTES = 5 * 1024 * 1024


def is_secret_file(path: str | Path) -> bool:
    name = Path(path).name
    if any(fnmatch.fnmatch(name, g) for g in SAFE_FILE_GLOBS):
        return False
    return any(fnmatch.fnmatch(name, g) for g in SECRET_FILE_GLOBS)


def is_sensitive_path(path: Path) -> bool:
    p = path.expanduser().resolve()
    return any(p == (HOME / s) or (HOME / s) in p.parents for s in SENSITIVE_HOME_PATHS)


# --------------------------------------------------------------------------- agent sandbox (Claude Code)
def agent_sandbox(allowed_domains: list[str]) -> dict:
    """SandboxSettings for agent Bash: OS-level isolation that the model cannot switch off."""
    return {
        "enabled": True,
        "autoAllowBashIfSandboxed": True,
        "allowUnsandboxedCommands": False,  # no dangerouslyDisableSandbox escape hatch
        "excludedCommands": [],
        "network": {"allowedDomains": list(allowed_domains), "allowLocalBinding": True},
    }


def agent_permission_settings() -> str:
    """Settings JSON with Read deny rules; these also restrict what sandboxed Bash can read."""
    deny = [f"Read(~/{p}/**)" for p in SENSITIVE_HOME_PATHS] + [f"Read(~/{p})" for p in SENSITIVE_HOME_PATHS]
    deny += [f"Read(**/{g})" for g in SECRET_FILE_GLOBS]
    deny += ["WebFetch", "WebSearch"]
    return json.dumps({"permissions": {"deny": deny}})


# --------------------------------------------------------------------------- test sandbox (macOS sandbox-exec)
def _sb_str(p: Path | str) -> str:
    return json.dumps(str(p))  # sandbox profile strings use the same escaping as JSON


def sandbox_profile(repo: Path) -> str:
    repo = repo.resolve()
    writable = [
        repo,
        Path("/private/tmp"),
        Path("/private/var/folders"),
        Path("/dev"),
        HOME / "Library/Caches",
        HOME / ".cache",
        HOME / ".npm",
    ]
    unreadable = [(HOME / p).resolve() for p in SENSITIVE_HOME_PATHS]
    lines = [
        "(version 1)",
        "(allow default)",
        "(deny network*)",
        # Localhost only. NB: `(allow network* (local ip "localhost:*"))` would also match outbound
        # internet connections, so bind/inbound/outbound are scoped separately.
        '(allow network-bind (local ip "localhost:*"))',
        '(allow network-inbound (local ip "localhost:*"))',
        '(allow network-outbound (remote ip "localhost:*"))',
        "(allow network* (remote unix-socket))",
        "(deny file-write*)",
        "(allow file-write* " + " ".join(f"(subpath {_sb_str(p)})" for p in writable) + ")",
        "(deny file-read* " + " ".join(f"(subpath {_sb_str(p)})" for p in unreadable) + ")",
    ]
    return "\n".join(lines)


def os_sandbox_available() -> bool:
    return sys.platform == "darwin" and shutil.which("sandbox-exec") is not None


def wrap_in_sandbox(command: str, repo: Path) -> str:
    """Return `command` wrapped so it runs with no network and writes confined to the repo."""
    return f"sandbox-exec -p {shlex.quote(sandbox_profile(repo))} /bin/sh -c {shlex.quote(command)}"


# --------------------------------------------------------------------------- test sandbox (Docker, any OS)
TEST_SANDBOXES = ("auto", "sandbox-exec", "docker", "none")
DEFAULT_TEST_IMAGE = "devagent-tests:latest"  # built from docker/tests.Dockerfile (`make docker-image`)


@functools.cache
def docker_available() -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        return subprocess.run(["docker", "info"], capture_output=True, timeout=20).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def docker_image_exists(image: str) -> bool:
    return subprocess.run(["docker", "image", "inspect", image], capture_output=True).returncode == 0


def pick_test_sandbox(mode: str | bool) -> str:
    """Resolve "auto" to the strongest sandbox this machine has: sandbox-exec (macOS), then Docker."""
    if mode is False or mode == "none":
        return "none"
    if mode is True or mode == "auto":
        if os_sandbox_available():
            return "sandbox-exec"
        return "docker" if docker_available() else "none"
    if mode not in TEST_SANDBOXES:
        raise ValueError(f"unknown test sandbox {mode!r}; choose one of {', '.join(TEST_SANDBOXES)}")
    return mode


def wrap_in_docker(command: str, repo: Path, image: str = DEFAULT_TEST_IMAGE) -> str:
    """Run `command` in a throwaway container that can see nothing but the repo.

    No network, a read-only filesystem except the repo and /tmp, no Linux capabilities, no privilege
    escalation, and none of the host's environment variables, home folder or credentials.
    """
    uid, gid = (os.getuid(), os.getgid()) if hasattr(os, "getuid") else (1000, 1000)
    # A Python path from the host (venv or sys.executable) doesn't exist in the container.
    command = re.sub(r"^\S*python[\d.]*(?=\s+-m\s)", "python", command)
    args = [
        "docker", "run", "--rm",
        "--network", "none",
        "--read-only", "--tmpfs", "/tmp:rw,exec,size=512m",  # noqa: S108 - private tmpfs inside the container
        "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
        "--pids-limit", "512", "--memory", "2g",
        "--user", f"{uid}:{gid}",
        "-e", "HOME=/tmp", "-e", "PYTHONDONTWRITEBYTECODE=1",
        "-v", f"{repo.resolve()}:/work", "-w", "/work",
        image, "sh", "-c", command,
    ]  # fmt: skip
    return shlex.join(args)


_SECRET_ENV = re.compile(r"(TOKEN|SECRET|PASSWORD|PASSWD|API_?KEY|ACCESS_KEY|PRIVATE_KEY|CREDENTIAL)", re.I)


def scrubbed_env() -> dict[str, str]:
    """The current environment without anything that looks like a secret, for running untrusted tests."""
    return {k: v for k, v in os.environ.items() if not _SECRET_ENV.search(k)}


# --------------------------------------------------------------------------- secret scanning before commit
@dataclass
class Finding:
    path: str
    reason: str


def scan_files(repo: Path, paths: list[str]) -> list[Finding]:
    findings: list[Finding] = []
    for rel in paths:
        f = repo / rel
        if not f.is_file():
            continue
        if is_secret_file(rel):
            findings.append(Finding(rel, "file type usually holds secrets"))
            continue
        size = f.stat().st_size
        if size > MAX_FILE_BYTES:
            findings.append(Finding(rel, f"large file ({size // 1024 // 1024} MB)"))
            continue
        try:
            text = f.read_text(errors="ignore")
        except OSError:
            continue
        for label, pattern in SECRET_PATTERNS:
            if pattern.search(text):
                findings.append(Finding(rel, f"looks like it contains a {label}"))
                break
    return findings
