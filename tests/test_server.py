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
    folder_resp = client.post("/api/folder", json={"path": "nested/dir"})
    assert folder_resp.status_code == 200
    assert (tmp_path / "nested/dir").is_dir()
    tree_after_folder = client.get("/api/tree").json()
    assert any(item["path"] == "nested" and item["kind"] == "dir" for item in tree_after_folder["entries"])
    assert any(item["path"] == "nested/dir" and item["kind"] == "dir" for item in tree_after_folder["entries"])
    delete_file = client.delete("/api/path", params={"path": "sample.txt"})
    assert delete_file.status_code == 200
    assert not (tmp_path / "sample.txt").exists()
    delete_dir = client.delete("/api/path", params={"path": "nested"})
    assert delete_dir.status_code == 200
    assert not (tmp_path / "nested").exists()
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


def test_session_can_append_message(tmp_path: Path, monkeypatch):
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
    create = client.post("/api/sessions", json={"task": "say hi", "mode": "auto", "project_root": str(tmp_path)})
    session_id = create.json()["session_id"]
    first = client.get(f"/api/sessions/{session_id}").json()
    assert any(message["role"] == "user" and message["content"] == "say hi" for message in first["messages"])
    first_len = len(first["messages"])
    reply = client.post(f"/api/sessions/{session_id}/message", json={"content": "update the code"})
    assert reply.status_code == 200
    updated = client.get(f"/api/sessions/{session_id}").json()
    assert len(updated["messages"]) > first_len
    assert any(message["role"] == "user" and message["content"] == "update the code" for message in updated["messages"])
    assert updated["task"] == "update the code"


def test_session_title_is_short(tmp_path: Path, monkeypatch):
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
    resp = client.post(
        "/api/sessions",
        json={
            "task": "你好，请你编写一套使用cpp语言的数组排序程序，请遵循我给你的项目结构和命名规范，路径是/home/bobchasm/test",
            "mode": "auto",
            "project_root": str(tmp_path),
        },
    )
    session_id = resp.json()["session_id"]
    record = client.get(f"/api/sessions/{session_id}").json()
    assert record["title"]
    assert len(record["title"]) <= 18


def test_session_title_can_be_renamed(tmp_path: Path, monkeypatch):
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
    resp = client.post(
        "/api/sessions",
        json={"task": "write a sorter", "mode": "auto", "project_root": str(tmp_path)},
    )
    session_id = resp.json()["session_id"]
    renamed = client.patch(f"/api/sessions/{session_id}", json={"title": "My Sorter"})
    assert renamed.status_code == 200
    record = client.get(f"/api/sessions/{session_id}").json()
    assert record["title"] == "My Sorter"


def test_session_title_is_generated_once(tmp_path: Path, monkeypatch):
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
    create = client.post("/api/sessions", json={"task": "write a sorter", "mode": "auto", "project_root": str(tmp_path)})
    session_id = create.json()["session_id"]
    first = client.get(f"/api/sessions/{session_id}").json()["title"]
    assert first
    client.post(f"/api/sessions/{session_id}/message", json={"content": "improve the sorter"})
    second = client.get(f"/api/sessions/{session_id}").json()["title"]
    assert second == first
