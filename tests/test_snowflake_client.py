from __future__ import annotations

from api.app import Settings
from api.snowflake_client import SnowflakeClient


def test_oauth_headers_use_bearer_token() -> None:
    client = SnowflakeClient(Settings(snowflake_oauth_token="oauth-token"))
    assert client._headers()["Authorization"].startswith("Bearer ")
    assert client._headers()["Authorization"].endswith("oauth-token")


def test_pat_headers_use_bearer_token() -> None:
    client = SnowflakeClient(Settings(snowflake_auth_method="pat", snowflake_pat_token="pat-token"))
    assert client._headers()["Authorization"].startswith("Bearer ")
    assert client._headers()["Authorization"].endswith("pat-token")


def test_key_pair_headers_use_generated_jwt(monkeypatch) -> None:
    client = SnowflakeClient(Settings(snowflake_auth_method="key_pair", snowflake_private_key_path="dummy"))
    monkeypatch.setattr(client, "_build_key_pair_jwt", lambda: "jwt-token")
    assert client._headers()["Authorization"].startswith("Bearer ")
    assert client._headers()["Authorization"].endswith("jwt-token")
