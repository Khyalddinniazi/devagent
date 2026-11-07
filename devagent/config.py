"""Settings, loaded from defaults, then <repo>/.devagent.toml, then CLI overrides."""

from __future__ import annotations

from pathlib import Path

import tomllib
from pydantic import BaseModel, Field

DEFAULT_MODEL = "claude-opus-5-5"


class StageConfig(BaseModel):
    model: str = DEFAULT_MODEL
    max_turns: int = 40
    effort: str | None = None  # low | medium | high | xhigh | max; None = model default


class Config(BaseModel):
    base_branch: str | None = None  # None = repo's current branch at start of run
    branch_prefix: str = "devagent/"
    test_command: str | None = None  # None = auto-detect
    test_timeout: int = 900
    max_debug: int = 3
    remote: str = "origin"
    pr_note: str | None = None  # extra text for the PR body, e.g. "Closes #12" (not shown to agents)
    # --- safety ---
    max_cost_usd: float = 5.0  # hard spending cap for one run (all stages together)
    sandbox: bool = True  # run agent Bash inside the OS sandbox
    sandbox_tests: bool = True  # run test commands inside macOS sandbox-exec (no network)
    allowed_domains: list[str] = Field(default_factory=list)  # network allowlist for sandboxed agent Bash
    trust_project: bool = False  # load the repo's own .claude settings / CLAUDE.md
    write_tests_without_framework: bool = False  # let the Tester invent a test setup when the repo has none
    planner: StageConfig = Field(default_factory=lambda: StageConfig(max_turns=30, effort="high"))
    coder: StageConfig = Field(default_factory=lambda: StageConfig(max_turns=60, effort="high"))
    tester: StageConfig = Field(default_factory=lambda: StageConfig(max_turns=40, effort="high"))
    debugger: StageConfig = Field(default_factory=lambda: StageConfig(max_turns=40, effort="high"))
    writer: StageConfig = Field(default_factory=lambda: StageConfig(max_turns=1, effort="low"))

    @classmethod
    def load(cls, repo: Path, **overrides) -> Config:
        data: dict = {}
        cfg_file = repo / ".devagent.toml"
        if cfg_file.exists():
            data = tomllib.loads(cfg_file.read_text())
        data.update({k: v for k, v in overrides.items() if v is not None})
        return cls.model_validate(data)
