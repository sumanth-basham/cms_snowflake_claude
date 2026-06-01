-- ============================================================
-- 01_create_roles_and_grants.sql
-- Sets up roles, warehouses, and databases for CMS Cortex Agent
-- Run as ACCOUNTADMIN
-- ============================================================

USE ROLE ACCOUNTADMIN;

-- ── Warehouse ──────────────────────────────────────────────
CREATE WAREHOUSE IF NOT EXISTS CMS_WH
  WAREHOUSE_SIZE = 'SMALL'
  AUTO_SUSPEND   = 60
  AUTO_RESUME    = TRUE
  COMMENT        = 'Warehouse for CMS Snowflake Cortex Agent';

-- ── Database & Schema ──────────────────────────────────────
CREATE DATABASE IF NOT EXISTS CMS_DB
  COMMENT = 'CMS (Centers for Medicare & Medicaid Services) data';

CREATE SCHEMA IF NOT EXISTS CMS_DB.RAW
  COMMENT = 'Raw CMS data loaded from external sources';

CREATE SCHEMA IF NOT EXISTS CMS_DB.ANALYTICS
  COMMENT = 'Curated CMS analytics tables for Cortex Agent';

CREATE SCHEMA IF NOT EXISTS CMS_DB.CORTEX
  COMMENT = 'Cortex Agent configurations and semantic models';

-- ── Application Role ───────────────────────────────────────
CREATE ROLE IF NOT EXISTS CMS_CORTEX_ROLE
  COMMENT = 'Role for CMS Cortex Agent – read access to analytics schema';

GRANT USAGE ON WAREHOUSE CMS_WH                 TO ROLE CMS_CORTEX_ROLE;
GRANT USAGE ON DATABASE  CMS_DB                 TO ROLE CMS_CORTEX_ROLE;
GRANT USAGE ON SCHEMA    CMS_DB.ANALYTICS       TO ROLE CMS_CORTEX_ROLE;
GRANT USAGE ON SCHEMA    CMS_DB.CORTEX          TO ROLE CMS_CORTEX_ROLE;
GRANT SELECT ON ALL TABLES IN SCHEMA CMS_DB.ANALYTICS TO ROLE CMS_CORTEX_ROLE;
GRANT SELECT ON FUTURE TABLES IN SCHEMA CMS_DB.ANALYTICS TO ROLE CMS_CORTEX_ROLE;

-- Allow the role to use Cortex AI functions
GRANT DATABASE ROLE SNOWFLAKE.CORTEX_USER TO ROLE CMS_CORTEX_ROLE;

-- ── API / Service Account Role ─────────────────────────────
CREATE ROLE IF NOT EXISTS CMS_API_ROLE
  COMMENT = 'Role for external API service account; narrower permissions than CORTEX_ROLE';

GRANT ROLE CMS_CORTEX_ROLE TO ROLE CMS_API_ROLE;

-- ── Developer Role ─────────────────────────────────────────
CREATE ROLE IF NOT EXISTS CMS_DEVELOPER_ROLE
  COMMENT = 'Full access role for developers building/testing the agent';

GRANT ROLE CMS_API_ROLE TO ROLE CMS_DEVELOPER_ROLE;
GRANT ALL PRIVILEGES ON DATABASE CMS_DB TO ROLE CMS_DEVELOPER_ROLE;
GRANT ALL PRIVILEGES ON ALL SCHEMAS IN DATABASE CMS_DB TO ROLE CMS_DEVELOPER_ROLE;

-- Assign developer role to SYSADMIN so it inherits management
GRANT ROLE CMS_DEVELOPER_ROLE TO ROLE SYSADMIN;
