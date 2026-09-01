from pathlib import Path

from fastapi.testclient import TestClient

from coding_agent.config import AgentSettings
from coding_agent.server import build_app


def test_server_routes(tmp_path: Path):
    (tmp_path / "sample.txt").write_text("hello", encoding="utf-8")
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text("internal", encoding="utf-8")
    settings = AgentSettings(
        workspace_root=tmp_path,
        model="test-model",
        base_url="http://localhost/v1",
        api_key="test-key",
    )
    client = TestClient(build_app(settings))
    assert client.get("/").status_code == 200
    tree = client.get("/api/tree").json()
    assert "sample.txt" in tree["files"]
    assert all(".git" not in item for item in tree["files"])
    file_resp = client.get("/api/file", params={"path": "sample.txt"})
    assert file_resp.status_code == 200
    assert file_resp.json()["content"] == "hello"
    save_resp = client.post("/api/file", json={"path": "nested/new.txt", "content": "world"})
    assert save_resp.status_code == 200
    assert (tmp_path / "nested/new.txt").read_text(encoding="utf-8") == "world"
