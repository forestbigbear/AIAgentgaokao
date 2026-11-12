import logging

from langgraph.graph import END, StateGraph

from app.agents.nodes import AgentNodes
from app.agents.repository import WorkflowRepository
from app.agents.scoring import ScoringPolicy
from app.agents.state import WorkflowState
from app.api.responses import AppError
from app.knowledge.service import KnowledgeService


logger = logging.getLogger(__name__)


class WorkflowService:
    def __init__(self, repository: WorkflowRepository, knowledge: KnowledgeService,
                 scoring: ScoringPolicy | None = None):
        self.repository = repository
        self.nodes = AgentNodes(repository, knowledge, scoring or ScoringPolicy())
        graph = StateGraph(WorkflowState)
        for name in (
            "student_profile", "task_planning", "data_retrieval",
            "university_matching", "recommendation", "risk_assessment",
        ):
            graph.add_node(name, getattr(self.nodes, name))
        graph.add_node("adjustment", self._adjustment)
        graph.set_entry_point("student_profile")
        graph.add_conditional_edges(
            "student_profile", lambda state: "stop" if state.get("errors") else "continue",
            {"stop": END, "continue": "task_planning"},
        )
        for start, end in (
            ("task_planning", "data_retrieval"),
            ("data_retrieval", "university_matching"),
            ("university_matching", "recommendation"),
            ("recommendation", "risk_assessment"),
        ):
            graph.add_edge(start, end)
        graph.add_conditional_edges(
            "risk_assessment",
            lambda state: "adjust" if state["risk_report"]["needs_adjustment"] else "finish",
            {"adjust": "adjustment", "finish": END},
        )
        graph.add_edge("adjustment", "task_planning")
        self.graph = graph.compile()

    def _adjustment(self, state: WorkflowState) -> dict:
        count = state["adjustment_count"] + 1
        self.repository.add_event(
            state["workflow_run_id"], "adjustment", "completed",
            {"previous_count": state["adjustment_count"],
             "reason": state["risk_report"]["tier_counts"]},
            {"adjustment_count": count, "next_node": "task_planning"},
        )
        return {"adjustment_count": count}

    def start(self, student_id: int, max_adjustments: int = 2) -> dict:
        student = self.repository.get_student(student_id)
        if student is None:
            raise AppError(404, "NOT_FOUND", "Student not found")
        run_id = self.repository.create_run(student_id, max_adjustments)
        try:
            result = self.graph.invoke({
                "workflow_run_id": run_id, "student_input": student,
                "adjustment_count": 0, "max_adjustments": max_adjustments,
                "agent_events": [], "errors": [],
            }, config={"recursion_limit": 32})
            if result.get("errors"):
                status = "invalid_input"
            elif not result.get("recommendations"):
                status = "insufficient_data"
            elif any(count == 0 for count in result["risk_report"]["tier_counts"].values()):
                status = "partial"
            else:
                status = "completed"
            summary = (
                "仅供志愿决策辅助，不保证录取。"
                + (" 当前包含模拟数据，不能用于实际填报。" if any(
                    item["evidence"]["simulated"] for item in result.get("recommendations", [])
                ) else "")
            )
            plan_id = self.repository.save_plan(
                run_id, student_id, student["exam_year"],
                result.get("recommendations", []), summary,
            )
            self.repository.finish(run_id, status, result["adjustment_count"],
                                   "; ".join(result.get("errors", [])) or None)
            return {
                "run": self.repository.get_run(run_id), "plan_id": plan_id,
                "student_profile": result.get("student_profile"),
                "task_plan": result.get("task_plan"),
                "knowledge_evidence": result.get("knowledge_evidence", []),
                "match_results": result.get("match_results", []),
                "unranked_candidates": result.get("unranked_candidates", []),
                "recommendations": result.get("recommendations", []),
                "risk_report": result.get("risk_report"),
                "data_gaps": result.get("data_gaps", []),
                "agent_events": result.get("agent_events", []),
                "errors": result.get("errors", []),
            }
        except Exception as exc:
            logger.exception("Workflow %s failed", run_id)
            self.repository.finish(run_id, "failed", 0, f"{type(exc).__name__}: {exc}"[:1000])
            raise AppError(500, "WORKFLOW_FAILED", f"Workflow {run_id} failed; inspect its events") from exc

    def get_run(self, run_id: int) -> dict:
        run = self.repository.get_run(run_id)
        if run is None:
            raise AppError(404, "NOT_FOUND", "Workflow run not found")
        return run
