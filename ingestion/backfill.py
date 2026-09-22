"""Phase one of the backfill: YouTube API work only, no HEAD checks.

For each channel with no last_checked_at, walks the uploads playlist back to the 36-month
cutoff, fetches video details in batches of 50, and writes rows to videos and a first
measurement to video_stats. A video at or under 180 seconds is written with is_short NULL;
phase two (a separate script) classifies those with the Shorts HEAD check. See
NEXT_STEPS.md step 5 and DECISIONS.md, 2026-09-19 ("The backfill runs in two phases",
"The backfill resumes on last_checked_at", "Playlist paging stops after 5 consecutive
videos outside the window").

Never uses search.list. playlistItems.list and videos.list each cost 1 quota unit per
call of up to 50 items, counted per call, not per video.

Usage:
    python backfill.py            # writes to the database
    python backfill.py --force    # also reprocesses channels that already have a last_checked_at
    python backfill.py --test     # processes 5 channels, writes nothing
"""

import sys

# Channel and video titles can contain any Unicode character (this set includes
# Japanese and Korean titles). On Windows, stdout otherwise defaults to the system
# codepage (e.g. cp1252) and crashes on anything outside it, so this must run before
# any print() call.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import argparse
import calendar
import re
from datetime import datetime, timezone

import requests

from config import YOUTUBE_API_KEY, supabase

YOUTUBE_PLAYLIST_ITEMS_URL = "https://www.googleapis.com/youtube/v3/playlistItems"
YOUTUBE_VIDEOS_URL = "https://www.googleapis.com/youtube/v3/videos"

BATCH_SIZE = 50  # both playlistItems.list maxResults and videos.list batch size
WRITE_CHUNK_SIZE = 250  # rows per upsert; a large brand channel can exceed 1,000 videos
BACKFILL_MONTHS = 36
MAX_CONSECUTIVE_OUTSIDE_WINDOW = 5

# The cutoff actually used by the one mass backfill run that populated this channel set
# (all 342 channels' last_checked_at fall on 2026-09-19; compute_cutoff() at that moment
# resolved to 2023-09-19). Fixed, not recomputed: refresh.py's new-video discovery must
# never import anything the original backfill deliberately left out, and a moving
# now() - 36 months would drift further from that boundary every month. compute_cutoff()
# below stays dynamic -- it's still needed for onboarding a channel in the future.
BACKFILL_CUTOFF = datetime(2023, 9, 19, tzinfo=timezone.utc)
SHORT_DURATION_SECONDS = 180
TEST_SAMPLE_SIZE = 5
QUOTA_COST_PER_CALL = 1

DURATION_PATTERN = re.compile(
    r"^P(?:(?P<days>\d+)D)?T?(?:(?P<hours>\d+)H)?(?:(?P<minutes>\d+)M)?(?:(?P<seconds>\d+)S)?$"
)
THUMBNAIL_PRIORITY = ["maxres", "standard", "high", "medium", "default"]


def compute_cutoff():
    """36 months before now, in UTC. Handles month underflow and short-month day overflow."""
    now = datetime.now(timezone.utc)
    year = now.year
    month = now.month - BACKFILL_MONTHS
    while month <= 0:
        month += 12
        year -= 1
    day = min(now.day, calendar.monthrange(year, month)[1])
    return now.replace(year=year, month=month, day=day)


def parse_duration_seconds(duration):
    """Parses an ISO 8601 duration (e.g. 'PT1H2M10S', 'P0D') into whole seconds."""
    match = DURATION_PATTERN.match(duration)
    if not match:
        return None
    parts = match.groupdict()
    days = int(parts["days"] or 0)
    hours = int(parts["hours"] or 0)
    minutes = int(parts["minutes"] or 0)
    seconds = int(parts["seconds"] or 0)
    return days * 86400 + hours * 3600 + minutes * 60 + seconds


def pick_thumbnail_url(thumbnails):
    for key in THUMBNAIL_PRIORITY:
        if key in thumbnails:
            return thumbnails[key]["url"]
    return None


def fetch_channels_to_process(force):
    """Returns (channels to process, count skipped as already done)."""
    response = (
        supabase.table("channels")
        .select("channel_id, name, uploads_playlist_id, last_checked_at")
        .order("name")
        .execute()
    )
    all_channels = response.data
    already_done = [c for c in all_channels if c["last_checked_at"] is not None]

    if force:
        return all_channels, 0
    return [c for c in all_channels if c["last_checked_at"] is None], len(already_done)


def collect_video_ids_in_window(uploads_playlist_id, cutoff):
    """Pages the uploads playlist, keeping IDs published on/after cutoff. Returns (ids, quota_used)."""
    video_ids = []
    consecutive_outside = 0
    page_token = None
    quota_used = 0

    while True:
        params = {
            "part": "contentDetails",
            "playlistId": uploads_playlist_id,
            "maxResults": BATCH_SIZE,
            "key": YOUTUBE_API_KEY,
        }
        if page_token:
            params["pageToken"] = page_token

        response = requests.get(YOUTUBE_PLAYLIST_ITEMS_URL, params=params)
        response.raise_for_status()
        quota_used += QUOTA_COST_PER_CALL
        data = response.json()

        stop = False
        for item in data.get("items", []):
            details = item["contentDetails"]
            published_at_str = details.get("videoPublishedAt")
            video_id = details.get("videoId")
            if not published_at_str or not video_id:
                continue  # deleted/private playlist entry; ignore, don't affect the counter

            published_at = datetime.fromisoformat(published_at_str.replace("Z", "+00:00"))
            if published_at >= cutoff:
                video_ids.append(video_id)
                consecutive_outside = 0
            else:
                consecutive_outside += 1
                if consecutive_outside >= MAX_CONSECUTIVE_OUTSIDE_WINDOW:
                    stop = True
                    break

        if stop:
            break

        page_token = data.get("nextPageToken")
        if not page_token:
            break

    return video_ids, quota_used


def fetch_video_details(video_ids):
    """Calls videos.list for one batch. Returns (items, quota_used)."""
    response = requests.get(YOUTUBE_VIDEOS_URL, params={
        "part": "snippet,contentDetails,statistics",
        "id": ",".join(video_ids),
        "maxResults": BATCH_SIZE,
        "key": YOUTUBE_API_KEY,
    })
    response.raise_for_status()
    return response.json().get("items", []), QUOTA_COST_PER_CALL


def build_records(item, channel_id, today):
    """Turns one videos.list item into (video_record, stats_record, is_pending, has_no_duration)."""
    video_id = item["id"]
    snippet = item["snippet"]
    content_details = item["contentDetails"]
    statistics = item.get("statistics", {})

    duration_raw = content_details.get("duration")
    has_no_duration = duration_raw is None
    duration_seconds = None if has_no_duration else parse_duration_seconds(duration_raw)

    is_pending = False
    if has_no_duration:
        is_short = None
    elif duration_seconds > SHORT_DURATION_SECONDS:
        is_short = False
    else:
        is_short = None  # at or under the threshold; phase two decides
        is_pending = True

    published_at = datetime.fromisoformat(snippet["publishedAt"].replace("Z", "+00:00"))

    video_record = {
        "video_id": video_id,
        "channel_id": channel_id,
        "title": snippet["title"],
        "description": snippet.get("description", "")[:500],
        "published_at": published_at.isoformat(),
        "duration_seconds": duration_seconds,
        "is_short": is_short,
        "thumbnail_url": pick_thumbnail_url(snippet.get("thumbnails", {})),
    }

    views = statistics.get("viewCount")
    likes = statistics.get("likeCount")
    comments = statistics.get("commentCount")

    stats_record = {
        "video_id": video_id,
        "captured_at": today.isoformat(),
        "age_days": (today - published_at.date()).days,
        "views": int(views) if views is not None else None,
        "likes": int(likes) if likes is not None else None,
        "comments": int(comments) if comments is not None else None,
    }

    return video_record, stats_record, is_pending, has_no_duration


def flush_chunk(video_chunk, stats_chunk):
    """Writes videos before video_stats: video_stats has a foreign key to videos."""
    if video_chunk:
        supabase.table("videos").upsert(video_chunk, on_conflict="video_id").execute()
    if stats_chunk:
        supabase.table("video_stats").upsert(stats_chunk, on_conflict="video_id,captured_at").execute()


def process_channel(channel, cutoff, test_mode):
    channel_id = channel["channel_id"]
    name = channel["name"]
    uploads_playlist_id = channel["uploads_playlist_id"]

    if not uploads_playlist_id:
        print(f"FAILED: {name} ({channel_id}): no uploads_playlist_id")
        return {"status": "failed", "quota_used": 0, "videos_written": 0}

    quota_used = 0
    videos_written = 0
    pending_classification = 0

    try:
        video_ids, playlist_quota = collect_video_ids_in_window(uploads_playlist_id, cutoff)
        quota_used += playlist_quota

        today = datetime.now(timezone.utc).date()
        video_chunk = []
        stats_chunk = []

        for i in range(0, len(video_ids), BATCH_SIZE):
            batch = video_ids[i:i + BATCH_SIZE]
            items, batch_quota = fetch_video_details(batch)
            quota_used += batch_quota

            for item in items:
                video_record, stats_record, is_pending, has_no_duration = build_records(item, channel_id, today)
                video_chunk.append(video_record)
                stats_chunk.append(stats_record)
                if is_pending:
                    pending_classification += 1
                if has_no_duration:
                    print(
                        f"  Warning: {video_record['video_id']} has no contentDetails.duration; "
                        "duration_seconds and is_short left NULL."
                    )

            if len(video_chunk) >= WRITE_CHUNK_SIZE:
                if not test_mode:
                    flush_chunk(video_chunk, stats_chunk)
                videos_written += len(video_chunk)
                video_chunk = []
                stats_chunk = []

        if video_chunk:
            if not test_mode:
                flush_chunk(video_chunk, stats_chunk)
            videos_written += len(video_chunk)

        if not test_mode:
            supabase.table("channels").update(
                {"last_checked_at": datetime.now(timezone.utc).isoformat()}
            ).eq("channel_id", channel_id).execute()

        print(
            f"{name} ({channel_id}): {len(video_ids)} in window, {videos_written} written, "
            f"{pending_classification} pending phase-two classification"
        )
        return {"status": "ok", "quota_used": quota_used, "videos_written": videos_written}

    except Exception as error:
        print(f"FAILED: {name} ({channel_id}): {error}")
        return {"status": "failed", "quota_used": quota_used, "videos_written": videos_written}


def parse_args():
    parser = argparse.ArgumentParser(description="Phase one of the backfill: YouTube API work only.")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Reprocess channels that already have a last_checked_at.",
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Process 5 channels and print what would be written, without touching the database.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    cutoff = compute_cutoff()

    to_process, skipped_count = fetch_channels_to_process(args.force)

    if args.test:
        to_process = to_process[:TEST_SAMPLE_SIZE]
        print(f"--test: processing {len(to_process)} channel(s), no database writes.\n")

    processed = 0
    failed = 0
    total_videos_written = 0
    total_quota_used = 0

    for channel in to_process:
        result = process_channel(channel, cutoff, args.test)
        total_quota_used += result["quota_used"]
        if result["status"] == "ok":
            processed += 1
            total_videos_written += result["videos_written"]
        else:
            failed += 1

    print("\n--- Summary ---")
    print(f"Channels processed: {processed}")
    print(f"Channels skipped (already done): {0 if args.test else skipped_count}")
    print(f"Channels failed: {failed}")
    print(f"Total videos written: {total_videos_written}")
    print(f"Total quota units used: {total_quota_used}")


if __name__ == "__main__":
    main()
