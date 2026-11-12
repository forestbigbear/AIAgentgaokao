import json

import httpx
import pytest

from app.api.responses import AppError
from app.core.config import Settings
from app.knowledge.models import ModelGateway


def test_missing_model_configuration_is_explicit():
    gateway = ModelGateway(Settings(_env_file=None))
    with pytest.raises(AppError) as exc:
        gateway.embed(["政策"])
    assert exc.value.code == "EMBEDDING_NOT_CONFIGURED"


def test_openai_compatible_embedding_and_chat_contract(monkeypatch):
    calls = []

    def handler(request):
        calls.append((request.url.path, request.headers["authorization"], json.loads(request.content)))
        if request.url.path.endswith("/embeddings"):
            return httpx.Response(200, json={"data": [
                {"index": 1, "embedding": [0.0, 1.0]},
                {"index": 0, "embedding": [1.0, 0.0]},
            ]})
        return httpx.Response(200, json={"choices": [{"message": {"content": "依据资料[1]。"}}]})

    transport = httpx.MockTransport(handler)
    real_client = httpx.Client
    monkeypatch.setattr(httpx, "Client", lambda **kwargs: real_client(transport=transport, **kwargs))
    gateway = ModelGateway(Settings(
        _env_file=None,
        embedding_api_base_url="https://example.test/v1", embedding_api_key="test-key",
        embedding_model="test-embedding",
        llm_api_base_url="https://example.test/v1", llm_api_key="test-key", llm_model="test-chat",
    ))

    assert gateway.embed(["甲", "乙"]) == [[1.0, 0.0], [0.0, 1.0]]
    assert gateway.answer("选科是什么？", "[1] 文档片段") == "依据资料[1]。"
    assert [call[0] for call in calls] == ["/v1/embeddings", "/v1/chat/completions"]
    assert all(call[1] == "Bearer test-key" for call in calls)
    assert calls[0][2]["model"] == "test-embedding"
    assert calls[1][2]["model"] == "test-chat"

