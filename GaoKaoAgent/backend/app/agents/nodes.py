from pydantic import ValidationError

from app.api.responses import AppError
from app.api.schemas import StudentCreate
from app.agents.repository import WorkflowRepository
from app.agents.rules import assess_risks, build_recommendations, evaluate_candidates, subjects_in
from app.agents.scoring import ScoringPolicy
from app.agents.state import WorkflowState
from app.knowledge.service import KnowledgeService


class AgentNodes:
    def __init__(self, repository: WorkflowRepository, knowledge: KnowledgeService,
                 scoring: ScoringPolicy):
        self.repository = repository
        self.knowledge = knowledge
        self.scoring = scoring

    def execute(self, name: str, operation, state: WorkflowState, inputs: dict) -> dict:
        run_id = state["workflow_run_id"]
        self.repository.add_event(run_id, name, "running", inputs)
        try:
            updates, output = operation(state)
        except Exception as exc:
            self.repository.add_event(run_id, name, "failed", inputs,
                                      error=f"{type(exc).__name__}: {exc}"[:1000])
            raise
        self.repository.add_event(run_id, name, "completed", inputs, output)
        updates["agent_events"] = [{"agent_name": name, "status": "completed",
                                    "input": inputs, "output": output}]
        return updates

    def student_profile(self, state: WorkflowState) -> dict:
        student = state["student_input"]
        inputs = {key: student.get(key) for key in (
            "province", "exam_year", "score", "rank_no", "subject_combination",
            "interests", "target_cities", "risk_preference",
        )}
        return self.execute("student_profile", self._student_profile, state, inputs)

    def _student_profile(self, state: WorkflowState) -> tuple[dict, dict]:
        student = state["student_input"]
        try:
            validated = StudentCreate.model_validate(student)
        except ValidationError as exc:
            issues = [".".join(map(str, issue["loc"])) + ": " + issue["msg"]
                      for issue in exc.errors()]
            self.repository.save_profile(student["id"], {}, issues)
            return {"student_profile": {}, "validation_issues": issues,
                    "errors": issues, "final_status": "invalid_input"}, {"issues": issues}
        subjects = sorted(subjects_in(validated.subject_combination))
        issues = []
        if not subjects:
            issues.append("选科组合无法识别，需要明确物理、化学、生物、历史、政治、地理或技术")
        if not validated.interests:
            issues.append("未填写专业兴趣，兴趣评分为 0")
        if not validated.target_cities:
            issues.append("未填写目标城市，城市评分为 0")
        profile = {
            "student_id": student["id"], "province": validated.province,
            "exam_year": validated.exam_year, "score": float(validated.score),
            "rank_no": validated.rank_no, "subjects": subjects,
            "interests": validated.interests, "target_cities": validated.target_cities,
            "risk_preference": validated.risk_preference,
        }
        self.repository.save_profile(student["id"], profile, issues)
        errors = issues[:1] if not subjects else []
        updates = {"student_profile": profile, "validation_issues": issues,
                   "errors": errors, "final_status": "invalid_input" if errors else "running"}
        return updates, {"profile": profile, "issues": issues}

    def task_planning(self, state: WorkflowState) -> dict:
        inputs = {"profile": state["student_profile"], "adjustment_count": state["adjustment_count"],
                  "previous_risk": state.get("risk_report", {}).get("tier_counts")}
        return self.execute("task_planning", self._task_planning, state, inputs)

    def _task_planning(self, state: WorkflowState) -> tuple[dict, dict]:
        profile = state["student_profile"]
        years = min(2 + 2 * state["adjustment_count"], 6)
        plan = {
            "province": profile["province"], "exam_year": profile["exam_year"],
            "history_years": years, "candidate_limit": 500,
            "knowledge_query": (
                f"{profile['province']} {profile['exam_year']} 招生政策 选科要求 "
                + " ".join(profile["interests"])
            ).strip(),
            "steps": ["mysql_admission_plans", "mysql_admission_records", "rag_search",
                      "subject_filter", "weighted_match", "tier_plan", "risk_review"],
        }
        return {"task_plan": plan}, plan

    def data_retrieval(self, state: WorkflowState) -> dict:
        return self.execute("data_retrieval", self._data_retrieval, state,
                            {"task_plan": state["task_plan"]})

    def _data_retrieval(self, state: WorkflowState) -> tuple[dict, dict]:
        plan = state["task_plan"]
        candidates, truncated = self.repository.retrieve_candidates(
            plan["province"], plan["exam_year"], plan["history_years"],
            plan["candidate_limit"],
        )
        gaps = []
        if not candidates:
            gaps.append("该省份和报考年份没有招生计划")
        if truncated:
            gaps.append("招生计划超过本次检索上限，结果不完整")
        try:
            knowledge = self.knowledge.search(plan["knowledge_query"], 5)
            if not knowledge:
                gaps.append("知识库没有检索到相关政策或专业资料")
        except AppError as exc:
            knowledge = []
            gaps.append(f"RAG 检索不可用（{exc.code}）")
        updates = {
            "structured_data": {"candidates": candidates, "truncated": truncated},
            "knowledge_evidence": knowledge, "data_gaps": gaps,
        }
        return updates, {"mysql_candidate_count": len(candidates),
                         "history_count": sum(len(row["history"]) for row in candidates),
                         "rag_passage_count": len(knowledge), "data_gaps": gaps}

    def university_matching(self, state: WorkflowState) -> dict:
        return self.execute("university_matching", self._university_matching, state,
                            {"candidate_count": len(state["structured_data"]["candidates"]),
                             "subjects": state["student_profile"]["subjects"],
                             "interests": state["student_profile"]["interests"],
                             "target_cities": state["student_profile"]["target_cities"]})

    def _university_matching(self, state: WorkflowState) -> tuple[dict, dict]:
        matches, gaps, unranked = evaluate_candidates(
            state["student_profile"], state["structured_data"]["candidates"], self.scoring
        )
        return {"match_results": matches, "unranked_candidates": unranked,
                "data_gaps": state["data_gaps"] + gaps}, {
            "matched_count": len(matches), "unranked_count": len(unranked),
            "excluded_or_missing_count": len(gaps), "scoring_weights": self.scoring.weights(),
            "scores": [{"university": item["university_name"], "major": item["major_name"],
                        "tier": item["tier"], "score": item["match_score"],
                        "breakdown": item["score_breakdown"]} for item in matches[:10]],
        }

    def recommendation(self, state: WorkflowState) -> dict:
        return self.execute("recommendation", self._recommendation, state,
                            {"match_count": len(state["match_results"]),
                             "risk_preference": state["student_profile"]["risk_preference"]})

    def _recommendation(self, state: WorkflowState) -> tuple[dict, dict]:
        items = build_recommendations(state["student_profile"], state["match_results"])
        return {"recommendations": items}, {
            "item_count": len(items), "tier_counts": {
                tier: sum(item["tier"] == tier for item in items) for tier in ("冲", "稳", "保")
            }, "all_evidence_from_database": True,
        }

    def risk_assessment(self, state: WorkflowState) -> dict:
        return self.execute("risk_assessment", self._risk_assessment, state,
                            {"item_count": len(state["recommendations"]),
                             "data_gaps": state["data_gaps"],
                             "adjustment_count": state["adjustment_count"]})

    def _risk_assessment(self, state: WorkflowState) -> tuple[dict, dict]:
        report = assess_risks(
            state["student_profile"], state["recommendations"],
            state["match_results"], state["data_gaps"],
            state["adjustment_count"], state["max_adjustments"],
            state["task_plan"]["history_years"], self.scoring,
        )
        return {"risk_report": report}, report
