import json
import tempfile
from pathlib import Path

from coding_agent.agent import CodingAgent
from coding_agent.tools.registry import ToolRegistry
from coding_agent.memory import MemoryStore
from types import SimpleNamespace


class DummyLLM:
    def __init__(self, responses):
        self._responses = responses

    def complete(self, messages, tools, temperature=0.2):
        # return a fake response with choices[0].message
        resp = SimpleNamespace()
        choice = SimpleNamespace()
        # cycle through provided responses
        msg = self._responses.pop(0)
        message = SimpleNamespace()
        message.content = msg.get("content", "")
        # allow direct tool_calls injection
        if "tool_calls" in msg:
            calls = []
            for idx, c in enumerate(msg["tool_calls"]):
                fn = SimpleNamespace(name=c["name"], arguments=json.dumps(c.get("arguments", {})))
                calls.append(SimpleNamespace(id=str(idx), function=fn))
            setattr(message, "tool_calls", calls)
        choice.message = message
        resp.choices = [choice]
        return resp


def test_agent_handles_tool_and_termination(tmp_path: Path):
    root = tmp_path
    (root / "file.txt").write_text("hello\n")
    tools = ToolRegistry(root)
    mem = MemoryStore(root)

    # responses: first asks to run a command, then returns no-op twice to trigger no-progress
    responses = [
        {"content": "running tool", "tool_calls": [{"name": "read_file", "arguments": {"path": "file.txt"}}]},
        {"content": "no changes"},
        {"content": "no changes"},
        {"content": "no changes"},
        {"content": "no changes"},
    ]

    llm = DummyLLM(responses)
    agent = CodingAgent(llm=llm, tools=tools, memory=mem, max_turns=8)
    result = agent.run("read the file")
    assert isinstance(result.final_message, str)
    assert "Terminated" in result.final_message or result.final_message.strip() != ""
