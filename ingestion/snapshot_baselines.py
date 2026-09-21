"""Exports the current baseline columns for every video to a local CSV, so a later run
that overwrites them (e.g. compute_baselines.py's nearest-pool fix, 2026-09-21) can be
compared before/after. Read-only: no writes, no computation, just a paginated export of
what's already stored.

Not a database table -- the project is already over the Supabase free-tier size limit
(see NEXT_STEPS.md), so nothing may be added there for a diagnostic snapshot. The CSV is
gitignored (ingestion/baseline_snapshot.csv): it is a working file, not source data.

Usage:
    python snapshot_baselines.py [--out PATH]
"""

import argparse
import csv
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
sys.stderr.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

from config import supabase

FETCH_PAGE_SIZE = 1000
DEFAULT_OUT_PATH = "baseline_snapshot.csv"
COLUMNS = ["video_id", "baseline_views", "baseline_likes", "baseline_comments", "baseline_kind"]


def fetch_all_baselines():
    rows = []
    start = 0
    while True:
        response = (
            supabase.table("videos")
            .select(", ".join(COLUMNS))
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


def parse_args():
    parser = argparse.ArgumentParser(description="Snapshots every video's current baseline columns to a CSV.")
    parser.add_argument("--out", default=DEFAULT_OUT_PATH, help=f"Output CSV path (default: {DEFAULT_OUT_PATH})")
    return parser.parse_args()


def main():
    args = parse_args()

    print("Fetching baseline columns for all videos...", flush=True)
    rows = fetch_all_baselines()

    with open(args.out, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    kind_counts = {}
    for row in rows:
        kind_counts[row["baseline_kind"]] = kind_counts.get(row["baseline_kind"], 0) + 1

    print(f"Wrote {len(rows)} row(s) to {args.out}")
    print(f"baseline_kind counts: {kind_counts}")


if __name__ == "__main__":
    main()
