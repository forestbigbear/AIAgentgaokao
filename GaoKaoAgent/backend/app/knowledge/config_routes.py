import ipaddress
from typing import Literal

from fastapi import APIRouter, Depends, Request
from chromadb import PersistentClient
from chromadb.errors import NotFoundError

from app.api.responses import AppError, success
from app.api.schemas import ApiEnvelope
from app.core.config import get_settings
from app.core.model_config import FIELDS, ModelConfigInput, ModelConfigStore
from app.knowledge.models import ModelGateway
from app.knowledge.service import KnowledgeService


router = APIRouter(prefix="/api/v1/model-settings", tags=["model-settings"])
Kind = Literal["embedding", "llm"]


def local_settings_access(request: Request) -> None:
    host = request.client.host if request.client else ""
    try:
        local = ipaddress.ip_address(host).is_loopback
    except ValueError:
        local = host == "testclient"
    if not local or request.headers.get("X-Local-Settings") != "1":
        raise AppError(403, "LOCAL_ONLY", "Model settings are available only from this computer")


Access = Depends(local_settings_access)


def activate(request: Request, settings) -> None:
    previous = request.app.state.knowledge_service
    knowledge = KnowledgeService(
        previous.repository, ModelGateway(settings), settings, previous.storage_root
    )
    request.app.state.knowledge_service = knowledge
    request.app.state.workflow_service.nodes.knowledge = knowledge
    get_settings.cache_clear()


def check_embedding_change(request: Request, payload: ModelConfigInput) -> None:
    current = request.app.state.model_config_store.settings()
    if (current.embedding_api_base_url, current.embedding_model) == (payload.base_url, payload.model):
        return
    chroma_path = request.app.state.knowledge_service.storage_root / "chroma"
    if not chroma_path.exists():
        return
    client = PersistentClient(path=str(chroma_path))
    try:
        collection = client.get_collection("gaokao_knowledge")
    except NotFoundError:
        return
    if collection.count():
        raise AppError(
            409, "EMBEDDING_INDEX_EXISTS",
            "Existing knowledge vectors must be removed and reindexed before changing the Embedding service or model",
        )


@router.get("", response_model=ApiEnvelope, dependencies=[Access])
def get_model_settings(request: Request):
    store: ModelConfigStore = request.app.state.model_config_store
    return success(store.public(store.settings()))


@router.put("/{kind}", response_model=ApiEnvelope, dependencies=[Access])
def save_model_settings(kind: Kind, payload: ModelConfigInput, request: Request):
    store: ModelConfigStore = request.app.state.model_config_store
    if kind == "embedding":
        check_embedding_change(request, payload)
    settings = store.update(kind, payload)
    activate(request, settings)
    return success(store.public(settings)[kind])


@router.delete("/{kind}", response_model=ApiEnvelope, dependencies=[Access])
def clear_model_settings(kind: Kind, request: Request):
    store: ModelConfigStore = request.app.state.model_config_store
    settings = store.update(kind, None)
    activate(request, settings)
    return success(store.public(settings)[kind])


@router.post("/{kind}/test", response_model=ApiEnvelope, dependencies=[Access])
def test_model_settings(kind: Kind, request: Request, payload: ModelConfigInput | None = None):
    store: ModelConfigStore = request.app.state.model_config_store
    settings = store.settings()
    if payload:
        base_field, key_field, model_field = FIELDS[kind]
        key = payload.api_key or getattr(settings, key_field)
        if not key:
            raise AppError(422, "MODEL_KEY_REQUIRED", "API key is required for connection test")
        settings = settings.model_copy(update={
            base_field: payload.base_url, key_field: key, model_field: payload.model,
        })
    gateway = ModelGateway(settings)
    if kind == "embedding":
        vector = gateway.embed(["高考志愿模型连接测试"])[0]
        return success({"connected": True, "dimension": len(vector)})
    answer = gateway.answer("请根据资料简短回复。", "[1] 这是一条连接测试资料。")
    return success({"connected": True, "sample_answer": answer[:200]})
