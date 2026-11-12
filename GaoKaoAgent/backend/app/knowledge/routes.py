from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Form, Path, Request, UploadFile
from pydantic import BaseModel, Field, field_validator
from starlette.concurrency import run_in_threadpool

from app.api.responses import success
from app.api.schemas import ApiEnvelope, PageParams
from app.knowledge.service import KnowledgeService, MAX_UPLOAD_BYTES


router = APIRouter(prefix="/api/v1", tags=["knowledge"])


class Question(BaseModel):
    question: str = Field(min_length=2, max_length=1000)
    limit: int = Field(default=5, ge=1, le=10)

    @field_validator("question")
    @classmethod
    def nonblank_question(cls, value: str) -> str:
        if len(value.strip()) < 2:
            raise ValueError("question must contain at least two nonblank characters")
        return value.strip()


def get_service(request: Request) -> KnowledgeService:
    return request.app.state.knowledge_service


ServiceDep = Annotated[KnowledgeService, Depends(get_service)]


@router.post("/knowledge-documents", status_code=201, response_model=ApiEnvelope)
async def upload_document(
    service: ServiceDep,
    file: UploadFile = File(),
    document_type: Literal["policy", "charter", "major"] = Form(),
    source_name: str = Form(min_length=1, max_length=200),
    source_url: str | None = Form(default=None, max_length=1000),
    applicable_region: str | None = Form(default=None, max_length=100),
    applicable_year: int | None = Form(default=None, ge=1900, le=2100),
    published_at: datetime | None = Form(default=None),
):
    if not source_name.strip():
        from app.api.responses import AppError
        raise AppError(422, "VALIDATION_ERROR", "Source name must not be blank")
    try:
        content = await file.read(MAX_UPLOAD_BYTES + 1)
    finally:
        await file.close()
    metadata = {
        "document_type": document_type,
        "source_name": source_name.strip(),
        "source_url": source_url,
        "applicable_region": applicable_region,
        "applicable_year": applicable_year,
        "published_at": published_at,
    }
    document = await run_in_threadpool(service.upload, file.filename or "", content, metadata)
    return success(document, status=201)


@router.get("/knowledge-documents", response_model=ApiEnvelope)
def list_documents(
    service: ServiceDep,
    paging: Annotated[PageParams, Depends()],
    status: Literal["pending_embedding", "indexing", "ready", "failed"] | None = None,
):
    items, total = service.repository.list_documents(paging.page, paging.page_size, status)
    items = [service.public_document(item) for item in items]
    return success(items, meta={"page": paging.page, "page_size": paging.page_size, "total": total})


@router.get("/knowledge-documents/{document_id}", response_model=ApiEnvelope)
def get_document(document_id: Annotated[int, Path(gt=0)], service: ServiceDep):
    return success(service.get_document(document_id))


@router.post("/knowledge-documents/{document_id}/index", response_model=ApiEnvelope)
def index_document(document_id: Annotated[int, Path(gt=0)], service: ServiceDep):
    return success(service.index(document_id))


@router.delete("/knowledge-documents/{document_id}", response_model=ApiEnvelope)
def delete_document(document_id: Annotated[int, Path(gt=0)], service: ServiceDep):
    service.delete(document_id)
    return success({"deleted": True})


@router.post("/knowledge-search", response_model=ApiEnvelope)
def search_knowledge(payload: Question, service: ServiceDep):
    return success(service.search(payload.question.strip(), payload.limit))


@router.post("/knowledge-qa", response_model=ApiEnvelope)
def answer_knowledge(payload: Question, service: ServiceDep):
    return success(service.answer(payload.question.strip(), payload.limit))

