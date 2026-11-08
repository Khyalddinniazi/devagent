# devagent architecture

## Design decisions

| Decision | Why |
|---|---|
| **The stage order is a state machine in Python, not chosen by an LLM** | Runs are predictable, can be resumed after a crash (`devagent resume`), and are easy to test |
| **One agent per role, each with a fresh context** | Agents pass work through files (`plan.md`, test reports) instead of one huge conversation, so each one stays focused and has only the tools it needs (least privilege) |
| **"Tests pass" is decided by running them, not by asking the model** | Models sometimes say "all tests pass" when they don't. The pipeline re-runs the suite itself and parses the result |
| **Separate Tester and Debugger with anti-cheating rules** | The agent that writes the tests isn't the one trying to make them pass, so tests aren't quietly weakened ("reward hacking") |
| **Deploy is plain code behind a human gate** | Pushing to GitHub is outward-facing and can't be undone, so no model decides when it happens |
| **Defence in depth** | Prompt rules → a guard hook on every tool call → an OS sandbox → a secret scan → human gates. Each layer covers the weakness of another |
| **Dependency injection** | The agent runner, approval gates and test runner are passed in, so the whole pipeline is tested with a scripted fake runner and no API calls |

## Project layout

| Path | Role |
|---|---|
| [devagent/pipeline.py](../devagent/pipeline.py) | State machine, approval gates, debug loop, budget, deploy checks |
| [devagent/runner.py](../devagent/runner.py) | Claude Agent SDK wrapper: per-agent options, sandbox, hooks, live tool output, cost |
| [devagent/agents/](../devagent/agents/) | One system prompt, tool set and prompt builder per agent |
| [devagent/tools/project_tools.py](../devagent/tools/project_tools.py) | Test detection and `run_tests` (also exposed to agents as an in-process MCP tool) |
| [devagent/security.py](../devagent/security.py) | Sandbox profiles, sensitive-path rules, secret scanner |
| [devagent/guards.py](../devagent/guards.py) | PreToolUse guard run before every tool call |
| [devagent/deploy.py](../devagent/deploy.py) | Preflight checks, git and `gh` |
| [docs/THREAT_MODEL.md](THREAT_MODEL.md) | Security analysis |

## Development

```bash
make check     # ruff lint + format check, mypy, pytest
```

The tests cover the pipeline (with a scripted fake runner), guards, test parsing, secret scanning, git
operations against temporary repos, real `sandbox-exec` and Docker checks, the red-team suite (run against both sandboxes), the fairness of every benchmark task, and the GitHub Action's injection defences. None of them
call the API. CI runs everything on Linux and macOS.
