"""LangGraph workflow integration against local MySQL and test-only Chroma vectors."""

import pytest
from fastapi.testclient import TestClient

from app.agents.repository import WorkflowRepository
from app.agents.workflow import WorkflowService
from app.core.config import Settings
from app.knowledge.models import ModelGateway
from app.knowledge.repository import KnowledgeRepository
from app.knowledge.service import KnowledgeService
from app.main import app


class TestEmbeddingGateway:
    embedding_ready = True
    chat_ready = False

    def embed(self, texts):
        return [[1.0, float("选科" in text), float("上海" in text)] for text in texts]


@pytest.fixture
def workflow_client(tmp_path):
    with TestClient(app) as client:
        original_knowledge = client.app.state.knowledge_service
        original_workflow = client.app.state.workflow_service
        settings = Settings(_env_file=None, embedding_model="workflow-test-embedding")
        knowledge = KnowledgeService(
            KnowledgeRepository(client.app.state.database), TestEmbeddingGateway(),
            settings, tmp_path,
        )
        client.app.state.knowledge_service = knowledge
        client.app.state.workflow_service = WorkflowService(
            WorkflowRepository(client.app.state.database), knowledge,
        )
        student_ids = []
        document_ids = []
        try:
            yield client, student_ids, document_ids
        finally:
            for document_id in document_ids:
                if knowledge.repository.get_document(document_id):
                    knowledge.delete(document_id)
            with client.app.state.database.transaction() as connection, connection.cursor() as cursor:
                for student_id in student_ids:
                    cursor.execute("SELECT id FROM workflow_runs WHERE student_id = %s", (student_id,))
                    run_ids = [row["id"] for row in cursor.fetchall()]
                    for run_id in run_ids:
                        cursor.execute("SELECT id FROM recommendation_plans WHERE workflow_run_id = %s", (run_id,))
                        for plan in cursor.fetchall():
                            cursor.execute("DELETE FROM recommendation_items WHERE plan_id = %s", (plan["id"],))
                            cursor.execute("DELETE FROM recommendation_plans WHERE id = %s", (plan["id"],))
                        cursor.execute("DELETE FROM workflow_events WHERE workflow_run_id = %s", (run_id,))
                    cursor.execute("DELETE FROM workflow_runs WHERE student_id = %s", (student_id,))
                    cursor.execute("DELETE FROM student_profiles WHERE student_id = %s", (student_id,))
                    cursor.execute("DELETE FROM students WHERE id = %s", (student_id,))
            client.app.state.knowledge_service = original_knowledge
            client.app.state.workflow_service = original_workflow


def create_student(client, student_ids, subjects="物理 化学", province="上海",
                   risk_preference="balanced"):
    response = client.post("/api/v1/students", json={
        "province": province, "exam_year": 2026, "score": 510,
        "rank_no": 10000, "subject_combination": subjects,
        "interests": ["计算机"], "target_cities": ["上海"],
        "risk_preference": risk_preference,
    })
    assert response.status_code == 201, response.text
    student_id = response.json()["data"]["id"]
    student_ids.append(student_id)
    return student_id


def test_end_to_end_mysql_chroma_six_agents(workflow_client):
    client, student_ids, document_ids = workflow_client
    document = client.post(
        "/api/v1/knowledge-documents",
        data={"document_type": "policy", "source_name": "模拟资料", "applicable_year": "2026"},
        files={"file": ("test-policy.txt", "上海 2026 招生政策：选科要求需核实。".encode())},
    )
    assert document.status_code == 201, document.text
    document_id = document.json()["data"]["id"]
    document_ids.append(document_id)
    assert document.json()["data"]["ingest_status"] == "ready"

    student_id = create_student(client, student_ids)
    response = client.post("/api/v1/workflow-runs", json={"student_id": student_id})
    assert response.status_code == 201, response.text
    result = response.json()["data"]
    run = result["run"]
    assert run["status"] == "completed"
    assert run["adjustment_count"] == 0
    assert result["plan_id"] is not None
    assert result["knowledge_evidence"][0]["document_id"] == document_id
    assert result["risk_report"]["tier_counts"] == {"冲": 2, "稳": 2, "保": 2}
    assert len(result["recommendations"]) == 6
    assert all(item["evidence"]["simulated"] for item in result["recommendations"])
    assert all(item["evidence"]["history_source"] == "模拟数据" for item in result["recommendations"])
    assert all(sum(item["evidence"]["score_breakdown"].values()) == item["match_score"]
               for item in result["recommendations"])
    assert all(item["major_name"] != "模拟历史学" for item in result["recommendations"])
    assert len(result["agent_events"]) == 6
    assert {event["agent_name"] for event in result["agent_events"]} == {
        "student_profile", "task_planning", "data_retrieval", "university_matching",
        "recommendation", "risk_assessment",
    }
    assert all(event["input"] and event["output"] for event in result["agent_events"])
    assert client.get(f"/api/v1/workflow-runs/{run['id']}").json()["data"]["plan"]["id"] == result["plan_id"]
    print("E2E:", {"run_id": run["id"], "status": run["status"],
                   "tier_counts": result["risk_report"]["tier_counts"],
                   "rag_passages": len(result["knowledge_evidence"]),
                   "simulated": True, "adjustments": run["adjustment_count"],
                   "first_score": result["recommendations"][0]["match_score"],
                   "first_breakdown": result["recommendations"][0]["evidence"]["score_breakdown"]})


def test_adjustment_finds_older_data_and_subjects_are_filtered(workflow_client):
    client, student_ids, _ = workflow_client
    student_id = create_student(client, student_ids, subjects="历史")
    response = client.post("/api/v1/workflow-runs", json={
        "student_id": student_id, "max_adjustments": 2,
    })
    assert response.status_code == 201, response.text
    result = response.json()["data"]
    assert result["run"]["status"] == "completed"
    assert result["run"]["adjustment_count"] == 1
    assert result["risk_report"]["tier_counts"] == {"冲": 1, "稳": 1, "保": 1}
    assert all("历史" in item["major_name"] for item in result["recommendations"])
    assert sum(event["agent_name"] == "risk_assessment" for event in result["agent_events"]) == 2
    assert sum(event["agent_name"] == "adjustment" for event in result["run"]["events"]) == 1
    assert any("历史位次较旧" in issue for issue in result["risk_report"]["issues"])


def test_adjustment_limit_is_respected(workflow_client):
    client, student_ids, _ = workflow_client
    student_id = create_student(client, student_ids, subjects="历史")
    response = client.post("/api/v1/workflow-runs", json={
        "student_id": student_id, "max_adjustments": 0,
    })
    assert response.status_code == 201, response.text
    result = response.json()["data"]
    assert result["run"]["status"] == "partial"
    assert result["run"]["adjustment_count"] == 0
    assert result["risk_report"]["tier_counts"] == {"冲": 0, "稳": 1, "保": 0}
    assert {item["major_name"] for item in result["unranked_candidates"]} == {
        "模拟历史教育", "模拟历史研究",
    }


def test_risk_preference_changes_quotas_and_scores(workflow_client):
    client, student_ids, _ = workflow_client
    conservative_id = create_student(client, student_ids, risk_preference="conservative")
    aggressive_id = create_student(client, student_ids, risk_preference="aggressive")
    conservative = client.post("/api/v1/workflow-runs", json={"student_id": conservative_id}).json()["data"]
    aggressive = client.post("/api/v1/workflow-runs", json={"student_id": aggressive_id}).json()["data"]
    assert conservative["risk_report"]["tier_counts"] == {"冲": 1, "稳": 2, "保": 2}
    assert aggressive["risk_report"]["tier_counts"] == {"冲": 2, "稳": 2, "保": 1}
    reach_name = "模拟计算机科学与技术"
    conservative_score = next(item["score_breakdown"]["risk"] for item in conservative["match_results"]
                              if item["major_name"] == reach_name)
    aggressive_score = next(item["score_breakdown"]["risk"] for item in aggressive["match_results"]
                            if item["major_name"] == reach_name)
    assert conservative_score == 0 and aggressive_score == 10


def test_missing_data_is_explicit_and_does_not_loop(workflow_client):
    client, student_ids, _ = workflow_client
    student_id = create_student(client, student_ids, province="北京")
    response = client.post("/api/v1/workflow-runs", json={"student_id": student_id})
    assert response.status_code == 201, response.text
    result = response.json()["data"]
    assert result["run"]["status"] == "insufficient_data"
    assert result["run"]["adjustment_count"] == 0
    assert result["recommendations"] == []
    assert any("没有招生计划" in gap for gap in result["data_gaps"])


def test_unrecognized_subject_stops_before_retrieval(workflow_client):
    client, student_ids, _ = workflow_client
    student_id = create_student(client, student_ids, subjects="未知选科")
    response = client.post("/api/v1/workflow-runs", json={"student_id": student_id})
    assert response.status_code == 201, response.text
    result = response.json()["data"]
    assert result["run"]["status"] == "invalid_input"
    assert result["plan_id"] is None
    assert [event["agent_name"] for event in result["agent_events"]] == ["student_profile"]


def test_missing_model_configuration_is_recorded_as_rag_gap(workflow_client):
    client, student_ids, _ = workflow_client
    client.app.state.knowledge_service.gateway = ModelGateway(Settings(
        _env_file=None, embedding_api_base_url="", embedding_api_key="", embedding_model="",
    ))
    student_id = create_student(client, student_ids)
    response = client.post("/api/v1/workflow-runs", json={"student_id": student_id})
    assert response.status_code == 201, response.text
    result = response.json()["data"]
    assert result["run"]["status"] == "completed"
    assert any("EMBEDDING_NOT_CONFIGURED" in gap for gap in result["data_gaps"])
    assert result["knowledge_evidence"] == []


def test_agent_failure_is_recorded(workflow_client, monkeypatch):
    client, student_ids, _ = workflow_client
    student_id = create_student(client, student_ids)
    repository = client.app.state.workflow_service.repository

    def fail(*_args):
        raise RuntimeError("test database retrieval failure")

    monkeypatch.setattr(repository, "retrieve_candidates", fail)
    response = client.post("/api/v1/workflow-runs", json={"student_id": student_id})
    assert response.status_code == 500
    assert response.json()["code"] == "WORKFLOW_FAILED"
    with client.app.state.database.connection() as connection, connection.cursor() as cursor:
        cursor.execute("SELECT id FROM workflow_runs WHERE student_id = %s ORDER BY id DESC LIMIT 1", (student_id,))
        run_id = cursor.fetchone()["id"]
    run = client.get(f"/api/v1/workflow-runs/{run_id}").json()["data"]
    assert run["status"] == "failed"
    assert any(event["agent_name"] == "data_retrieval" and event["status"] == "failed"
               and "RuntimeError" in event["error_message"] for event in run["events"])
