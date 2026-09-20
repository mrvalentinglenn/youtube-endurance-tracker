"""Verifies the Shorts HEAD check against a set of videos of known status.

Run this before any Shorts classification runs over the videos table (see
NEXT_STEPS.md step 4). It confirms that a HEAD request to
youtube.com/shorts/{video_id} reliably tells Shorts (200) apart from regular
videos (303 redirecting to /watch?v=), and reports how the check behaves
under repetition, since the throttling for the backfill is still an open
question (see NEXT_STEPS.md).

No custom User-Agent is ever set. A browser-like string routes every request
into a regional GDPR consent redirect, which returns 302 for Shorts and
regular videos alike -- a check with zero discriminating power that still
looks like it's working (see DECISIONS.md, 2026-09-18, "Shorts
classification"). Non-browser clients get the real answer.

This script only talks to youtube.com. It costs no YouTube API quota, touches
no database, and needs no API keys.
"""

import csv
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

# Video titles can contain any Unicode character. On Windows, stdout otherwise
# defaults to the system codepage (e.g. cp1252) and crashes on anything outside it,
# so this must run before any print() call.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import requests

CSV_PATH = Path(__file__).resolve().parent / "test_shorts.csv"
SHORTS_URL = "https://www.youtube.com/shorts/{video_id}"
REQUEST_DELAY_SECONDS = 1
MAX_ATTEMPTS = 3


def read_videos(path):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def check_video(video_id):
    """Sends the HEAD request, retrying on failure. Returns (status_code, location)."""
    url = SHORTS_URL.format(video_id=video_id)
    last_error = None

    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = requests.head(url, allow_redirects=False, timeout=10)
            return response.status_code, response.headers.get("Location")
        except requests.RequestException as error:
            last_error = error
            if attempt < MAX_ATTEMPTS:
                time.sleep(REQUEST_DELAY_SECONDS)

    print(f"  ({video_id}: request failed after {MAX_ATTEMPTS} attempts: {last_error})")
    return None, None


def classify(status_code, location):
    """Turns a status code + Location header into 'shorts', 'video', or 'inconclusive'. Never guesses."""
    if status_code == 200:
        return "shorts"
    if status_code == 303 and location and urlparse(location).path.startswith("/watch"):
        return "video"
    return "inconclusive"


def evaluate(expected, verdict):
    """Compares the verdict to the expected status: 'pass', 'fail', or 'inconclusive'."""
    if verdict == expected:
        return "pass"
    if verdict == "inconclusive":
        return "inconclusive"
    return "fail"


def run_checks(videos):
    results = []
    for i, row in enumerate(videos):
        video_id = row["video_id"]
        expected = row["expected"]

        status_code, location = check_video(video_id)
        verdict = classify(status_code, location)
        outcome = evaluate(expected, verdict)

        results.append({
            "video_id": video_id,
            "expected": expected,
            "status_code": status_code,
            "location": location,
            "verdict": verdict,
            "outcome": outcome,
        })

        if i < len(videos) - 1:
            time.sleep(REQUEST_DELAY_SECONDS)

    return results


def print_table(results):
    columns = f"{'video_id':<13} {'expected':<8} {'status':<7} {'location':<45} {'verdict':<13} result"
    print(columns)
    print("-" * len(columns))
    for r in results:
        status = str(r["status_code"]) if r["status_code"] is not None else "-"
        location = r["location"] or "-"
        if len(location) > 45:
            location = location[:42] + "..."
        result = "pass" if r["outcome"] == "pass" else "fail"
        print(f"{r['video_id']:<13} {r['expected']:<8} {status:<7} {location:<45} {r['verdict']:<13} {result}")


def print_summary(results):
    passed = sum(1 for r in results if r["outcome"] == "pass")
    failed = sum(1 for r in results if r["outcome"] == "fail")
    inconclusive = sum(1 for r in results if r["outcome"] == "inconclusive")
    print()
    print(f"Passed: {passed}/{len(results)}")
    print(f"Failed: {failed}")
    print(f"Inconclusive: {inconclusive}")


def main():
    videos = read_videos(CSV_PATH)
    results = run_checks(videos)

    print_table(results)
    print_summary(results)

    if any(r["outcome"] != "pass" for r in results):
        sys.exit(1)


if __name__ == "__main__":
    main()
