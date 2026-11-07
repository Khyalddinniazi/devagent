"""Run state persisted to <repo>/.devagent/<run-id>/state.json so runs can be resumed."""

from __future__ import annotations

import re
import secrets
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, Field

STATE_DIR = ".devagent"


class Stage(str, Enum):
    NEW = "new"
    PLANNED = "planned"
    APPROVED = "approved"
    CODED = "coded"
    TESTED = "tested"  # tests written + run (pass or fail)
    READY = "ready"  # tests green, awaiting deploy confirmation
    DEPLOYED = "deployed"
    ABORTED = "aborted"  # user rejected the plan


class StageCost(BaseModel):
    stage: str
    cost_usd: float = 0.0
    turns: int = 0
    is_error: bool = False


class RunState(BaseModel):
    run_id: str
    task: str
    repo: str
    stage: Stage = Stage.NEW
    base_branch: str | None = None
    branch: str | None = None
    debug_attempts: int = 0
    tests_passed: bool | None = None
    test_summary: str | None = None
    security_alerts: list[str] = Field(default_factory=list)  # INJECTION-ALERT lines reported by agents
    tests_skipped: bool = False  # True when the project has no test suite (nothing verified)
    pr_url: str | None = None
    error: str | None = None  # set when the last attempt failed; `stage` stays at the last completed stage
    costs: list[StageCost] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    # ---- paths -------------------------------------------------------------
    @property
    def dir(self) -> Path:
        return Path(self.repo) / STATE_DIR / self.run_id

    @property
    def plan_path(self) -> Path:
        return self.dir / "plan.md"

    @property
    def test_report_path(self) -> Path:
        return self.dir / "test_report.json"

    @property
    def debug_log_path(self) -> Path:
        return self.dir / "debug_log.md"

    # ---- persistence -------------------------------------------------------
    @classmethod
    def new(cls, task: str, repo: Path) -> RunState:
        slug = re.sub(r"[^a-z0-9]+", "-", task.lower()).strip("-")[:40].strip("-") or "task"
        run_id = f"{datetime.now():%Y%m%d-%H%M%S}-{slug}-{secrets.token_hex(2)}"
        state = cls(run_id=run_id, task=task, repo=str(repo.resolve()))
        state.save()
        return state

    @classmethod
    def load(cls, repo: Path, run_id: str) -> RunState:
        path = repo.resolve() / STATE_DIR / run_id / "state.json"
        return cls.model_validate_json(path.read_text())

    def save(self) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        (self.dir / "state.json").write_text(self.model_dump_json(indent=2))

    @property
    def total_cost(self) -> float:
        return sum(c.cost_usd for c in self.costs)
