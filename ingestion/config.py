"""Shared configuration for the ingestion scripts.

Loads environment variables from .env and exposes what every ingestion script
needs: the Supabase credentials, the YouTube API key, and a ready-to-use
Supabase client. Keep this file small and free of script-specific logic
(spreadsheet parsing, YouTube API calls, upserts belong in the scripts that
import from here).
"""

import os

from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_SECRET_KEY = os.environ.get("SUPABASE_SECRET_KEY")
YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY")
# Direct Postgres connection (session pooler). Not required: only scripts that need a
# real session (SET statement_timeout, long-running DDL like REFRESH MATERIALIZED VIEW
# outside the REST/RPC gateway) use it -- everything else uses the supabase client below.
SUPABASE_DB_URL = os.environ.get("SUPABASE_DB_URL")

_required = {
    "SUPABASE_URL": SUPABASE_URL,
    "SUPABASE_SECRET_KEY": SUPABASE_SECRET_KEY,
    "YOUTUBE_API_KEY": YOUTUBE_API_KEY,
}
_missing = [name for name, value in _required.items() if not value]
if _missing:
    raise RuntimeError(
        f"Missing required environment variable(s): {', '.join(_missing)}. "
        "Check your .env file."
    )

supabase = create_client(SUPABASE_URL, SUPABASE_SECRET_KEY)
