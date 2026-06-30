from __future__ import annotations

from functools import lru_cache
from typing import Any

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from agents.analyst_agent import AnalystAgent
from agents.orchestrator import Orchestrator
from agents.search_agent import SearchAgent
from api.snowflake_client import SnowflakeClient, SnowflakeError


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    snowflake_account: str = "example-account"
    snowflake_user: str = "cms_service_account"
    snowflake_role: str = "CMS_API_ROLE"
    snowflake_warehouse: str = "CMS_WH"
    snowflake_database: str = "CMS_DB"
    snowflake_schema: str = "ANALYTICS"
    snowflake_auth_method: str = "oauth"
    snowflake_oauth_token: str | None = None
    snowflake_pat_token: str | None = None
    snowflake_private_key_path: str | None = None
    snowflake_private_key_passphrase: str | None = None
    semantic_model_stage: str = "@CMS_DB.CORTEX.CMS_SEMANTIC_STAGE/semantic_model.yaml"
    cortex_search_service: str | None = "CMS_PROVIDER_SEARCH"
    api_host: str = "127.0.0.1"
    api_port: int = 8000
    dashboard_host: str = "127.0.0.1"
    dashboard_port: int = 8080
    cors_origins: str = "http://127.0.0.1:8080,http://localhost:8080"
    statement_poll_attempts: int = 8
    statement_poll_interval_seconds: float = 0.25

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()] or ["*"]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def get_snowflake_client(settings: Settings = Depends(get_settings)) -> SnowflakeClient:
    return SnowflakeClient(settings)


def get_orchestrator(client: SnowflakeClient = Depends(get_snowflake_client)) -> Orchestrator:
    return Orchestrator(AnalystAgent(client), SearchAgent(client))


class AskRequest(BaseModel):
    question: str = Field(..., min_length=3)
    conversation_history: list[dict[str, Any]] = Field(default_factory=list)
    include_summary: bool = False


class AskResponse(BaseModel):
    agent: str
    question: str
    sql: str | None
    interpretation: str | None = None
    columns: list[str] = Field(default_factory=list)
    data: list[list[Any]] = Field(default_factory=list)
    summary: str | None = None
    request_id: str | None = None
    suggested_visualization: dict[str, Any] | None = None
    fallback_reason: str | None = None
    results: list[dict[str, Any]] | None = None


class DashboardResponse(AskResponse):
    dashboard_spec: dict[str, Any]
    dashboard_code: str


class SqlRequest(BaseModel):
    sql: str = Field(..., min_length=6)


class SqlResponse(BaseModel):
    columns: list[str]
    data: list[list[Any]]
    row_count: int


app = FastAPI(
    title="CMS Snowflake AI Agent",
    version="1.0.0",
    description="FastAPI bridge for Snowflake Cortex Analyst, Cortex Search, and a local CMS dashboard.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health(settings: Settings = Depends(get_settings)) -> dict[str, Any]:
    return {
        "status": "ok",
        "snowflake_account": settings.snowflake_account,
        "semantic_model_stage": settings.semantic_model_stage,
    }


@app.post("/api/ask", response_model=AskResponse)
def ask(body: AskRequest, orchestrator: Orchestrator = Depends(get_orchestrator)) -> AskResponse:
    try:
        result = orchestrator.answer(
            body.question,
            conversation_history=body.conversation_history,
            include_summary=body.include_summary,
        )
    except SnowflakeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return AskResponse(**result)


@app.post("/api/ask/dashboard", response_model=DashboardResponse)
def ask_dashboard(body: AskRequest, orchestrator: Orchestrator = Depends(get_orchestrator)) -> DashboardResponse:
    try:
        result = orchestrator.build_dashboard(body.question, conversation_history=body.conversation_history)
    except SnowflakeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return DashboardResponse(**result)


@app.post("/api/sql", response_model=SqlResponse)
def execute_sql(body: SqlRequest, client: SnowflakeClient = Depends(get_snowflake_client)) -> SqlResponse:
    try:
        result = client.execute_sql(body.sql)
    except SnowflakeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    columns = [
        column.get("name", f"column_{index}")
        for index, column in enumerate(result.get("resultSetMetaData", {}).get("rowType", []))
    ]
    data = result.get("data", [])
    return SqlResponse(columns=columns, data=data, row_count=len(data))
