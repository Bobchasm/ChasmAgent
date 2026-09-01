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

