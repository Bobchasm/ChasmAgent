from __future__ import annotations

import json
import logging
from json import JSONDecodeError
from dataclasses import dataclass, field
from typing import Any, Callable

from .context import ConversationState
from .llm import LLMClient
from .memory import MemoryStore
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
    memory: MemoryStore | None = None
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

    def _build_state(self, task: str) -> ConversationState:
        state = ConversationState()
        memory_text = self.memory.render() if self.memory else ""
        state.append({"role": "system", "content": system_prompt(memory_text)})
        state.append({"role": "user", "content": task})
        return state

    def _append_tool_result(self, state: ConversationState, call_id: str, output: str) -> None:
        state.append({"role": "tool", "tool_call_id": call_id, "content": output})

    def _handle_tool_call(self, call: Any, state: ConversationState) -> tuple[bool, str]:
        try:
            args = json.loads(call.function.arguments or "{}")
        except JSONDecodeError as exc:
            message = f"invalid tool arguments for {call.function.name}: {exc}"
            self._emit("tool_error", name=call.function.name, error=message)
            self._append_tool_result(state, call.id, message)
            return False, message

        self._emit("tool_call", name=call.function.name, args=args)
        if self.mode == "dry-run":
            output = f"dry-run: skipped {call.function.name}"
            self._append_tool_result(state, call.id, output)
            self._emit("tool_result", name=call.function.name, ok=True, output=output)
            return True, output

        try:
            output = self.tools.execute(call.function.name, args)
            ok = True
        except Exception as exc:  # noqa: BLE001
            ok = False
            output = f"{type(exc).__name__}: {exc}"

        output = truncate_text(output, self.max_tool_output_chars)
        self._append_tool_result(state, call.id, output)
        self._emit("tool_result", name=call.function.name, ok=ok, output=output)

        return ok, output

    def run(self, task: str) -> AgentRunResult:
        self.events = []
        consecutive_tool_failures = 0
        last_tool_outputs: dict[str, str] = {}
        no_progress_turns = 0
        state = self._build_state(task)
        self._emit("task", task=task)

        for turn in range(1, self.max_turns + 1):
            state.compact(self.max_history_messages)
            self._emit("turn_start", turn=turn, messages=len(state.messages))
            try:
                response = self.llm.complete(state.messages, self.tools.specs())
            except Exception as exc:  # noqa: BLE001
                final = f"model_error: {type(exc).__name__}: {exc}"
                self._emit("final", text=final)
                return AgentRunResult(task=task, final_message=final, events=self.events, workspace_root=self.tools.workspace_root)

            message = response.choices[0].message
            reasoning = getattr(message, "reasoning_content", None)
            if reasoning:
                self._emit("reasoning", text=reasoning)

            assistant_payload: dict[str, Any] = {"role": "assistant", "content": message.content or ""}
            tool_calls = list(getattr(message, "tool_calls", None) or [])
            if tool_calls:
                assistant_payload["tool_calls"] = [
                    {"id": call.id, "type": "function", "function": {"name": call.function.name, "arguments": call.function.arguments}}
                    for call in tool_calls
                ]
            state.append(assistant_payload)

            if not tool_calls:
                final = message.content or ""
                self._emit("final", text=final)
                if self.memory:
                    self.memory.update_from_run(task, final, self.events)
                return AgentRunResult(task=task, final_message=final, events=self.events, workspace_root=self.tools.workspace_root)

            for call in tool_calls:
                ok, output = self._handle_tool_call(call, state)
                if ok:
                    consecutive_tool_failures = 0
                else:
                    consecutive_tool_failures += 1
                prev = last_tool_outputs.get(call.function.name)
                if prev is None or prev != output:
                    no_progress_turns = 0
                    last_tool_outputs[call.function.name] = output
                else:
                    no_progress_turns += 1

            if consecutive_tool_failures >= 3:
                final = f"Terminated: {consecutive_tool_failures} consecutive tool failures."
                self._emit("final", text=final)
                if self.memory:
                    self.memory.update_from_run(task, final, self.events)
                return AgentRunResult(task=task, final_message=final, events=self.events, workspace_root=self.tools.workspace_root)

            if no_progress_turns >= 4:
                final = "Terminated: no progress detected across multiple turns."
                self._emit("final", text=final)
                if self.memory:
                    self.memory.update_from_run(task, final, self.events)
                return AgentRunResult(task=task, final_message=final, events=self.events, workspace_root=self.tools.workspace_root)

        final = "Reached the turn limit before completion."
        self._emit("final", text=final)
        if self.memory:
            self.memory.update_from_run(task, final, self.events)
        return AgentRunResult(task=task, final_message=final, events=self.events, workspace_root=self.tools.workspace_root)
