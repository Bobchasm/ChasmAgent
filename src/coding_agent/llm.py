from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from openai import OpenAI


@dataclass(slots=True)
class LLMClient:
    api_key: str
    base_url: str
    model: str

    def __post_init__(self) -> None:
        self._client = OpenAI(api_key=self.api_key, base_url=self.base_url)

    def complete(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]], temperature: float = 0.2):
        return self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            tools=tools,
            temperature=temperature,
        )

