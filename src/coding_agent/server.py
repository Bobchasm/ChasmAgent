from __future__ import annotations

import json
import threading
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from .agent import CodingAgent
from .config import AgentSettings
from .llm import LLMClient
from .logging import setup_logging
from .memory import MemoryStore
from .session import SessionStore
from .tools.filesystem import read_file, write_file
from .tools.registry import ToolRegistry
from .utils import is_ignored_path


def _llm(settings: AgentSettings) -> LLMClient:
    return LLMClient(
        api_key=settings.api_key,
        base_url=settings.base_url,
        model=settings.model,
        extra_body={"enable_thinking": True} if settings.enable_thinking else None,
    )


def build_app(settings: AgentSettings | None = None) -> FastAPI:
    settings = settings or AgentSettings.from_env()
    setup_logging(settings.log_level)
    app = FastAPI(title="Chasm Agent")
    base_dir = Path(__file__).resolve().parent / "web"
    app.mount("/static", StaticFiles(directory=str(base_dir / "static")), name="static")
    store = SessionStore(settings.workspace_root)
    project_lock = threading.Lock()
    active_project_root = settings.workspace_root.resolve()
    index_html = (base_dir / "templates" / "index.html").read_text(encoding="utf-8")

    def get_project_root() -> Path:
        with project_lock:
            return active_project_root

    def set_project_root(path: Path) -> Path:
        nonlocal active_project_root
        resolved = path.expanduser().resolve()
        if not resolved.exists() or not resolved.is_dir():
            raise HTTPException(status_code=400, detail="project path is not a directory")
        with project_lock:
            active_project_root = resolved
        return resolved

    def run_session(session_id: str) -> None:
        session = store.get(session_id)
        if session is None:
            return
        store.update(session_id, status="running")
        project_root = Path(session.project_root or get_project_root())
        agent = CodingAgent(
            llm=_llm(settings),
            tools=ToolRegistry(project_root),
            memory=MemoryStore(project_root),
            max_turns=settings.max_turns,
            max_history_messages=settings.max_history_messages,
            max_tool_output_chars=settings.max_tool_output_chars,
            mode=session.mode,
            sink=lambda event: store.append_event(session_id, event),
        )
        try:
            result = agent.run(session.task)
            store.update(session_id, result=result.final_message, status="done")
        except Exception as exc:  # noqa: BLE001
            store.update(session_id, result=f"{type(exc).__name__}: {exc}", status="error")

    @app.get("/", response_class=HTMLResponse)
    def index():
        return HTMLResponse(index_html)

    @app.get("/api/project")
    def get_project():
        root = get_project_root()
        return {"project_root": str(root), "workspace_root": str(settings.workspace_root)}

    @app.get("/api/browse")
    def browse(path: str | None = None):
        target = Path(path).expanduser().resolve() if path else get_project_root()
        if not target.exists() or not target.is_dir():
            raise HTTPException(status_code=400, detail="path is not a directory")
        entries = []
        try:
            for child in sorted(target.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower())):
                if is_ignored_path(child):
                    continue
                entries.append(
                    {
                        "name": child.name,
                        "path": str(child),
                        "kind": "dir" if child.is_dir() else "file",
                    }
                )
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc))
        parent = str(target.parent) if target.parent != target else None
        return {"path": str(target), "parent": parent, "entries": entries[:500]}

    @app.post("/api/project")
    def choose_project(payload: dict[str, str]):
        path = (payload.get("path") or "").strip()
        if not path:
            raise HTTPException(status_code=400, detail="path is required")
        resolved = set_project_root(Path(path))
        return {"project_root": str(resolved)}

    @app.get("/api/tree")
    def tree():
        items = []
        root = get_project_root()
        for path in sorted(root.rglob("*")):
            if path.is_dir():
                continue
            if is_ignored_path(path):
                continue
            items.append(str(path.relative_to(root)))
        return {"root": str(root), "files": items[:800]}

    @app.get("/api/sessions")
    def list_sessions(limit: int = 20):
        return {"sessions": [item.to_dict() for item in store.list_recent(limit)]}

    @app.get("/api/file")
    def get_file(path: str):
        try:
            content = read_file(get_project_root(), path)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="file not found")
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=str(exc))
        return {"path": path, "content": content}

    @app.post("/api/file")
    def save_file(payload: dict[str, str]):
        path = (payload.get("path") or "").strip()
        content = payload.get("content", "")
        if not path:
            raise HTTPException(status_code=400, detail="path is required")
        try:
            message = write_file(get_project_root(), path, content)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=str(exc))
        return {"message": message}

    @app.post("/api/sessions")
    def create_session(payload: dict[str, str], background_tasks: BackgroundTasks):
        task = (payload.get("task") or "").strip()
        if not task:
            raise HTTPException(status_code=400, detail="task is required")
        mode = payload.get("mode") or "auto"
        project_root_value = (payload.get("project_root") or "").strip()
        project_root = Path(project_root_value) if project_root_value else get_project_root()
        record = store.create(task, str(project_root), mode)
        background_tasks.add_task(run_session, record.id)
        return {"session_id": record.id}

    @app.get("/api/sessions/{session_id}")
    def get_session(session_id: str):
        record = store.get(session_id)
        if record is None:
            raise HTTPException(status_code=404, detail="session not found")
        return record.to_dict()

    @app.get("/api/sessions/{session_id}/events")
    def stream_session_events(session_id: str):
        record = store.get(session_id)
        if record is None:
            raise HTTPException(status_code=404, detail="session not found")

        def event_gen():
            last_idx = 0
            while True:
                events = store.get_events_since(session_id, last_idx)
                for ev in events:
                    payload = json.dumps(ev, ensure_ascii=False)
                    yield f"data: {payload}\n\n"
                    last_idx += 1

                rec = store.get(session_id)
                if rec is None:
                    break
                if rec.status in {"done", "error"} and last_idx >= len(rec.events):
                    break

                store.wait_for_events(session_id, last_idx, timeout=15)

            yield 'data: {"kind": "end", "payload": {}}\n\n'

        return StreamingResponse(event_gen(), media_type="text/event-stream")

    return app
