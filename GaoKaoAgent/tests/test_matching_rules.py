"""Deterministic matching rules, with every admission value marked as simulated."""

import pytest
from pydantic import ValidationError

from app.agents.rules import build_recommendations, evaluate_candidates, meets_subjects
from app.agents.scoring import ScoringPolicy
from app.core.config import Settings


PROFILE = {
    "province": "上海", "exam_year": 2026, "rank_no": 10000,
    "subjects": ["物理", "化学"], "interests": ["计算机"],
    "target_cities": ["上海"], "risk_preference": "balanced",
}


def candidate(ranks=(9000,), requirement="物理、化学"):
    return {
        "plan_id": 1, "university_id": 1, "major_id": 1,
        "university_name": "模拟院校", "major_name": "模拟计算机专业",
        "city": "上海", "category": "模拟数据", "plan_province": "上海",
        "plan_year": 2026, "university_year": 2026, "major_year": 2026,
        "plan_subjects": requirement, "major_subjects": requirement,
        "plan_source": "模拟数据", "university_source": "模拟数据",
        "major_source": "模拟数据", "plan_url": None, "plan_updated_at": "2026-01-01",
        "history": [
            {"id": index, "exam_year": 2025 - index, "min_rank_no": rank,
             "source_name": "模拟数据", "source_url": None,
             "updated_at": "2026-01-01"}
            for index, rank in enumerate(ranks)
        ],
    }


@pytest.mark.parametrize("requirement,expected", [
    ("物理、化学", True), ("物理+化学", True),
    ("物理或历史", True), ("历史或生物", False),
    ("物理、化学或生物", True), ("不限", True),
    ("待公布", False), (None, False), ("不限，历史", False),
])
def test_subject_requirements_are_hard_constraints(requirement, expected):
    assert meets_subjects({"物理", "化学"}, requirement) is expected


def test_wrong_subject_or_year_never_reaches_recommendations():
    wrong_subject = candidate(requirement="历史")
    wrong_year = {**candidate(), "major_id": 2, "major_year": 2025}
    matches, gaps, missing = evaluate_candidates(PROFILE, [wrong_subject, wrong_year], ScoringPolicy())
    assert matches == missing == []
    assert any("选科要求" in gap for gap in gaps)
    assert any("年份不匹配" in gap for gap in gaps)


def test_three_year_median_weights_and_source_evidence():
    matches, gaps, missing = evaluate_candidates(
        PROFILE, [candidate(ranks=(8000, 12000, 10000))], ScoringPolicy()
    )
    assert not gaps and not missing
    item = matches[0]
    assert item["history_reference_rank"] == 10000
    assert item["rank_ratio"] == 1
    assert item["tier"] == "稳"
    assert item["score_breakdown"] == {
        "rank": 25, "interest": 15, "city": 10,
        "risk": 10, "data_quality": 3.75,
    }
    assert item["match_score"] == 63.75
    assert item["history_spread"] == 0.4
    recommendation = build_recommendations(PROFILE, matches)[0]
    assert len(recommendation["evidence"]["history_records"]) == 3
    assert recommendation["evidence"]["simulated"] is True
    assert recommendation["risk_level"] == "unknown"
    assert "评分不是录取概率" in recommendation["reason_text"]
    assert "历年最低位次波动较大" in recommendation["risk_notes"]


def test_missing_history_is_visible_but_not_recommended():
    row = candidate(ranks=())
    matches, gaps, missing = evaluate_candidates(PROFILE, [row], ScoringPolicy())
    assert matches == []
    assert len(missing) == 1 and missing[0]["major_name"] == row["major_name"]
    assert "缺少可用历史最低位次" in gaps[0]


def test_configurable_weights_and_risk_preference_change_score():
    row = candidate(ranks=(7000,))
    policy = ScoringPolicy(rank=30, interest=35, city=10, risk=10, data_quality=15)
    conservative = {**PROFILE, "risk_preference": "conservative"}
    aggressive = {**PROFILE, "risk_preference": "aggressive"}
    low = evaluate_candidates(conservative, [row], policy)[0][0]
    high = evaluate_candidates(aggressive, [row], policy)[0][0]
    assert low["tier"] == high["tier"] == "冲"
    assert low["score_breakdown"]["interest"] == 35
    assert high["score_breakdown"]["risk"] - low["score_breakdown"]["risk"] == 10
    assert high["match_score"] - low["match_score"] == 10


def test_invalid_weight_configuration_is_rejected():
    with pytest.raises(ValidationError, match="sum to 100"):
        Settings(_env_file=None, match_rank_weight=49)
    with pytest.raises(ValidationError, match="lower than"):
        Settings(_env_file=None, match_reach_ratio=1.3)
