from __future__ import annotations

import json
import logging
import time
from json import JSONDecodeError
from dataclasses import asdict, dataclass, field
from typing import Any, Callable

from .context import ConversationState
from .llm import LLMClient
from .memory import MemoryArchive, MemoryStore
from .prompts import planner_prompt, reflection_prompt, system_prompt
from .types import AgentEvent, AgentRunResult, RunReport
from .tools.registry import ToolRegistry
from .utils import truncate_text

logger = logging.getLogger(__name__)


EventSink = Callable[[AgentEvent], None]


@dataclass(slots=True)
class CodingAgent:
    llm: LLMClient
    tools: ToolRegistry
    memory: MemoryStore | None = None
    archive: MemoryArchive | None = None
    session_id: str | None = None
    user_id: int = 1
    enable_planning: bool = False
    enable_reflection: bool = False
    max_turns: int = 12
    max_history_messages: int = 18
    max_tool_output_chars: int = 12_000
    mode: str = "auto"
    events: list[AgentEvent] = field(default_factory=list)
    sink: EventSink | None = None
    should_stop: Callable[[], bool] | None = None

    def _emit(self, kind: str, **payload: Any) -> None:
        event = AgentEvent(kind=kind, payload=payload)
        self.events.append(event)
        if self.sink:
            self.sink(event)

    def _parse_json_object(self, text: str) -> dict[str, Any]:
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`")
        try:
            obj = json.loads(cleaned)
            if isinstance(obj, dict):
                return obj
        except Exception:
            pass
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start >= 0 and end > start:
            try:
                obj = json.loads(cleaned[start : end + 1])
                if isinstance(obj, dict):
                    return obj
            except Exception:
                return {}
        return {}

    def _format_plan(self, plan: dict[str, Any]) -> str:
        steps = plan.get("steps") or []
        lines = [f"Goal: {plan.get('goal', '').strip()}"]
        if steps:
            lines.append("Steps:")
            for idx, step in enumerate(steps, start=1):
                if isinstance(step, dict):
                    title = str(step.get("title", "")).strip()
                    detail = str(step.get("detail", "")).strip()
                    suffix = f" - {detail}" if detail else ""
                    lines.append(f"{idx}. {title}{suffix}")
        risks = plan.get("risks") or []
        if risks:
            lines.append("Risks:")
            lines.extend(f"- {str(item)}" for item in risks[:5])
        success = plan.get("success_criteria") or []
        if success:
            lines.append("Success criteria:")
            lines.extend(f"- {str(item)}" for item in success[:5])
        return "\n".join(lines).strip()

    def _plan_task(self, task: str, context: str) -> dict[str, Any]:
        if not self.enable_planning:
            return {
                "goal": task[:120],
                "steps": [{"title": "Inspect workspace", "detail": "Locate relevant files and understand the current state."}],
                "risks": ["Model output may need recovery after tool failures."],
                "success_criteria": ["Task is completed and verified."],
            }
        messages = [
            {"role": "system", "content": planner_prompt()},
            {"role": "user", "content": f"Task:\n{task}\n\nContext:\n{context or 'None'}"},
        ]
        try:
            response = self.llm.complete(messages, [])
            content = response.choices[0].message.content or ""
            plan = self._parse_json_object(content)
        except Exception as exc:  # noqa: BLE001
            self._emit("planner_error", error=f"{type(exc).__name__}: {exc}")
            plan = {}
        if not plan:
            plan = {
                "goal": task[:120],
                "steps": [{"title": "Inspect workspace", "detail": "Locate relevant files and understand the current state."}],
                "risks": ["Model output may need recovery after tool failures."],
                "success_criteria": ["Task is completed and verified."],
            }
        return plan

    def _reflect(self, task: str, final_message: str, plan: dict[str, Any], report: RunReport) -> dict[str, Any]:
        if not self.enable_reflection:
            return {
                "summary": final_message[:240],
                "status": report.status,
                "next_steps": [],
                "lessons": [],
                "files": [],
            }
        context = json.dumps(
            {
                "task": task,
                "final_message": final_message,
                "plan": plan,
                "report": {
                    "status": report.status,
                    "turns": report.turns,
                    "tool_calls": report.tool_calls,
                    "tool_failures": report.tool_failures,
                    "duration_ms": report.duration_ms,
                },
            },
            ensure_ascii=False,
            indent=2,
        )
        messages = [
            {"role": "system", "content": reflection_prompt()},
            {"role": "user", "content": context},
        ]
        try:
            response = self.llm.complete(messages, [])
            content = response.choices[0].message.content or ""
            reflection = self._parse_json_object(content)
        except Exception as exc:  # noqa: BLE001
            reflection = {"summary": f"reflection_error: {type(exc).__name__}: {exc}"}
        if not reflection:
            reflection = {"summary": final_message[:240], "status": report.status}
        return reflection

    def _build_state(
        self,
        task: str,
        plan_text: str,
        retrieval_text: str,
        conversation_messages: list[dict[str, Any]] | None = None,
    ) -> ConversationState:
        state = ConversationState()
        memory_text = self.memory.render() if self.memory else ""
        state.append({"role": "system", "content": system_prompt(memory_text, retrieval_text, plan_text)})
        for message in conversation_messages or []:
            state.append(dict(message))
        if not conversation_messages:
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

    def run(self, task: str, conversation_messages: list[dict[str, Any]] | None = None) -> AgentRunResult:
        self.events = []
        started_at = time.monotonic()
        consecutive_tool_failures = 0
        last_tool_outputs: dict[str, str] = {}
        no_progress_turns = 0
        self._emit("task", task=task)
        retrieval_text = (
            self.archive.render(
                task,
                self.user_id,
                str(self.tools.workspace_root),
                exclude_session_id=self.session_id,
            )
            if self.archive
            else ""
        )
        plan = self._plan_task(task, retrieval_text)
        plan_text = self._format_plan(plan)
        self._emit("plan", plan=plan, text=plan_text)
        state = self._build_state(task, plan_text, retrieval_text, conversation_messages=conversation_messages)

        for turn in range(1, self.max_turns + 1):
            if self.should_stop and self.should_stop():
                final = "Terminated: stopped by user."
                self._emit("final", text=final)
                report = RunReport(
                    status="stopped",
                    turns=turn - 1,
                    tool_calls=sum(1 for event in self.events if event.kind == "tool_call"),
                    tool_failures=sum(1 for event in self.events if event.kind == "tool_error"),
                    duration_ms=int((time.monotonic() - started_at) * 1000),
                    plan_steps=len(plan.get("steps") or []),
                )
                self._emit("report", report=asdict(report))
                return AgentRunResult(task=task, final_message=final, events=self.events, workspace_root=self.tools.workspace_root)
            state.compact(self.max_history_messages)
            self._emit("turn_start", turn=turn, messages=len(state.messages))
            try:
                response = self.llm.complete(state.messages, self.tools.specs())
            except Exception as exc:  # noqa: BLE001
                final = f"model_error: {type(exc).__name__}: {exc}"
                self._emit("final", text=final)
                report = RunReport(
                    status="error",
                    turns=turn,
                    tool_calls=sum(1 for event in self.events if event.kind == "tool_call"),
                    tool_failures=sum(1 for event in self.events if event.kind == "tool_error"),
                    duration_ms=int((time.monotonic() - started_at) * 1000),
                    plan_steps=len(plan.get("steps") or []),
                )
                self._emit("report", report=asdict(report))
                return AgentRunResult(task=task, final_message=final, events=self.events, workspace_root=self.tools.workspace_root)
            if self.should_stop and self.should_stop():
                final = "Terminated: stopped by user."
                self._emit("final", text=final)
                report = RunReport(
                    status="stopped",
                    turns=turn,
                    tool_calls=sum(1 for event in self.events if event.kind == "tool_call"),
                    tool_failures=sum(1 for event in self.events if event.kind == "tool_error"),
                    duration_ms=int((time.monotonic() - started_at) * 1000),
                    plan_steps=len(plan.get("steps") or []),
                )
                self._emit("report", report=asdict(report))
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
                reflection = self._reflect(
                    task,
                    final,
                    plan,
                    RunReport(
                        status="done",
                        turns=turn,
                        tool_calls=sum(1 for event in self.events if event.kind == "tool_call"),
                        tool_failures=sum(1 for event in self.events if event.kind == "tool_error"),
                        duration_ms=int((time.monotonic() - started_at) * 1000),
                        plan_steps=len(plan.get("steps") or []),
                    ),
                )
                if self.memory:
                    self.memory.update_from_run(task, final, self.events, reflection=reflection)
                self._emit("reflection", reflection=reflection)
                self._emit(
                    "report",
                    report={
                        "status": "done",
                        "turns": turn,
                        "tool_calls": sum(1 for event in self.events if event.kind == "tool_call"),
                        "tool_failures": sum(1 for event in self.events if event.kind == "tool_error"),
                        "duration_ms": int((time.monotonic() - started_at) * 1000),
                        "plan_steps": len(plan.get("steps") or []),
                    },
                )
                return AgentRunResult(task=task, final_message=final, events=self.events, workspace_root=self.tools.workspace_root)

            for call in tool_calls:
                if self.should_stop and self.should_stop():
                    final = "Terminated: stopped by user."
                    self._emit("final", text=final)
                    return AgentRunResult(task=task, final_message=final, events=self.events, workspace_root=self.tools.workspace_root)
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
                self._emit(
                    "report",
                    report={
                        "status": "error",
                        "turns": turn,
                        "tool_calls": sum(1 for event in self.events if event.kind == "tool_call"),
                        "tool_failures": sum(1 for event in self.events if event.kind == "tool_error"),
                        "duration_ms": int((time.monotonic() - started_at) * 1000),
                        "plan_steps": len(plan.get("steps") or []),
                    },
                )
                return AgentRunResult(task=task, final_message=final, events=self.events, workspace_root=self.tools.workspace_root)

            if no_progress_turns >= 4:
                final = "Terminated: no progress detected across multiple turns."
                self._emit("final", text=final)
                if self.memory:
                    self.memory.update_from_run(task, final, self.events)
                self._emit(
                    "report",
                    report={
                        "status": "error",
                        "turns": turn,
                        "tool_calls": sum(1 for event in self.events if event.kind == "tool_call"),
                        "tool_failures": sum(1 for event in self.events if event.kind == "tool_error"),
                        "duration_ms": int((time.monotonic() - started_at) * 1000),
                        "plan_steps": len(plan.get("steps") or []),
                    },
                )
                return AgentRunResult(task=task, final_message=final, events=self.events, workspace_root=self.tools.workspace_root)

        final = "Reached the turn limit before completion."
        self._emit("final", text=final)
        if self.memory:
            self.memory.update_from_run(task, final, self.events)
        self._emit(
            "report",
            report={
                "status": "limit",
                "turns": self.max_turns,
                "tool_calls": sum(1 for event in self.events if event.kind == "tool_call"),
                "tool_failures": sum(1 for event in self.events if event.kind == "tool_error"),
                "duration_ms": int((time.monotonic() - started_at) * 1000),
                "plan_steps": len(plan.get("steps") or []),
            },
        )
        return AgentRunResult(task=task, final_message=final, events=self.events, workspace_root=self.tools.workspace_root)
