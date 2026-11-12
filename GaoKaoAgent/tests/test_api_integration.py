"""Stage 3 API checks against the local MySQL instance and simulated seed rows."""

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    with TestClient(app) as value:
        yield value


def _cleanup(client: TestClient, student_id: int | None, plan_id: int | None) -> None:
    if student_id is None:
        return
    with client.app.state.database.transaction() as connection, connection.cursor() as cursor:
        if plan_id is not None:
            cursor.execute("DELETE FROM recommendation_items WHERE plan_id = %s", (plan_id,))
            cursor.execute("DELETE FROM recommendation_plans WHERE id = %s", (plan_id,))
        cursor.execute("DELETE FROM students WHERE id = %s", (student_id,))


def test_catalog_filters_and_validation(client):
    response = client.get("/api/v1/universities", params={"province": "上海", "year": 2026})
    assert response.status_code == 200
    assert response.json()["meta"]["total"] >= 1
    assert all(row["source_name"] == "模拟数据" for row in response.json()["data"])
    university_id = next(row["id"] for row in response.json()["data"]
                         if row["name"] == "模拟院校A")

    majors = client.get("/api/v1/majors", params={"university_id": university_id, "subject": "物理"})
    assert majors.status_code == 200
    assert majors.json()["meta"]["total"] >= 1
    major_id = majors.json()["data"][0]["id"]

    plans = client.get("/api/v1/admission-plans", params={"province": "上海", "year": 2026, "major_id": major_id})
    records = client.get("/api/v1/admission-records", params={"province": "上海", "year": 2025, "major_id": major_id})
    assert plans.status_code == records.status_code == 200
    assert plans.json()["meta"]["total"] >= 1
    assert records.json()["meta"]["total"] >= 1
    assert plans.json()["data"][0]["source_name"] == "模拟数据"
    assert records.json()["data"][0]["source_name"] == "模拟数据"

    assert client.get("/api/v1/universities", params={"name": "' OR 1=1 --"}).json()["meta"]["total"] == 0
    invalid = client.get("/api/v1/admission-plans", params={"page_size": 101})
    assert invalid.status_code == 422
    assert invalid.json()["code"] == "VALIDATION_ERROR"


def test_student_and_plan_lifecycle(client):
    student_id = plan_id = None
    try:
        invalid = client.post("/api/v1/students", json={"province": " ", "exam_year": 2026})
        assert invalid.status_code == 422
        assert invalid.json()["code"] == "VALIDATION_ERROR"

        response = client.post("/api/v1/students", json={
            "province": "上海", "exam_year": 2026, "score": 510,
            "rank_no": 9000, "subject_combination": "物理 化学",
            "interests": ["计算机"], "target_cities": ["上海"],
            "risk_preference": "balanced",
        })
        assert response.status_code == 201, response.text
        student_id = response.json()["data"]["id"]
        assert response.json()["data"]["interests"] == ["计算机"]

        assert client.get(f"/api/v1/students/{student_id}").status_code == 200
        assert client.get("/api/v1/students", params={"page_size": 1}).json()["meta"]["page_size"] == 1
        changed = client.patch(f"/api/v1/students/{student_id}", json={"target_cities": ["上海", "苏州"]})
        assert changed.status_code == 200
        assert changed.json()["data"]["target_cities"] == ["上海", "苏州"]
        assert client.patch(f"/api/v1/students/{student_id}", json={}).status_code == 422
        assert client.patch(f"/api/v1/students/{student_id}", json={"province": None}).status_code == 422

        candidate = client.get("/api/v1/admission-plans", params={"province": "上海", "year": 2026}).json()["data"][0]
        item = {
            "university_id": candidate["university_id"], "major_id": candidate["major_id"],
            "tier": "稳", "match_score": 75.5,
            "reason_text": "测试草稿，由调用者填写的理由", "evidence": {"source_name": "模拟数据"},
            "risk_level": "unknown",
        }
        rejected = client.post("/api/v1/plans", json={
            "student_id": student_id, "items": [{**item, "major_id": 999999999}],
        })
        assert rejected.status_code == 422
        assert rejected.json()["code"] == "INVALID_CANDIDATE"
        assert client.get("/api/v1/plans", params={"student_id": student_id}).json()["meta"]["total"] == 0

        saved = client.post("/api/v1/plans", json={
            "student_id": student_id, "summary": "仅供测试的人工草稿", "items": [item],
        })
        assert saved.status_code == 201, saved.text
        plan_id = saved.json()["data"]["id"]
        assert saved.json()["data"]["status"] == "draft"
        assert saved.json()["data"]["items"][0]["evidence"] == {"source_name": "模拟数据"}

        history = client.get("/api/v1/plans", params={"student_id": student_id})
        assert history.status_code == 200
        assert history.json()["meta"]["total"] == 1
        assert history.json()["data"][0]["item_count"] == 1
        assert client.get(f"/api/v1/plans/{plan_id}").json()["data"]["items"][0]["tier"] == "稳"
        assert client.get("/api/v1/plans/999999999").status_code == 404
    finally:
        _cleanup(client, student_id, plan_id)
