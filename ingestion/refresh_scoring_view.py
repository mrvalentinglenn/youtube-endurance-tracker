"""Refreshes the videos_scored materialised view via the refresh_scoring_view() RPC (see
DECISIONS.md, 2026-09-20, "Refreshing videos_scored needs a database function and two
raised timeouts"). Small and reusable on purpose -- step 6's refresh script needs exactly
this call as its final step, after its own checks pass.

The refresh takes over a minute on 98,300 rows. The default Supabase/httpx client read
timeout (~60s) raises httpx.ReadTimeout on a refresh that actually succeeds server-side --
Postgres keeps running the REFRESH regardless of whether the client is still listening.
So this script builds its own client with a long read timeout instead of using the shared
one from config.py, and it does not treat a timeout on the RPC call itself as failure --
only a verification query afterwards decides that.

Verification, not trust: after the call returns (or times out client-side), this queries
videos_scored for one or more sentinel videos and confirms their stored values (e.g.
score_views) reflect what's currently in videos.baseline_views -- not just that the RPC
call returned without raising.

videos_scored is granted to anon only (DECISIONS.md, 2026-09-20, step 7b: "the only
object the front end reads"), deliberately -- service_role, which every other ingestion
script uses, has no SELECT grant on it at all. Discovered here: the secret-key client
gets `permission denied for materialized view videos_scored`. Rather than widen that
grant (a schema change this script has no business making on its own), verification
reads through a second client built with the front end's own publishable key, from
frontend/.env -- the same credential and the same read path the site itself uses, so a
successful verification here means the site would see it too.

Usage:
    python refresh_scoring_view.py [--sentinel VIDEO_ID ...]
"""

import argparse
import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
sys.stderr.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

import httpx
from postgrest.exceptions import APIError
from supabase import create_client
from supabase.client import ClientOptions

from config import SUPABASE_SECRET_KEY, SUPABASE_URL, supabase

REFRESH_READ_TIMEOUT_SECONDS = 600  # 10 minutes; the refresh itself measured over a minute
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
        "--sentinel",
        action="append",
        default=[],
        metavar="VIDEO_ID",
        help="A video_id to verify after the refresh (repeatable). Its videos_scored row is "
             "checked against the current videos.baseline_views, not just the RPC's own response.",
    )
    return parser.parse_args()


def main():
    args = parse_args()

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
