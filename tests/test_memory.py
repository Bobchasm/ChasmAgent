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
        reflection={
            "summary": "finished the change",
            "lessons": ["keep edits small"],
            "next_steps": ["add tests"],
            "files": ["a.txt"],
            "decisions": ["use the same session"],
            "preferences": ["prefer concise edits"],
        },
    )
    rendered = memory.render()
    assert "finished the change" in rendered
    assert "a.txt" in rendered
    assert "keep edits small" in rendered
    assert "add tests" in rendered
    assert "prefer concise edits" in rendered
    assert memory.path.exists()
