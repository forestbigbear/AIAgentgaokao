from app.api.responses import AppError
from app.api.schemas import PlanCreate, StudentCreate, StudentUpdate
from app.db.repository import Repository


class BasicService:
    def __init__(self, repository: Repository):
        self.repository = repository

    def get_student(self, student_id: int) -> dict:
        student = self.repository.get_student(student_id)
        if student is None:
            raise AppError(404, "NOT_FOUND", "Student not found")
        return student

    def create_student(self, payload: StudentCreate) -> dict:
        return self.repository.create_student(payload.model_dump())

    def update_student(self, student_id: int, payload: StudentUpdate) -> dict:
        self.get_student(student_id)
        student = self.repository.update_student(student_id, payload.model_dump(exclude_unset=True))
        if student is None:
            raise AppError(404, "NOT_FOUND", "Student not found")
        return student

    def save_plan(self, payload: PlanCreate) -> dict:
        student = self.get_student(payload.student_id)
        result = self.repository.create_plan(student, payload.model_dump())
        if result is None:
            raise AppError(404, "NOT_FOUND", "Student not found")
        if "invalid_candidate" in result:
            raise AppError(
                422, "INVALID_CANDIDATE",
                "Candidate has no admission plan for the student's province and exam year",
            )
        return result

    def get_plan(self, plan_id: int) -> dict:
        plan = self.repository.get_plan(plan_id)
        if plan is None:
            raise AppError(404, "NOT_FOUND", "Plan not found")
        return plan

    def list_plans(self, student_id: int, page: int, page_size: int) -> tuple[list[dict], int]:
        self.get_student(student_id)
        return self.repository.list_plans(student_id, page, page_size)

