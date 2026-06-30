# CMS Snowflake Claude Agent

A production-ready starter for CMS analytics that combines Snowflake Cortex Analyst, optional Cortex Search, a FastAPI backend, and a lightweight local dashboard.

## Repository layout

- `.github/prompts/snowflake-ai-agent.prompt.md` – source prompt used for the scaffold
- `snowflake/setup.sql` – roles, warehouse, sample CMS tables, seed data, and semantic-model stage
- `snowflake/semantic_model.yaml` – Cortex Analyst semantic model
- `snowflake/cortex_search_setup.sql` – optional Cortex Search service for provider lookups
- `agents/` – analyst, search, and orchestration logic
- `api/` – FastAPI app and Snowflake REST client
- `dashboard/` – static dashboard plus local launcher
- `tests/` – focused agent, orchestrator, and API tests

## Quick start

1. Copy the environment template:

   ```bash
   cp .env.template .env
   ```

2. Update `.env` with valid Snowflake credentials. OAuth is the safest default for local development. If you prefer key-pair JWT auth, generate the RSA key separately and set `SNOWFLAKE_PRIVATE_KEY_PATH`.

3. Create Snowflake objects:

   ```bash
   snowsql -f snowflake/setup.sql
   snowsql -q "PUT file://snowflake/semantic_model.yaml @CMS_DB.CORTEX.CMS_SEMANTIC_STAGE AUTO_COMPRESS=FALSE OVERWRITE=TRUE"
   snowsql -f snowflake/cortex_search_setup.sql
   ```

4. Install dependencies:

   ```bash
   make setup
   ```

5. Start the local API and dashboard together:

   ```bash
   make run
   ```

   - API: `http://127.0.0.1:8000`
   - Dashboard: `http://127.0.0.1:8080`

## API endpoints

- `GET /api/health`
- `POST /api/ask`
- `POST /api/ask/dashboard`
- `POST /api/sql`

`/api/ask` routes the question through the orchestrator. Analytical questions use Cortex Analyst. Entity-style lookup questions can use Cortex Search first and fall back to a guarded SQL search.

## Local dashboard behavior

The dashboard is intentionally simple and dependency-light:

- submits natural-language prompts to the FastAPI backend
- renders returned SQL and tabular rows
- shows a lightweight SVG chart preview when the agent returns a chart hint
- can request a dashboard payload from `/api/ask/dashboard`

## Testing

```bash
make test
```

The tests mock the Snowflake-facing behavior so they can run without real credentials.

## Notes and assumptions

- The Snowflake REST wrappers are defensive because response envelopes can vary by account features and rollout stage.
- The local dashboard does not require external JavaScript CDNs.
- `/api/sql` only accepts read-only SQL (`SELECT`, `WITH`, `SHOW`, `DESCRIBE`).
- The scaffold avoids hardcoded secrets; populate `.env` locally before connecting to Snowflake.
