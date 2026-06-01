-- ============================================================
-- 03_create_cortex_agent.sql
-- Creates a Snowflake Cortex Analyst semantic model stage
-- and registers the Cortex Agent REST endpoint.
-- ============================================================

USE ROLE    CMS_DEVELOPER_ROLE;
USE WAREHOUSE CMS_WH;
USE DATABASE  CMS_DB;
USE SCHEMA    CMS_DB.CORTEX;

-- ── Stage to host the semantic model YAML ──────────────────
CREATE STAGE IF NOT EXISTS CMS_SEMANTIC_STAGE
  DIRECTORY = (ENABLE = TRUE)
  ENCRYPTION = (TYPE = 'SNOWFLAKE_SSE')
  COMMENT = 'Stores YAML semantic model definitions for Cortex Analyst';

-- Upload the semantic model (run from SnowSQL or Snowsight):
--   PUT file://snowflake/semantic_models/cms_semantic_model.yaml
--       @CMS_DB.CORTEX.CMS_SEMANTIC_STAGE AUTO_COMPRESS=FALSE;

-- ── Verify the uploaded file ───────────────────────────────
-- LIST @CMS_DB.CORTEX.CMS_SEMANTIC_STAGE;

-- ── Grant stage access to API role ─────────────────────────
GRANT READ ON STAGE CMS_SEMANTIC_STAGE TO ROLE CMS_API_ROLE;

-- ── Network Rule & External Access Integration ─────────────
-- Required if calling external APIs (e.g., Claude) from Snowpark.
-- Adjust allowed_values to match your Claude API endpoint.
CREATE NETWORK RULE IF NOT EXISTS CLAUDE_API_RULE
  TYPE            = HOST_PORT
  MODE            = EGRESS
  VALUE_LIST      = ('api.anthropic.com:443')
  COMMENT         = 'Allow egress to Anthropic Claude API';

CREATE EXTERNAL ACCESS INTEGRATION IF NOT EXISTS CLAUDE_ACCESS_INTEGRATION
  ALLOWED_NETWORK_RULES    = (CLAUDE_API_RULE)
  ENABLED                  = TRUE
  COMMENT                  = 'EAI for Claude API calls from Snowpark UDFs';

-- Grant to developer/API roles
GRANT USAGE ON INTEGRATION CLAUDE_ACCESS_INTEGRATION TO ROLE CMS_API_ROLE;

-- ── Cortex Analyst – verify REST API readiness ─────────────
-- The Cortex Analyst endpoint is available at:
--   POST /api/v2/cortex/analyst/message
-- No additional DDL required – the endpoint is built-in.
-- See the Python API client (api/snowflake_client.py) for usage.

-- ── Optional: Cortex Search Service ───────────────────────
-- If your use case requires full-text / hybrid search:
-- CREATE CORTEX SEARCH SERVICE IF NOT EXISTS CMS_PROVIDER_SEARCH
--   ON PROVIDER_NAME, SPECIALTY, CITY
--   WAREHOUSE = CMS_WH
--   TARGET_LAG = '1 hour'
--   AS
--     SELECT PROVIDER_ID, PROVIDER_NAME, SPECIALTY, CITY, STATE
--     FROM CMS_DB.ANALYTICS.PROVIDERS;
