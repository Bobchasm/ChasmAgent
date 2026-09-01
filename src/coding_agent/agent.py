from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Callable

from .context import ConversationState
from .llm import LLMClient
from .prompts import system_prompt
from .types import AgentEvent, AgentRunResult
from .tools.registry import ToolRegistry
from .utils import truncate_text

logger = logging.getLogger(__name__)


EventSink = Callable[[AgentEvent], None]


@dataclass(slots=True)
class CodingAgent:
    llm: LLMClient
    tools: ToolRegistry
    max_turns: int = 12
    max_history_messages: int = 18
    max_tool_output_chars: int = 12_000
    mode: str = "auto"
    events: list[AgentEvent] = field(default_factory=list)
    sink: EventSink | None = None

    def _emit(self, kind: str, **payload: Any) -> None:
        event = AgentEvent(kind=kind, payload=payload)
        self.events.append(event)
        if self.sink:
            self.sink(event)

    def run(self, task: str) -> AgentRunResult:
        state = ConversationState()
        state.append({"role": "system", "content": system_prompt()})
        state.append({"role": "user", "content": task})
        self._emit("task", task=task)

        for turn in range(1, self.max_turns + 1):
            state.compact(self.max_history_messages)
            self._emit("turn_start", turn=turn, messages=len(state.messages))
            response = self.llm.complete(state.messages, self.tools.specs())
            message = response.choices[0].message
            reasoning = getattr(message, "reasoning_content", None)
            if reasoning:
                self._emit("reasoning", text=reasoning)
            assistant_payload: dict[str, Any] = {"role": "assistant", "content": message.content or ""}
            if getattr(message, "tool_calls", None):
                assistant_payload["tool_calls"] = []
                for call in message.tool_calls:
                    assistant_payload["tool_calls"].append(
                        {"id": call.id, "type": "function", "function": {"name": call.function.name, "arguments": call.function.arguments}}
                    )
            state.append(assistant_payload)

            if not getattr(message, "tool_calls", None):
                final = message.content or ""
                self._emit("final", text=final)
                return AgentRunResult(task=task, final_message=final, events=self.events, workspace_root=self.tools.workspace_root)

            for call in message.tool_calls:
                args = json.loads(call.function.arguments or "{}")
                self._emit("tool_call", name=call.function.name, args=args)
                if self.mode == "dry-run":
                    ok = True
                    output = f"dry-run: skipped {call.function.name}"
                else:
                    try:
                        output = self.tools.execute(call.function.name, args)
                        ok = True
                    except Exception as exc:  # noqa: BLE001
                        ok = False
                        output = f"{type(exc).__name__}: {exc}"
                output = truncate_text(output, self.max_tool_output_chars)
                state.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": output,
                    }
                )
                self._emit("tool_result", name=call.function.name, ok=ok, output=output)

        final = "Reached the turn limit before completion."
        self._emit("final", text=final)
        return AgentRunResult(task=task, final_message=final, events=self.events, workspace_root=self.tools.workspace_root)
