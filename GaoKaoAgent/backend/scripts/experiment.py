"""Reproducible Stage 8 comparison on the local, simulated admissions dataset."""

import argparse
import hashlib
import json
import platform
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from time import perf_counter_ns

from fastapi.testclient import TestClient

from app.agents.repository import WorkflowRepository
from app.agents.rules import TIER_QUOTAS, meets_subjects, subjects_in
from app.agents.scoring import ScoringPolicy
from app.core.config import PROJECT_ROOT, get_settings
from app.main import app


CASES = (
    {"name": "balanced_computer_shanghai", "risk_preference": "balanced",
     "interests": ["计算机"], "target_cities": ["上海"]},
    {"name": "conservative_computer_shanghai", "risk_preference": "conservative",
     "interests": ["计算机"], "target_cities": ["上海"]},
    {"name": "aggressive_software_suzhou", "risk_preference": "aggressive",
     "interests": ["软件"], "target_cities": ["苏州"]},
)
RISK_CODES = (
    "subject_exclusion", "simulated_source", "single_history_year",
    "stale_history", "missing_tier", "knowledge_unavailable",
)


def usable_history(row):
    return [record for record in row["history"]
            if record["min_rank_no"] and record["min_rank_no"] > 0][:3]


def applicable(row, profile):
    return (row["plan_province"] == profile["province"]
            and row["plan_year"] == profile["exam_year"]
            and row["university_year"] == profile["exam_year"]
            and row["major_year"] == profile["exam_year"])


def subject_ok(row, profile):
    chosen = set(profile["subjects"])
    return (meets_subjects(chosen, row["plan_subjects"])
            and meets_subjects(chosen, row["major_subjects"]))


def traditional_rule(profile, rows, policy):
    """Common rank-only baseline: hard filters, rank bands, and fixed tier quotas."""
    groups = {tier: [] for tier in ("冲", "稳", "保")}
    warnings = set()
    for row in rows:
        if not applicable(row, profile):
            continue
        if not subject_ok(row, profile):
            warnings.add("subject_exclusion")
            continue
        history = usable_history(row)
        if not history:
            continue
        ratio = median(item["min_rank_no"] for item in history) / profile["rank_no"]
        groups[policy.tier(ratio)].append((ratio, row))

    # Within a band, prefer the nearer reach, nearest steady, or safer safety rank.
    groups["冲"].sort(key=lambda pair: (-pair[0], pair[1]["plan_id"]))
    groups["稳"].sort(key=lambda pair: (abs(pair[0] - 1), pair[1]["plan_id"]))
    groups["保"].sort(key=lambda pair: (-pair[0], pair[1]["plan_id"]))
    selected = []
    for tier, quota in TIER_QUOTAS[profile["risk_preference"]].items():
        selected.extend({"university_id": row["university_id"],
                         "major_id": row["major_id"], "university_name": row["university_name"],
                         "major_name": row["major_name"], "tier": tier}
                        for _, row in groups[tier][:quota])

    chosen_rows = {(row["university_id"], row["major_id"]): row for row in rows}
    for item in selected:
        row = chosen_rows[(item["university_id"], item["major_id"])]
        sources = [row["plan_source"], row["university_source"], row["major_source"],
                   *(record["source_name"] for record in usable_history(row))]
        if any("模拟" in (source or "") for source in sources):
            warnings.add("simulated_source")
        if len(usable_history(row)) == 1:
            warnings.add("single_history_year")
        if profile["exam_year"] - usable_history(row)[0]["exam_year"] > 2:
            warnings.add("stale_history")
    if any(not groups[tier] for tier in groups):
        warnings.add("missing_tier")
    return selected, warnings


def reference_risks(profile, rows, selected, embedding_ready):
    """Independent observable labels for the six predefined risk/data-gap types."""
    risks = set()
    lookup = {(row["university_id"], row["major_id"]): row for row in rows}
    if any(applicable(row, profile) and not subject_ok(row, profile) for row in rows):
        risks.add("subject_exclusion")
    if len({item["tier"] for item in selected}) < 3:
        risks.add("missing_tier")
    if not embedding_ready:
        risks.add("knowledge_unavailable")
    for item in selected:
        row = lookup[(item["university_id"], item["major_id"])]
        history = usable_history(row)
        sources = [row["plan_source"], row["university_source"], row["major_source"],
                   *(record["source_name"] for record in history)]
        if any("模拟" in (source or "") for source in sources):
            risks.add("simulated_source")
        if len(history) == 1:
            risks.add("single_history_year")
        if history and profile["exam_year"] - history[0]["exam_year"] > 2:
            risks.add("stale_history")
    return risks


def agent_risk_codes(report):
    text = "\n".join(report["issues"])
    markers = {
        "subject_exclusion": "不满足选科要求",
        "simulated_source": "使用模拟数据",
        "single_history_year": "仅有一年历史位次",
        "stale_history": "历史位次较旧",
        "missing_tier": "志愿梯度缺少",
        "knowledge_unavailable": "RAG 检索不可用",
    }
    return {code for code, marker in markers.items() if marker in text}


def metrics(profile, rows, selected, detected, embedding_ready):
    lookup = {(row["university_id"], row["major_id"]): row for row in rows}
    satisfied = preference_hits = 0
    for item in selected:
        row = lookup[(item["university_id"], item["major_id"])]
        satisfied += int(applicable(row, profile) and subject_ok(row, profile)
                         and bool(usable_history(row)))
        preference_hits += int(any(interest in row["major_name"] + (row["category"] or "")
                                   for interest in profile["interests"]))
    truth = reference_risks(profile, rows, selected, embedding_ready)
    return {
        "recommended_count": len(selected), "hard_conditions_satisfied": satisfied,
        "preference_hits": preference_hits,
        "reference_risks": sorted(truth), "detected_risks": sorted(detected),
        "risk_true_positives": len(truth & detected),
        "risk_false_positives": len(detected - truth),
    }


def cleanup_students(database, student_ids):
    with database.transaction() as connection, connection.cursor() as cursor:
        for student_id in student_ids:
            cursor.execute("SELECT id FROM recommendation_plans WHERE student_id = %s", (student_id,))
            for plan in cursor.fetchall():
                cursor.execute("DELETE FROM recommendation_items WHERE plan_id = %s", (plan["id"],))
            cursor.execute("DELETE FROM recommendation_plans WHERE student_id = %s", (student_id,))
            cursor.execute(
                "DELETE FROM workflow_events WHERE workflow_run_id IN "
                "(SELECT id FROM workflow_runs WHERE student_id = %s)", (student_id,)
            )
            cursor.execute("DELETE FROM workflow_runs WHERE student_id = %s", (student_id,))
            cursor.execute("DELETE FROM student_profiles WHERE student_id = %s", (student_id,))
            cursor.execute("DELETE FROM students WHERE id = %s", (student_id,))


def run(repeats):
    settings = get_settings()
    policy = ScoringPolicy.from_settings(settings)
    results = []
    with TestClient(app) as client:
        database = client.app.state.database
        repository = WorkflowRepository(database)
        rows, truncated = repository.retrieve_candidates("上海", 2026, 2, 500)
        expected = {f"模拟院校{letter}" for letter in "ABCDEFGHI"}
        if (truncated or len(rows) != 9 or {row["university_name"] for row in rows} != expected
                or any(row["plan_source"] != "模拟数据" for row in rows)):
            raise RuntimeError("Experiment requires the unchanged nine-candidate simulated seed dataset")
        snapshot = hashlib.sha256(json.dumps(rows, ensure_ascii=False, sort_keys=True,
                                             default=str).encode("utf-8")).hexdigest()
        with database.connection() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT VERSION() AS version")
            mysql_version = cursor.fetchone()["version"]
        embedding_ready = client.app.state.knowledge_service.gateway.embedding_ready
        student_ids = []
        try:
            for case in CASES:
                payload = {
                    "province": "上海", "exam_year": 2026, "score": 510,
                    "rank_no": 10000, "subject_combination": "物理 化学",
                    "interests": case["interests"], "target_cities": case["target_cities"],
                    "risk_preference": case["risk_preference"],
                }
                response = client.post("/api/v1/students", json=payload)
                if response.status_code != 201:
                    raise RuntimeError(f"Student creation failed: {response.status_code} {response.text}")
                student_id = response.json()["data"]["id"]
                student_ids.append(student_id)
                profile = {**payload, "subjects": sorted(subjects_in(payload["subject_combination"]))}
                trials = []
                for index in range(repeats):
                    def baseline_trial():
                        start = perf_counter_ns()
                        current_rows, current_truncated = repository.retrieve_candidates("上海", 2026, 2, 500)
                        if current_truncated:
                            raise RuntimeError("Candidate retrieval truncated")
                        items, warnings = traditional_rule(profile, current_rows, policy)
                        duration = (perf_counter_ns() - start) / 1_000_000
                        return {"duration_ms": round(duration, 3),
                                "items": items, **metrics(profile, current_rows, items, warnings,
                                                         embedding_ready)}

                    def agent_trial():
                        start = perf_counter_ns()
                        response = client.post("/api/v1/workflow-runs", json={
                            "student_id": student_id, "max_adjustments": 0,
                        })
                        duration = (perf_counter_ns() - start) / 1_000_000
                        if response.status_code != 201:
                            raise RuntimeError(f"Workflow failed: {response.status_code} {response.text}")
                        result = response.json()["data"]
                        return {"duration_ms": round(duration, 3),
                                "status": result["run"]["status"],
                                "agent_event_count": len(result["agent_events"]),
                                "rag_passages": len(result["knowledge_evidence"]),
                                "items": [{key: item[key] for key in (
                                    "university_id", "major_id", "university_name", "major_name", "tier"
                                )} for item in result["recommendations"]],
                                **metrics(profile, rows, result["recommendations"],
                                          agent_risk_codes(result["risk_report"]), embedding_ready)}

                    if index % 2 == 0:
                        baseline = baseline_trial()
                        agent = agent_trial()
                    else:
                        agent = agent_trial()
                        baseline = baseline_trial()
                    trials.append({"repeat": index + 1, "traditional_rule": baseline,
                                   "multi_agent": agent})
                results.append({"case": case["name"], "input": payload, "trials": trials})
        finally:
            cleanup_students(database, student_ids)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "environment": {"python": platform.python_version(), "mysql": mysql_version,
                        "embedding_configured": embedding_ready,
                        "llm_configured": bool(settings.llm_api_key and settings.llm_model)},
        "dataset": {"kind": "simulated", "candidate_count": len(rows),
                    "snapshot_sha256": snapshot, "source": "sql/seed_simulated_data.sql"},
        "method": {"history_years": 2, "max_adjustments": 0,
                   "tier_quotas": TIER_QUOTAS, "risk_codes": RISK_CODES,
                   "timing": "multi-agent FastAPI TestClient POST including MySQL writes and RAG; "
                             "traditional rule in-process including MySQL retrieval, no writes"},
        "repeats_per_case": repeats, "cases": results,
        "cleanup": "Temporary students, workflow runs, profiles, and plans deleted after sampling",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--output", type=Path, default=PROJECT_ROOT / "docs" / "实验原始结果.json")
    arguments = parser.parse_args()
    if arguments.repeats < 1:
        parser.error("--repeats must be positive")
    result = run(arguments.repeats)
    arguments.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Saved {len(result['cases'])} cases x {result['repeats_per_case']} repeats to {arguments.output}")


if __name__ == "__main__":
    main()
