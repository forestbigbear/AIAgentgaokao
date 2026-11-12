from typing import Annotated

from fastapi import APIRouter, Depends, Path, Request
from pydantic import BaseModel, Field

from app.agents.workflow import WorkflowService
from app.api.responses import success
from app.api.schemas import ApiEnvelope


router = APIRouter(prefix="/api/v1", tags=["workflows"])


class WorkflowStart(BaseModel):
    student_id: int = Field(gt=0)
    max_adjustments: int = Field(default=2, ge=0, le=2)


def get_service(request: Request) -> WorkflowService:
    return request.app.state.workflow_service


ServiceDep = Annotated[WorkflowService, Depends(get_service)]


@router.post("/workflow-runs", status_code=201, response_model=ApiEnvelope)
def start_workflow(payload: WorkflowStart, service: ServiceDep):
    return success(service.start(payload.student_id, payload.max_adjustments), status=201)


@router.get("/workflow-runs/{run_id}", response_model=ApiEnvelope)
def get_workflow(run_id: Annotated[int, Path(gt=0)], service: ServiceDep):
    return success(service.get_run(run_id))
