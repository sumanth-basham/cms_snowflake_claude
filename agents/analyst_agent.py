from __future__ import annotations

from typing import Any

from api.snowflake_client import SnowflakeClient


def _is_number(value: Any) -> bool:
    try:
        float(value)
        return True
    except (TypeError, ValueError):
        return False


def suggest_visualization(columns: list[str], data: list[list[Any]]) -> dict[str, Any]:
    if not columns or not data:
        return {"type": "table", "reason": "No rows returned."}

    first_row = data[0]
    numeric_indexes = [idx for idx, value in enumerate(first_row) if _is_number(value)]
    label_indexes = [idx for idx, value in enumerate(first_row) if isinstance(value, str) and value]

    if label_indexes and numeric_indexes:
        return {
            "type": "bar",
            "x": columns[label_indexes[0]],
            "y": columns[numeric_indexes[0]],
            "title": f"{columns[numeric_indexes[0]]} by {columns[label_indexes[0]]}",
        }
    if len(numeric_indexes) >= 2:
        return {
            "type": "scatter",
            "x": columns[numeric_indexes[0]],
            "y": columns[numeric_indexes[1]],
            "title": f"{columns[numeric_indexes[1]]} vs {columns[numeric_indexes[0]]}",
        }
    if numeric_indexes:
        return {"type": "metric", "value": columns[numeric_indexes[0]], "title": columns[numeric_indexes[0]]}
    return {"type": "table", "title": "Query results"}


class AnalystAgent:
    """Wrap Snowflake Cortex Analyst with a deterministic local summary layer."""

    def __init__(self, snowflake_client: SnowflakeClient) -> None:
        self._snowflake = snowflake_client

    def run(
        self,
        question: str,
        conversation_history: list[dict[str, Any]] | None = None,
        include_summary: bool = False,
    ) -> dict[str, Any]:
        result = self._snowflake.ask(question, conversation_history=conversation_history, execute=True)
        columns = result.get("columns", [])
        data = result.get("data", [])
        interpretation = result.get("interpretation", "")

        summary = None
        if include_summary:
            summary = self._build_summary(question, interpretation, columns, data)

        return {
            "agent": "analyst",
            "question": question,
            "sql": result.get("sql"),
            "interpretation": interpretation,
            "columns": columns,
            "data": data,
            "summary": summary,
            "request_id": result.get("analyst_response", {}).get("request_id"),
            "suggested_visualization": suggest_visualization(columns, data),
        }

    @staticmethod
    def _build_summary(
        question: str,
        interpretation: str,
        columns: list[str],
        data: list[list[Any]],
    ) -> str:
        if not data:
            return interpretation or f"No rows matched the question: {question}"

        row_count = len(data)
        preview_pairs = []
        for index, value in enumerate(data[0][: min(len(columns), 3)]):
            preview_pairs.append(f"{columns[index]}={value}")

        preview = ", ".join(preview_pairs)
        lead = interpretation or f"Answered: {question}"
        return f"{lead} Returned {row_count} row(s); first row snapshot: {preview}."
