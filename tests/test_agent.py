from pathlib import Path

from coding_agent.agent import CodingAgent
from coding_agent.session import SessionStore
from coding_agent.tools.registry import ToolRegistry


class FakeLLM:
    def __init__(self, responses):
        self.responses = responses
        self.calls = 0

    def complete(self, messages, tools, temperature=0.2):
        response = self.responses[self.calls]
        self.calls += 1
        return response


class FakeMessage:
    def __init__(self, content="", tool_calls=None):
        self.content = content
        self.tool_calls = tool_calls


class FakeToolCall:
    def __init__(self, call_id, name, arguments):
        self.id = call_id
        self.function = type("Fn", (), {"name": name, "arguments": arguments})


class FakeResponse:
    def __init__(self, message):
        self.choices = [type("Choice", (), {"message": message})]


def test_agent_runs_tool_then_finishes(tmp_path: Path):
    llm = FakeLLM(
        [
            FakeResponse(FakeMessage(tool_calls=[FakeToolCall("1", "write_file", '{"path":"x.txt","content":"ok"}')])),
            FakeResponse(FakeMessage(content="done")),
        ]
    )
    agent = CodingAgent(llm=llm, tools=ToolRegistry(tmp_path))
    result = agent.run("create a file")
    assert result.final_message == "done"
    assert (tmp_path / "x.txt").read_text() == "ok"

