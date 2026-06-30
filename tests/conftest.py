from __future__ import annotations

import os

os.environ.setdefault("SNOWFLAKE_ACCOUNT", "test-account")
os.environ.setdefault("SNOWFLAKE_USER", "test-user")
os.environ.setdefault("SNOWFLAKE_AUTH_METHOD", "oauth")
os.environ.setdefault("SNOWFLAKE_OAUTH_TOKEN", "fake-token")
os.environ.setdefault("CORS_ORIGINS", "http://127.0.0.1:8080")
