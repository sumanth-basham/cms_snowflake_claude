from __future__ import annotations

import json
from typing import Any

from agents.analyst_agent import AnalystAgent, suggest_visualization
from agents.search_agent import SearchAgent

SEARCH_HINTS = {"find", "lookup", "search", "who is", "where is", "provider named"}
ANALYTICS_HINTS = {"total", "trend", "highest", "lowest", "average", "compare", "count", "show"}


class Orchestrator:
    """Route CMS questions between search and analyst capabilities."""

    def __init__(self, analyst_agent: AnalystAgent, search_agent: SearchAgent) -> None:
        self._analyst_agent = analyst_agent
        self._search_agent = search_agent

    def choose_agent(self, question: str) -> str:
        lowered = question.lower()
        if any(hint in lowered for hint in SEARCH_HINTS) and not any(hint in lowered for hint in ANALYTICS_HINTS):
            return "search"
        return "analyst"

    def answer(
        self,
        question: str,
        conversation_history: list[dict[str, Any]] | None = None,
        include_summary: bool = False,
    ) -> dict[str, Any]:
        route = self.choose_agent(question)
        if route == "search":
            return self._search_agent.run(question)

        analyst_result = self._analyst_agent.run(
            question,
            conversation_history=conversation_history,
            include_summary=include_summary,
        )
        if analyst_result.get("sql") or analyst_result.get("data"):
            return analyst_result

        fallback = self._search_agent.run(question)
        fallback["fallback_reason"] = "Analyst agent did not return executable SQL or rows."
        return fallback

    def build_dashboard(
        self,
        question: str,
        conversation_history: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        answer = self.answer(question, conversation_history=conversation_history, include_summary=True)
        spec = self._build_dashboard_spec(answer)
        answer["dashboard_spec"] = spec
        answer["dashboard_code"] = self._build_dashboard_code(spec)
        return answer

    def _build_dashboard_spec(self, answer: dict[str, Any]) -> dict[str, Any]:
        columns = answer.get("columns", [])
        data = answer.get("data", [])
        visualization = answer.get("suggested_visualization") or suggest_visualization(columns, data)
        return {
            "title": answer.get("question", "CMS dashboard"),
            "chart": visualization,
            "columns": columns,
            "rows": data,
            "summary": answer.get("summary") or answer.get("interpretation") or answer.get("summary", ""),
        }

    @staticmethod
    def _build_dashboard_code(spec: dict[str, Any]) -> str:
        spec_json = json.dumps(spec, indent=2)
        return (
            "// Render this payload with dashboard/assets/charts.js\n"
            f"const dashboardSpec = {spec_json};\n"
            "window.renderAgentChart(document.getElementById('chart-root'), dashboardSpec);"
        )
