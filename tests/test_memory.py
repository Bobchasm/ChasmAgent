from pathlib import Path

from coding_agent.memory import MemoryStore
from coding_agent.types import AgentEvent


def test_memory_persists(tmp_path: Path):
    memory = MemoryStore(tmp_path)
    memory.append_fact("use structured tools")
    memory.update_from_run(
        "add a feature",
        "done",
        [AgentEvent(kind="tool_call", payload={"name": "write_file", "args": {"path": "a.txt"}})],
    )
    rendered = memory.render()
    assert "done" in rendered
    assert "a.txt" in rendered
    assert memory.path.exists()

