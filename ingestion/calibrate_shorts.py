"""Calibration run for the Shorts HEAD check: how youtube.com responds to sustained
volume, before phase two of the backfill classifies all 62,000+ pending videos.

Samples 500 videos with is_short IS NULL and fires HEAD requests at
youtube.com/shorts/{id} at the given --concurrency, reporting timing and failure
statistics. WRITES NOTHING TO THE DATABASE: this is a measurement, not a
classification run, and the sampled videos stay NULL for phase two to classify.

--concurrency 1 (the default) reproduces the first, sequential run: 500/500 succeeded,
0 failures, 0 429s, 409 Shorts / 91 regular videos, median 1,505ms / p95 2,399ms, no
failure clustering. That run showed the response time is network latency, not
throttling, so a delay between requests buys nothing -- the open question is only how
much to parallelize. This run's report compares against those baseline numbers directly,
including the 200/303 split: if aggressive concurrency pushes requests into a consent or
interstitial path, status codes can stay plausible while carrying no information (see
DECISIONS.md, 2026-09-18, "Shorts classification", on the User-Agent version of this same
failure mode), so a split that drifts well away from roughly 82/18 is a red flag even with
zero errors.

Throwaway diagnostic, not part of the pipeline. See NEXT_STEPS.md's open question on
backfill throttling. Run with `python -u` (or rely on the line-buffered stdout set below)
so progress is visible in a redirected log instead of going dark until the end.
"""

import argparse
import math
import random
import statistics
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed

# Video titles can contain any Unicode character. On Windows, stdout otherwise
# defaults to the system codepage (e.g. cp1252) and crashes on anything outside it,
# so this must run before any print() call. line_buffering=True keeps a redirected
# log live instead of only appearing when the process exits.
sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
sys.stderr.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

import requests

from config import supabase
from verify_shorts_check import SHORTS_URL

SAMPLE_SIZE = 500
FETCH_PAGE_SIZE = 1000
REQUEST_TIMEOUT_SECONDS = 10
BLOCK_SIZE = 100
MAX_CONSECUTIVE_FAILURES = 50

# From the first, sequential (--concurrency 1) run, for direct comparison in the report.
BASELINE_MEDIAN_MS = 1505
BASELINE_P95_MS = 2399
BASELINE_SHORTS_COUNT = 409
BASELINE_VIDEOS_COUNT = 91
BASELINE_POPULATION_SIZE = 62215  # videos with is_short NULL at the time of that run
SPLIT_DRIFT_WARNING_POINTS = 10  # percentage points before the 200/303 split is flagged


def fetch_pending_video_ids():
    """All video_ids with is_short IS NULL, paginated past PostgREST's row cap.

    Random.sample needs the full population in hand -- there is no ORDER BY random()
    available through the client without a database function, so the randomness
    happens here rather than in the query.
    """
    video_ids = []
    start = 0
    while True:
        response = (
            supabase.table("videos")
            .select("video_id")
            .is_("is_short", "null")
            .order("video_id")
            .range(start, start + FETCH_PAGE_SIZE - 1)
            .execute()
        )
        rows = response.data
        video_ids.extend(row["video_id"] for row in rows)
        if len(rows) < FETCH_PAGE_SIZE:
            break
        start += FETCH_PAGE_SIZE
    return video_ids


def make_session(concurrency):
    session = requests.Session()
    adapter = requests.adapters.HTTPAdapter(pool_maxsize=max(concurrency, 10))
    session.mount("https://", adapter)
    return session


def send_request(session, video_id):
    """One HEAD request, no retry: a calibration run needs the raw failure rate.

    Same request shape as verify_shorts_check.check_video (same URL template, redirects
    not followed, no custom User-Agent) minus the retry loop, which would hide the
    failure behaviour this script exists to measure.
    """
    url = SHORTS_URL.format(video_id=video_id)
    start = time.monotonic()
    try:
        response = session.head(url, allow_redirects=False, timeout=REQUEST_TIMEOUT_SECONDS)
        elapsed = time.monotonic() - start
        return {"status_code": response.status_code, "elapsed": elapsed, "error": None}
    except requests.RequestException as error:
        elapsed = time.monotonic() - start
        return {"status_code": None, "elapsed": elapsed, "error": type(error).__name__}


def percentile(sorted_values, pct):
    if not sorted_values:
        return None
    k = max(0, min(len(sorted_values) - 1, math.ceil(pct * len(sorted_values)) - 1))
    return sorted_values[k]


def run_calibration(sample, concurrency):
    """Runs the sample at the given concurrency, stopping early on a failure streak.

    Results come back in completion order, not submission order, once concurrency > 1
    -- which is what the per-block report wants anyway, since it is asking about
    wall-clock progression through the run. "Consecutive failures" is therefore also
    judged in completion order; at concurrency > 1 that is an approximation of true
    back-to-back failures, not an exact count, and the report says so.

    Stopping only stops submitting *new* requests; up to `concurrency` already-in-flight
    ones are still allowed to finish, so the overrun past the trigger point is bounded.
    """
    session = make_session(concurrency)
    results = []
    consecutive_failures = 0
    stopped_early = False

    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        pending = set()
        sample_iter = iter(sample)

        def submit_next():
            video_id = next(sample_iter, None)
            if video_id is None:
                return
            pending.add(executor.submit(send_request, session, video_id))

        for _ in range(concurrency):
            submit_next()

        while pending:
            done_future = next(as_completed(pending))
            pending.discard(done_future)
            result = done_future.result()
            results.append(result)

            consecutive_failures = consecutive_failures + 1 if result["error"] else 0
            if consecutive_failures > MAX_CONSECUTIVE_FAILURES:
                stopped_early = True
                print(
                    f"\nStopping early: {consecutive_failures} consecutive failures "
                    f"after {len(results)} requests.",
                    flush=True,
                )
                break

            if len(results) % BLOCK_SIZE == 0:
                block = results[-BLOCK_SIZE:]
                block_failures = sum(1 for r in block if r["error"] is not None)
                print(f"  ...{len(results)}/{len(sample)} done, {block_failures} failure(s) in that block", flush=True)

            submit_next()

    return results, stopped_early


def print_report(results, total_elapsed, concurrency, stopped_early, sample_overlap_note):
    n = len(results)
    status_counts = Counter(r["status_code"] for r in results if r["error"] is None)
    error_counts = Counter(r["error"] for r in results if r["error"] is not None)
    total_failures = sum(error_counts.values())
    successful_times = sorted(r["elapsed"] for r in results if r["error"] is None)

    print("\n--- Calibration report ---")
    print(f"Concurrency: {concurrency}")
    print(f"Stopped early: {'yes' if stopped_early else 'no'}")
    print(f"Sample overlap with the first run: {sample_overlap_note}")
    print(f"Requests sent: {n}")
    print(f"Total elapsed: {total_elapsed:.1f}s")
    if total_elapsed > 0:
        print(f"Effective rate: {n / total_elapsed:.2f} requests/second")

    print("\nStatus codes:")
    for status_code, count in sorted(status_counts.items(), key=lambda kv: -kv[1]):
        print(f"  {status_code}: {count}")
    print(f"  429 (rate limited): {status_counts.get(429, 0)}")

    shorts_count = status_counts.get(200, 0)
    video_count = status_counts.get(303, 0)
    classified = shorts_count + video_count
    if classified:
        current_pct = shorts_count / classified * 100
        baseline_pct = BASELINE_SHORTS_COUNT / (BASELINE_SHORTS_COUNT + BASELINE_VIDEOS_COUNT) * 100
        drift = abs(current_pct - baseline_pct)
        print(
            f"\n200/303 split: {shorts_count}/{video_count} ({current_pct:.1f}% shorts) "
            f"vs. baseline {BASELINE_SHORTS_COUNT}/{BASELINE_VIDEOS_COUNT} ({baseline_pct:.1f}% shorts)"
        )
        if drift > SPLIT_DRIFT_WARNING_POINTS:
            print(
                f"  RED FLAG: split drifted {drift:.1f} points from baseline -- status codes may be "
                "plausible but uninformative (e.g. a consent/interstitial path), not a real classification."
            )
        else:
            print(f"  Within {drift:.1f} points of baseline, no drift flag.")
    else:
        print("\n200/303 split: no successful classifications to compare against baseline.")

    print(f"\nRequests failed outright: {total_failures}")
    for error_type, count in error_counts.most_common():
        print(f"  {error_type}: {count}")

    if successful_times:
        median_ms = statistics.median(successful_times) * 1000
        p95_ms = percentile(successful_times, 0.95) * 1000
        print(
            f"\nResponse time (successful requests): median {median_ms:.0f}ms, p95 {p95_ms:.0f}ms "
            f"vs. baseline median {BASELINE_MEDIAN_MS}ms, p95 {BASELINE_P95_MS}ms "
            f"({median_ms - BASELINE_MEDIAN_MS:+.0f}ms / {p95_ms - BASELINE_P95_MS:+.0f}ms)"
        )
    else:
        print("\nNo successful requests to compute response time percentiles.")

    print("\nFailures per 100-request block (completion order; checks for progressive throttling):")
    for block_start in range(0, n, BLOCK_SIZE):
        block = results[block_start:block_start + BLOCK_SIZE]
        block_failures = sum(1 for r in block if r["error"] is not None)
        print(f"  {block_start + 1}-{block_start + len(block)}: {block_failures} failure(s)")


def parse_args():
    parser = argparse.ArgumentParser(description="Calibrates the Shorts HEAD check's request rate.")
    parser.add_argument(
        "--concurrency",
        type=int,
        default=1,
        help="Number of HEAD requests in flight at once (default 1: sequential, matches the first run).",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    video_ids = fetch_pending_video_ids()
    if not video_ids:
        print("No videos with is_short IS NULL found. Nothing to calibrate against.")
        return

    sample = random.sample(video_ids, min(SAMPLE_SIZE, len(video_ids)))
    print(
        f"Calibrating against {len(sample)} videos at concurrency {args.concurrency}, "
        "no database writes.",
        flush=True,
    )

    # There is no record of the first run's exact video IDs (it printed aggregate stats
    # only), so exact overlap can't be checked. The NULL population size hasn't changed
    # since (nothing has written to is_short), so the two independent draws' expected
    # overlap can still be estimated: n1*n2/N.
    expected_overlap = len(sample) * SAMPLE_SIZE / BASELINE_POPULATION_SIZE
    overlap_note = (
        f"not tracked (first run's IDs weren't logged); statistically expected "
        f"~{expected_overlap:.1f} videos in common out of {len(sample)}, since both are "
        f"independent random draws from the same ~{BASELINE_POPULATION_SIZE:,}-video NULL "
        "population, unchanged between runs. Doesn't matter for correctness either way: "
        "sampled videos are never written, so overlap or not, they stay NULL for phase two."
    )

    run_start = time.monotonic()
    results, stopped_early = run_calibration(sample, args.concurrency)
    total_elapsed = time.monotonic() - run_start

    print_report(results, total_elapsed, args.concurrency, stopped_early, overlap_note)


if __name__ == "__main__":
    main()
