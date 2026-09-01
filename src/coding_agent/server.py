from __future__ import annotations

import threading
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .agent import CodingAgent
from .config import AgentSettings
from .llm import LLMClient
from .logging import setup_logging
from .session import SessionStore
from .tools.registry import ToolRegistry


def build_app(settings: AgentSettings | None = None) -> FastAPI:
    settings = settings or AgentSettings.from_env()
    setup_logging(settings.log_level)
    app = FastAPI(title="Chasm Agent")
    base_dir = Path(__file__).resolve().parent / "web"
    app.mount("/static", StaticFiles(directory=str(base_dir / "static")), name="static")
    store = SessionStore()
    index_html = (base_dir / "templates" / "index.html").read_text(encoding="utf-8")

    class SessionRequest(BaseModel):
        task: str = Field(min_length=1)
        mode: str = Field(default="auto")

    def run_session(session_id: str) -> None:
        session = store.get(session_id)
        if session is None:
            return
        session.status = "running"
        llm = LLMClient(api_key=settings.api_key, base_url=settings.base_url, model=settings.model)
        agent = CodingAgent(
            llm=llm,
            tools=ToolRegistry(settings.workspace_root),
            max_turns=settings.max_turns,
            max_history_messages=settings.max_history_messages,
            max_tool_output_chars=settings.max_tool_output_chars,
            mode=session.mode,
            sink=lambda event: store.append_event(session_id, event),
        )
        try:
            result = agent.run(session.task)
            session.result = result.final_message
            session.status = "done"
        except Exception as exc:  # noqa: BLE001
            session.result = f"{type(exc).__name__}: {exc}"
            session.status = "error"

    @app.get("/", response_class=HTMLResponse)
    def index():
        return HTMLResponse(index_html)

    @app.post("/api/sessions")
    def create_session(payload: SessionRequest, background_tasks: BackgroundTasks):
        record = store.create(payload.task, payload.mode)
        background_tasks.add_task(run_session, record.id)
        return {"session_id": record.id}

    @app.get("/api/sessions/{session_id}")
    def get_session(session_id: str):
        record = store.get(session_id)
        if record is None:
            raise HTTPException(status_code=404, detail="session not found")
        return record

    @app.get("/api/tree")
    def tree():
        items = []
        for path in sorted(settings.workspace_root.rglob("*")):
            if path.is_dir():
                continue
            rel = path.relative_to(settings.workspace_root)
            items.append(str(rel))
        return {"root": str(settings.workspace_root), "files": items[:800]}

    return app
