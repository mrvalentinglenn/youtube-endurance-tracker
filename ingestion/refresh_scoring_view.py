"""Refreshes the videos_scored, videos_slim and videos_search materialised views over a
direct Postgres connection, and verifies against the database rather than trusting the
call's own response.

videos_slim is a slim, category-and-format-ordered copy of videos_scored's own columns
(NEXT_STEPS.md step 10f), used by the front end's step 1 (filter and sort) before step 2
fetches full rows from videos_scored for just the matching video_ids. videos_search is the
same idea for a keyword search: the same slim columns plus fts and its own GIN index, so a
narrow keyword filter doesn't have to walk videos_scored's much larger table either. Both
always refresh plain, never concurrently, regardless of what videos_scored does -- a
concurrent refresh applies row-by-row diffs and would scatter their (category, is_short)
physical ordering back to an unordered layout, which is the entire reason step 1 is cheap
for either of them.

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
import os
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
    """Reads VITE_SUPABASE_URL / VITE_SUPABASE_PUBLISHABLE_KEY for the anon key. Checks
    the environment first, then falls back to reading frontend/.env directly -- the
    original approach, kept for local runs. Not loaded via config.py: no other ingestion
    script needs the anon key, and config.py's own docstring asks to keep it free of
    script-specific concerns.

    The environment path exists for GitHub Actions (NEXT_STEPS.md step 12): the runner
    checks out the repo but frontend/.env is gitignored and never committed, so the file
    this originally relied on doesn't exist there. The workflow sets these two names
    directly from secrets instead. Same two values either way -- this only changes where
    they're read from, never what they are or how they're used below."""
    env_url = os.environ.get("VITE_SUPABASE_URL")
    env_key = os.environ.get("VITE_SUPABASE_PUBLISHABLE_KEY")
    if env_url and env_key:
        return create_client(env_url, env_key)

    if not FRONTEND_ENV_PATH.exists():
        raise RuntimeError(
            f"Can't verify: VITE_SUPABASE_URL/VITE_SUPABASE_PUBLISHABLE_KEY are not set, and "
            f"{FRONTEND_ENV_PATH} was not found either (needed for the anon key)."
        )
    text = FRONTEND_ENV_PATH.read_text(encoding="utf-8")
    url_match = re.search(r"^VITE_SUPABASE_URL=(.+)$", text, re.MULTILINE)
    key_match = re.search(r"^VITE_SUPABASE_PUBLISHABLE_KEY=(.+)$", text, re.MULTILINE)
    if not url_match or not key_match:
        raise RuntimeError(f"Can't verify: {FRONTEND_ENV_PATH} is missing VITE_SUPABASE_URL or VITE_SUPABASE_PUBLISHABLE_KEY.")
    return create_client(url_match.group(1).strip(), key_match.group(1).strip())


def run_refresh(view_name="videos_scored", timeout_minutes=DIRECT_STATEMENT_TIMEOUT_MINUTES, concurrent=False):
    """Opens its own psycopg connection -- no REST/RPC gateway in the path. autocommit=True:
    SET statement_timeout must apply to the session before the REFRESH runs, not be scoped
    to (and rolled back with) a transaction. view_name is never user input -- always one of
    the two known view names -- so interpolating it into the statement is safe."""
    if not SUPABASE_DB_URL:
        raise RuntimeError("SUPABASE_DB_URL is not set (check the root .env).")

    statement = (
        f"REFRESH MATERIALIZED VIEW CONCURRENTLY public.{view_name}"
        if concurrent else
        f"REFRESH MATERIALIZED VIEW public.{view_name}"
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


SLIM_VIEWS = ("videos_slim", "videos_search")


def verify_row_counts_match(anon_client):
    """videos_slim and videos_search carry no computation of their own -- both are direct
    column subsets of videos_scored -- so all three row counts must always be equal. A
    mismatch means one refresh silently ran on stale data or didn't complete, the one
    failure mode a materialised view gives no other signal for."""
    scored_count = anon_client.table("videos_scored").select("video_id", count="exact").limit(1).execute().count
    counts = {"videos_scored": scored_count}
    for view_name in SLIM_VIEWS:
        counts[view_name] = anon_client.table(view_name).select("video_id", count="exact").limit(1).execute().count

    matches = all(count == scored_count for count in counts.values())
    counts_str = ", ".join(f"{name}: {count}" for name, count in counts.items())
    print(f"  {counts_str} -- {'MATCH' if matches else 'MISMATCH'}")
    return matches


def run(sentinels, timeout_minutes=DIRECT_STATEMENT_TIMEOUT_MINUTES, concurrent=False):
    """Callable core, reused by this script's own CLI main() and by refresh.py. Refreshes
    videos_scored (plain or concurrent, as requested), then videos_slim and videos_search
    -- always plain, regardless of `concurrent`: their (category, is_short) physical
    ordering is what makes a narrow-filter query on them cheap, and only a full rebuild
    preserves that ordering. Verifies row counts match across all three views, then every
    sentinel against videos_scored. Returns True only if every refresh ran AND every check
    passed. A caller with no sentinels to check should not call this -- verification is the
    whole point, not an optional extra (see main()'s own guard below).
    """
    run_refresh("videos_scored", timeout_minutes=timeout_minutes, concurrent=concurrent)
    for view_name in SLIM_VIEWS:
        run_refresh(view_name, timeout_minutes=timeout_minutes, concurrent=False)

    anon_client = build_anon_client()

    print("\nVerifying row counts match:")
    counts_match = verify_row_counts_match(anon_client)

    print("\nVerifying against videos_scored:")
    all_match = True
    for video_id in sentinels:
        if not verify_sentinel(anon_client, video_id):
            all_match = False

    all_match = all_match and counts_match

    if all_match:
        print("\nAll checks pass. Refresh confirmed complete.")
    else:
        print("\nAt least one check did not pass -- the refresh may not have completed. Not confirmed.")
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
