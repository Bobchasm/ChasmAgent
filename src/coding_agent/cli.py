from __future__ import annotations

import os
from pathlib import Path

import typer
import uvicorn
from rich.console import Console

from .agent import CodingAgent
from .config import AgentSettings
from .llm import LLMClient
from .logging import setup_logging
from .tools.registry import ToolRegistry

app = typer.Typer(add_completion=False, no_args_is_help=True)
console = Console()


@app.command()
def run(
    task: str = typer.Argument(..., help="Task for the coding agent."),
    workspace: Path = typer.Option(Path("."), "--workspace", "-w", help="Workspace root."),
    mode: str = typer.Option("auto", "--mode", help="Execution mode."),
):
    settings = AgentSettings.from_env(str(workspace))
    setup_logging(settings.log_level)
    if not settings.api_key:
        raise typer.BadParameter("OPENAI_API_KEY is required")
    agent = CodingAgent(
        llm=LLMClient(api_key=settings.api_key, base_url=settings.base_url, model=settings.model),
        tools=ToolRegistry(settings.workspace_root),
        max_turns=settings.max_turns,
        max_history_messages=settings.max_history_messages,
        max_tool_output_chars=settings.max_tool_output_chars,
        mode=mode,
    )
    result = agent.run(task)
    console.print(result.final_message)


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8000, "--port"),
    reload: bool = typer.Option(False, "--reload"),
    workspace: Path = typer.Option(Path("."), "--workspace", "-w"),
    mode: str = typer.Option("auto", "--mode"),
):
    settings = AgentSettings.from_env(str(workspace))
    os.environ["CHASM_WORKSPACE"] = str(settings.workspace_root)
    os.environ["CHASM_MODE"] = mode
    os.environ["OPENAI_MODEL"] = settings.model
    os.environ["OPENAI_BASE_URL"] = settings.base_url
    os.environ["CHASM_LOG_LEVEL"] = settings.log_level
    uvicorn.run("coding_agent.server:build_app", factory=True, host=host, port=port, reload=reload)
