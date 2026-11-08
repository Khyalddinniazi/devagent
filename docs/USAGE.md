# Using devagent

```bash
devagent run "add rate limiting to the /login endpoint" --repo ~/code/myapp
devagent run "..." --no-deploy          # stop when tests pass; leave changes uncommitted
devagent run "..." --yes                # skip both approval gates (CI)
devagent status --repo ~/code/myapp     # list runs
devagent resume <run-id> --repo ...     # continue from the last completed stage
```

| Option | Meaning |
|---|---|
| `--max-debug N` | Debugger attempts before giving up (default 3) |
| `--base BRANCH` · `--test-command CMD` · `--model ID` | Override detection and defaults |
| `--max-cost USD` | Spending limit for the whole run (default 5) |
| `--test-sandbox MODE` | Where tests run: `auto` (default: sandbox-exec on macOS, else Docker), `sandbox-exec`, `docker`, `none` |
| `--allow-network DOMAIN` | Let agents reach one domain, for example `pypi.org` (repeatable) |
| `--allow-untested` | With `--yes`, allow deploying when there's no test suite |
| `--trust-project` | Load the repo's own `.claude` settings |
| `--no-sandbox` | ⚠️ Turn off the sandboxes, for troubleshooting only |

If a project has no test suite (for example a plain HTML site), devagent detects that, skips the Tester
and labels the run **NOT TESTED** at the send prompt and in the PR.

Per-repo config goes in `.devagent.toml`:

```toml
test_command = "pytest -q -rf"
max_debug = 3
base_branch = "main"
max_cost_usd = 3.0
allowed_domains = ["pypi.org", "files.pythonhosted.org"]   # only if agents must install packages
[coder]
model = "claude-opus-5-5"
max_turns = 80
effort = "xhigh"
```

The artifacts of each run (plan, each agent's summary, test report, debug log, state) are saved in
`<repo>/.devagent/<run-id>/`. That folder is added to `.git/info/exclude`, so it's never committed.
