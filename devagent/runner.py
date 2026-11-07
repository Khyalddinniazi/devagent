"""Thin wrapper over claude_agent_sdk.query(): one call per pipeline stage."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    TextBlock,
    ToolUseBlock,
    query,
)
from rich.console import Console

from .agents.base import AgentSpec
from .config import Config, StageConfig
from .guards import make_guard_hooks
from .security import agent_permission_settings, agent_sandbox
from .tools.project_tools import TOOL_SERVER_NAME, build_tool_server


@dataclass
class StageResult:
    text: str
    cost_usd: float = 0.0
    turns: int = 0
    is_error: bool = False
    error: str | None = None


class Runner(Protocol):
    async def run(self, spec: AgentSpec, prompt: str, budget_usd: float | None = None) -> StageResult: ...


def _describe_tool(block: ToolUseBlock) -> str:
    inp = block.input or {}
    detail = inp.get("command") or inp.get("file_path") or inp.get("pattern") or inp.get("args") or ""
    detail = str(detail).replace("\n", " ")
    return f"{block.name} {detail[:100]}".rstrip()


class SDKRunner:
    def __init__(self, repo: Path, config: Config, console: Console | None = None, verbose: bool = False):
        self.repo = repo.resolve()
        self.config = config
        self.console = console or Console()
        self.verbose = verbose
        self._hooks = make_guard_hooks(self.repo)

    def _options(self, spec: AgentSpec, budget_usd: float | None = None) -> ClaudeAgentOptions:
        stage: StageConfig = getattr(self.config, spec.name)
        cfg = self.config
        mcp = {}
        if spec.use_project_tools:
            test_sandbox = cfg.test_sandbox if cfg.sandbox_tests else "none"
            mcp[TOOL_SERVER_NAME] = build_tool_server(self.repo, cfg.test_command, cfg.test_timeout, test_sandbox, cfg.test_image)
        kwargs: dict[str, Any] = dict(
            system_prompt=spec.system_prompt,
            allowed_tools=spec.allowed_tools,
            disallowed_tools=[*spec.disallowed_tools, "WebFetch", "WebSearch"],
            permission_mode=spec.permission_mode,
            cwd=str(self.repo),
            model=stage.model,
            max_turns=stage.max_turns,
            mcp_servers=mcp,
            strict_mcp_config=True,  # ignore any MCP servers configured elsewhere
            hooks=self._hooks,
            # Untrusted repos could ship .claude/settings.json with hooks/permissions: load nothing unless
            # trusted. An empty list also skips ~/.claude user settings, so runs are reproducible.
            setting_sources=["project"] if cfg.trust_project else [],
            settings=agent_permission_settings(),
            env={"PYTHONDONTWRITEBYTECODE": "1"},  # keep agents' test runs from littering the diff
        )
        if cfg.sandbox:
            kwargs["sandbox"] = agent_sandbox(cfg.allowed_domains)
        if budget_usd is not None:
            kwargs["max_budget_usd"] = round(max(budget_usd, 0.01), 2)
        if stage.effort:
            kwargs["effort"] = stage.effort
        return ClaudeAgentOptions(**kwargs)

    async def run(self, spec: AgentSpec, prompt: str, budget_usd: float | None = None) -> StageResult:
        texts: list[str] = []
        result: ResultMessage | None = None
        try:
            async for msg in query(prompt=prompt, options=self._options(spec, budget_usd)):
                if isinstance(msg, AssistantMessage):
                    for block in msg.content:
                        if isinstance(block, TextBlock) and block.text.strip():
                            texts.append(block.text)
                            if self.verbose:
                                self.console.print(f"[dim]{spec.name}:[/] {block.text.strip()}")
                        elif isinstance(block, ToolUseBlock):
                            self.console.print(f"  [cyan]{spec.name}[/] → {_describe_tool(block)}", highlight=False)
                elif isinstance(msg, ResultMessage):
                    result = msg
        except Exception as e:  # CLI missing, process error, auth, ...
            return StageResult(text="\n".join(texts), is_error=True, error=f"{type(e).__name__}: {e}")

        if result is None:
            return StageResult(text="\n".join(texts), is_error=True, error="agent ended without a result")
        final = result.result if isinstance(result.result, str) and result.result.strip() else (texts[-1] if texts else "")
        err = None
        if result.is_error:
            err = f"{result.subtype}" + (f": {result.errors}" if getattr(result, "errors", None) else "")
            if result.subtype == "error_max_budget_usd":
                err = "spending limit reached (raise it with --max-cost)"
        return StageResult(
            text=final, cost_usd=result.total_cost_usd or 0.0, turns=result.num_turns, is_error=result.is_error, error=err
        )
