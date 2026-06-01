"""
main.py – FastAPI application exposing the CMS Snowflake Cortex Agent.

Endpoints:
  POST /api/ask                 – Natural-language question → Cortex Analyst + optional Claude summary
  POST /api/ask/dashboard       – NL question → Cortex Analyst → Claude dashboard code
  POST /api/sql                 – Execute raw SQL (admin use)
  GET  /api/health              – Liveness probe
"""

from __future__ import annotations

import logging
import traceback
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .claude_client import ClaudeClient
from .config import Settings, get_settings
from .snowflake_client import SnowflakeClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s – %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(application: FastAPI):  # noqa: ANN001
    settings = get_settings()
    _setup_cors(application, settings)
    logger.info("CMS Cortex Agent API started. Snowflake account: %s", settings.snowflake_account)
    yield


app = FastAPI(
    title="CMS Snowflake Cortex Agent API",
    description=(
        "REST API that bridges Claude AI with the Snowflake Cortex Analyst "
        "for CMS (Centers for Medicare & Medicaid Services) healthcare analytics."
    ),
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)


# ── CORS ──────────────────────────────────────────────────────────────────
def _setup_cors(application: FastAPI, settings: Settings) -> None:
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


# ── Dependency injection ──────────────────────────────────────────────────
def get_snowflake_client(settings: Settings = Depends(get_settings)) -> SnowflakeClient:
    return SnowflakeClient(settings)


def get_claude_client(settings: Settings = Depends(get_settings)) -> ClaudeClient:
    return ClaudeClient(settings)


# ── Request / Response models ─────────────────────────────────────────────
class AskRequest(BaseModel):
    question: str = Field(..., min_length=3, description="Natural-language question about CMS data.")
    conversation_history: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Previous Cortex Analyst conversation turns for multi-turn Q&A.",
    )
    include_summary: bool = Field(
        default=False,
        description="If true, include a Claude-generated natural-language summary.",
    )
    execute_sql: bool = Field(
        default=True,
        description="If true, automatically execute the SQL returned by Cortex Analyst.",
    )


class AskResponse(BaseModel):
    question: str
    sql: str | None
    interpretation: str
    columns: list[str]
    data: list[list[Any]]
    summary: str | None = None
    request_id: str | None = None


class DashboardRequest(BaseModel):
    question: str = Field(..., min_length=3)
    conversation_history: list[dict[str, Any]] = Field(default_factory=list)


class DashboardResponse(BaseModel):
    question: str
    sql: str | None
    interpretation: str
    dashboard_code: str


class SqlRequest(BaseModel):
    sql: str = Field(..., min_length=5)


class SqlResponse(BaseModel):
    columns: list[str]
    data: list[list[Any]]
    row_count: int


# ── Routes ────────────────────────────────────────────────────────────────
@app.get("/api/health", tags=["System"])
async def health() -> dict[str, str]:
    """Liveness probe."""
    return {"status": "ok"}


@app.post("/api/ask", response_model=AskResponse, tags=["Cortex Agent"])
async def ask(
    body: AskRequest,
    sf_client: SnowflakeClient = Depends(get_snowflake_client),
    claude_client: ClaudeClient = Depends(get_claude_client),
) -> AskResponse:
    """
    Send a natural-language question to the Snowflake Cortex Analyst.

    The agent translates the question into SQL using the CMS semantic model,
    optionally executes the SQL, and optionally generates a Claude summary.
    """
    try:
        result = sf_client.ask(
            question=body.question,
            conversation_history=body.conversation_history or None,
            execute=body.execute_sql,
        )
    except Exception as exc:
        logger.error("Cortex Analyst error: %s\n%s", exc, traceback.format_exc())
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Cortex Analyst error: {exc}",
        ) from exc

    summary: str | None = None
    if body.include_summary and result["data"]:
        try:
            summary = claude_client.summarise_results(
                question=body.question,
                columns=result["columns"],
                data=result["data"],
                interpretation=result["interpretation"],
            )
        except Exception as exc:
            logger.warning("Claude summary failed (non-fatal): %s", exc)
            summary = None

    request_id: str | None = result["analyst_response"].get("request_id")

    return AskResponse(
        question=body.question,
        sql=result["sql"],
        interpretation=result["interpretation"],
        columns=result["columns"],
        data=result["data"],
        summary=summary,
        request_id=request_id,
    )


@app.post("/api/ask/dashboard", response_model=DashboardResponse, tags=["Cortex Agent"])
async def ask_dashboard(
    body: DashboardRequest,
    sf_client: SnowflakeClient = Depends(get_snowflake_client),
    claude_client: ClaudeClient = Depends(get_claude_client),
) -> DashboardResponse:
    """
    End-to-end pipeline: NL question → Cortex Analyst → execute SQL → Claude dashboard code.

    Returns ready-to-run Streamlit Python code.
    """
    try:
        result = sf_client.ask(
            question=body.question,
            conversation_history=body.conversation_history or None,
            execute=True,
        )
    except Exception as exc:
        logger.error("Cortex Analyst error: %s", exc)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    if not result["sql"]:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Cortex Analyst did not return SQL for this question.",
        )

    try:
        dashboard_code = claude_client.generate_dashboard_code(
            question=body.question,
            columns=result["columns"],
            data=result["data"],
            interpretation=result["interpretation"],
        )
    except Exception as exc:
        logger.error("Claude dashboard generation error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Claude error: {exc}",
        ) from exc

    return DashboardResponse(
        question=body.question,
        sql=result["sql"],
        interpretation=result["interpretation"],
        dashboard_code=dashboard_code,
    )


@app.post("/api/sql", response_model=SqlResponse, tags=["SQL"])
async def execute_sql(
    body: SqlRequest,
    sf_client: SnowflakeClient = Depends(get_snowflake_client),
) -> SqlResponse:
    """Execute a raw SQL statement against Snowflake (for admin / debugging)."""
    try:
        result = sf_client.execute_sql(body.sql)
    except Exception as exc:
        logger.error("SQL execution error: %s", exc)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    columns = [
        col["name"]
        for col in result.get("resultSetMetaData", {}).get("rowType", [])
    ]
    data = result.get("data", [])
    return SqlResponse(columns=columns, data=data, row_count=len(data))
