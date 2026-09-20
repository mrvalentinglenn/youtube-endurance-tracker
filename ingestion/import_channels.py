"""Imports channels from data/channels_complete.xlsx into the channels table.

Re-runnable: upserts on channel_id, so running it again updates existing rows
and adds new ones without creating duplicates. It never deletes a channel,
even one that has disappeared from the spreadsheet (see DECISIONS.md,
2026-09-19).

Usage:
    python import_channels.py            # writes to the database
    python import_channels.py --test     # processes 5 channels, writes nothing
"""

import sys

# Channel titles can contain any Unicode character. On Windows, stdout otherwise
# defaults to the system codepage (e.g. cp1252) and crashes on anything outside it,
# so this must run before any print() call.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import argparse
import re
from pathlib import Path

import openpyxl
import requests

from config import YOUTUBE_API_KEY, supabase

SPREADSHEET_PATH = Path(__file__).resolve().parent.parent / "data" / "channels_complete.xlsx"
SHEET_NAME = "Channels Youtube"
BATCH_SIZE = 50
TEST_SAMPLE_SIZE = 5

COLUMN_COUNT = 11  # A through K

CHANNEL_ID_PATTERN = re.compile(r"^UC[A-Za-z0-9_-]{22}$")
YOUTUBE_CHANNELS_URL = "https://www.googleapis.com/youtube/v3/channels"
QUOTA_COST_PER_CALL = 1  # channels.list costs 1 unit per call, regardless of how many IDs


def _clean(value):
    """Turns a spreadsheet cell into a stripped string, treating blank/None as ''."""
    if value is None:
        return ""
    return str(value).strip()


def _is_truthy(value):
    """Sport columns G-J: true if the cell has any content after stripping."""
    return _clean(value) != ""


def read_spreadsheet(path):
    """Reads the spreadsheet into row dicts, skipping rows with no channel ID.

    Also flags rows with a missing category/subcategory and rows that repeat a
    channel ID already seen earlier in the sheet (only the first occurrence of
    a duplicate ID is kept, since a repeated primary key would break the
    upsert).
    """
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb[SHEET_NAME]

    rows = []
    skipped_no_id = 0
    missing_fields = []
    duplicates = []
    seen_at_row = {}

    for row_number, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
        if all(cell is None or _clean(cell) == "" for cell in row):
            continue  # trailing blank row past the real data, not a spreadsheet row

        # In read-only mode, openpyxl trims each row to its own trailing extent,
        # so a row with no data past column H comes back shorter than one that
        # has data through column J. Pad it back out so fixed indices are safe.
        if len(row) < COLUMN_COUNT:
            row = row + (None,) * (COLUMN_COUNT - len(row))

        spreadsheet_name = _clean(row[0])
        channel_id = _clean(row[3])
        if not channel_id:
            skipped_no_id += 1
            continue

        if channel_id in seen_at_row:
            duplicates.append({
                "row_number": row_number,
                "channel_id": channel_id,
                "spreadsheet_name": spreadsheet_name,
                "first_seen_row": seen_at_row[channel_id],
            })
            continue  # keep the first occurrence only

        seen_at_row[channel_id] = row_number

        category = _clean(row[4])
        subcategory = _clean(row[5])
        missing = [label for label, value in (("category", category), ("subcategory", subcategory)) if not value]
        if missing:
            missing_fields.append({
                "row_number": row_number,
                "spreadsheet_name": spreadsheet_name,
                "missing": " and ".join(missing),
            })

        rows.append({
            "row_number": row_number,
            "spreadsheet_name": spreadsheet_name,
            "channel_id": channel_id,
            "category": category,
            "subcategory": subcategory,
            "is_swimming": _is_truthy(row[6]),
            "is_cycling": _is_truthy(row[7]),
            "is_running": _is_truthy(row[8]),
            "is_triathlon": _is_truthy(row[9]),
        })

    wb.close()
    return rows, skipped_no_id, missing_fields, duplicates


def warn_on_malformed_ids(rows):
    for row in rows:
        if not CHANNEL_ID_PATTERN.match(row["channel_id"]):
            print(
                f"Warning: row {row['row_number']} ('{row['spreadsheet_name']}') has an ID that "
                f"doesn't look like a channel ID: '{row['channel_id']}'. Sending it to the API anyway."
            )


def report_missing_fields(missing_fields):
    if not missing_fields:
        return
    print(f"\n{len(missing_fields)} row(s) missing category and/or subcategory:")
    for entry in missing_fields:
        print(f"  Row {entry['row_number']} ('{entry['spreadsheet_name']}'): missing {entry['missing']}")


def report_duplicates(duplicates):
    if not duplicates:
        return
    print(f"\n{len(duplicates)} duplicate channel ID row(s), keeping the first occurrence only:")
    for entry in duplicates:
        print(
            f"  Row {entry['row_number']} ('{entry['spreadsheet_name']}'): channel ID "
            f"{entry['channel_id']} already seen at row {entry['first_seen_row']}"
        )


def fetch_channels_from_api(channel_ids):
    """Calls channels.list in batches of 50. Returns (results, quota_used).

    results maps channel_id -> {"name", "uploads_playlist_id", "subscriber_count"}.
    An ID the API doesn't recognise is simply absent from results.
    """
    results = {}
    quota_used = 0

    for i in range(0, len(channel_ids), BATCH_SIZE):
        batch = channel_ids[i:i + BATCH_SIZE]
        response = requests.get(YOUTUBE_CHANNELS_URL, params={
            "part": "snippet,contentDetails,statistics",
            "id": ",".join(batch),
            "maxResults": BATCH_SIZE,
            "key": YOUTUBE_API_KEY,
        })
        response.raise_for_status()
        quota_used += QUOTA_COST_PER_CALL

        for item in response.json().get("items", []):
            subscriber_count = item.get("statistics", {}).get("subscriberCount")
            results[item["id"]] = {
                "name": item["snippet"]["title"],
                "uploads_playlist_id": item["contentDetails"]["relatedPlaylists"]["uploads"],
                "subscriber_count": int(subscriber_count) if subscriber_count is not None else None,
            }

    return results, quota_used


def build_records(rows, api_results):
    """Splits rows into channels to write (API recognised the ID) and ones that weren't."""
    to_write = []
    not_recognised = []

    for row in rows:
        api_data = api_results.get(row["channel_id"])
        if api_data is None:
            not_recognised.append(row)
            continue
        to_write.append({
            "channel_id": row["channel_id"],
            "name": api_data["name"],
            "category": row["category"],
            "subcategory": row["subcategory"],
            "is_swimming": row["is_swimming"],
            "is_cycling": row["is_cycling"],
            "is_running": row["is_running"],
            "is_triathlon": row["is_triathlon"],
            "uploads_playlist_id": api_data["uploads_playlist_id"],
            "subscriber_count": api_data["subscriber_count"],
            # last_checked_at is intentionally omitted: it belongs to the
            # backfill/refresh runs, and leaving it out of the payload means
            # the upsert never touches it.
        })

    return to_write, not_recognised


def find_orphaned_channels(spreadsheet_channel_ids):
    """Channel IDs that exist in the database but not in the spreadsheet. Reported, never deleted."""
    existing = supabase.table("channels").select("channel_id").execute()
    existing_ids = {row["channel_id"] for row in existing.data}
    return sorted(existing_ids - set(spreadsheet_channel_ids))


def parse_args():
    parser = argparse.ArgumentParser(description="Import channels from the spreadsheet into Supabase.")
    parser.add_argument(
        "--test",
        action="store_true",
        help="Process 5 channels and print what would be written, without touching the database.",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    rows, skipped_no_id, missing_fields, duplicates = read_spreadsheet(SPREADSHEET_PATH)
    total_rows_read = len(rows) + skipped_no_id

    warn_on_malformed_ids(rows)
    report_missing_fields(missing_fields)
    report_duplicates(duplicates)

    if args.test:
        rows = rows[:TEST_SAMPLE_SIZE]
        print(f"\n--test: processing {len(rows)} channel(s), no database writes.")

    channel_ids = [row["channel_id"] for row in rows]
    api_results, quota_used = fetch_channels_from_api(channel_ids)
    to_write, not_recognised = build_records(rows, api_results)

    if args.test:
        print(f"\nWould upsert {len(to_write)} channel(s):")
        for record in to_write:
            print(
                f"  {record['channel_id']}  {record['name']!r}  "
                f"({record['category']} > {record['subcategory']})  subs={record['subscriber_count']}"
            )
        if not_recognised:
            print(f"\n{len(not_recognised)} channel(s) not recognised by the API:")
            for row in not_recognised:
                print(f"  {row['channel_id']}  (spreadsheet name: '{row['spreadsheet_name']}')")
        print(f"\nQuota units used: {quota_used}")
        return

    orphaned = find_orphaned_channels(channel_ids)

    if to_write:
        supabase.table("channels").upsert(to_write, on_conflict="channel_id").execute()

    if not_recognised:
        print(f"\n{len(not_recognised)} channel(s) not recognised by the API, not written:")
        for row in not_recognised:
            print(f"  {row['channel_id']}  (spreadsheet name: '{row['spreadsheet_name']}')")

    if orphaned:
        print(f"\n{len(orphaned)} channel(s) in the database but not in the spreadsheet (left untouched):")
        for channel_id in orphaned:
            print(f"  {channel_id}")

    print("\n--- Summary ---")
    print(f"Rows read: {total_rows_read}")
    print(f"Rows skipped (no channel ID): {skipped_no_id}")
    print(f"Duplicate channel IDs skipped: {len(duplicates)}")
    print(f"Rows missing category/subcategory: {len(missing_fields)}")
    print(f"Channels written: {len(to_write)}")
    print(f"Channels not recognised by the API: {len(not_recognised)}")
    print(f"Channels orphaned: {len(orphaned)}")
    print(f"Quota units used: {quota_used}")


if __name__ == "__main__":
    main()
