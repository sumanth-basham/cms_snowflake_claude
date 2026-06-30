from __future__ import annotations

from agents.orchestrator import Orchestrator


class StubAnalystAgent:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def run(self, question, conversation_history=None, include_summary=False):
        self.calls.append((question, include_summary))
        return dict(self.result)


class StubSearchAgent:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def run(self, question, limit=5):
        self.calls.append((question, limit))
        return dict(self.result)


ANALYST_RESULT = {
    "agent": "analyst",
    "question": "Which providers received the highest Medicare payments?",
    "sql": "SELECT PROVIDER_NAME, TOTAL_PAID FROM top_providers",
    "interpretation": "These providers lead spending.",
    "columns": ["PROVIDER_NAME", "TOTAL_PAID"],
    "data": [["Sunset Health System", 37000.0]],
    "summary": "These providers lead spending.",
    "suggested_visualization": {"type": "bar", "x": "PROVIDER_NAME", "y": "TOTAL_PAID"},
}

SEARCH_RESULT = {
    "agent": "search",
    "question": "Find Riverside Clinic",
    "sql": None,
    "columns": ["PROVIDER_NAME", "STATE"],
    "data": [["Riverside Clinic", "CA"]],
    "results": [{"PROVIDER_NAME": "Riverside Clinic", "STATE": "CA"}],
    "summary": "Found 1 provider match.",
    "suggested_visualization": {"type": "table"},
}


def test_orchestrator_routes_search_queries() -> None:
    analyst = StubAnalystAgent(ANALYST_RESULT)
    search = StubSearchAgent(SEARCH_RESULT)
    orchestrator = Orchestrator(analyst, search)

    result = orchestrator.answer("Find Riverside Clinic")

    assert result["agent"] == "search"
    assert not analyst.calls
    assert search.calls


def test_orchestrator_falls_back_when_analyst_has_no_sql() -> None:
    analyst = StubAnalystAgent({**ANALYST_RESULT, "sql": None, "data": []})
    search = StubSearchAgent(SEARCH_RESULT)
    orchestrator = Orchestrator(analyst, search)

    result = orchestrator.answer("Which provider is Riverside Clinic?")

    assert result["agent"] == "search"
    assert result["fallback_reason"]


def test_build_dashboard_returns_code_and_spec() -> None:
    orchestrator = Orchestrator(StubAnalystAgent(ANALYST_RESULT), StubSearchAgent(SEARCH_RESULT))

    result = orchestrator.build_dashboard("Which providers received the highest Medicare payments?")

    assert "dashboard_code" in result
    assert result["dashboard_spec"]["chart"]["type"] == "bar"
