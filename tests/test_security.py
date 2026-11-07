import json
import subprocess
import sys
from pathlib import Path

import pytest

from devagent.security import (
    agent_permission_settings,
    agent_sandbox,
    is_secret_file,
    os_sandbox_available,
    scan_files,
    wrap_in_sandbox,
)
from devagent.tools.project_tools import run_tests

needs_sandbox = pytest.mark.skipif(not os_sandbox_available(), reason="macOS sandbox-exec not available")


def test_is_secret_file():
    for name in [".env", ".env.production", ".envrc", "server.pem", "id_rsa", "id_ed25519", "creds/credentials.json"]:
        assert is_secret_file(name), name
    for name in [".env.example", "id_rsa.pub", "environment.py", "app.js"]:
        assert not is_secret_file(name), name


def test_scan_files(tmp_path):
    (tmp_path / "ok.py").write_text("x = 1\n")
    (tmp_path / "aws.py").write_text("KEY = 'AKIA" + "A" * 16 + "'\n")
    (tmp_path / "gh.txt").write_text("token ghp_" + "a" * 36)
    (tmp_path / "k.txt").write_text("-----BEGIN " + "OPENSSH PRIVATE KEY-----\nabc")
    (tmp_path / ".env").write_text("A=1")
    (tmp_path / "big.bin").write_bytes(b"0" * (6 * 1024 * 1024))
    found = {f.path for f in scan_files(tmp_path, ["ok.py", "aws.py", "gh.txt", "k.txt", ".env", "big.bin", "missing"])}
    assert found == {"aws.py", "gh.txt", "k.txt", ".env", "big.bin"}


def test_agent_settings_shape():
    sb = agent_sandbox([])
    assert sb["enabled"] and sb["allowUnsandboxedCommands"] is False and sb["network"]["allowedDomains"] == []
    deny = json.loads(agent_permission_settings())["permissions"]["deny"]
    assert "Read(~/.ssh/**)" in deny and "Read(**/.env)" in deny and "WebFetch" in deny


def test_noop_test_command_is_skipped(tmp_path):
    r = run_tests(tmp_path, "true")
    assert r.skipped and r.passed
    r = run_tests(tmp_path, None)  # nothing detectable
    assert r.skipped


def _sb(cmd: str, repo: Path) -> subprocess.CompletedProcess:
    return subprocess.run(wrap_in_sandbox(cmd, repo), shell=True, cwd=repo, capture_output=True, text=True, timeout=30)


@needs_sandbox
def test_sandbox_blocks_network_and_outside_writes(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    assert _sb("echo hi > inside.txt", repo).returncode == 0 and (repo / "inside.txt").exists()
    outside = Path.home() / ".devagent_sandbox_probe"
    assert _sb(f"echo x > {outside}", repo).returncode != 0 and not outside.exists()
    assert _sb("curl -sS -m 5 https://example.com -o /dev/null", repo).returncode != 0
    gh_dir = Path.home() / ".config/gh"
    if gh_dir.exists():
        assert _sb(f"ls {gh_dir}", repo).returncode != 0


@needs_sandbox
def test_sandbox_allows_localhost(tmp_path):
    # Plain sockets on purpose: http.server.HTTPServer does a DNS lookup (getfqdn) at startup, which
    # hangs inside the no-network sandbox on some machines (seen on GitHub's macOS runners).
    script = tmp_path / "srv.py"
    script.write_text(
        "import socket, threading\n"
        "srv = socket.socket(); srv.bind(('127.0.0.1', 0)); srv.listen(1)\n"
        "def serve():\n"
        "    conn, _ = srv.accept(); conn.sendall(b'ok'); conn.close()\n"
        "threading.Thread(target=serve, daemon=True).start()\n"
        "c = socket.create_connection(('127.0.0.1', srv.getsockname()[1]), timeout=5)\n"
        "print(c.recv(2).decode())\n"
    )
    r = _sb(f"{sys.executable} {script}", tmp_path)
    assert r.stdout.strip() == "ok", r.stderr


@needs_sandbox
def test_run_tests_is_sandboxed(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_net.py").write_text(
        "import urllib.request\ndef test_net():\n    urllib.request.urlopen('https://example.com', timeout=5)\n"
    )
    r = run_tests(tmp_path, f"{sys.executable} -m pytest -q -rf -p no:cacheprovider")
    assert r.sandboxed and not r.passed
