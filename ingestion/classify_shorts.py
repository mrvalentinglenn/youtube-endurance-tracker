"""Phase two of the backfill: classifies videos with is_short IS NULL via the Shorts
HEAD check, at the concurrency validated by calibrate_shorts.py (500 videos, 0
failures, 0 429s, no response-time or 200/303-split drift vs. sequential -- see
NEXT_STEPS.md's throttling question).

The work queue is "is_short IS NULL", so this script is resumable by construction and
doubles as the future daily reclassify job (step 12b) -- see DECISIONS.md, 2026-09-19,
"The backfill runs in two phases".

200 -> is_short true. 303 with a Location pointing at /watch?v= -> is_short false.
Anything else (or a request exception) is inconclusive: left NULL, logged, never
guessed. Results are written in batches of 500 so an interruption never loses more than
the batch in progress -- and in practice loses nothing already completed, since the
buffer is flushed before the process exits either way.

This run is long enough (calibration projected ~74 minutes) to hit trouble that a 36-second
calibration burst wouldn't. It aborts immediately on any 429, on more than 50 consecutive
request failures, or on the running 200/303 split drifting more than 10 points from the
~82/18 baseline over a full rolling 1,000-video window. The work queue is shuffled before
processing so that window is a cross-section of channels, not one Shorts-heavy brand's
contiguous run -- and if it aborts anyway, the report names how many distinct channels the
offending window covered, so a real signal isn't confused with one channel's output.
"""

import random
import sys
import time
from collections import Counter, deque
from concurrent.futures import ThreadPoolExecutor, as_completed

# Video titles can contain any Unicode character. On Windows, stdout otherwise
# defaults to the system codepage (e.g. cp1252) and crashes on anything outside it,
# so this must run before any print() call. line_buffering=True keeps a redirected
# log live instead of only appearing when the process exits.
sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
sys.stderr.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

import requests

from config import supabase
from verify_shorts_check import SHORTS_URL, classify

CONCURRENCY = 20  # validated in calibrate_shorts.py: no failures, no drift vs. sequential
FETCH_PAGE_SIZE = 1000
REQUEST_TIMEOUT_SECONDS = 10
WRITE_BATCH_SIZE = 500  # also the progress-log interval
UPDATE_CHUNK_SIZE = 150  # per .in_() call, to keep the filter URL a safe length
DB_WRITE_MAX_ATTEMPTS = 3
DB_WRITE_RETRY_DELAY_SECONDS = 2
MAX_CONSECUTIVE_FAILURES = 50
RATIO_WINDOW_SIZE = 1000
RATIO_DRIFT_THRESHOLD_POINTS = 10
BASELINE_SHORTS_PCT = 82.0  # roughly 82/18, from both calibration runs (81.8%, 81.2%)


def fetch_pending_work():
    """All (video_id, channel_id) pairs with is_short IS NULL, paginated past PostgREST's row cap."""
    work = []
    start = 0
    while True:
        response = (
            supabase.table("videos")
            .select("video_id, channel_id")
            .is_("is_short", "null")
            .range(start, start + FETCH_PAGE_SIZE - 1)
            .execute()
        )
        rows = response.data
        work.extend((row["video_id"], row["channel_id"]) for row in rows)
        if len(rows) < FETCH_PAGE_SIZE:
            break
        start += FETCH_PAGE_SIZE
    return work


def make_session():
    session = requests.Session()
    adapter = requests.adapters.HTTPAdapter(pool_maxsize=max(CONCURRENCY, 10))
    session.mount("https://", adapter)
    return session


def send_request(session, video_id, channel_id):
    """Same request shape as verify_shorts_check.check_video, minus the retry loop:
    a retry would hide the failure behaviour the abort conditions need to see."""
    url = SHORTS_URL.format(video_id=video_id)
    try:
        response = session.head(url, allow_redirects=False, timeout=REQUEST_TIMEOUT_SECONDS)
        return {
            "video_id": video_id,
            "channel_id": channel_id,
            "status_code": response.status_code,
            "location": response.headers.get("Location"),
            "error": None,
        }
    except requests.RequestException as error:
        return {
            "video_id": video_id,
            "channel_id": channel_id,
            "status_code": None,
            "location": None,
            "error": type(error).__name__,
        }


def chunked(items, size):
    for i in range(0, len(items), size):
        yield items[i:i + size]


def update_with_retry(is_short, video_ids):
    """A run this long (~74 minutes) will hit the occasional transient DB error --
    seen in practice: a Postgres statement timeout on one otherwise-ordinary chunk
    update. Retried here, unlike the YouTube requests: a DB write retry doesn't hide
    anything the abort conditions need to see, since it isn't part of the throttling
    signal being measured.
    """
    last_error = None
    for attempt in range(1, DB_WRITE_MAX_ATTEMPTS + 1):
        try:
            supabase.table("videos").update({"is_short": is_short}).in_("video_id", video_ids).execute()
            return
        except Exception as error:
            last_error = error
            if attempt < DB_WRITE_MAX_ATTEMPTS:
                time.sleep(DB_WRITE_RETRY_DELAY_SECONDS)
    raise last_error


def flush_batch(shorts_ids, long_form_ids):
    """A real UPDATE, not an upsert: upsert goes through INSERT ... ON CONFLICT DO
    UPDATE, and Postgres checks NOT NULL constraints on the proposed insert row before
    it even checks for a conflict -- so a payload with only video_id and is_short fails
    on channel_id NOT NULL, even though the row already exists and would only be
    updated. .update().in_(...) has no INSERT path, so it can't hit that.

    Chunked to keep each request's URL comfortably under typical length limits.
    """
    for chunk in chunked(shorts_ids, UPDATE_CHUNK_SIZE):
        update_with_retry(True, chunk)
    for chunk in chunked(long_form_ids, UPDATE_CHUNK_SIZE):
        update_with_retry(False, chunk)


def log_progress(processed, total, run_start, shorts_count, long_form_count, total_failures):
    elapsed = time.monotonic() - run_start
    rate = processed / elapsed if elapsed > 0 else 0
    classified = shorts_count + long_form_count
    shorts_pct = shorts_count / classified * 100 if classified else 0
    print(
        f"  ...{processed}/{total} done, {total - processed} remaining, {rate:.2f} req/s, "
        f"{shorts_count}/{long_form_count} shorts/long-form ({shorts_pct:.1f}% shorts), "
        f"{total_failures} failure(s) so far",
        flush=True,
    )


def process_queue(work_items):
    session = make_session()
    total = len(work_items)

    shorts_count = 0
    long_form_count = 0
    inconclusive_count = 0
    failure_counts = Counter()
    consecutive_failures = 0
    ratio_window = deque(maxlen=RATIO_WINDOW_SIZE)  # (channel_id, "shorts"/"video"/"other")
    shorts_batch_ids = []
    long_form_batch_ids = []
    processed = 0
    aborted_reason = None

    run_start = time.monotonic()

    with ThreadPoolExecutor(max_workers=CONCURRENCY) as executor:
        pending = set()
        items_iter = iter(work_items)

        def submit_next():
            item = next(items_iter, None)
            if item is None:
                return
            video_id, channel_id = item
            pending.add(executor.submit(send_request, session, video_id, channel_id))

        for _ in range(CONCURRENCY):
            submit_next()

        while pending:
            done_future = next(as_completed(pending))
            pending.discard(done_future)
            result = done_future.result()
            processed += 1

            if result["error"] is not None:
                consecutive_failures += 1
                failure_counts[result["error"]] += 1
                inconclusive_count += 1
                print(f"  Inconclusive: {result['video_id']} (request failed: {result['error']})")
                ratio_window.append((result["channel_id"], "other"))
            else:
                consecutive_failures = 0
                verdict = classify(result["status_code"], result["location"])
                if verdict == "shorts":
                    shorts_count += 1
                    shorts_batch_ids.append(result["video_id"])
                    ratio_window.append((result["channel_id"], "shorts"))
                elif verdict == "video":
                    long_form_count += 1
                    long_form_batch_ids.append(result["video_id"])
                    ratio_window.append((result["channel_id"], "video"))
                else:
                    inconclusive_count += 1
                    print(f"  Inconclusive: {result['video_id']} (status {result['status_code']})")
                    ratio_window.append((result["channel_id"], "other"))

            if result["status_code"] == 429:
                aborted_reason = f"429 received on video {result['video_id']} after {processed} requests"
                break

            if consecutive_failures > MAX_CONSECUTIVE_FAILURES:
                aborted_reason = f"{consecutive_failures} consecutive failures after {processed} requests"
                break

            if len(ratio_window) >= RATIO_WINDOW_SIZE:
                shorts_in_window = sum(1 for _, v in ratio_window if v == "shorts")
                video_in_window = sum(1 for _, v in ratio_window if v == "video")
                classified_in_window = shorts_in_window + video_in_window
                if classified_in_window > 0:
                    pct = shorts_in_window / classified_in_window * 100
                    drift = abs(pct - BASELINE_SHORTS_PCT)
                    if drift > RATIO_DRIFT_THRESHOLD_POINTS:
                        distinct_channels = len({c for c, _ in ratio_window})
                        aborted_reason = (
                            f"200/303 split drifted to {pct:.1f}% shorts ({drift:.1f} points from the "
                            f"{BASELINE_SHORTS_PCT}% baseline) over the last {RATIO_WINDOW_SIZE} videos, "
                            f"ending at request {processed}. That window covered {distinct_channels} "
                            "distinct channel(s) -- check whether this is a real signal or one channel's "
                            "output before re-running."
                        )
                        break

            if processed % WRITE_BATCH_SIZE == 0:
                flush_batch(shorts_batch_ids, long_form_batch_ids)
                shorts_batch_ids.clear()
                long_form_batch_ids.clear()
                log_progress(processed, total, run_start, shorts_count, long_form_count, sum(failure_counts.values()))

            if aborted_reason is None:
                submit_next()

    flush_batch(shorts_batch_ids, long_form_batch_ids)  # whatever's left, including a partial batch at abort or the end

    return {
        "processed": processed,
        "shorts_count": shorts_count,
        "long_form_count": long_form_count,
        "inconclusive_count": inconclusive_count,
        "failure_counts": failure_counts,
        "elapsed": time.monotonic() - run_start,
        "aborted_reason": aborted_reason,
    }


def main():
    work_items = fetch_pending_work()
    total = len(work_items)
    if total == 0:
        print("No videos with is_short IS NULL found. Nothing to classify.")
        return

    # Shuffled so a rolling 1,000-video window is a cross-section of channels, not one
    # channel's contiguous run (which would legitimately have a lopsided Shorts ratio).
    random.shuffle(work_items)

    print(f"Classifying {total} videos at concurrency {CONCURRENCY}.", flush=True)

    stats = process_queue(work_items)

    print("\n--- Summary ---")
    if stats["aborted_reason"]:
        print(f"ABORTED: {stats['aborted_reason']}")
    print(f"Processed: {stats['processed']}/{total}")
    print(f"Classified as Shorts: {stats['shorts_count']}")
    print(f"Classified as long-form: {stats['long_form_count']}")
    print(f"Left NULL (inconclusive): {stats['inconclusive_count']}")
    total_failures = sum(stats["failure_counts"].values())
    print(f"Failures: {total_failures}")
    for error_type, count in stats["failure_counts"].most_common():
        print(f"  {error_type}: {count}")
    print(f"Elapsed: {stats['elapsed']:.1f}s")
    if stats["elapsed"] > 0:
        print(f"Effective rate: {stats['processed'] / stats['elapsed']:.2f} requests/second")

    if stats["aborted_reason"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
