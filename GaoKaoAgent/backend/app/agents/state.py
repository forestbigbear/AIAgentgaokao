from operator import add
from typing import Annotated, TypedDict


class WorkflowState(TypedDict, total=False):
    workflow_run_id: int
    student_input: dict
    student_profile: dict
    validation_issues: list[str]
    task_plan: dict
    structured_data: dict
    knowledge_evidence: list[dict]
    data_gaps: list[str]
    match_results: list[dict]
    unranked_candidates: list[dict]
    recommendations: list[dict]
    risk_report: dict
    adjustment_count: int
    max_adjustments: int
    agent_events: Annotated[list[dict], add]
    errors: Annotated[list[str], add]
    final_status: str
