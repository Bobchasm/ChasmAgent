from pathlib import Path

from fastapi.testclient import TestClient

from coding_agent.config import AgentSettings
from coding_agent.server import build_app


class DummyMessage:
    def __init__(self, content="done", tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls


class DummyResponse:
    def __init__(self, message):
        self.choices = [type("Choice", (), {"message": message})]


class DummyLLM:
    def complete(self, messages, tools, temperature=0.2):
        return DummyResponse(DummyMessage())


def test_server_routes(tmp_path: Path):
    (tmp_path / "sample.txt").write_text("hello", encoding="utf-8")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text("internal", encoding="utf-8")
    settings = AgentSettings(
        workspace_root=tmp_path,
        data_dir=tmp_path / ".data",
        model="test-model",
        base_url="http://localhost/v1",
        api_key="test-key",
    )
    client = TestClient(build_app(settings))
    assert client.get("/").status_code == 200
    bootstrap = client.post("/api/auth/bootstrap")
    assert bootstrap.status_code == 200
    project = client.get("/api/project").json()
    assert project["project_root"] == str(tmp_path)
    browse = client.get("/api/browse", params={"path": str(tmp_path)}).json()
    assert browse["path"] == str(tmp_path)
    tree = client.get("/api/tree").json()
    assert "sample.txt" in tree["files"]
    assert all(".git" not in item for item in tree["files"])
    file_resp = client.get("/api/file", params={"path": "sample.txt"})
    assert file_resp.status_code == 200
    assert file_resp.json()["content"] == "hello"
    project_resp = client.post("/api/project", json={"path": str(tmp_path)})
    assert project_resp.status_code == 200
    save_resp = client.post("/api/file", json={"path": "nested/new.txt", "content": "world"})
    assert save_resp.status_code == 200
    assert (tmp_path / "nested/new.txt").read_text(encoding="utf-8") == "world"


def test_session_roundtrip(tmp_path: Path, monkeypatch):
    from coding_agent import server as server_module

    monkeypatch.setattr(server_module, "_llm", lambda settings: DummyLLM())
    settings = AgentSettings(
        workspace_root=tmp_path,
        data_dir=tmp_path / ".data",
        model="test-model",
        base_url="http://localhost/v1",
        api_key="test-key",
    )
    client = TestClient(build_app(settings))
    client.post("/api/auth/bootstrap")
    resp = client.post("/api/sessions", json={"task": "say hi", "mode": "auto", "project_root": str(tmp_path)})
    assert resp.status_code == 200
    session_id = resp.json()["session_id"]
    record = client.get(f"/api/sessions/{session_id}").json()
    assert record["status"] == "done"
    assert record["result"] == "done"
    assert record["project_root"] == str(tmp_path)
    assert client.delete(f"/api/sessions/{session_id}").status_code == 200
    assert client.get(f"/api/sessions/{session_id}").status_code == 404
