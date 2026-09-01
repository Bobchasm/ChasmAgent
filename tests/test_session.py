from pathlib import Path

from coding_agent.session import SessionStore
from coding_agent.types import AgentEvent


def test_sessions_persist(tmp_path: Path):
    store = SessionStore(tmp_path)
    record = store.create("build feature", str(tmp_path), "auto")
    store.append_event(record.id, AgentEvent(kind="task", payload={"task": "build feature"}))

    reloaded = SessionStore(tmp_path)
    loaded = reloaded.get(record.id)
    assert loaded is not None
    assert loaded.task == "build feature"
    assert loaded.project_root == str(tmp_path)
    assert loaded.events[0]["kind"] == "task"
    assert reloaded.list_recent()[0].id == record.id
