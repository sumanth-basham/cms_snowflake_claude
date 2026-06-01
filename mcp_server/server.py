"""
mcp_server/server.py
MCP (Model Context Protocol) server that exposes the CMS Snowflake Cortex
Agent as tools usable from Claude Code / Claude Desktop.

Tools exposed
─────────────
  cms_ask              – Ask a natural-language question; returns SQL + data.
  cms_dashboard        – Question → Cortex + Claude → Streamlit code.
  cms_execute_sql      – Execute raw SQL (read-only guard included).
  cms_summarise        – Summarise previously retrieved data with Claude.

Run locally:
  python -m mcp_server.server

Configure in Claude Desktop (claude_desktop_config.json):
  {
    "mcpServers": {
      "cms_snowflake": {
        "command": "python",
        "args": ["-m", "mcp_server.server"],
        "cwd": "/path/to/cms_snowflake_claude",
        "env": { "DOTENV_PATH": ".env" }
      }
    }
  }
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Any

# Allow running as `python -m mcp_server.server` from the project root
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from api.config import get_settings
from api.snowflake_client import SnowflakeClient
from api.claude_client import ClaudeClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s – %(message)s")
logger = logging.getLogger(__name__)

# ── Singletons ───────────────────────────────────────────────────────────────
_settings = get_settings()
_sf_client = SnowflakeClient(_settings)
_claude_client = ClaudeClient(_settings)

# ── Tool definitions ─────────────────────────────────────────────────────────
TOOLS: list[Tool] = [
    Tool(
        name="cms_ask",
        description=(
            "Ask a natural-language question about CMS (Centers for Medicare & Medicaid "
            "Services) data. The Snowflake Cortex Analyst translates the question into SQL "
            "using the CMS semantic model, executes it, and returns the results."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "Natural-language question about CMS data.",
                },
                "include_summary": {
                    "type": "boolean",
                    "default": True,
                    "description": "Include a Claude-generated executive summary.",
                },
            },
            "required": ["question"],
        },
    ),
    Tool(
        name="cms_dashboard",
        description=(
            "Generate a complete Streamlit dashboard for a CMS data question. "
            "The Cortex Analyst retrieves the data and Claude writes the Python/Streamlit code."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "Natural-language question; the dashboard will visualise the answer.",
                },
            },
            "required": ["question"],
        },
    ),
    Tool(
        name="cms_execute_sql",
        description=(
            "Execute a read-only SQL SELECT statement against CMS_DB.ANALYTICS in Snowflake. "
            "Only SELECT statements are permitted."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "sql": {
                    "type": "string",
                    "description": "A SQL SELECT statement to execute.",
                },
            },
            "required": ["sql"],
        },
    ),
    Tool(
        name="cms_summarise",
        description=(
            "Given columns and row data (from a previous cms_ask call), "
            "ask Claude to produce a concise executive summary."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "question": {"type": "string"},
                "columns": {"type": "array", "items": {"type": "string"}},
                "data": {"type": "array"},
                "interpretation": {"type": "string", "default": ""},
            },
            "required": ["question", "columns", "data"],
        },
    ),
]


# ── Handler ──────────────────────────────────────────────────────────────────
async def handle_call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Dispatch a tool call to the appropriate handler."""

    if name == "cms_ask":
        result = _sf_client.ask(
            question=arguments["question"],
            execute=True,
        )
        output: dict[str, Any] = {
            "sql": result["sql"],
            "interpretation": result["interpretation"],
            "columns": result["columns"],
            "row_count": len(result["data"]),
            "data": result["data"][:50],  # cap rows sent to Claude
        }
        if arguments.get("include_summary", True) and result["data"]:
            output["summary"] = _claude_client.summarise_results(
                question=arguments["question"],
                columns=result["columns"],
                data=result["data"],
                interpretation=result["interpretation"],
            )
        return [TextContent(type="text", text=json.dumps(output, indent=2))]

    if name == "cms_dashboard":
        result = _sf_client.ask(question=arguments["question"], execute=True)
        if not result["sql"]:
            return [TextContent(type="text", text="Cortex Analyst could not generate SQL for this question.")]
        code = _claude_client.generate_dashboard_code(
            question=arguments["question"],
            columns=result["columns"],
            data=result["data"],
            interpretation=result["interpretation"],
        )
        payload = {
            "sql": result["sql"],
            "interpretation": result["interpretation"],
            "streamlit_code": code,
        }
        return [TextContent(type="text", text=json.dumps(payload, indent=2))]

    if name == "cms_execute_sql":
        sql = arguments["sql"].strip()
        if not sql.upper().lstrip("(").startswith("SELECT"):
            return [TextContent(type="text", text="Error: Only SELECT statements are permitted.")]
        result = _sf_client.execute_sql(sql)
        columns = [col["name"] for col in result.get("resultSetMetaData", {}).get("rowType", [])]
        data = result.get("data", [])
        return [TextContent(type="text", text=json.dumps({"columns": columns, "data": data}, indent=2))]

    if name == "cms_summarise":
        summary = _claude_client.summarise_results(
            question=arguments["question"],
            columns=arguments["columns"],
            data=arguments["data"],
            interpretation=arguments.get("interpretation", ""),
        )
        return [TextContent(type="text", text=summary)]

    return [TextContent(type="text", text=f"Unknown tool: {name}")]


# ── Server bootstrap ──────────────────────────────────────────────────────────
async def main() -> None:
    server = Server("cms-snowflake-claude")

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return TOOLS

    @server.call_tool()
    async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
        logger.info("Tool call: %s  args=%s", name, list(arguments.keys()))
        try:
            return await handle_call_tool(name, arguments)
        except Exception as exc:
            logger.error("Tool %s failed: %s", name, exc)
            return [TextContent(type="text", text=f"Error: {exc}")]

    async with stdio_server() as (read_stream, write_stream):
        logger.info("CMS Snowflake Claude MCP server running (stdio transport).")
        await server.run(read_stream, write_stream, server.create_initialization_options())


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
