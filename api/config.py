"""
config.py – Application settings loaded from environment variables / .env file.
"""

from __future__ import annotations

from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── Snowflake connection ───────────────────────────────────────────────
    snowflake_account: str = ""
    """Snowflake account identifier, e.g. 'myorg-myaccount'."""

    snowflake_user: str = ""
    """Snowflake login name / service-account username."""

    snowflake_role: str = "CMS_API_ROLE"
    """Snowflake role to assume when running queries."""

    snowflake_warehouse: str = "CMS_WH"
    """Virtual warehouse for Cortex Analyst queries."""

    snowflake_database: str = "CMS_DB"
    snowflake_schema: str = "ANALYTICS"

    # ── Authentication method ──────────────────────────────────────────────
    snowflake_auth_method: str = "key_pair"
    """One of: key_pair | oauth | pat"""

    snowflake_private_key_path: Optional[str] = None
    """Path to RSA private key PEM file (key_pair auth)."""

    snowflake_private_key_passphrase: Optional[str] = None
    """Optional passphrase for encrypted private key."""

    snowflake_oauth_token: Optional[str] = None
    """OAuth access token (oauth auth)."""

    snowflake_password: Optional[str] = None
    """Password or Personal Access Token (pat auth)."""

    # ── Snowflake REST API base URL ────────────────────────────────────────
    @property
    def snowflake_base_url(self) -> str:
        account = self.snowflake_account.lower().replace("_", "-")
        return f"https://{account}.snowflakecomputing.com"

    # ── Cortex Analyst semantic model ─────────────────────────────────────
    semantic_model_stage: str = "@CMS_DB.CORTEX.CMS_SEMANTIC_STAGE/cms_semantic_model.yaml"
    """Stage path to the YAML semantic model for Cortex Analyst."""

    # ── Anthropic / Claude ─────────────────────────────────────────────────
    anthropic_api_key: str = ""
    """Anthropic API key for Claude integration."""

    claude_model: str = "claude-opus-4-5"
    """Claude model ID to use for dashboard generation."""

    # ── FastAPI server ─────────────────────────────────────────────────────
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    api_reload: bool = False
    cors_origins: list[str] = ["http://localhost:8501"]
    """Allowed CORS origins (Streamlit default port: 8501)."""


def get_settings() -> Settings:
    return Settings()
