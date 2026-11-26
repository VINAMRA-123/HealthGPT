"""Pytest setup that runs before any test module is imported.

app.auth and app.db read their settings at import time. Providing harmless
defaults here lets the tests run on a fresh machine or in CI without a real
.env file. Real values from your environment or .env still win.
"""

import os

# Tests must never upload traces, even if your .env turns tracing on.
os.environ["LANGSMITH_TRACING"] = "false"
os.environ["LANGCHAIN_TRACING_V2"] = "false"

os.environ.setdefault("SUPABASE_URL", "https://example-project.supabase.co")
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+psycopg://test:test@localhost:5432/test",
)
