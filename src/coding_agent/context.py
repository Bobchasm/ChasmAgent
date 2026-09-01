from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ConversationState:
    messages: list[dict[str, Any]] = field(default_factory=list)
    summary: str = ""

    def append(self, message: dict[str, Any]) -> None:
        self.messages.append(message)

    def compact(self, max_messages: int) -> None:
        if len(self.messages) <= max_messages:
            return
        removed = self.messages[:-max_messages]
        self.messages = self.messages[-max_messages:]
        notes: list[str] = []
        for msg in removed:
            role = msg.get("role", "unknown")
            content = msg.get("content")
            if isinstance(content, str) and content.strip():
                notes.append(f"{role}: {content.strip()[:180]}")
            if msg.get("tool_calls"):
                notes.append(f"{role}: tool calls recorded")
        if notes:
            self.summary = (self.summary + "\n" if self.summary else "") + "\n".join(notes[-8:])

