from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from openai import OpenAI
import json
import re
from types import SimpleNamespace


@dataclass(slots=True)
class LLMClient:
    api_key: str
    base_url: str
    model: str
    extra_body: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        self._client = OpenAI(api_key=self.api_key, base_url=self.base_url)

    def complete(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]], temperature: float = 0.2):
        # Primary call to the OpenAI-compatible client
        resp = self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            tools=tools,
            temperature=temperature,
            extra_body=self.extra_body or None,
        )

        # Post-process response: some gateways/models embed function/tool calls
        try:
            choice = resp.choices[0]
            message = getattr(choice, "message", None)
            if message is None:
                return resp

            # ensure message has content attribute
            content = getattr(message, "content", "") or ""

            # attach parsed tool_calls if not provided by the gateway
            if not getattr(message, "tool_calls", None):
                parsed_calls = self._parse_tool_calls_from_text(content)
                if parsed_calls:
                    # create lightweight tool call objects compatible with agent expectations
                    tool_calls = []
                    for idx, call in enumerate(parsed_calls):
                        fn = SimpleNamespace(name=call.get("name"), arguments=json.dumps(call.get("arguments", {})))
                        tc = SimpleNamespace(id=str(idx), function=fn)
                        tool_calls.append(tc)
                    setattr(message, "tool_calls", tool_calls)

            # also support an extra field for reasoning content
            reasoning_match = re.search(r"<REASONING>(.*?)</REASONING>", content, flags=re.S)
            if reasoning_match:
                setattr(message, "reasoning_content", reasoning_match.group(1).strip())

        except Exception:
            # non-fatal: return original response
            return resp

        return resp

    def _parse_tool_calls_from_text(self, text: str) -> list[dict]:
        """Try to locate JSON describing tool calls inside the assistant content.

        Accepts either a single JSON object with fields {"name","arguments"}
        or a top-level list of such objects. Also accepts inline lines like:
        CALL_TOOL name: {json}
        Returns list of dicts with keys 'name' and 'arguments'.
        """
        results: list[dict] = []

        # 1) find explicit JSON blocks
        for m in re.finditer(r"```(?:json)?\s*(\{[\s\S]*?\})\s*```", text, flags=re.I):
            blob = m.group(1)
            try:
                obj = json.loads(blob)
            except Exception:
                continue
            if isinstance(obj, dict):
                # single call format
                if "name" in obj and "arguments" in obj:
                    results.append({"name": obj["name"], "arguments": obj["arguments"]})
                # maybe a wrapper
                elif "tool_calls" in obj and isinstance(obj["tool_calls"], list):
                    for c in obj["tool_calls"]:
                        if isinstance(c, dict) and "function" in c:
                            fn = c.get("function")
                            args = fn.get("arguments") if isinstance(fn, dict) else None
                            results.append({"name": fn.get("name") if isinstance(fn, dict) else None, "arguments": args})

        if results:
            return results

        # 2) try to parse any standalone JSON object in the text
        json_obj_match = re.search(r"(\{[\s\S]*\})", text)
        if json_obj_match:
            try:
                obj = json.loads(json_obj_match.group(1))
                if isinstance(obj, dict) and "name" in obj and "arguments" in obj:
                    return [{"name": obj["name"], "arguments": obj["arguments"]}]
                if isinstance(obj, list):
                    parsed = []
                    for item in obj:
                        if isinstance(item, dict) and "name" in item and "arguments" in item:
                            parsed.append({"name": item["name"], "arguments": item["arguments"]})
                    if parsed:
                        return parsed
            except Exception:
                pass

        # 3) line-based CALL_TOOL patterns: CALL_TOOL <name>: <json>
        for m in re.finditer(r"CALL_TOOL\s+(\w[\w-]*)\s*:\s*(\{[\s\S]*?\})(?:\n|$)", text):
            name = m.group(1)
            try:
                args = json.loads(m.group(2))
            except Exception:
                args = {}
            results.append({"name": name, "arguments": args})

        return results
