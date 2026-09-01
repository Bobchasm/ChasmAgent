from coding_agent.llm import LLMClient


def test_llm_client_initializes():
    client = LLMClient(api_key="test-key", base_url="https://dashscope.aliyuncs.com/compatible-mode/v1", model="qwen3.8-flash")
    assert hasattr(client, "_client")

