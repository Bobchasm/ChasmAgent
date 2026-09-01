from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


@dataclass(slots=True)
class AgentSettings:
    workspace_root: Path
    model: str
    base_url: str
    api_key: str
    provider: str = "openai"
    enable_thinking: bool = False
    log_level: str = "INFO"
    max_turns: int = 12
    max_history_messages: int = 18
    max_tool_output_chars: int = 12_000
    mode: str = "auto"

    @classmethod
    def from_env(cls, workspace: str | None = None) -> "AgentSettings":
        root = Path(workspace or os.getenv("CHASM_WORKSPACE", ".")).expanduser().resolve()
        load_dotenv(dotenv_path=Path.cwd() / ".env", override=False)
        load_dotenv(dotenv_path=root / ".env", override=False)
        provider = os.getenv("CHASM_PROVIDER", "openai").lower()
        dashscope_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
        api_key = os.getenv("OPENAI_API_KEY") or os.getenv("DASHSCOPE_API_KEY") or ""
        return cls(
            workspace_root=root,
            provider=provider,
            model=os.getenv("OPENAI_MODEL", "gpt-5"),
            base_url=os.getenv("OPENAI_BASE_URL", dashscope_url if provider == "dashscope" else "https://api.openai.com/v1"),
            api_key=api_key,
            enable_thinking=os.getenv("CHASM_ENABLE_THINKING", "0").lower() in {"1", "true", "yes", "on"},
            log_level=os.getenv("CHASM_LOG_LEVEL", "INFO").upper(),
            max_turns=int(os.getenv("CHASM_MAX_TURNS", "12")),
            max_history_messages=int(os.getenv("CHASM_MAX_HISTORY", "18")),
            max_tool_output_chars=int(os.getenv("CHASM_MAX_TOOL_OUTPUT_CHARS", "12000")),
            mode=os.getenv("CHASM_MODE", "auto"),
        )
