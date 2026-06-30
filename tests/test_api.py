from __future__ import annotations

from fastapi.testclient import TestClient

from api.app import app, get_orchestrator, get_snowflake_client


class FakeOrchestrator:
    def answer(self, question, conversation_history=None, include_summary=False):
        return {
            "agent": "analyst",
            "question": question,
            "sql": "SELECT 1",
            "interpretation": "Synthetic response",
            "columns": ["VALUE"],
            "data": [[1]],
            "summary": "Synthetic response",
            "request_id": "req-1",
            "suggested_visualization": {"type": "metric", "value": "VALUE"},
        }

    def build_dashboard(self, question, conversation_history=None):
        return {
            **self.answer(question, conversation_history, include_summary=True),
            "dashboard_spec": {
                "title": question,
                "chart": {"type": "metric", "value": "VALUE"},
                "columns": ["VALUE"],
                "rows": [[1]],
                "summary": "Synthetic response",
            },
            "dashboard_code": "const dashboardSpec = {\"title\": \"test\"};",
        }


class FakeSnowflakeClient:
    def execute_sql(self, sql):
        return {
            "resultSetMetaData": {"rowType": [{"name": "VALUE"}]},
            "data": [[1]],
        }


app.dependency_overrides[get_orchestrator] = lambda: FakeOrchestrator()
app.dependency_overrides[get_snowflake_client] = lambda: FakeSnowflakeClient()
client = TestClient(app)


def test_health_endpoint() -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_ask_endpoint() -> None:
    response = client.post("/api/ask", json={"question": "Which providers are top paid?", "include_summary": True})
    assert response.status_code == 200
    assert response.json()["sql"] == "SELECT 1"


def test_dashboard_endpoint() -> None:
    response = client.post("/api/ask/dashboard", json={"question": "Build a provider dashboard"})
    assert response.status_code == 200
    assert "dashboard_spec" in response.json()


def test_sql_endpoint() -> None:
    response = client.post("/api/sql", json={"sql": "SELECT 1"})
    assert response.status_code == 200
    assert response.json()["row_count"] == 1
