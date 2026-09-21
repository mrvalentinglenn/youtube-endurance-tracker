"""Refreshes the videos_scored materialised view, verifying against the database rather
than trusting the call's own response either way.

Two paths:

--direct (recommended on this database, see below) opens a real Postgres session via
psycopg and SUPABASE_DB_URL (the session pooler, not the transaction one -- SET
statement_timeout needs to survive for the following statement, which a transaction-mode
pooler cannot guarantee), sets statement_timeout explicitly, and runs
`REFRESH MATERIALIZED VIEW CONCURRENTLY public.videos_scored` directly. No REST/RPC
gateway in the path at all.

The default path calls the refresh_scoring_view() RPC (DECISIONS.md, 2026-09-20,
"Refreshing videos_scored needs a database function and two raised timeouts") through the
Supabase client. This was the original design -- the client has no other way to run DDL
-- but proved unreliable once nearly every row's baseline changed at once (2026-09-21):
Supabase's own gateway in front of PostgREST returns a 504 "upstream request timeout" on
a refresh this large, independent of any timeout set on this end (raising this script's
own client timeout does nothing, since the gateway is what's cutting the connection, not
this client), and confirmed by a 15-minute wait that the refresh had NOT completed
server-side either. --direct exists because of that -- prefer it.

Verification, not trust: after either path, this queries videos_scored for one or more
sentinel videos and confirms their stored values (e.g. score_views) reflect what's
currently in videos.baseline_views -- not just that the call returned without raising.

videos_scored is granted to anon only (DECISIONS.md, 2026-09-20, step 7b: "the only
object the front end reads"), deliberately -- service_role, which every other ingestion
script uses, has no SELECT grant on it at all (confirmed: the secret-key client gets
`permission denied for materialized view videos_scored`). Rather than widen that grant (a
schema change this script has no business making on its own), verification reads through
a second client built with the front end's own publishable key, from frontend/.env -- the
same credential and the same read path the site itself uses, so a successful
verification here means the site would see it too.

Usage:
    python refresh_scoring_view.py --direct [--sentinel VIDEO_ID ...]
    python refresh_scoring_view.py [--sentinel VIDEO_ID ...]   # the RPC path
"""

import argparse
import re
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
sys.stderr.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

import httpx
import psycopg
from postgrest.exceptions import APIError
from supabase import create_client
from supabase.client import ClientOptions

from config import SUPABASE_DB_URL, SUPABASE_SECRET_KEY, SUPABASE_URL, supabase

REFRESH_READ_TIMEOUT_SECONDS = 600  # 10 minutes; used by the RPC path's client
DIRECT_STATEMENT_TIMEOUT_MINUTES = 30  # used by --direct's session
FRONTEND_ENV_PATH = Path(__file__).resolve().parent.parent / "frontend" / ".env"


def build_long_timeout_client():
    """A separate client from config.py's shared one, with a read timeout long enough to
    outlast the refresh. Not thread-shared -- this script is single-threaded."""
    options = ClientOptions(postgrest_client_timeout=REFRESH_READ_TIMEOUT_SECONDS)
    return create_client(SUPABASE_URL, SUPABASE_SECRET_KEY, options=options)


def build_anon_client():
    """Reads frontend/.env directly for VITE_SUPABASE_URL / VITE_SUPABASE_PUBLISHABLE_KEY
    -- the only credential with SELECT on videos_scored. Not loaded via config.py: no
    ingestion script needs the anon key for anything else, and config.py's own docstring
    asks to keep it free of script-specific concerns."""
    if not FRONTEND_ENV_PATH.exists():
        raise RuntimeError(f"Can't verify: {FRONTEND_ENV_PATH} not found (needed for the anon key).")
    text = FRONTEND_ENV_PATH.read_text(encoding="utf-8")
    url_match = re.search(r"^VITE_SUPABASE_URL=(.+)$", text, re.MULTILINE)
    key_match = re.search(r"^VITE_SUPABASE_PUBLISHABLE_KEY=(.+)$", text, re.MULTILINE)
    if not url_match or not key_match:
        raise RuntimeError(f"Can't verify: {FRONTEND_ENV_PATH} is missing VITE_SUPABASE_URL or VITE_SUPABASE_PUBLISHABLE_KEY.")
    return create_client(url_match.group(1).strip(), key_match.group(1).strip())


def call_refresh_direct(timeout_minutes):
    """Opens its own psycopg connection -- no REST/RPC gateway in the path, so the 504
    seen on the RPC path can't happen here. autocommit=True: SET statement_timeout must
    apply to the session before the REFRESH runs, not be scoped to (and rolled back
    with) a transaction."""
    if not SUPABASE_DB_URL:
        raise RuntimeError("SUPABASE_DB_URL is not set (check the root .env) -- required for --direct.")

    print(f"Connecting directly to Postgres (session pooler)...", flush=True)
    with psycopg.connect(SUPABASE_DB_URL, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(f"SET statement_timeout = '{timeout_minutes}min'")
            print(
                f"statement_timeout set to {timeout_minutes} minutes. Running "
                f"REFRESH MATERIALIZED VIEW CONCURRENTLY public.videos_scored -- "
                f"this measured ~6 minutes on this run's diff, waiting for it to finish...",
                flush=True,
            )
            start = time.monotonic()
            cur.execute("REFRESH MATERIALIZED VIEW CONCURRENTLY public.videos_scored")
            elapsed = time.monotonic() - start
            print(f"REFRESH completed in {elapsed:.1f}s.")


def call_refresh():
    client = build_long_timeout_client()
    print(f"Calling refresh_scoring_view() (client read timeout {REFRESH_READ_TIMEOUT_SECONDS}s)...", flush=True)
    try:
        client.rpc("refresh_scoring_view").execute()
        print("RPC call returned normally.")
    except httpx.ReadTimeout:
        print(
            "Client-side httpx.ReadTimeout on the RPC call. Per DECISIONS.md this can "
            "happen even when the refresh succeeds server-side -- verifying below rather "
            "than treating this as failure."
        )
    except APIError as error:
        # Seen in practice: Supabase's own gateway (not this client -- raising our
        # postgrest_client_timeout does nothing here) gives up on the long-running RPC
        # and returns a 504 "upstream request timeout" itself. The REFRESH statement
        # was already dispatched to Postgres, which has its own 15-minute
        # statement_timeout for service_role (see DECISIONS.md) and is not necessarily
        # cancelled just because the gateway closed the HTTP response -- so this is
        # treated the same as a client-side read timeout: not fatal, verify below.
        if str(error.code) == "504" or "timeout" in str(error).lower():
            print(f"Server-side gateway timeout on the RPC call ({error}). Verifying below rather than treating this as failure.")
        else:
            print(f"RPC call raised a non-timeout error: {error}")
            raise


def verify_sentinel(anon_client, video_id):
    """Compares videos.baseline_views (the just-written source) against
    videos_scored.score_views's implied baseline (views / score_views) for one video.
    Rather than recomputing score_views ourselves (duplicating the view's own division
    and its zero guard), this fetches both rows and reports them side by side so a human
    can see whether the view is now serving the new baseline."""
    video = supabase.table("videos").select("video_id, baseline_views").eq("video_id", video_id).execute().data
    scored = anon_client.table("videos_scored").select("video_id, views, score_views").eq("video_id", video_id).execute().data

    if not video or not scored:
        print(f"  {video_id}: not found in videos and/or videos_scored -- cannot verify")
        return False

    baseline_views = video[0]["baseline_views"]
    views = scored[0]["views"]
    score_views = scored[0]["score_views"]

    implied_baseline = views / score_views if score_views else None
    matches = (
        implied_baseline is not None
        and baseline_views is not None
        and abs(implied_baseline - baseline_views) < 0.5
    )
    print(
        f"  {video_id}: videos.baseline_views={baseline_views}  "
        f"videos_scored: views={views} score_views={score_views} implied_baseline={implied_baseline} "
        f"-- {'MATCHES (view is current)' if matches else 'DOES NOT MATCH (view is stale?)'}"
    )
    return matches


def parse_args():
    parser = argparse.ArgumentParser(description="Refreshes videos_scored and verifies it against videos.")
    parser.add_argument(
        "--direct",
        action="store_true",
        help="Use a direct psycopg connection (SUPABASE_DB_URL) instead of the refresh_scoring_view() "
             "RPC. Recommended: the RPC path 504s on a large refresh. See module docstring.",
    )
    parser.add_argument(
        "--timeout-minutes",
        type=int,
        default=DIRECT_STATEMENT_TIMEOUT_MINUTES,
        help=f"--direct only: statement_timeout for the session, in minutes (default {DIRECT_STATEMENT_TIMEOUT_MINUTES}).",
    )
    parser.add_argument(
        "--sentinel",
        action="append",
        default=[],
        metavar="VIDEO_ID",
        help="A video_id to verify after the refresh (repeatable). Its videos_scored row is "
             "checked against the current videos.baseline_views, not just the call's own response.",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    if args.direct:
        call_refresh_direct(args.timeout_minutes)
    else:
        call_refresh()

    if not args.sentinel:
        print("No --sentinel given -- nothing verified. Pass one or more --sentinel VIDEO_ID.")
        sys.exit(1)

    anon_client = build_anon_client()

    print("\nVerifying against videos_scored:")
    all_match = True
    for video_id in args.sentinel:
        if not verify_sentinel(anon_client, video_id):
            all_match = False

    if not all_match:
        print("\nAt least one sentinel did not match -- the refresh may not have completed. Not confirmed.")
        sys.exit(1)

    print("\nAll sentinels match. Refresh confirmed complete.")


if __name__ == "__main__":
    main()
