from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class ToolResult:
    name: str
    ok: bool
    output: str
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class AgentEvent:
    kind: str
    payload: dict[str, Any]


@dataclass(slots=True)
class AgentRunResult:
    task: str
    final_message: str
    events: list[AgentEvent]
    workspace_root: Path


@dataclass(slots=True)
class PlanItem:
    title: str
    detail: str = ""


@dataclass(slots=True)
class RunReport:
    status: str
    turns: int
    tool_calls: int
    tool_failures: int
    duration_ms: int
    plan_steps: int = 0
