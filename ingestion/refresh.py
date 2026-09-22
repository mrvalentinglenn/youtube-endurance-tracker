"""The 30-day refresh (NEXT_STEPS.md step 6). One run:

  channels.list (name, subscriber_count) -> new videos -> re-measure videos under 180
  days -> Shorts check for newly-pending videos, with in-run retries -> baselines ->
  avatars -> checks -> refresh videos_scored.

Avatar failures are logged and never fail the run (DECISIONS.md, 2026-09-21: avatars are
decoration, kept off the import's failure path). A classify_shorts abort (429, consecutive
failures, ratio drift) is also not a hard gate -- logged, and whatever is still
is_short IS NULL is left for the next run to pick up, same as any other stray NULL.

Channels with last_checked_at NULL (never backfilled) are skipped and reported, not
processed -- onboarding a new channel stays a manual import, then a manual backfill run;
only after that is it eligible here.

New videos: per channel, pages the uploads playlist from newest, stopping after 5
consecutive videos whose video_id we already have (DECISIONS.md, 2026-09-19's "5
consecutive outside the window" heuristic, adapted from "outside the date window" to
"already known" -- same reordering risk, same fix). Capped at NEW_VIDEO_MAX_PAGES pages
per channel as a safety net: every backfilled channel should have real overlap with what
we already have, so hitting the cap means something is wrong, not that a channel is just
prolific.

Re-measurement: videos.list omits any video_id it no longer recognises -- deleted or made
private. Skipped and logged, never written as zero, never counted as a channel failure.
Hidden likes / disabled comments are written as NULL, matching build_records() elsewhere.

Baselines: compute_baselines.py now writes only rows whose value actually changed (see
that module for the type-safe comparison and why it matters). Most of the archive is
frozen and could not have changed, so this is the difference between rewriting 98,300
rows a month and rewriting a few thousand.

Checks before the refresh, any one of which stops the run with a non-zero exit and skips
the refresh entirely: videos row count dropped (it must only grow or stay the same),
any baseline write failure, more than 5% of channels failed during new-video discovery,
or quota used passed 9,500 (soft warning at 8,000). videos_scored keeps showing the
previous run's data on failure -- stale but correct, never a refresh built on a run that
didn't finish cleanly.

Refresh: plain by default (the site has no visitors yet), over the direct connection,
with a session statement_timeout. See refresh_scoring_view.py.

Usage:
    python refresh.py            # writes to the database, refreshes videos_scored
    python refresh.py --test     # 5 channels, real API calls, no writes, no refresh
    python refresh.py --concurrent-refresh   # once the site is live
"""

import argparse
import random
import sys
import time
from datetime import datetime, timedelta, timezone

sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
sys.stderr.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

import requests

import compute_baselines
import refresh_scoring_view
import sync_avatars
from backfill import (
    YOUTUBE_PLAYLIST_ITEMS_URL,
    YOUTUBE_VIDEOS_URL,
    BATCH_SIZE as API_BATCH_SIZE,
    WRITE_CHUNK_SIZE,
    build_records,
    fetch_video_details,
    flush_chunk,
)
from classify_shorts import fetch_pending_work, make_session, process_queue, send_request
from config import YOUTUBE_API_KEY, supabase
from verify_shorts_check import classify

YOUTUBE_CHANNELS_URL = "https://www.googleapis.com/youtube/v3/channels"

FETCH_PAGE_SIZE = 1000
CHANNELS_BATCH_SIZE = 50
YOUNG_AGE_DAYS = 180
CONSECUTIVE_KNOWN_STOP = 5
NEW_VIDEO_MAX_PAGES = 10  # safety cap; a normal month never approaches this
SHORT_DURATION_SECONDS = 180
TEST_SAMPLE_SIZE = 5

SHORTS_CHECK_MAX_PASSES = 3
SHORTS_CHECK_RETRY_DELAY_SECONDS = 5

FAILED_CHANNEL_RATE_THRESHOLD = 0.05
QUOTA_SOFT_WARNING = 8000
QUOTA_HARD_STOP = 9500

REFRESH_TIMEOUT_MINUTES = 15


class QuotaExceeded(Exception):
    pass


def chunked(items, size):
    for i in range(0, len(items), size):
        yield items[i:i + size]


class QuotaTracker:
    """Shared across every phase, so the hard stop applies to the run as a whole, not
    per phase. Raises as soon as a call would push the total over QUOTA_HARD_STOP --
    checked before, not after, so the run never actually places a call that would
    exceed it."""

    def __init__(self):
        self.total = 0
        self.warned = False

    def add(self, units, phase):
        if self.total + units > QUOTA_HARD_STOP:
            raise QuotaExceeded(
                f"Quota hard stop: {self.total} used, {units} more needed by {phase} "
                f"would exceed {QUOTA_HARD_STOP}."
            )
        self.total += units
        if self.total >= QUOTA_SOFT_WARNING and not self.warned:
            self.warned = True
            print(f"  WARNING: quota usage at {self.total}, approaching the {QUOTA_HARD_STOP} soft/hard stop.")


# --- Phase: channel metadata -------------------------------------------------------

def fetch_channels_for_refresh():
    """Channels eligible for the refresh: last_checked_at is set, i.e. already
    backfilled. Returns (eligible, skipped) -- skipped channels are reported, not
    silently dropped."""
    response = (
        supabase.table("channels")
        .select("channel_id, name, uploads_playlist_id, last_checked_at")
        .order("name")
        .execute()
    )
    all_channels = response.data
    eligible = [c for c in all_channels if c["last_checked_at"] is not None]
    skipped = [c for c in all_channels if c["last_checked_at"] is None]
    return eligible, skipped


def fetch_channel_metadata(channel_ids, quota):
    """channels.list, part=snippet,statistics, batches of 50. Returns channel_id ->
    {name, subscriber_count}. A channel_id the API doesn't recognise is absent from the
    result, same as sync_avatars.fetch_thumbnails."""
    metadata = {}
    for batch in chunked(channel_ids, CHANNELS_BATCH_SIZE):
        response = requests.get(YOUTUBE_CHANNELS_URL, params={
            "part": "snippet,statistics",
            "id": ",".join(batch),
            "maxResults": CHANNELS_BATCH_SIZE,
            "key": YOUTUBE_API_KEY,
        })
        response.raise_for_status()
        quota.add(1, "channels.list (metadata)")
        for item in response.json().get("items", []):
            stats = item.get("statistics", {})
            subscriber_count = stats.get("subscriberCount")
            metadata[item["id"]] = {
                "name": item["snippet"]["title"],
                "subscriber_count": int(subscriber_count) if subscriber_count is not None else None,
            }
    return metadata


def update_channel_metadata(channels, metadata, test_mode):
    updated = 0
    not_found = []
    for channel in channels:
        info = metadata.get(channel["channel_id"])
        if info is None:
            not_found.append(channel)
            continue
        if not test_mode:
            supabase.table("channels").update(info).eq("channel_id", channel["channel_id"]).execute()
        updated += 1
    return updated, not_found


# --- Phase: new videos ---------------------------------------------------------------

def fetch_known_video_ids(channel_id):
    ids = set()
    start = 0
    while True:
        response = (
            supabase.table("videos")
            .select("video_id")
            .eq("channel_id", channel_id)
            .range(start, start + FETCH_PAGE_SIZE - 1)
            .execute()
        )
        rows = response.data
        ids.update(r["video_id"] for r in rows)
        if len(rows) < FETCH_PAGE_SIZE:
            break
        start += FETCH_PAGE_SIZE
    return ids


def discover_new_video_ids(uploads_playlist_id, known_ids, quota):
    """Pages the uploads playlist from newest, stopping after CONSECUTIVE_KNOWN_STOP
    consecutive already-known videos. Returns (new_video_ids, hit_page_cap)."""
    new_ids = []
    consecutive_known = 0
    page_token = None
    pages = 0

    while True:
        params = {
            "part": "contentDetails",
            "playlistId": uploads_playlist_id,
            "maxResults": API_BATCH_SIZE,
            "key": YOUTUBE_API_KEY,
        }
        if page_token:
            params["pageToken"] = page_token

        response = requests.get(YOUTUBE_PLAYLIST_ITEMS_URL, params=params)
        response.raise_for_status()
        quota.add(1, "playlistItems.list (new-video discovery)")
        pages += 1
        data = response.json()

        stop = False
        for item in data.get("items", []):
            video_id = item["contentDetails"].get("videoId")
            if not video_id:
                continue
            if video_id in known_ids:
                consecutive_known += 1
                if consecutive_known >= CONSECUTIVE_KNOWN_STOP:
                    stop = True
                    break
            else:
                new_ids.append(video_id)
                consecutive_known = 0

        if stop:
            break
        if pages >= NEW_VIDEO_MAX_PAGES:
            return new_ids, True

        page_token = data.get("nextPageToken")
        if not page_token:
            break

    return new_ids, False


def process_new_videos_for_channel(channel, quota, test_mode, today):
    """Returns a per-channel result dict. Raises never -- failures are caught by the
    caller so one channel's problem doesn't stop the others (same pattern as
    backfill.py's process_channel)."""
    channel_id = channel["channel_id"]
    known_ids = fetch_known_video_ids(channel_id)
    new_ids, hit_cap = discover_new_video_ids(channel["uploads_playlist_id"], known_ids, quota)

    if hit_cap:
        print(
            f"  WARNING: {channel['name']} ({channel_id}) hit the {NEW_VIDEO_MAX_PAGES}-page "
            "safety cap while looking for new videos -- worth checking by hand."
        )

    if not new_ids:
        return {"new_written": 0, "pending_classification": 0, "pending_ids": []}

    video_chunk = []
    stats_chunk = []
    pending_classification = 0
    pending_ids = []  # (video_id, channel_id) -- only populated for --test's in-memory Shorts check
    written = 0

    for batch in chunked(new_ids, API_BATCH_SIZE):
        items, batch_quota = fetch_video_details(batch)
        quota.add(batch_quota, "videos.list (new-video details)")
        for item in items:
            video_record, stats_record, is_pending, has_no_duration = build_records(item, channel_id, today)
            video_chunk.append(video_record)
            stats_chunk.append(stats_record)
            if is_pending:
                pending_classification += 1
                if test_mode:
                    pending_ids.append((video_record["video_id"], channel_id))
            if has_no_duration:
                print(f"    Warning: {video_record['video_id']} has no contentDetails.duration.")

        if len(video_chunk) >= WRITE_CHUNK_SIZE:
            if not test_mode:
                flush_chunk(video_chunk, stats_chunk)
            written += len(video_chunk)
            video_chunk, stats_chunk = [], []

    if video_chunk:
        if not test_mode:
            flush_chunk(video_chunk, stats_chunk)
        written += len(video_chunk)

    return {"new_written": written, "pending_classification": pending_classification, "pending_ids": pending_ids}


# --- Phase: re-measure videos under 180 days ------------------------------------------

def fetch_young_videos(channel_ids=None):
    """video_id -> published_at (parsed) for every video younger than 180 days. Scoped to
    channel_ids when given (--test's 5-channel sample) -- a video ages regardless of
    whether its channel published anything new this run, but a real run's-worth of
    videos.list calls (~410) is not what --test should cost."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=YOUNG_AGE_DAYS)).isoformat()
    videos = {}
    start = 0
    while True:
        query = supabase.table("videos").select("video_id, published_at, channel_id").gte("published_at", cutoff)
        if channel_ids:
            query = query.in_("channel_id", channel_ids)
        response = query.range(start, start + FETCH_PAGE_SIZE - 1).execute()
        rows = response.data
        for row in rows:
            videos[row["video_id"]] = datetime.fromisoformat(row["published_at"].replace("Z", "+00:00"))
        if len(rows) < FETCH_PAGE_SIZE:
            break
        start += FETCH_PAGE_SIZE
    return videos


def remeasure_young_videos(young_videos, quota, test_mode, today):
    """Batches videos.list(part=statistics) in groups of 50, writes one video_stats row
    per video actually returned. A video_id videos.list doesn't return is deleted or
    private this cycle: skipped and logged, never written as zero, never treated as a
    failure. Hidden likes / disabled comments come back as NULL from the API and are
    written as NULL, same as build_records() does for new videos.
    """
    video_ids = list(young_videos.keys())
    stats_chunk = []
    measured = 0
    missing = []

    for batch in chunked(video_ids, API_BATCH_SIZE):
        response = requests.get(YOUTUBE_VIDEOS_URL, params={
            "part": "statistics",
            "id": ",".join(batch),
            "maxResults": API_BATCH_SIZE,
            "key": YOUTUBE_API_KEY,
        })
        response.raise_for_status()
        quota.add(1, "videos.list (re-measurement)")

        items = response.json().get("items", [])
        returned_ids = {item["id"] for item in items}
        batch_missing = [vid for vid in batch if vid not in returned_ids]
        missing.extend(batch_missing)

        for item in items:
            video_id = item["id"]
            statistics = item.get("statistics", {})
            views = statistics.get("viewCount")
            likes = statistics.get("likeCount")
            comments = statistics.get("commentCount")
            published_at = young_videos[video_id]
            stats_chunk.append({
                "video_id": video_id,
                "captured_at": today.isoformat(),
                "age_days": (today - published_at.date()).days,
                "views": int(views) if views is not None else None,
                "likes": int(likes) if likes is not None else None,
                "comments": int(comments) if comments is not None else None,
            })
            measured += 1

        if len(stats_chunk) >= WRITE_CHUNK_SIZE:
            if not test_mode:
                supabase.table("video_stats").upsert(stats_chunk, on_conflict="video_id,captured_at").execute()
            stats_chunk = []

    if stats_chunk:
        if not test_mode:
            supabase.table("video_stats").upsert(stats_chunk, on_conflict="video_id,captured_at").execute()

    if missing:
        print(f"  {len(missing)} video(s) no longer available (deleted or private), skipped: {missing[:10]}"
              + (" ..." if len(missing) > 10 else ""))

    return {"measured": measured, "missing": len(missing)}


# --- Phase: Shorts classification, with in-run retries --------------------------------

def run_shorts_classification(test_mode, in_memory_pending=None):
    """Up to SHORTS_CHECK_MAX_PASSES passes over classify_shorts's own work queue
    (is_short IS NULL, table-wide). There is no daily reclassify job yet (NEXT_STEPS.md
    step 12b), so this run is also the safety net for any stray NULLs left by a previous
    run, not just this run's own new videos -- reusing fetch_pending_work() unfiltered is
    deliberate, not an oversight.

    classify_shorts.process_queue() has no per-request retry of its own by design (its
    docstring: a retry would hide the failure behaviour its abort conditions need to
    see); retries happen here instead, as separate passes, each re-fetching what's still
    NULL. An abort (429, consecutive failures, ratio drift) stops the retry loop early
    and is logged -- not a hard gate for the run as a whole.

    In --test, the newly-discovered videos were never written, so is_short IS NULL over
    the real table finds nothing belonging to this run (fetch_pending_work() can still
    find stray NULLs left over from a real previous run, which is real but not what
    --test is meant to preview). Instead this runs the actual HEAD check -- read-only,
    no YouTube API quota, it only talks to youtube.com -- directly against the videos
    held in memory from this run's new-video discovery, and prints each one's real
    verdict without writing anything.
    """
    if test_mode:
        pending = in_memory_pending or []
        print(f"--test: {len(pending)} newly-discovered video(s) pending Shorts classification. "
              f"Running the real HEAD check in memory (read-only, no quota, nothing written):")
        session = make_session()
        shorts = long_form = inconclusive = 0
        for video_id, channel_id in pending:
            result = send_request(session, video_id, channel_id)
            if result["error"] is not None:
                verdict = "inconclusive"
                inconclusive += 1
                print(f"    {video_id}: inconclusive (request failed: {result['error']})")
                continue
            verdict = classify(result["status_code"], result["location"])
            if verdict == "shorts":
                shorts += 1
            elif verdict == "video":
                long_form += 1
            else:
                inconclusive += 1
            print(f"    {video_id}: {verdict} (status={result['status_code']})")
        return {
            "classified_shorts": shorts, "classified_long_form": long_form,
            "still_null": inconclusive, "aborted": False, "aborted_reason": None,
        }

    total_shorts = 0
    total_long_form = 0
    aborted = False
    aborted_reason = None
    still_null = 0

    for attempt in range(1, SHORTS_CHECK_MAX_PASSES + 1):
        pending = fetch_pending_work()
        if not pending:
            still_null = 0
            break
        print(f"  Shorts classification pass {attempt}: {len(pending)} pending.")
        random.shuffle(pending)
        stats = process_queue(pending)
        total_shorts += stats["shorts_count"]
        total_long_form += stats["long_form_count"]
        still_null = stats["inconclusive_count"]

        if stats["aborted_reason"]:
            aborted = True
            aborted_reason = stats["aborted_reason"]
            print(f"  Shorts classification pass {attempt} aborted: {aborted_reason}")
            break
        if still_null == 0:
            break
        if attempt < SHORTS_CHECK_MAX_PASSES:
            time.sleep(SHORTS_CHECK_RETRY_DELAY_SECONDS)

    if aborted:
        still_null = len(fetch_pending_work())  # honest count of what's actually still NULL

    return {
        "classified_shorts": total_shorts, "classified_long_form": total_long_form,
        "still_null": still_null, "aborted": aborted, "aborted_reason": aborted_reason,
    }


# --- Phase: avatars --------------------------------------------------------------------

def run_avatars(test_mode):
    """Decoration, never a hard gate -- any failure here (including one that escapes
    sync_avatars.run() entirely) is caught, logged, and the refresh run continues."""
    try:
        return sync_avatars.run(test_mode=test_mode, sample_size=TEST_SAMPLE_SIZE if test_mode else None)
    except Exception as error:
        print(f"  Avatar sync failed entirely (non-fatal): {error}")
        return {"channels_read": 0, "uploaded": 0, "no_thumbnail": 0, "failed": 0, "quota_used": 0, "error": str(error)}


# --- Orchestration -----------------------------------------------------------------

def run(test_mode=False, concurrent_refresh=False, refresh_timeout_minutes=REFRESH_TIMEOUT_MINUTES, sentinels=None):
    quota = QuotaTracker()
    today = datetime.now(timezone.utc).date()

    videos_before = supabase.table("videos").select("video_id", count="exact").limit(1).execute().count
    print(f"Starting refresh. videos row count before: {videos_before}."
          + (" --test: 5 channels, real API calls, no writes, no refresh." if test_mode else ""),
          flush=True)

    eligible_channels, skipped_channels = fetch_channels_for_refresh()
    if skipped_channels:
        print(f"Skipped {len(skipped_channels)} channel(s), never backfilled: "
              f"{[c['name'] for c in skipped_channels]}")

    channels = eligible_channels[:TEST_SAMPLE_SIZE] if test_mode else eligible_channels

    failure = None  # set to a string reason if a hard gate trips; run continues to report, refresh is skipped

    # Pre-declared with safe defaults: if QuotaExceeded fires partway through the try
    # block below, the checks and summary sections still need these names to exist,
    # reflecting whatever partial progress was made rather than crashing on a NameError
    # on top of the quota failure itself.
    channels_updated, channels_not_found = 0, []
    new_written_total, pending_total, failed_channels, failed_rate = 0, 0, [], 0.0
    remeasure_result = {"measured": 0, "missing": 0}
    shorts_result = {"classified_shorts": 0, "classified_long_form": 0, "still_null": 0, "aborted": False, "aborted_reason": None}
    baseline_totals = {"young_written": 0, "young_unchanged": 0, "era_written": 0, "era_unchanged": 0, "write_failures": 0}
    avatar_result = {"channels_read": 0, "uploaded": 0, "no_thumbnail": 0, "failed": 0, "quota_used": 0}

    updated_word = "would update" if test_mode else "updated"
    written_word = "would write" if test_mode else "written"
    measured_word = "would measure" if test_mode else "measured"

    try:
        # --- Phase: channels.list ---
        print(f"\n--- Channel metadata ({len(channels)} channel(s)) ---", flush=True)
        metadata = fetch_channel_metadata([c["channel_id"] for c in channels], quota)
        channels_updated, channels_not_found = update_channel_metadata(channels, metadata, test_mode)
        print(f"  {updated_word.capitalize()}: {channels_updated}. Not found in API response: {len(channels_not_found)}.")

        # --- Phase: new videos ---
        print(f"\n--- New videos ---", flush=True)
        new_written_total = 0
        pending_total = 0
        pending_ids_total = []
        failed_channels = []
        for channel in channels:
            try:
                result = process_new_videos_for_channel(channel, quota, test_mode, today)
                new_written_total += result["new_written"]
                pending_total += result["pending_classification"]
                pending_ids_total.extend(result["pending_ids"])
                if result["new_written"]:
                    print(f"  {channel['name']} ({channel['channel_id']}): {written_word} {result['new_written']} new video(s)")
            except Exception as error:
                failed_channels.append(channel)
                print(f"  FAILED: {channel['name']} ({channel['channel_id']}): {error}")

        failed_rate = len(failed_channels) / len(channels) if channels else 0
        print(f"  New videos {written_word}: {new_written_total}. Channels failed: {len(failed_channels)} "
              f"({failed_rate:.1%}).")

        # --- Phase: re-measure videos under 180 days ---
        # Scoped to the --test sample's own channels in test mode -- otherwise this phase
        # alone would cost a real run's ~410 videos.list calls even under --test, which
        # defeats the point of a "handful of channels" preview.
        print(f"\n--- Re-measuring videos under {YOUNG_AGE_DAYS} days ---", flush=True)
        young_videos = fetch_young_videos(channel_ids=[c["channel_id"] for c in channels] if test_mode else None)
        if not sentinels and young_videos:
            # No --sentinel given (the normal case for a scheduled, unattended run).
            # Verification without a real video_id to check is not verification at all
            # -- refresh_scoring_view.py's own main() refuses to run bare for exactly
            # this reason. Auto-pick one video this run just re-measured, so the
            # refresh is always actually checked, not just assumed to have worked.
            sentinels = [next(iter(young_videos))]
            print(f"  No --sentinel given; auto-selected {sentinels[0]} for post-refresh verification.")
        remeasure_result = remeasure_young_videos(young_videos, quota, test_mode, today)
        print(f"  {measured_word.capitalize()}: {remeasure_result['measured']}. Missing (deleted/private): {remeasure_result['missing']}.")

        # --- Phase: Shorts classification ---
        print(f"\n--- Shorts classification ---", flush=True)
        shorts_result = run_shorts_classification(test_mode, in_memory_pending=pending_ids_total)
        print(
            f"  Classified as Shorts: {shorts_result['classified_shorts']}, "
            f"long-form: {shorts_result['classified_long_form']}, "
            f"still NULL: {shorts_result['still_null']}"
            + (f" (aborted: {shorts_result['aborted_reason']})" if shorts_result["aborted"] else "")
        )

        # --- Phase: baselines ---
        print(f"\n--- Baselines ---", flush=True)
        if test_mode:
            baseline_totals = compute_baselines.run(test_mode=True, sample_size=TEST_SAMPLE_SIZE)
        else:
            baseline_totals = compute_baselines.run(test_mode=False)

        # --- Phase: avatars ---
        print(f"\n--- Avatars ---", flush=True)
        avatar_result = run_avatars(test_mode)
        quota.total += avatar_result.get("quota_used", 0)  # tracked, but avatars never trip the hard stop retroactively

    except QuotaExceeded as error:
        failure = str(error)

    # --- Checks ---
    print(f"\n--- Checks ---", flush=True)
    videos_after = supabase.table("videos").select("video_id", count="exact").limit(1).execute().count
    print(f"  videos row count: {videos_before} -> {videos_after}")

    if failure is None:
        if videos_after < videos_before:
            failure = f"videos row count dropped ({videos_before} -> {videos_after}); videos must never be deleted."
        elif not test_mode and baseline_totals.get("write_failures"):
            failure = f"{baseline_totals['write_failures']} baseline write failure(s)."
        elif failed_rate > FAILED_CHANNEL_RATE_THRESHOLD:
            failure = f"{len(failed_channels)}/{len(channels)} channels failed ({failed_rate:.1%}), over the {FAILED_CHANNEL_RATE_THRESHOLD:.0%} threshold."
        elif quota.total > QUOTA_HARD_STOP:
            failure = f"quota used ({quota.total}) exceeded the hard stop ({QUOTA_HARD_STOP})."

    print(f"  Quota used: {quota.total}")

    uploaded_word = "would upload" if test_mode else "uploaded"

    print(f"\n--- Summary ---")
    print(f"Channels eligible: {len(eligible_channels)}, skipped (never backfilled): {len(skipped_channels)}, processed: {len(channels)}")
    print(f"Channel metadata {updated_word}: {channels_updated}")
    print(f"New videos {written_word}: {new_written_total}, pending Shorts classification: {pending_total}")
    print(f"Videos {measured_word}: {remeasure_result['measured']}, no longer available: {remeasure_result['missing']}")
    print(
        f"Shorts classified: {shorts_result['classified_shorts']} shorts / "
        f"{shorts_result['classified_long_form']} long-form, still NULL: {shorts_result['still_null']}"
    )
    print(
        f"Baselines -- current {written_word}: {baseline_totals['young_written']}, unchanged: {baseline_totals['young_unchanged']}; "
        f"era {written_word}: {baseline_totals['era_written']}, unchanged: {baseline_totals['era_unchanged']}"
    )
    print(f"Avatars -- {uploaded_word}: {avatar_result['uploaded']}, no thumbnail: {avatar_result['no_thumbnail']}, failed: {avatar_result['failed']}")
    print(f"Total quota used: {quota.total} / 10,000")

    if test_mode:
        print("\n--test: no writes were made, refresh was not called.")
        return {"ok": True, "test_mode": True}

    if failure:
        print(f"\nFAILED: {failure}")
        print("videos_scored was NOT refreshed -- it still shows the previous run's data.")
        return {"ok": False, "failure": failure}

    # --- Refresh ---
    print(f"\n--- Refresh ---", flush=True)
    all_match = refresh_scoring_view.run(
        sentinels or [], timeout_minutes=refresh_timeout_minutes, concurrent=concurrent_refresh,
    )
    if not all_match:
        print("\nFAILED: refresh ran but sentinel verification did not match.")
        return {"ok": False, "failure": "refresh verification failed"}

    print("\nRun completed successfully.")
    return {"ok": True}


def parse_args():
    parser = argparse.ArgumentParser(description="The 30-day refresh: new videos, re-measurement, baselines, avatars, refresh.")
    parser.add_argument("--test", action="store_true", help="5 channels, real API calls, no database writes, no refresh.")
    parser.add_argument("--concurrent-refresh", action="store_true", help="Refresh concurrently instead of plain -- only once the site is live.")
    parser.add_argument("--refresh-timeout-minutes", type=int, default=REFRESH_TIMEOUT_MINUTES, help=f"statement_timeout for the refresh (default {REFRESH_TIMEOUT_MINUTES}).")
    parser.add_argument("--sentinel", action="append", default=[], metavar="VIDEO_ID", help="A video_id to verify after the refresh (repeatable).")
    return parser.parse_args()


def main():
    args = parse_args()
    result = run(
        test_mode=args.test,
        concurrent_refresh=args.concurrent_refresh,
        refresh_timeout_minutes=args.refresh_timeout_minutes,
        sentinels=args.sentinel,
    )
    if not result["ok"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
