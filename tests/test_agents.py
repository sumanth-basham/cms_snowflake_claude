from __future__ import annotations

from agents.analyst_agent import AnalystAgent, suggest_visualization
from agents.search_agent import SearchAgent


class FakeSnowflakeClient:
    def ask(self, question, conversation_history=None, execute=True):
        return {
            "sql": "SELECT PROVIDER_NAME, TOTAL_PAID FROM top_providers",
            "columns": ["PROVIDER_NAME", "TOTAL_PAID"],
            "data": [["General Hospital NYC", 25500.0], ["Sunset Health System", 37000.0]],
            "interpretation": "These providers received the highest payments.",
            "analyst_response": {"request_id": "req-123"},
        }

    def search(self, query, limit=5):
        return {
            "sql": "SELECT * FROM PROVIDERS WHERE PROVIDER_NAME ILIKE '%clinic%'",
            "columns": ["PROVIDER_ID", "PROVIDER_NAME", "STATE"],
            "data": [["P002", "Riverside Clinic", "CA"]],
        }


def test_analyst_agent_returns_summary_and_chart_hint() -> None:
    agent = AnalystAgent(FakeSnowflakeClient())
    result = agent.run("Which providers received the highest payments?", include_summary=True)

    assert result["agent"] == "analyst"
    assert result["request_id"] == "req-123"
    assert result["summary"] is not None
    assert result["suggested_visualization"]["type"] == "bar"


def test_search_agent_formats_records() -> None:
    agent = SearchAgent(FakeSnowflakeClient())
    result = agent.run("Find Riverside Clinic")

    assert result["agent"] == "search"
    assert result["results"][0]["PROVIDER_NAME"] == "Riverside Clinic"
    assert "Best match" in result["summary"]


def test_visualization_falls_back_to_metric_for_numeric_rows() -> None:
    chart = suggest_visualization(["TOTAL_PAID"], [[1234.5]])
    assert chart["type"] == "metric"
