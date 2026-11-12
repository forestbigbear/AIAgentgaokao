import json

import httpx
import pytest
from fastapi.testclient import TestClient
from starlette.requests import Request

from app.api.responses import AppError
from app.core.model_config import ModelConfigStore
from app.knowledge.config_routes import local_settings_access
from app.knowledge.service import KnowledgeService
from app.knowledge.vectors import VectorStore
from app.main import app


HEADERS = {"X-Local-Settings": "1"}


def test_model_settings_are_local_and_never_echo_keys(tmp_path):
    env = tmp_path / ".env"
    env.write_text("# existing configuration\nDB_PASSWORD=keep-me\n", encoding="utf-8")
    with TestClient(app) as client:
        client.app.state.model_config_store = ModelConfigStore(env)
        assert client.get("/api/v1/model-settings").status_code == 403
        assert client.put("/api/v1/model-settings/llm", json={
            "base_url": "https://example.test/v1", "model": "test-chat",
            "api_key": "test-key-do-not-leak",
        }).status_code == 403

        missing_key = client.put("/api/v1/model-settings/llm", headers=HEADERS, json={
            "base_url": "https://example.test/v1", "model": "test-chat",
        })
        assert missing_key.status_code == 422
        assert missing_key.json()["code"] == "MODEL_KEY_REQUIRED"

        saved = client.put("/api/v1/model-settings/llm", headers=HEADERS, json={
            "base_url": "https://example.test/v1/", "model": "test-chat",
            "api_key": "test-key-do-not-leak",
        })
        assert saved.status_code == 200, saved.text
        assert saved.json()["data"] == {
            "base_url": "https://example.test/v1", "model": "test-chat",
            "has_key": True, "ready": True,
        }
        assert "test-key-do-not-leak" not in saved.text
        listing = client.get("/api/v1/model-settings", headers=HEADERS)
        assert listing.status_code == 200
        assert "test-key-do-not-leak" not in listing.text
        assert listing.json()["data"]["llm"]["ready"]
        assert "DB_PASSWORD=keep-me" in env.read_text(encoding="utf-8")
        assert "# existing configuration" in env.read_text(encoding="utf-8")

        retained = client.put("/api/v1/model-settings/llm", headers=HEADERS, json={
            "base_url": "https://example.test/v1", "model": "test-chat-v2",
            "api_key": None,
        })
        assert retained.status_code == 200
        assert "test-key-do-not-leak" in env.read_text(encoding="utf-8")
        assert retained.json()["data"]["model"] == "test-chat-v2"

        cleared = client.delete("/api/v1/model-settings/llm", headers=HEADERS)
        assert cleared.status_code == 200
        assert not cleared.json()["data"]["has_key"]
        assert "test-key-do-not-leak" not in env.read_text(encoding="utf-8")
        assert "DB_PASSWORD=keep-me" in env.read_text(encoding="utf-8")


def test_model_settings_validate_url_and_test_without_saving(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text("DB_PASSWORD=keep-me\n", encoding="utf-8")
    calls = []

    def handler(request):
        calls.append((request.url.path, request.headers["authorization"], json.loads(request.content)))
        if request.url.path.endswith("/embeddings"):
            return httpx.Response(200, json={"data": [{"index": 0, "embedding": [0.1, 0.2]}]})
        return httpx.Response(200, json={"choices": [{"message": {"content": "连接正常。"}}]})

    real_client = httpx.Client
    monkeypatch.setattr(httpx, "Client", lambda **kwargs: real_client(
        transport=httpx.MockTransport(handler), **kwargs
    ))
    with TestClient(app) as client:
        client.app.state.model_config_store = ModelConfigStore(env)
        for url in ("http://example.test/v1", "https://user:secret@example.test/v1",
                    "https://example.test/v1/embeddings"):
            rejected = client.put("/api/v1/model-settings/embedding", headers=HEADERS, json={
                "base_url": url, "model": "test-embed", "api_key": "test-key",
            })
            assert rejected.status_code == 422, url
        assert "EMBEDDING_MODEL" not in env.read_text(encoding="utf-8")

        embedding = client.post("/api/v1/model-settings/embedding/test", headers=HEADERS, json={
            "base_url": "https://example.test/v1", "model": "test-embed", "api_key": "test-key",
        })
        chat = client.post("/api/v1/model-settings/llm/test", headers=HEADERS, json={
            "base_url": "https://example.test/v1", "model": "test-chat", "api_key": "test-key",
        })
        assert embedding.status_code == chat.status_code == 200
        assert embedding.json()["data"] == {"connected": True, "dimension": 2}
        assert chat.json()["data"]["sample_answer"] == "连接正常。"
        assert "test-key" not in embedding.text + chat.text
        assert [call[0] for call in calls] == ["/v1/embeddings", "/v1/chat/completions"]
        assert all(call[1] == "Bearer test-key" for call in calls)
        assert "EMBEDDING_MODEL" not in env.read_text(encoding="utf-8")


def test_remote_client_cannot_read_model_settings():
    request = Request({"type": "http", "client": ("192.0.2.10", 1234),
                       "headers": [(b"x-local-settings", b"1")]})
    with pytest.raises(AppError) as exc:
        local_settings_access(request)
    assert exc.value.code == "LOCAL_ONLY"


def test_saved_settings_activate_current_knowledge_and_workflow(tmp_path):
    env = tmp_path / ".env"
    env.write_text("DB_PASSWORD=keep-me\n", encoding="utf-8")
    with TestClient(app) as client:
        original = client.app.state.knowledge_service
        client.app.state.model_config_store = ModelConfigStore(env)
        client.app.state.knowledge_service = KnowledgeService(
            original.repository, original.gateway, original.settings, tmp_path,
        )
        try:
            response = client.put("/api/v1/model-settings/embedding", headers=HEADERS, json={
                "base_url": "https://example.test/v1", "model": "embed-v1", "api_key": "test-key",
            })
            assert response.status_code == 200, response.text
            active = client.app.state.knowledge_service
            assert active.gateway.embedding_ready
            assert active.gateway.settings.embedding_model == "embed-v1"
            assert client.app.state.workflow_service.nodes.knowledge is active

            response = client.put("/api/v1/model-settings/llm", headers=HEADERS, json={
                "base_url": "https://example.test/v1", "model": "chat-v1", "api_key": "chat-key",
            })
            assert response.status_code == 200, response.text
            active = client.app.state.knowledge_service
            assert active.gateway.chat_ready
            assert active.gateway.settings.llm_model == "chat-v1"
            assert client.app.state.workflow_service.nodes.knowledge is active
        finally:
            client.app.state.knowledge_service = original
            client.app.state.workflow_service.nodes.knowledge = original


def test_embedding_change_requires_empty_vector_index(tmp_path):
    env = tmp_path / ".env"
    env.write_text("DB_PASSWORD=keep-me\n", encoding="utf-8")
    with TestClient(app) as client:
        original = client.app.state.knowledge_service
        client.app.state.model_config_store = ModelConfigStore(env)
        client.app.state.knowledge_service = KnowledgeService(
            original.repository, original.gateway, original.settings, tmp_path,
        )
        try:
            first = {"base_url": "https://example.test/v1", "model": "embed-v1", "api_key": "key-v1"}
            assert client.put("/api/v1/model-settings/embedding", headers=HEADERS, json=first).status_code == 200
            vectors = VectorStore(tmp_path / "chroma", "embed-v1")
            vectors.upsert(1, [{"chunk_index": 0, "content": "test", "page_or_section": "1"}], [[0.1, 0.2]])
            changed = {"base_url": "https://other.test/v1", "model": "embed-v2", "api_key": "key-v2"}
            rejected = client.put("/api/v1/model-settings/embedding", headers=HEADERS, json=changed)
            assert rejected.status_code == 409
            assert rejected.json()["code"] == "EMBEDDING_INDEX_EXISTS"
            assert "embed-v1" in env.read_text(encoding="utf-8")
            assert "embed-v2" not in env.read_text(encoding="utf-8")

            vectors.delete(1)
            saved = client.put("/api/v1/model-settings/embedding", headers=HEADERS, json=changed)
            assert saved.status_code == 200, saved.text
            assert VectorStore(tmp_path / "chroma", "embed-v2").collection.count() == 0
        finally:
            client.app.state.knowledge_service = original
            client.app.state.workflow_service.nodes.knowledge = original
