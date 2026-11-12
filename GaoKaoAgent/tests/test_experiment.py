from scripts.experiment import agent_risk_codes, metrics, traditional_rule
from app.agents.scoring import ScoringPolicy


def candidate(identifier, ratio, name):
    return {
        "plan_id": identifier, "university_id": identifier, "major_id": identifier,
        "university_name": f"模拟院校{identifier}", "major_name": name,
        "category": "模拟数据", "plan_province": "上海", "plan_year": 2026,
        "university_year": 2026, "major_year": 2026,
        "plan_subjects": "物理", "major_subjects": "物理",
        "plan_source": "模拟数据", "university_source": "模拟数据",
        "major_source": "模拟数据",
        "history": [{"min_rank_no": int(10000 * ratio), "exam_year": 2025,
                     "source_name": "模拟数据"}],
    }


def test_traditional_rule_uses_rank_not_interests_and_reports_basic_risks():
    profile = {"province": "上海", "exam_year": 2026, "rank_no": 10000,
               "subjects": ["物理", "化学"], "interests": ["计算机"],
               "risk_preference": "conservative"}
    rows = [candidate(1, 0.65, "模拟计算机"), candidate(2, 0.85, "模拟软件")]
    excluded = candidate(3, 1.1, "模拟历史")
    excluded["plan_subjects"] = excluded["major_subjects"] = "历史"
    rows.append(excluded)

    selected, detected = traditional_rule(profile, rows, ScoringPolicy())

    assert [item["major_id"] for item in selected] == [2]
    assert detected == {"subject_exclusion", "simulated_source", "single_history_year",
                        "missing_tier"}
    measured = metrics(profile, rows, selected, detected, embedding_ready=False)
    assert measured["hard_conditions_satisfied"] == 1
    assert measured["preference_hits"] == 0
    assert measured["risk_true_positives"] == 4
    assert "knowledge_unavailable" in measured["reference_risks"]


def test_agent_risk_categories_are_taken_from_reported_issues():
    issues = ["RAG 检索不可用（EMBEDDING_NOT_CONFIGURED）",
              "模拟院校/模拟专业 使用模拟数据", "志愿梯度缺少：保"]
    assert agent_risk_codes({"issues": issues}) == {
        "knowledge_unavailable", "simulated_source", "missing_tier",
    }
