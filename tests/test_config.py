from coding_agent.config import AgentSettings


def test_dashscope_env(monkeypatch, tmp_path):
    monkeypatch.setenv("CHASM_PROVIDER", "dashscope")
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test-dashscope-key")
    monkeypatch.setenv("OPENAI_MODEL", "qwen3.8-flash")
    settings = AgentSettings.from_env(str(tmp_path))
    assert settings.provider == "dashscope"
    assert settings.api_key == "test-dashscope-key"
    assert settings.base_url == "https://dashscope.aliyuncs.com/compatible-mode/v1"
    assert settings.model == "qwen3.8-flash"

