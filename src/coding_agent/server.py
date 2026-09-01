from __future__ import annotations

import json
import threading
from pathlib import Path

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
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
    store = SessionStore(settings.data_dir, legacy_workspace_root=settings.workspace_root)
    db = store.db
    project_lock = threading.Lock()
    active_project_root = settings.workspace_root.resolve()
    cancel_events: dict[str, threading.Event] = {}
    index_html = (base_dir / "templates" / "index.html").read_text(encoding="utf-8")

    def _cookie_name() -> str:
        return "chasm_session"

    def _require_user(request: Request):
        user = getattr(request.state, "user", None)
        if user is None:
            raise HTTPException(status_code=401, detail="authentication required")
        return user

    @app.middleware("http")
    async def auth_middleware(request: Request, call_next):
        path = request.url.path
        if path == "/" or path.startswith("/static") or path.startswith("/api/auth"):
            return await call_next(request)
        token = request.cookies.get(_cookie_name())
        if not token:
            return JSONResponse({"detail": "authentication required"}, status_code=401)
        user = db.get_user_by_token(token)
        if user is None:
            return JSONResponse({"detail": "authentication required"}, status_code=401)
        request.state.user = user
        return await call_next(request)

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
        cancel_event = cancel_events.setdefault(session_id, threading.Event())
        agent = CodingAgent(
            llm=_llm(settings),
            tools=ToolRegistry(project_root),
            memory=MemoryStore(project_root, namespace=session_id),
            max_turns=settings.max_turns,
            max_history_messages=settings.max_history_messages,
            max_tool_output_chars=settings.max_tool_output_chars,
            mode=session.mode,
            sink=lambda event: store.append_event(session_id, event),
            should_stop=cancel_event.is_set,
        )
        try:
            result = agent.run(session.task)
            final_message = "Terminated: stopped by user." if cancel_event.is_set() else result.final_message
            status = "stopped" if cancel_event.is_set() else "done"
            store.append_message(session_id, "assistant", final_message)
            store.update(session_id, result=final_message, status=status)
        except Exception as exc:  # noqa: BLE001
            store.update(session_id, result=f"{type(exc).__name__}: {exc}", status="error")
        finally:
            cancel_events.pop(session_id, None)

    @app.get("/", response_class=HTMLResponse)
    def index():
        return HTMLResponse(index_html)

    @app.get("/api/auth/status")
    def auth_status(request: Request):
        token = request.cookies.get(_cookie_name())
        user = db.get_user_by_token(token) if token else None
        bootstrap = db.get_user_by_username("local") is not None and user is None
        return {
            "authenticated": user is not None,
            "bootstrap_available": bootstrap,
            "user": None if user is None else {"id": user.id, "username": user.username},
        }

    def _set_auth_cookie(response, token: str):
        response.set_cookie(
            _cookie_name(),
            token,
            httponly=True,
            samesite="lax",
            secure=False,
            max_age=60 * 60 * 24 * 30,
        )
        return response

    @app.post("/api/auth/bootstrap")
    def auth_bootstrap():
        user = db.ensure_system_user()
        token = db.create_auth_session(user.id)
        return _set_auth_cookie(JSONResponse({"user": {"id": user.id, "username": user.username}}), token)

    @app.post("/api/auth/register")
    def auth_register(payload: dict[str, str]):
        username = (payload.get("username") or "").strip()
        password = payload.get("password") or ""
        if not username or not password:
            raise HTTPException(status_code=400, detail="username and password are required")
        try:
            user = db.create_user(username, password)
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=str(exc))
        token = db.create_auth_session(user.id)
        return _set_auth_cookie(JSONResponse({"user": {"id": user.id, "username": user.username}}), token)

    @app.post("/api/auth/login")
    def auth_login(payload: dict[str, str]):
        username = (payload.get("username") or "").strip()
        password = payload.get("password") or ""
        if not username or not password:
            raise HTTPException(status_code=400, detail="username and password are required")
        user = db.authenticate(username, password)
        if user is None:
            raise HTTPException(status_code=401, detail="invalid credentials")
        token = db.create_auth_session(user.id)
        return _set_auth_cookie(JSONResponse({"user": {"id": user.id, "username": user.username}}), token)

    @app.post("/api/auth/logout")
    def auth_logout(request: Request):
        token = request.cookies.get(_cookie_name())
        if token:
            db.revoke_auth_session(token)
        response = JSONResponse({"ok": True})
        response.delete_cookie(_cookie_name())
        return response

    @app.get("/api/project")
    def get_project(request: Request):
        _require_user(request)
        root = get_project_root()
        return {"project_root": str(root), "workspace_root": str(settings.workspace_root)}

    @app.get("/api/browse")
    def browse(request: Request, path: str | None = None):
        _require_user(request)
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
    def choose_project(request: Request, payload: dict[str, str]):
        user = _require_user(request)
        path = (payload.get("path") or "").strip()
        if not path:
            raise HTTPException(status_code=400, detail="path is required")
        resolved = set_project_root(Path(path))
        db.upsert_project(user.id, str(resolved))
        return {"project_root": str(resolved)}

    @app.get("/api/tree")
    def tree(request: Request):
        _require_user(request)
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
    def list_sessions(request: Request, limit: int = 20):
        user = _require_user(request)
        return {"sessions": [item.to_dict() for item in store.list_recent(limit, user_id=user.id)]}

    @app.get("/api/file")
    def get_file(request: Request, path: str):
        _require_user(request)
        try:
            content = read_file(get_project_root(), path)
        except FileNotFoundError:
            raise HTTPException(status_code=404, detail="file not found")
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=str(exc))
        return {"path": path, "content": content}

    @app.post("/api/file")
    def save_file(request: Request, payload: dict[str, str]):
        _require_user(request)
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
    def create_session(request: Request, payload: dict[str, str], background_tasks: BackgroundTasks):
        user = _require_user(request)
        task = (payload.get("task") or "").strip()
        if not task:
            raise HTTPException(status_code=400, detail="task is required")
        mode = payload.get("mode") or "auto"
        project_root_value = (payload.get("project_root") or "").strip()
        project_root = Path(project_root_value) if project_root_value else get_project_root()
        record = store.create(task, str(project_root), mode, user_id=user.id)
        background_tasks.add_task(run_session, record.id)
        return {"session_id": record.id}

    @app.get("/api/sessions/{session_id}")
    def get_session(request: Request, session_id: str):
        user = _require_user(request)
        record = store.get(session_id)
        if record is None:
            raise HTTPException(status_code=404, detail="session not found")
        if record.user_id != user.id:
            raise HTTPException(status_code=404, detail="session not found")
        return record.to_dict()

    @app.get("/api/sessions/{session_id}/events")
    def stream_session_events(request: Request, session_id: str, since: int = 0):
        user = _require_user(request)
        record = store.get(session_id)
        if record is None:
            raise HTTPException(status_code=404, detail="session not found")
        if record.user_id != user.id:
            raise HTTPException(status_code=404, detail="session not found")

        def event_gen():
            last_idx = 0
            if since > 0:
                last_idx = since
            while True:
                events = store.get_events_since(session_id, last_idx)
                for ev in events:
                    payload = json.dumps(ev, ensure_ascii=False)
                    yield f"data: {payload}\n\n"
                    last_idx += 1

                rec = store.get(session_id)
                if rec is None:
                    break
                if rec.status in {"done", "error", "stopped"} and last_idx >= len(rec.events):
                    break

                store.wait_for_events(session_id, last_idx, timeout=15)

            yield 'data: {"kind": "end", "payload": {}}\n\n'

        return StreamingResponse(event_gen(), media_type="text/event-stream")

    @app.delete("/api/sessions/{session_id}")
    def delete_session(request: Request, session_id: str):
        user = _require_user(request)
        record = store.get(session_id)
        if record is None or record.user_id != user.id:
            raise HTTPException(status_code=404, detail="session not found")
        store.delete(session_id, user.id)
        cancel_events.pop(session_id, None)
        return {"ok": True}

    @app.post("/api/sessions/{session_id}/stop")
    def stop_session(request: Request, session_id: str):
        user = _require_user(request)
        record = store.get(session_id)
        if record is None or record.user_id != user.id:
            raise HTTPException(status_code=404, detail="session not found")
        event = cancel_events.setdefault(session_id, threading.Event())
        event.set()
        if record.status == "running":
            store.update(session_id, status="stopped", result="Terminated: stopped by user.")
        return {"ok": True}

    return app
