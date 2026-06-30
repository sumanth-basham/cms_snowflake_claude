from __future__ import annotations

import base64
import hashlib
import json
import logging
import re
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import jwt
from cryptography.hazmat.primitives import serialization

logger = logging.getLogger(__name__)

READ_ONLY_SQL = re.compile(r"^\s*(SELECT|WITH|SHOW|DESCRIBE)\b", re.IGNORECASE)
MUTATING_SQL = re.compile(
    r"\b(INSERT|UPDATE|DELETE|MERGE|COPY|PUT|GET|ALTER|DROP|TRUNCATE|CALL|CREATE|GRANT|REVOKE|USE)\b",
    re.IGNORECASE,
)


class SnowflakeError(RuntimeError):
    """Raised when Snowflake API communication fails."""


class SnowflakeClient:
    def __init__(self, settings: Any, transport: httpx.BaseTransport | None = None) -> None:
        self.settings = settings
        self._transport = transport
        self._timeout = httpx.Timeout(60.0, connect=10.0)

    @property
    def base_url(self) -> str:
        return f"https://{self.settings.snowflake_account}.snowflakecomputing.com"

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "cms-snowflake-agent/1.0",
        }
        auth_method = self.settings.snowflake_auth_method.lower()
        if auth_method == "oauth":
            token = self.settings.snowflake_oauth_token
            if not token:
                raise SnowflakeError("SNOWFLAKE_OAUTH_TOKEN is required for oauth authentication.")
            headers["Authorization"] = "Bearer " + token
            return headers
        if auth_method == "pat":
            token = self.settings.snowflake_pat_token
            if not token:
                raise SnowflakeError("SNOWFLAKE_PAT_TOKEN is required for pat authentication.")
            headers["Authorization"] = "Bearer " + token
            return headers
        if auth_method == "key_pair":
            headers["Authorization"] = "Bearer " + self._build_key_pair_jwt()
            headers["X-Snowflake-Authorization-Token-Type"] = "KEYPAIR_JWT"
            return headers
        raise SnowflakeError(f"Unsupported SNOWFLAKE_AUTH_METHOD: {self.settings.snowflake_auth_method}")

    def _build_key_pair_jwt(self) -> str:
        key_path = self.settings.snowflake_private_key_path
        if not key_path:
            raise SnowflakeError("SNOWFLAKE_PRIVATE_KEY_PATH is required for key_pair authentication.")

        private_key_bytes = Path(key_path).expanduser().read_bytes()
        password = self.settings.snowflake_private_key_passphrase
        private_key = serialization.load_pem_private_key(
            private_key_bytes,
            password.encode() if password else None,
        )
        public_key = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.DER,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        fingerprint = "SHA256:" + base64.b64encode(hashlib.sha256(public_key).digest()).decode()
        account = self.settings.snowflake_account.upper()
        user = self.settings.snowflake_user.upper()
        now = datetime.now(UTC)
        payload = {
            "iss": f"{account}.{user}.{fingerprint}",
            "sub": f"{account}.{user}",
            "iat": now,
            "exp": now + timedelta(minutes=59),
        }
        token = jwt.encode(payload, private_key, algorithm="RS256")
        return token if isinstance(token, str) else token.decode()

    def _request(self, method: str, path: str, json_body: dict[str, Any] | None = None) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        with httpx.Client(timeout=self._timeout, transport=self._transport) as client:
            response = client.request(method, url, headers=self._headers(), json=json_body)
        if response.status_code >= 400:
            raise SnowflakeError(self._error_message(response))
        payload = self._json(response)
        if response.status_code == 202 and payload.get("statementHandle"):
            return self._poll_statement(payload["statementHandle"])
        return payload

    def _poll_statement(self, statement_handle: str) -> dict[str, Any]:
        attempts = max(1, int(self.settings.statement_poll_attempts))
        for _ in range(attempts):
            payload = self._request("GET", f"/api/v2/statements/{statement_handle}")
            status = str(payload.get("status", "")).upper()
            if status in {"SUCCESS", "SUCCEEDED"} or payload.get("data") or payload.get("resultSetMetaData"):
                return payload
            if status in {"FAILED_WITH_ERROR", "FAILED", "ABORTED"}:
                raise SnowflakeError(payload.get("message", f"Statement {statement_handle} failed."))
            time.sleep(self.settings.statement_poll_interval_seconds)
        raise SnowflakeError(f"Statement {statement_handle} did not finish within the configured polling window.")

    @staticmethod
    def _json(response: httpx.Response) -> dict[str, Any]:
        if not response.content:
            return {}
        try:
            return response.json()
        except json.JSONDecodeError as exc:
            raise SnowflakeError(f"Snowflake returned invalid JSON: {response.text[:200]}") from exc

    @staticmethod
    def _error_message(response: httpx.Response) -> str:
        try:
            payload = response.json()
        except json.JSONDecodeError:
            return f"Snowflake API error {response.status_code}: {response.text[:200]}"
        message = payload.get("message") or payload.get("error") or payload
        return f"Snowflake API error {response.status_code}: {message}"

    @staticmethod
    def is_safe_read_only_sql(sql: str) -> bool:
        normalized = sql.strip().rstrip(";")
        if not normalized:
            return False
        if not READ_ONLY_SQL.match(normalized):
            return False
        if MUTATING_SQL.search(normalized.split(None, 1)[-1]):
            return False
        return ";" not in normalized

    @staticmethod
    def _escape_like_literal(value: str) -> str:
        return (
            value.replace("\\", "\\\\")
            .replace("%", "\\%")
            .replace("_", "\\_")
            .replace("'", "''")
        )

    def cortex_analyst_message(
        self,
        question: str,
        conversation_history: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        messages = list(conversation_history or [])
        messages.append({"role": "user", "content": [{"type": "text", "text": question}]})
        payload = {
            "messages": messages,
            "semantic_model_file": self.settings.semantic_model_stage,
        }
        return self._request("POST", "/api/v2/cortex/analyst/message", json_body=payload)

    def execute_sql(self, sql: str) -> dict[str, Any]:
        if not self.is_safe_read_only_sql(sql):
            raise SnowflakeError("Only read-only SELECT, WITH, SHOW, or DESCRIBE statements are allowed.")
        payload = {
            "statement": sql,
            "role": self.settings.snowflake_role,
            "warehouse": self.settings.snowflake_warehouse,
            "database": self.settings.snowflake_database,
            "schema": self.settings.snowflake_schema,
            "timeout": 60,
        }
        return self._request("POST", "/api/v2/statements", json_body=payload)

    def ask(
        self,
        question: str,
        conversation_history: list[dict[str, Any]] | None = None,
        execute: bool = True,
    ) -> dict[str, Any]:
        analyst_response = self.cortex_analyst_message(question, conversation_history)
        result = {
            "question": question,
            "analyst_response": analyst_response,
            "sql": None,
            "columns": [],
            "data": [],
            "interpretation": "",
        }
        for item in analyst_response.get("message", {}).get("content", []):
            if item.get("type") == "sql":
                result["sql"] = item.get("statement") or item.get("sql")
            elif item.get("type") == "text":
                result["interpretation"] = item.get("text", "")
        if execute and result["sql"]:
            sql_response = self.execute_sql(result["sql"])
            result["columns"] = [
                col.get("name", f"column_{idx}")
                for idx, col in enumerate(sql_response.get("resultSetMetaData", {}).get("rowType", []))
            ]
            result["data"] = sql_response.get("data", [])
        return result

    def search(self, query: str, limit: int = 5) -> dict[str, Any]:
        service_name = self.settings.cortex_search_service
        if service_name:
            try:
                path = (
                    f"/api/v2/databases/{self.settings.snowflake_database}/schemas/"
                    f"{self.settings.snowflake_schema}/cortex-search-services/{service_name}:query"
                )
                payload = {"query": query, "limit": limit}
                response = self._request("POST", path, json_body=payload)
                records = response.get("results") or response.get("data") or []
                if records and isinstance(records[0], dict):
                    columns = list(records[0].keys())
                    rows = [[record.get(column) for column in columns] for record in records]
                    return {"columns": columns, "data": rows, "raw": response, "sql": None}
            except SnowflakeError:
                logger.info("Falling back to SQL search for query '%s'.", query)

        escaped = self._escape_like_literal(query)
        sql = (
            "SELECT PROVIDER_ID, PROVIDER_NAME, PROVIDER_TYPE, SPECIALTY, CITY, STATE "
            "FROM CMS_DB.ANALYTICS.PROVIDERS "
            f"WHERE PROVIDER_NAME ILIKE '%{escaped}%' ESCAPE '\\' "
            f"OR SPECIALTY ILIKE '%{escaped}%' ESCAPE '\\' "
            f"OR CITY ILIKE '%{escaped}%' ESCAPE '\\' "
            f"ORDER BY PROVIDER_NAME LIMIT {int(limit)}"
        )
        response = self.execute_sql(sql)
        columns = [col.get("name", f"column_{idx}") for idx, col in enumerate(response.get("resultSetMetaData", {}).get("rowType", []))]
        return {"columns": columns, "data": response.get("data", []), "raw": response, "sql": sql}
