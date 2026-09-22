"""Refreshes the videos_scored materialised view over a direct Postgres connection, and
verifies against the database rather than trusting the call's own response.

Only the direct path exists now. The original design called the refresh_scoring_view()
RPC (DECISIONS.md, 2026-09-20) through the Supabase client -- the only way to run DDL
without a direct connection -- but it proved unreliable once nearly every row's baseline
changed at once (2026-09-21): Supabase's own gateway in front of PostgREST returns a 504
"upstream request timeout" on a refresh that size, independent of any timeout set on this
end, and a 15-minute wait confirmed the refresh had NOT completed server-side either. The
RPC path was removed once this script's caller (step 6's refresh.py) was built, per
NEXT_STEPS.md step 6 -- there is no small refresh that would make it safe to keep: every
refresh rebuilds the whole view.

Plain vs. concurrent: plain (the default) blocks reads for its duration but rebuilds the
view compactly; concurrent keeps the view readable throughout but leaves old row versions
behind, which bloated videos_scored from 244 MB to 556 MB after two such refreshes in a
row (DECISIONS.md, 2026-09-21). Plain is correct while there are no visitors; switch to
concurrent once the site is live, with an occasional plain refresh at a quiet moment to
compact (same entry).

Verification, not trust: after the refresh, this queries videos_scored for one or more
sentinel videos and confirms their stored values (e.g. score_views) reflect what's
currently in videos.baseline_views -- not just that the call returned without raising.

videos_scored is granted to anon (DECISIONS.md, 2026-09-20, step 7b: "the only object the
front end reads") and, separately, to service_role (DECISIONS.md, 2026-09-21). Verification
deliberately reads through a second client built with the front end's own publishable key,
from frontend/.env, rather than the shared service_role client every other ingestion script
uses -- it checks the same read path a real visitor uses, including the anon grant itself,
which a service_role-based check would not.

Usage:
    python refresh_scoring_view.py [--sentinel VIDEO_ID ...] [--concurrent] [--timeout-minutes N]
"""

import argparse
import re
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
sys.stderr.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

import psycopg
from supabase import create_client

from config import SUPABASE_DB_URL, supabase

DIRECT_STATEMENT_TIMEOUT_MINUTES = 30
FRONTEND_ENV_PATH = Path(__file__).resolve().parent.parent / "frontend" / ".env"


def build_anon_client():
    """Reads frontend/.env directly for VITE_SUPABASE_URL / VITE_SUPABASE_PUBLISHABLE_KEY.
    Not loaded via config.py: no other ingestion script needs the anon key, and config.py's
    own docstring asks to keep it free of script-specific concerns."""
    if not FRONTEND_ENV_PATH.exists():
        raise RuntimeError(f"Can't verify: {FRONTEND_ENV_PATH} not found (needed for the anon key).")
    text = FRONTEND_ENV_PATH.read_text(encoding="utf-8")
    url_match = re.search(r"^VITE_SUPABASE_URL=(.+)$", text, re.MULTILINE)
    key_match = re.search(r"^VITE_SUPABASE_PUBLISHABLE_KEY=(.+)$", text, re.MULTILINE)
    if not url_match or not key_match:
        raise RuntimeError(f"Can't verify: {FRONTEND_ENV_PATH} is missing VITE_SUPABASE_URL or VITE_SUPABASE_PUBLISHABLE_KEY.")
    return create_client(url_match.group(1).strip(), key_match.group(1).strip())


def run_refresh(timeout_minutes=DIRECT_STATEMENT_TIMEOUT_MINUTES, concurrent=False):
    """Opens its own psycopg connection -- no REST/RPC gateway in the path. autocommit=True:
    SET statement_timeout must apply to the session before the REFRESH runs, not be scoped
    to (and rolled back with) a transaction."""
    if not SUPABASE_DB_URL:
        raise RuntimeError("SUPABASE_DB_URL is not set (check the root .env).")

    statement = (
        "REFRESH MATERIALIZED VIEW CONCURRENTLY public.videos_scored"
        if concurrent else
        "REFRESH MATERIALIZED VIEW public.videos_scored"
    )
    print("Connecting directly to Postgres (session pooler)...", flush=True)
    with psycopg.connect(SUPABASE_DB_URL, autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute(f"SET statement_timeout = '{timeout_minutes}min'")
            print(f"statement_timeout set to {timeout_minutes} minutes. Running: {statement}", flush=True)
            start = time.monotonic()
            cur.execute(statement)
            elapsed = time.monotonic() - start
            print(f"REFRESH completed in {elapsed:.1f}s.")
            return elapsed


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


def run(sentinels, timeout_minutes=DIRECT_STATEMENT_TIMEOUT_MINUTES, concurrent=False):
    """Callable core, reused by this script's own CLI main() and by refresh.py. Refreshes,
    then verifies every sentinel; returns True only if the refresh ran AND every sentinel
    matched. A caller with no sentinels to check should not call this -- verification is
    the whole point, not an optional extra (see main()'s own guard below).
    """
    run_refresh(timeout_minutes=timeout_minutes, concurrent=concurrent)

    anon_client = build_anon_client()
    print("\nVerifying against videos_scored:")
    all_match = True
    for video_id in sentinels:
        if not verify_sentinel(anon_client, video_id):
            all_match = False

    if all_match:
        print("\nAll sentinels match. Refresh confirmed complete.")
    else:
        print("\nAt least one sentinel did not match -- the refresh may not have completed. Not confirmed.")
    return all_match


def parse_args():
    parser = argparse.ArgumentParser(description="Refreshes videos_scored over the direct connection and verifies it.")
    parser.add_argument(
        "--concurrent",
        action="store_true",
        help="Refresh concurrently (keeps the view readable throughout, but leaves old row "
             "versions behind -- use only once the site is live; plain is correct until then).",
    )
    parser.add_argument(
        "--timeout-minutes",
        type=int,
        default=DIRECT_STATEMENT_TIMEOUT_MINUTES,
        help=f"statement_timeout for the session, in minutes (default {DIRECT_STATEMENT_TIMEOUT_MINUTES}).",
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

    if not args.sentinel:
        print("No --sentinel given -- nothing would be verified. Pass one or more --sentinel VIDEO_ID.")
        sys.exit(1)

    all_match = run(args.sentinel, timeout_minutes=args.timeout_minutes, concurrent=args.concurrent)
    if not all_match:
        sys.exit(1)


if __name__ == "__main__":
    main()
