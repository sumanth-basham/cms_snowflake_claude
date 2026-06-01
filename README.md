# CMS Snowflake + Claude Analytics

> **Natural-language analytics for CMS (Centers for Medicare & Medicaid Services) data**,
> powered by **Snowflake Cortex Analyst** and **Anthropic Claude AI**.

---

## Architecture Overview

```
┌──────────────────────────────────────────────────────────────────────┐
│                         User / Claude Code                           │
│   (browser, Claude Desktop MCP, Cursor IDE, Streamlit app)           │
└────────────┬─────────────────────────────────────────────────────────┘
             │  Natural-language question
             ▼
┌──────────────────────────────────────────────────────────────────────┐
│                    FastAPI Backend  (api/)                            │
│                                                                      │
│  POST /api/ask           – NL → Cortex Analyst → SQL → data         │
│  POST /api/ask/dashboard – NL → SQL → data → Claude dashboard code  │
│  POST /api/sql           – raw SQL execution                         │
└────────────┬───────────────────────────────┬────────────────────────┘
             │                               │
             ▼                               ▼
┌─────────────────────────┐    ┌─────────────────────────────────────┐
│  Snowflake Cortex        │    │        Anthropic Claude API          │
│  Analyst REST API        │    │  (summaries, dashboard code gen)     │
│  /api/v2/cortex/analyst  │    └─────────────────────────────────────┘
│  /api/v2/statements      │
│                          │
│  CMS_DB.ANALYTICS        │
│  ├── PROVIDERS           │
│  ├── CLAIMS              │
│  ├── DRUG_UTILIZATION    │
│  └── QUALITY_MEASURES    │
└─────────────────────────┘
```

### How the Workflow Works

1. **Snowflake Cortex Agent** – The agent lives inside your Snowflake environment,
   connected to CMS data via a YAML **Semantic Model** (`snowflake/semantic_models/cms_semantic_model.yaml`).
   All queries honour your existing RBAC governance (`CMS_CORTEX_ROLE`, `CMS_API_ROLE`).

2. **Expose the API** – `api/main.py` wraps the Snowflake Cortex Analyst REST endpoint
   as a FastAPI service.  Three authentication methods are supported:
   `key_pair` (JWT, recommended), `oauth`, and `pat`.

3. **Connect to Claude** – Two integration paths are provided:
   - **MCP Server** (`mcp_server/server.py`) – plug the Cortex Agent directly into
     Claude Code, Claude Desktop, or Cursor as a set of tools.
   - **Streamlit App** (`streamlit_app/`) – a full-featured web UI that bridges
     Claude and Snowflake for dashboard generation.

4. **Create Dashboards** – Prompt Claude (via the Dashboard Builder page or the
   `cms_dashboard` MCP tool) to generate ready-to-run Streamlit/Plotly code from
   your CMS data query results.

---

## Repository Structure

```
cms_snowflake_claude/
│
├── snowflake/
│   ├── setup/
│   │   ├── 01_create_roles_and_grants.sql   # RBAC setup (run as ACCOUNTADMIN)
│   │   ├── 02_create_sample_tables.sql      # CMS schema + seed data
│   │   └── 03_create_cortex_agent.sql       # Stage, network rules, EAI
│   └── semantic_models/
│       └── cms_semantic_model.yaml          # Cortex Analyst semantic model
│
├── api/                                     # FastAPI backend
│   ├── main.py                              # API routes
│   ├── config.py                            # Pydantic settings (env vars)
│   ├── auth.py                              # Key-pair / OAuth / PAT auth
│   ├── snowflake_client.py                  # Snowflake REST client
│   ├── claude_client.py                     # Anthropic Claude client
│   └── requirements.txt
│
├── mcp_server/                              # MCP server for Claude Code
│   ├── server.py                            # Tool definitions + handlers
│   └── requirements.txt
│
├── streamlit_app/                           # Streamlit frontend
│   ├── app.py                               # Home page
│   ├── requirements.txt
│   └── pages/
│       ├── 1_Ask_CMS.py                     # NL Q&A chat interface
│       ├── 2_Dashboard_Builder.py           # Claude-generated dashboards
│       ├── 3_Drug_Utilization.py            # Pre-built Part-D dashboard
│       ├── 4_Quality_Measures.py            # Pre-built star ratings dashboard
│       └── 5_Claims_Analysis.py             # Pre-built claims dashboard
│
├── tests/
│   └── test_api.py                          # FastAPI unit tests (mocked)
│
├── .env.example                             # Environment variable template
├── .gitignore
├── pyproject.toml
├── requirements.txt                         # Root dev/test dependencies
└── README.md
```

---

## Quick Start

### Prerequisites

- Python 3.11+
- A Snowflake account with Cortex AI enabled
- An Anthropic API key
- RSA key pair for Snowflake service account (recommended)

### 1 – Snowflake Setup

Run the scripts in order from Snowsight or SnowSQL:

```bash
# As ACCOUNTADMIN
snowsql -f snowflake/setup/01_create_roles_and_grants.sql
snowsql -f snowflake/setup/02_create_sample_tables.sql
snowsql -f snowflake/setup/03_create_cortex_agent.sql

# Upload the semantic model to the internal stage
snowsql -q "PUT file://snowflake/semantic_models/cms_semantic_model.yaml \
  @CMS_DB.CORTEX.CMS_SEMANTIC_STAGE AUTO_COMPRESS=FALSE OVERWRITE=TRUE;"
```

### 2 – Environment Configuration

```bash
cp .env.example .env
# Edit .env – fill in SNOWFLAKE_ACCOUNT, SNOWFLAKE_USER, ANTHROPIC_API_KEY, etc.
```

### 3 – Install Dependencies

```bash
python -m venv .venv && source .venv/bin/activate

# API backend
pip install -r api/requirements.txt

# MCP server
pip install -r mcp_server/requirements.txt

# Streamlit dashboard
pip install -r streamlit_app/requirements.txt
```

### 4 – Run the API Backend

```bash
uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
```

Interactive API docs: [http://localhost:8000/docs](http://localhost:8000/docs)

### 5 – Run the Streamlit Dashboard

In a separate terminal:

```bash
streamlit run streamlit_app/app.py
```

Open [http://localhost:8501](http://localhost:8501).

### 6 – (Optional) Claude Code / Claude Desktop via MCP

Add the following to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "cms_snowflake": {
      "command": "python",
      "args": ["-m", "mcp_server.server"],
      "cwd": "/path/to/cms_snowflake_claude",
      "env": {}
    }
  }
}
```

Available MCP tools:
| Tool | Description |
|------|-------------|
| `cms_ask` | Natural-language Q&A – returns SQL + data + optional Claude summary |
| `cms_dashboard` | Generates complete Streamlit dashboard code |
| `cms_execute_sql` | Read-only SELECT execution |
| `cms_summarise` | Claude executive summary of provided data |

---

## Authentication

The API supports three Snowflake authentication methods (set via `SNOWFLAKE_AUTH_METHOD`):

| Method | `SNOWFLAKE_AUTH_METHOD` | Required Variables |
|--------|-------------------------|--------------------|
| **Key-Pair JWT** *(recommended)* | `key_pair` | `SNOWFLAKE_PRIVATE_KEY_PATH` |
| **OAuth** | `oauth` | `SNOWFLAKE_OAUTH_TOKEN` |
| **PAT / Password** *(dev only)* | `pat` | `SNOWFLAKE_PASSWORD` |

To generate an RSA key pair:

```bash
openssl genrsa 2048 | openssl pkcs8 -topk8 -inform PEM -out rsa_key.p8 -nocrypt
openssl rsa -in rsa_key.p8 -pubout -out rsa_key.pub
```

Register the public key with Snowflake:

```sql
ALTER USER cms_service_account
  SET RSA_PUBLIC_KEY='<paste contents of rsa_key.pub without header/footer>';
```

---

## Running Tests

```bash
pip install -r requirements.txt
pytest tests/ -v
```

All tests use `unittest.mock` to stub Snowflake and Anthropic network calls –
no real credentials are needed.

---

## API Reference

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/health` | Liveness probe |
| `POST` | `/api/ask` | NL question → Cortex Analyst → SQL + data + optional summary |
| `POST` | `/api/ask/dashboard` | NL question → SQL + Claude Streamlit code |
| `POST` | `/api/sql` | Execute raw SQL statement |

Full OpenAPI spec: `/docs` (Swagger UI) or `/redoc` (ReDoc).

---

## CMS Data Model

| Table | Description |
|-------|-------------|
| `PROVIDERS` | Medicare-enrolled hospitals and physicians |
| `CLAIMS` | Fee-for-service inpatient/outpatient claims |
| `DRUG_UTILIZATION` | Part-D prescription drug utilization by provider |
| `QUALITY_MEASURES` | CMS star ratings and performance rates |

In production, replace the seed data with real CMS datasets from the
[Snowflake Data Marketplace](https://app.snowflake.com/marketplace) or
loaded from [data.cms.gov](https://data.cms.gov).

---

## Security Notes

- **Never commit `.env`** – it is in `.gitignore`.
- Private key files (`*.p8`, `*.pem`) are also excluded by `.gitignore`.
- The MCP server's `cms_execute_sql` tool guards against non-SELECT statements.
- The Cortex Agent runs under `CMS_API_ROLE` which has read-only access to `ANALYTICS` schema.
- OAuth tokens and PATs should be rotated regularly; key-pair auth is preferred.
