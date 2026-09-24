"""Verifies the Shorts HEAD check from wherever this script is actually running.

The check was validated from Spain (NEXT_STEPS.md step 4, verify_shorts_check.py). A
GitHub Actions runner sits in a US data centre, and the reason the check works at all --
no custom User-Agent -- is specifically about avoiding a *regional* GDPR consent
redirect (DECISIONS.md, 2026-09-18, "Shorts classification"). A consent redirect
returns a plausible-looking status on every request while carrying zero discriminating
power, so this needs checking from the runner itself before the scheduled refresh is
trusted to classify anything there.

Read-only: no database writes. Samples videos already classified (is_short IS NOT NULL)
with duration_seconds <= 180 -- the population the HEAD check actually governs -- split
as evenly as possible between the two classifications and capped per channel so the
sample isn't dominated by whichever channel happens to have the most short videos.
Re-runs the HEAD check on each and compares the fresh verdict against the stored value.

Reuses the check itself rather than re-implementing it: check_video(), classify() and
evaluate() all come from verify_shorts_check.py unchanged -- the same request shape (no
custom User-Agent, redirects not followed, retried on failure), the same 200/303 rule,
the same pass/fail/inconclusive comparison. Only the database sampling, the concurrency,
and the report shape are new here.

Usage:
    python check_shorts_from_runner.py [--sample-size N] [--concurrency N]
"""

import argparse
import random
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed

# Video titles never appear in this script's own output, but channel_id/video_id are
# plain ASCII regardless -- reconfigured anyway, matching every other script here, since
# this runs unattended and a crash on an unexpected encoding is worse than the one line
# it costs to prevent it.
sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
sys.stderr.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

from config import supabase
from verify_shorts_check import check_video, classify, evaluate

FETCH_PAGE_SIZE = 1000
SAMPLE_SIZE = 200
MAX_PER_CHANNEL = 5  # keeps ~200 videos spread across at least ~40 of the 342 channels
CONCURRENCY = 10
SHORT_DURATION_SECONDS = 180


def fetch_known_candidates(is_short):
    """video_id -> channel_id for every video already classified as `is_short`, at or
    under 180 seconds -- the exact population the HEAD check exists to resolve. Ordered
    and paginated explicitly: an unordered .range() can silently lose rows across pages
    (DECISIONS.md, 2026-09-22)."""
    rows = []
    start = 0
    while True:
        response = (
            supabase.table("videos")
            .select("video_id, channel_id")
            .eq("is_short", is_short)
            .lte("duration_seconds", SHORT_DURATION_SECONDS)
            .order("video_id")
            .range(start, start + FETCH_PAGE_SIZE - 1)
            .execute()
        )
        page = response.data
        rows.extend(page)
        if len(page) < FETCH_PAGE_SIZE:
            break
        start += FETCH_PAGE_SIZE
    return rows


def sample_capped_per_channel(rows, target, max_per_channel):
    """Shuffles and takes up to `target` rows, never more than `max_per_channel` from
    any one channel, so the sample genuinely spans many channels instead of however many
    one prolific channel happens to contribute to a plain random draw."""
    shuffled = rows[:]
    random.shuffle(shuffled)
    per_channel = Counter()
    sample = []
    for row in shuffled:
        if len(sample) >= target:
            break
        if per_channel[row["channel_id"]] >= max_per_channel:
            continue
        sample.append(row)
        per_channel[row["channel_id"]] += 1
    return sample


def parse_args():
    parser = argparse.ArgumentParser(description="Verifies the Shorts HEAD check from this runner against known values.")
    parser.add_argument("--sample-size", type=int, default=SAMPLE_SIZE, help=f"Total videos to check (default {SAMPLE_SIZE}, half known Shorts / half known regular).")
    parser.add_argument("--concurrency", type=int, default=CONCURRENCY, help=f"HEAD requests in flight at once (default {CONCURRENCY}).")
    return parser.parse_args()


def main():
    args = parse_args()
    per_side_target = args.sample_size // 2

    print("Fetching known-status candidates (is_short IS NOT NULL, duration <= 180s)...", flush=True)
    shorts_pool = fetch_known_candidates(True)
    videos_pool = fetch_known_candidates(False)
    print(f"  {len(shorts_pool)} known Shorts, {len(videos_pool)} known regular videos available to sample from.")

    if not shorts_pool or not videos_pool:
        print("Not enough known-status videos on one side to sample from. Nothing to check.")
        sys.exit(1)

    shorts_sample = sample_capped_per_channel(shorts_pool, per_side_target, MAX_PER_CHANNEL)
    videos_sample = sample_capped_per_channel(videos_pool, per_side_target, MAX_PER_CHANNEL)
    # (video_id, expected_verdict) -- expected_verdict uses the same 'shorts'/'video'
    # vocabulary classify()/evaluate() already use, so evaluate() needs no adapting.
    sample = (
        [(row["video_id"], "shorts") for row in shorts_sample]
        + [(row["video_id"], "video") for row in videos_sample]
    )
    random.shuffle(sample)
    distinct_channels = len({row["channel_id"] for row in shorts_sample + videos_sample})

    print(
        f"Sampled {len(sample)} videos ({len(shorts_sample)} known Shorts, "
        f"{len(videos_sample)} known regular), across {distinct_channels} distinct channels. "
        f"Running the HEAD check at concurrency {args.concurrency}, read-only.",
        flush=True,
    )

    results = {}  # video_id -> (status_code, location)
    run_start = time.monotonic()
    with ThreadPoolExecutor(max_workers=args.concurrency) as executor:
        future_to_id = {executor.submit(check_video, video_id): video_id for video_id, _ in sample}
        for future in as_completed(future_to_id):
            video_id = future_to_id[future]
            results[video_id] = future.result()
    elapsed = time.monotonic() - run_start

    status_counts = Counter()
    outcome_counts = Counter()
    disagreements = []
    failures = []

    for video_id, expected in sample:
        status_code, location = results[video_id]
        if status_code is None:
            failures.append(video_id)
            continue

        status_counts[status_code] += 1
        verdict = classify(status_code, location)
        outcome = evaluate(expected, verdict)
        outcome_counts[outcome] += 1
        if outcome == "fail":
            disagreements.append((video_id, expected, verdict, status_code, location))

    print(f"\n--- Report (elapsed {elapsed:.1f}s) ---")
    print(f"Checked: {len(sample)}  Failed outright (no response after retries): {len(failures)}")
    if failures:
        print("  Failed video_ids:", ", ".join(failures))

    print("\nStatus codes:")
    for code in (200, 303, 302):
        print(f"  {code}: {status_counts.get(code, 0)}")
    other = sum(count for code, count in status_counts.items() if code not in (200, 303, 302))
    print(f"  other: {other}")
    if other:
        other_breakdown = {code: count for code, count in status_counts.items() if code not in (200, 303, 302)}
        print(f"    breakdown: {other_breakdown}")

    responded = len(sample) - len(failures)
    print(f"\nAgree with stored is_short: {outcome_counts['pass']}/{responded}")
    print(f"Disagree: {outcome_counts['fail']}")
    print(f"Inconclusive (neither a clean 200 nor a 303 to /watch): {outcome_counts['inconclusive']}")

    if disagreements:
        print("\nDisagreements (video_id, expected, got, status, location):")
        for video_id, expected, verdict, status_code, location in disagreements:
            print(f"  {video_id}: expected={expected} got={verdict} status={status_code} location={location}")

    print(
        f"\n302 (consent/interstitial redirect) count: {status_counts.get(302, 0)}. "
        "If this is most or all of the responses, the check is not discriminating from "
        "this runner -- every request looks the same regardless of the real answer."
    )

    if outcome_counts["fail"] > 0 or status_counts.get(302, 0) == responded:
        sys.exit(1)


if __name__ == "__main__":
    main()
