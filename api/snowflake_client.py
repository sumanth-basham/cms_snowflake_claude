"""
snowflake_client.py – Thin wrapper around Snowflake REST APIs.

Covers:
  • Cortex Analyst  /api/v2/cortex/analyst/message
  • Standard SQL    /api/v2/statements      (for direct queries)
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from .auth import get_auth_header
from .config import Settings

logger = logging.getLogger(__name__)

_TIMEOUT = httpx.Timeout(120.0, connect=10.0)


class SnowflakeClient:
    """HTTP client for Snowflake REST endpoints."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._base_url = settings.snowflake_base_url

    # ── Internal request helper ──────────────────────────────────────────
    def _request(
        self,
        method: str,
        path: str,
        json_body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        headers = get_auth_header(self.settings)
        headers["Content-Type"] = "application/json"
        headers["Accept"] = "application/json"
        headers["User-Agent"] = "cms-snowflake-claude/1.0"

        url = f"{self._base_url}{path}"
        logger.debug("Snowflake REST %s %s", method, url)

        with httpx.Client(timeout=_TIMEOUT) as client:
            response = client.request(method, url, headers=headers, json=json_body)

        if response.status_code not in (200, 202):
            logger.error("Snowflake API error %s: %s", response.status_code, response.text)
            response.raise_for_status()

        return response.json()

    # ── Cortex Analyst ───────────────────────────────────────────────────
    def cortex_analyst_message(
        self,
        question: str,
        conversation_history: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """
        Send a natural-language question to Cortex Analyst.

        Parameters
        ----------
        question:
            The user's natural-language question.
        conversation_history:
            Optional list of previous {role, content} messages for multi-turn
            conversations. Each content item should be a list with at least one
            element that has a ``type`` of ``"text"`` and a ``text`` field.

        Returns
        -------
        dict
            Full Cortex Analyst response object containing ``message``,
            ``request_id``, and optionally ``sql`` / ``interpretation``.
        """
        messages: list[dict[str, Any]] = list(conversation_history or [])
        messages.append(
            {
                "role": "user",
                "content": [{"type": "text", "text": question}],
            }
        )

        payload: dict[str, Any] = {
            "messages": messages,
            "semantic_model_file": self.settings.semantic_model_stage,
        }

        return self._request("POST", "/api/v2/cortex/analyst/message", json_body=payload)

    # ── Direct SQL execution ─────────────────────────────────────────────
    def execute_sql(self, sql: str) -> dict[str, Any]:
        """
        Execute an arbitrary SQL statement via the Snowflake Statements API.

        This is used for running SQL returned by Cortex Analyst before
        passing results to Claude for dashboard generation.
        """
        payload = {
            "statement": sql,
            "role": self.settings.snowflake_role,
            "warehouse": self.settings.snowflake_warehouse,
            "database": self.settings.snowflake_database,
            "schema": self.settings.snowflake_schema,
            "timeout": 60,
        }
        return self._request("POST", "/api/v2/statements", json_body=payload)

    # ── Convenience: question → SQL → data ──────────────────────────────
    def ask(
        self,
        question: str,
        conversation_history: list[dict[str, Any]] | None = None,
        execute: bool = True,
    ) -> dict[str, Any]:
        """
        High-level helper: send *question* to Cortex Analyst, optionally
        execute the returned SQL, and return a combined result dict.

        Returns
        -------
        dict with keys:
          - ``question``         : original question
          - ``analyst_response`` : raw Cortex Analyst response
          - ``sql``              : generated SQL (if any)
          - ``data``             : query result rows (if ``execute=True``)
          - ``columns``          : column names  (if ``execute=True``)
          - ``interpretation``   : analyst's natural-language answer
        """
        analyst_response = self.cortex_analyst_message(question, conversation_history)

        result: dict[str, Any] = {
            "question": question,
            "analyst_response": analyst_response,
            "sql": None,
            "data": [],
            "columns": [],
            "interpretation": "",
        }

        # Extract SQL and interpretation from analyst response
        message = analyst_response.get("message", {})
        for content_item in message.get("content", []):
            if content_item.get("type") == "sql":
                result["sql"] = content_item.get("statement")
            elif content_item.get("type") == "text":
                result["interpretation"] = content_item.get("text", "")

        # Execute SQL if returned
        if execute and result["sql"]:
            sql_response = self.execute_sql(result["sql"])
            result["columns"] = [
                col["name"] for col in sql_response.get("resultSetMetaData", {}).get("rowType", [])
            ]
            result["data"] = sql_response.get("data", [])

        return result
