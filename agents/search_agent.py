from __future__ import annotations

from typing import Any

from api.snowflake_client import SnowflakeClient


class SearchAgent:
    """Entity-focused search for provider lookups and lightweight discovery."""

    def __init__(self, snowflake_client: SnowflakeClient) -> None:
        self._snowflake = snowflake_client

    def run(self, query: str, limit: int = 5) -> dict[str, Any]:
        result = self._snowflake.search(query, limit=limit)
        columns = result.get("columns", [])
        data = result.get("data", [])
        records = [dict(zip(columns, row, strict=False)) for row in data]
        return {
            "agent": "search",
            "question": query,
            "sql": result.get("sql"),
            "columns": columns,
            "data": data,
            "results": records,
            "summary": self._summarize(query, records),
            "suggested_visualization": {"type": "table", "title": "Search results"},
        }

    @staticmethod
    def _summarize(query: str, records: list[dict[str, Any]]) -> str:
        if not records:
            return f"No provider records matched '{query}'."
        first = records[0]
        provider_name = first.get("PROVIDER_NAME") or first.get("provider_name") or "the top match"
        return f"Found {len(records)} provider match(es) for '{query}'. Best match: {provider_name}."
