from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Request

from app.api.responses import success
from app.api.schemas import ApiEnvelope, PageParams, PlanCreate, StudentCreate, StudentUpdate
from app.db.repository import Repository
from app.services.basic import BasicService


router = APIRouter(prefix="/api/v1")
PositiveId = Annotated[int, Path(gt=0)]
YearFilter = Annotated[int | None, Query(ge=2020, le=2100)]


def get_repository(request: Request) -> Repository:
    return Repository(request.app.state.database)


RepositoryDep = Annotated[Repository, Depends(get_repository)]


def get_service(repository: RepositoryDep) -> BasicService:
    return BasicService(repository)


ServiceDep = Annotated[BasicService, Depends(get_service)]


def list_response(items: list[dict], total: int, paging: PageParams):
    return success(items, meta={"page": paging.page, "page_size": paging.page_size, "total": total})


@router.post("/students", status_code=201, response_model=ApiEnvelope, tags=["students"])
def create_student(payload: StudentCreate, service: ServiceDep):
    return success(service.create_student(payload), status=201)


@router.get("/students", response_model=ApiEnvelope, tags=["students"])
def list_students(repository: RepositoryDep, paging: Annotated[PageParams, Depends()]):
    items, total = repository.list_students(paging.page, paging.page_size)
    return list_response(items, total, paging)


@router.get("/students/{student_id}", response_model=ApiEnvelope, tags=["students"])
def get_student(student_id: PositiveId, service: ServiceDep):
    return success(service.get_student(student_id))


@router.patch("/students/{student_id}", response_model=ApiEnvelope, tags=["students"])
def update_student(student_id: PositiveId, payload: StudentUpdate, service: ServiceDep):
    return success(service.update_student(student_id, payload))


@router.get("/universities", response_model=ApiEnvelope, tags=["catalog"])
def list_universities(
    repository: RepositoryDep, paging: Annotated[PageParams, Depends()],
    province: str | None = Query(default=None, max_length=50),
    year: YearFilter = None,
    name: str | None = Query(default=None, max_length=200),
    city: str | None = Query(default=None, max_length=50),
):
    items, total = repository.list_catalog(
        "universities", {"province": province, "year": year, "name": name, "city": city},
        paging.page, paging.page_size,
    )
    return list_response(items, total, paging)


@router.get("/majors", response_model=ApiEnvelope, tags=["catalog"])
def list_majors(
    repository: RepositoryDep, paging: Annotated[PageParams, Depends()],
    university_id: int | None = Query(default=None, gt=0),
    province: str | None = Query(default=None, max_length=50),
    year: YearFilter = None,
    name: str | None = Query(default=None, max_length=200),
    subject: str | None = Query(default=None, max_length=100),
):
    items, total = repository.list_catalog(
        "majors", {"university_id": university_id, "province": province, "year": year,
                   "name": name, "subject": subject}, paging.page, paging.page_size,
    )
    return list_response(items, total, paging)


@router.get("/admission-plans", response_model=ApiEnvelope, tags=["catalog"])
def list_admission_plans(
    repository: RepositoryDep, paging: Annotated[PageParams, Depends()],
    province: str | None = Query(default=None, max_length=50),
    year: YearFilter = None,
    university_id: int | None = Query(default=None, gt=0),
    major_id: int | None = Query(default=None, gt=0),
    university_name: str | None = Query(default=None, max_length=200),
    major_name: str | None = Query(default=None, max_length=200),
    subject: str | None = Query(default=None, max_length=100),
):
    items, total = repository.list_catalog(
        "admission_plans", {"province": province, "year": year,
                            "university_id": university_id, "major_id": major_id,
                            "university_name": university_name, "major_name": major_name,
                            "subject": subject}, paging.page, paging.page_size,
    )
    return list_response(items, total, paging)


@router.get("/admission-records", response_model=ApiEnvelope, tags=["catalog"])
def list_admission_records(
    repository: RepositoryDep, paging: Annotated[PageParams, Depends()],
    province: str | None = Query(default=None, max_length=50),
    year: YearFilter = None,
    university_id: int | None = Query(default=None, gt=0),
    major_id: int | None = Query(default=None, gt=0),
    university_name: str | None = Query(default=None, max_length=200),
    major_name: str | None = Query(default=None, max_length=200),
):
    items, total = repository.list_catalog(
        "admission_records", {"province": province, "year": year,
                              "university_id": university_id, "major_id": major_id,
                              "university_name": university_name, "major_name": major_name},
        paging.page, paging.page_size,
    )
    return list_response(items, total, paging)


@router.post("/plans", status_code=201, response_model=ApiEnvelope, tags=["plans"])
def save_plan(payload: PlanCreate, service: ServiceDep):
    return success(service.save_plan(payload), status=201)


@router.get("/plans", response_model=ApiEnvelope, tags=["plans"])
def list_plans(
    service: ServiceDep, paging: Annotated[PageParams, Depends()],
    student_id: int = Query(gt=0),
):
    items, total = service.list_plans(student_id, paging.page, paging.page_size)
    return list_response(items, total, paging)


@router.get("/plans/{plan_id}", response_model=ApiEnvelope, tags=["plans"])
def get_plan(plan_id: PositiveId, service: ServiceDep):
    return success(service.get_plan(plan_id))

