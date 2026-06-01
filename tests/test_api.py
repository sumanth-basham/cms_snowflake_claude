"""
tests/test_api.py – Unit tests for the FastAPI CMS Cortex Agent backend.

Uses unittest.mock to stub out all Snowflake and Anthropic network calls so
the tests run without real credentials.
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

# ── Minimal env so Settings validation passes ─────────────────────────────────
import os

os.environ.setdefault("SNOWFLAKE_ACCOUNT", "test-account")
os.environ.setdefault("SNOWFLAKE_USER", "test-user")
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")

from api.main import app  # noqa: E402 – import after env setup

client = TestClient(app)

# ── Fixtures / helpers ────────────────────────────────────────────────────────

MOCK_ANALYST_RESPONSE: dict[str, Any] = {
    "request_id": "abc123",
    "message": {
        "role": "analyst",
        "content": [
            {"type": "sql", "statement": "SELECT * FROM CMS_DB.ANALYTICS.PROVIDERS LIMIT 5"},
            {"type": "text", "text": "Here are the top providers by Medicare payments."},
        ],
    },
}

MOCK_SQL_RESPONSE: dict[str, Any] = {
    "resultSetMetaData": {
        "rowType": [
            {"name": "PROVIDER_NAME"},
            {"name": "STATE"},
            {"name": "PAID_AMOUNT"},
        ]
    },
    "data": [
        ["General Hospital NYC", "NY", "11500.00"],
        ["Riverside Clinic", "CA", "2000.00"],
    ],
}

MOCK_CLAUDE_SUMMARY = "General Hospital NYC leads Medicare payments in NY."
MOCK_CLAUDE_CODE = "import streamlit as st\nst.title('Test Dashboard')"


# ── /api/health ───────────────────────────────────────────────────────────────
def test_health() -> None:
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


# ── /api/ask ──────────────────────────────────────────────────────────────────
@patch("api.snowflake_client.SnowflakeClient._request")
def test_ask_returns_sql_and_data(mock_request: MagicMock) -> None:
    """POST /api/ask should translate question → SQL, execute it, return data."""
    mock_request.side_effect = [MOCK_ANALYST_RESPONSE, MOCK_SQL_RESPONSE]

    resp = client.post(
        "/api/ask",
        json={"question": "Which providers have the highest Medicare payments?"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["sql"] == "SELECT * FROM CMS_DB.ANALYTICS.PROVIDERS LIMIT 5"
    assert body["interpretation"] == "Here are the top providers by Medicare payments."
    assert body["columns"] == ["PROVIDER_NAME", "STATE", "PAID_AMOUNT"]
    assert len(body["data"]) == 2
    assert body["request_id"] == "abc123"
    assert body["summary"] is None  # include_summary=False by default


@patch("api.claude_client.ClaudeClient.summarise_results", return_value=MOCK_CLAUDE_SUMMARY)
@patch("api.snowflake_client.SnowflakeClient._request")
def test_ask_with_summary(mock_request: MagicMock, mock_summary: MagicMock) -> None:
    """POST /api/ask with include_summary=True should call Claude for a summary."""
    mock_request.side_effect = [MOCK_ANALYST_RESPONSE, MOCK_SQL_RESPONSE]

    resp = client.post(
        "/api/ask",
        json={
            "question": "Which providers have the highest Medicare payments?",
            "include_summary": True,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["summary"] == MOCK_CLAUDE_SUMMARY
    mock_summary.assert_called_once()


@patch("api.snowflake_client.SnowflakeClient._request")
def test_ask_cortex_error_returns_502(mock_request: MagicMock) -> None:
    """When Cortex Analyst raises, the API should return 502."""
    mock_request.side_effect = RuntimeError("Snowflake connection refused")

    resp = client.post("/api/ask", json={"question": "test"})
    assert resp.status_code == 502
    assert "Cortex Analyst error" in resp.json()["detail"]


def test_ask_empty_question_returns_422() -> None:
    """Empty question should fail Pydantic validation (422)."""
    resp = client.post("/api/ask", json={"question": ""})
    assert resp.status_code == 422


# ── /api/ask/dashboard ────────────────────────────────────────────────────────
@patch("api.claude_client.ClaudeClient.generate_dashboard_code", return_value=MOCK_CLAUDE_CODE)
@patch("api.snowflake_client.SnowflakeClient._request")
def test_dashboard_returns_code(mock_request: MagicMock, mock_code: MagicMock) -> None:
    """POST /api/ask/dashboard should return Streamlit Python code from Claude."""
    mock_request.side_effect = [MOCK_ANALYST_RESPONSE, MOCK_SQL_RESPONSE]

    resp = client.post(
        "/api/ask/dashboard",
        json={"question": "Show provider payments as a bar chart"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "streamlit" in body["dashboard_code"].lower()
    mock_code.assert_called_once()


@patch("api.snowflake_client.SnowflakeClient._request")
def test_dashboard_no_sql_returns_422(mock_request: MagicMock) -> None:
    """If Cortex Analyst returns no SQL, /api/ask/dashboard should return 422."""
    mock_request.return_value = {
        "request_id": "no-sql",
        "message": {
            "role": "analyst",
            "content": [{"type": "text", "text": "I don't understand that question."}],
        },
    }

    resp = client.post("/api/ask/dashboard", json={"question": "xyz gibberish"})
    assert resp.status_code == 422


# ── /api/sql ──────────────────────────────────────────────────────────────────
@patch("api.snowflake_client.SnowflakeClient._request")
def test_execute_sql(mock_request: MagicMock) -> None:
    """POST /api/sql should return columns + rows."""
    mock_request.return_value = MOCK_SQL_RESPONSE

    resp = client.post("/api/sql", json={"sql": "SELECT * FROM CMS_DB.ANALYTICS.PROVIDERS"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["columns"] == ["PROVIDER_NAME", "STATE", "PAID_AMOUNT"]
    assert body["row_count"] == 2


# ── Auth helpers ──────────────────────────────────────────────────────────────
def test_get_auth_header_key_pair_missing_key() -> None:
    """Key-pair auth without a key file should raise ValueError."""
    from api.auth import get_auth_header
    from api.config import Settings

    settings = Settings(
        snowflake_account="test",
        snowflake_user="user",
        snowflake_auth_method="key_pair",
        snowflake_private_key_path=None,
    )
    with pytest.raises(ValueError, match="SNOWFLAKE_PRIVATE_KEY_PATH"):
        get_auth_header(settings)


def test_get_auth_header_oauth_missing_token() -> None:
    """OAuth auth without a token should raise ValueError."""
    from api.auth import get_auth_header
    from api.config import Settings

    settings = Settings(
        snowflake_account="test",
        snowflake_user="user",
        snowflake_auth_method="oauth",
        snowflake_oauth_token=None,
    )
    with pytest.raises(ValueError, match="SNOWFLAKE_OAUTH_TOKEN"):
        get_auth_header(settings)


# ── Claude client helpers ─────────────────────────────────────────────────────
def test_extract_code_block() -> None:
    """_extract_code_block should strip fences."""
    from api.claude_client import _extract_code_block

    fenced = "```python\nimport streamlit as st\nst.title('hi')\n```"
    assert _extract_code_block(fenced) == "import streamlit as st\nst.title('hi')"

    no_fence = "import streamlit as st"
    assert _extract_code_block(no_fence) == "import streamlit as st"
