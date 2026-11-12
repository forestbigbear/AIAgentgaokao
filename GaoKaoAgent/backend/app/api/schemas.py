from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class PageParams(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


class ApiEnvelope(BaseModel):
    code: str
    message: str
    data: Any = None
    meta: dict | None = None


class StudentCreate(BaseModel):
    province: str = Field(min_length=1, max_length=50)
    exam_year: int = Field(ge=2020, le=2100)
    score: Decimal = Field(ge=0, le=999.9, max_digits=6, decimal_places=1)
    rank_no: int = Field(gt=0)
    subject_combination: str = Field(min_length=1, max_length=100)
    interests: list[str] = Field(default_factory=list, max_length=20)
    target_cities: list[str] = Field(default_factory=list, max_length=20)
    risk_preference: Literal["conservative", "balanced", "aggressive"] = "balanced"

    @field_validator("province", "subject_combination")
    @classmethod
    def nonblank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value

    @field_validator("interests", "target_cities")
    @classmethod
    def clean_list(cls, values: list[str] | None) -> list[str] | None:
        if values is None:
            return None
        cleaned = [item.strip() for item in values]
        if any(not item or len(item) > 100 for item in cleaned):
            raise ValueError("entries must be 1-100 nonblank characters")
        return cleaned


class StudentUpdate(StudentCreate):
    province: str | None = Field(default=None, min_length=1, max_length=50)
    exam_year: int | None = Field(default=None, ge=2020, le=2100)
    score: Decimal | None = Field(default=None, ge=0, le=999.9, max_digits=6, decimal_places=1)
    rank_no: int | None = Field(default=None, gt=0)
    subject_combination: str | None = Field(default=None, min_length=1, max_length=100)
    interests: list[str] | None = Field(default=None, max_length=20)
    target_cities: list[str] | None = Field(default=None, max_length=20)
    risk_preference: Literal["conservative", "balanced", "aggressive"] | None = None

    @model_validator(mode="after")
    def require_change(self):
        if not self.model_fields_set or any(getattr(self, field) is None for field in self.model_fields_set):
            raise ValueError("provide at least one non-null field")
        return self


class PlanItemCreate(BaseModel):
    university_id: int = Field(gt=0)
    major_id: int = Field(gt=0)
    tier: Literal["冲", "稳", "保"]
    match_score: Decimal = Field(ge=0, le=100, max_digits=5, decimal_places=2)
    reason_text: str = Field(min_length=1, max_length=10000)
    evidence: dict = Field(default_factory=dict)
    risk_level: Literal["low", "medium", "high", "unknown"] = "unknown"
    risk_notes: str | None = Field(default=None, max_length=10000)

    @field_validator("reason_text")
    @classmethod
    def reason_nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("must not be blank")
        return value.strip()


class PlanCreate(BaseModel):
    student_id: int = Field(gt=0)
    summary: str | None = Field(default=None, max_length=10000)
    items: list[PlanItemCreate] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def unique_candidates(self):
        pairs = [(item.university_id, item.major_id) for item in self.items]
        if len(set(pairs)) != len(pairs):
            raise ValueError("duplicate university/major candidate")
        return self

