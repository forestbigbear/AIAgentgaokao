from fastapi.testclient import TestClient

from app.main import app


def test_health_and_swagger():
    with TestClient(app) as client:
        response = client.get("/api/health")
        assert response.status_code == 200
        assert response.json()["data"] == {"status": "ok"}
        assert client.get("/docs").status_code == 200
        assert client.get("/openapi.json").status_code == 200


def test_database_health_reports_missing_server(monkeypatch):
    with TestClient(app) as client:
        def unavailable():
            raise OSError("unavailable")

        monkeypatch.setattr(app.state.database, "check_connection", unavailable)
        response = client.get("/api/health/db")
        assert response.status_code == 503
        assert response.json()["message"] == "MySQL unavailable or database missing"

