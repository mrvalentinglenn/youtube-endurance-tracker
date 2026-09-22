"""Computes both baselines for every channel: the current baseline (step 7 of
NEXT_STEPS.md) and the era baseline (step 8). The era pass extends this script; it does
not replace the current-baseline path, which is unchanged for videos 180 days old or
younger ("still growing").

CURRENT BASELINE (videos 180 days old or younger). See DECISIONS.md, 2026-09-18,
"Baseline window: 180 days to 24 months" and "Baseline sample...":
  - POOL: the channel's mature videos (older than 180 days) published within the last 24
    months, split by format (is_short); a NULL-format video is in neither pool.
  - Every write-target video gets its format's pool-derived baseline, or
    baseline_kind = 'insufficient' if its format has no baseline (or it has no format).

ERA BASELINE (videos older than 180 days). See DECISIONS.md, 2026-09-20, "Era baseline
members must also be older than 180 days", "...falls back to the current baseline", and
"One-sided era windows are accepted, not flagged":
  - Each mature video is scored against its own contemporaries: a window centred on its
    own published_at, 6 months either side, truncated at the 180-day line (never on the
    past side -- a channel's oldest videos get a one-sided window on purpose, and it is
    not flagged). The window is anchored to the video's own publication date, never to
    today, so a frozen video's score does not drift between runs on its own.
  - Within the window, the sample is the up-to-20 videos NEAREST to the video's own
    published_at, not the 20 most recent. Up to 10 are taken from each side (before and
    after); if one side is short, the shortfall is filled from the other side's
    next-nearest, capped at 20 total. Ties (equal distance, or two candidates sharing a
    publication time) are broken by video_id, so the sample -- and therefore a frozen
    video's score -- is stable between runs.

    This replaced a bug: the original implementation reused the current baseline's "most
    recent 20" rule for the era window too. Since the window is centred on the video but
    "most recent" always samples its late end, every video was compared only against
    what its channel published after it -- on a fast-growing channel, that means
    systematically comparing old videos against a bigger, later version of the channel.
    Measured on FloTrack: a video published 2024-04-01 had its baseline built entirely
    from videos published 2024-09-24 to 2024-09-30, six months later and one week wide.
  - If a metric has fewer than 10 qualifying videos in the 6-month window, it widens to
    12 months (both sides, same nearest-first sampling). If still short, that metric
    falls back to the channel's current baseline (same pool as above, same per-metric
    rules). Only if that also fails does the metric stay NULL.
  - baseline_kind when metrics resolve at different tiers (the one genuinely ambiguous
    case): 'era' if *any* metric resolved from a 6- or 12-month window, else 'current' if
    *any* metric used the fallback, else 'insufficient'. This is precedence, not a 3-way
    vote -- chosen because it is what a video with even one era-quality metric should be
    labelled, and it is unambiguous to compute and to explain.

Both paths, independently per metric (views, likes, comments): drop videos with a NULL
value for that metric (hidden likes, disabled comments -- never treated as zero) and
require at least 10. The current baseline then takes the 20 most recent by published_at;
the era baseline takes the 20 nearest to the subject video's published_at, balanced across
both sides (see above). Either way, the sample is then medianed. A median of exactly 0 is
stored as-is -- a channel whose comments are genuinely, measurably zero is a real fact, not
a missing measurement. The divide-by-zero guard belongs in the score view, at division
time, not here.

A video is never part of its own baseline. For the era pass this does not follow from the
window alone (a video's own window trivially contains its own date), so it is asserted
explicitly after the exclusion filter, not just relied upon.

Computed in Python, not SQL (see DECISIONS.md, 2026-09-20, "Baselines are computed in
Python, not in SQL") so a single channel's computation can be read, stepped through, and
checked by hand -- see --channel.

Writes with .update(), never .upsert() (same NOT NULL pitfall as classify_shorts.py hit).
Step 7's write targets all share one payload per format, so one .update().in_(...) per
format was enough. Step 8's mature videos each have their own window and can each compute
a different baseline, so instead of one write per video, video_ids are grouped by their
*exact* computed payload within each channel and format before writing -- videos whose
windows land on the same 20-video sample naturally collapse into one write.

Reads are per channel, not per video ("Compute per channel with the channel's videos
already in memory"): each channel's videos and latest stats are fetched once, and every
video's era window is found in that in-memory set via binary search (bisect) rather than
a fresh query.
"""

import argparse
import calendar
import sys
import time
from bisect import bisect_left, bisect_right
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from statistics import median

# Channel and video titles can contain any Unicode character. On Windows, stdout otherwise
# defaults to the system codepage (e.g. cp1252) and crashes on anything outside it, so this
# must run before any print() call.
sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
sys.stderr.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

import threading

from supabase import create_client

from config import SUPABASE_SECRET_KEY, SUPABASE_URL, supabase

_thread_local = threading.local()


def get_write_client():
    """Each writer thread gets its own Supabase client. The shared client from config.py
    is fine for this script's sequential reads (one channel at a time, main thread only),
    but sharing it across the write concurrency's worker threads produced a real Windows
    socket error (httpx.ReadError / WinError 10035) under concurrent writes -- httpx's
    connection pool was not safe to hit from multiple threads at once in practice here,
    whatever the theory says.
    """
    client = getattr(_thread_local, "client", None)
    if client is None:
        client = create_client(SUPABASE_URL, SUPABASE_SECRET_KEY)
        _thread_local.client = client
    return client

FETCH_PAGE_SIZE = 1000
STATS_FETCH_CHUNK_SIZE = 150  # video_ids per .in_() call when fetching video_stats
UPDATE_CHUNK_SIZE = 150  # video_ids per .in_() call when writing baselines back
DB_WRITE_MAX_ATTEMPTS = 3
DB_WRITE_RETRY_DELAY_SECONDS = 2
TEST_SAMPLE_SIZE = 5
WRITE_CONCURRENCY = 10  # era writes can't collapse into one call per format like step 7's;
                        # 77,613 mature videos means tens of thousands of write calls

MATURE_AGE_DAYS = 180
BASELINE_WINDOW_MONTHS = 24  # current baseline
ERA_WINDOW_MONTHS = 6  # era baseline, before widening
ERA_WIDENED_WINDOW_MONTHS = 12  # era baseline, after widening
BASELINE_MIN_VIDEOS = 10
BASELINE_CAP = 20
METRICS = ("views", "likes", "comments")


def shift_months(reference, months):
    """`reference` shifted by `months` calendar months (either direction), clamping the
    day for short months."""
    total = reference.month - 1 + months
    year = reference.year + total // 12
    month = total % 12 + 1
    day = min(reference.day, calendar.monthrange(year, month)[1])
    return reference.replace(year=year, month=month, day=day)


def months_ago(reference, months):
    return shift_months(reference, -months)


def compute_window_boundaries():
    """Computed once per run, in UTC, so every channel is judged against the same instant."""
    now = datetime.now(timezone.utc)
    cutoff_180 = now - timedelta(days=MATURE_AGE_DAYS)
    cutoff_24mo = months_ago(now, BASELINE_WINDOW_MONTHS)
    return cutoff_180, cutoff_24mo


def chunked(items, size):
    for i in range(0, len(items), size):
        yield items[i:i + size]


def fetch_channels(channel_id=None):
    query = supabase.table("channels").select("channel_id, name").order("name")
    if channel_id:
        query = query.eq("channel_id", channel_id)
    return query.execute().data


def fetch_channel_videos(channel_id):
    """All of the channel's videos: video_id, published_at (parsed), is_short, and the
    currently-stored baseline columns. The stored columns are read here, not fetched
    separately, so process_channel can compare a freshly computed payload against what's
    already there and skip writing rows that would not actually change -- see
    baseline_unchanged(). Paginated -- several channels exceed 1,000 videos (FloTrack
    alone has 5,529)."""
    videos = []
    start = 0
    while True:
        response = (
            supabase.table("videos")
            .select(
                "video_id, published_at, is_short, "
                "baseline_views, baseline_likes, baseline_comments, baseline_kind"
            )
            .eq("channel_id", channel_id)
            .order("video_id")
            .range(start, start + FETCH_PAGE_SIZE - 1)
            .execute()
        )
        rows = response.data
        for row in rows:
            row["published_at"] = datetime.fromisoformat(row["published_at"].replace("Z", "+00:00"))
        videos.extend(rows)
        if len(rows) < FETCH_PAGE_SIZE:
            break
        start += FETCH_PAGE_SIZE
    return videos


def fetch_latest_stats(video_ids):
    """video_id -> latest video_stats row (highest captured_at; most videos have exactly one).
    captured_at is a date string, so lexicographic comparison is correct."""
    latest = {}
    for id_chunk in chunked(video_ids, STATS_FETCH_CHUNK_SIZE):
        start = 0
        while True:
            response = (
                supabase.table("video_stats")
                .select("video_id, captured_at, views, likes, comments")
                .in_("video_id", id_chunk)
                .order("id")
                .range(start, start + FETCH_PAGE_SIZE - 1)
                .execute()
            )
            rows = response.data
            for row in rows:
                existing = latest.get(row["video_id"])
                if existing is None or row["captured_at"] > existing["captured_at"]:
                    latest[row["video_id"]] = row
            if len(rows) < FETCH_PAGE_SIZE:
                break
            start += FETCH_PAGE_SIZE
    return latest


def compute_metrics_from_pool(pool, exclude_video_id=None):
    """Current-baseline sampling: pool is a list of {video_id, published_at, views,
    likes, comments}, any order. Per metric independently: drop videos with a NULL value
    for that metric (and the excluded video, if any), require at least 10, take the 20
    most recent by published_at, median.

    exclude_video_id is unused by the current baseline's own callers (a young video is
    never a member of its own pool in the first place, since the pool is mature videos
    only) but is kept so a caller can assert exclusion where it matters. The era baseline
    uses its own sampling -- see compute_era_metrics_from_window -- because "most recent
    20" is wrong for a window centred on the subject video.
    """
    ordered = sorted(pool, key=lambda v: v["published_at"])
    result = {}
    for metric in METRICS:
        eligible = [v for v in ordered if v[metric] is not None and v["video_id"] != exclude_video_id]
        if exclude_video_id is not None:
            assert all(v["video_id"] != exclude_video_id for v in eligible), (
                f"{exclude_video_id} was not excluded from its own baseline"
            )
        if len(eligible) < BASELINE_MIN_VIDEOS:
            result[metric] = None
            continue
        sample = eligible[-BASELINE_CAP:]  # most recent BASELINE_CAP, since eligible is ascending
        result[metric] = median(v[metric] for v in sample)
    return result


def nearest_balanced_sample(candidates, published_at, per_side=BASELINE_MIN_VIDEOS, cap=BASELINE_CAP):
    """Up to `cap` candidates nearest to `published_at`, taking at most `per_side` from
    each side of it (published before / on-or-after) and filling any shortfall on one
    side from the other side's next-nearest. `candidates`: list of {video_id,
    published_at, ...}, already filtered to one metric's eligible pool.

    A candidate sharing `published_at` exactly is placed on the "after" side, arbitrarily
    but consistently -- the split only needs to be deterministic, since real videos this
    close together are a rounding case, not the common one. Nearness ties (including two
    candidates sharing a publication time) are broken by video_id, so the sample a frozen
    video draws does not depend on an unstable sort between runs.
    """
    before, after = [], []
    for c in candidates:
        (before if c["published_at"] < published_at else after).append(c)

    before.sort(key=lambda c: (published_at - c["published_at"], c["video_id"]))
    after.sort(key=lambda c: (c["published_at"] - published_at, c["video_id"]))

    chosen = before[:per_side] + after[:per_side]
    if len(chosen) < cap:
        leftover = sorted(
            before[per_side:] + after[per_side:],
            key=lambda c: (abs(c["published_at"] - published_at), c["video_id"]),
        )
        chosen += leftover[:cap - len(chosen)]
    return chosen


def compute_era_metrics_from_window(window, video, exclude_video_id):
    """window: candidates already restricted to the era time window (see window_slice).
    Per metric independently: drop videos with a NULL value for that metric and the
    subject video itself, require at least 10, then take the up-to-20 nearest to the
    subject's published_at via nearest_balanced_sample, and median them.

    The exclusion is asserted, not just relied upon: the subject's own date trivially
    sits inside its own window, so the window alone would not keep it out.

    Returns (result, samples): samples[metric] is the actual list of candidates the
    median was taken over (None where the metric didn't resolve). Cheap to carry --
    it's the same list objects already built for the median, not a copy -- and it's
    what --compare-video prints to show a video's real pool, not just its number.
    """
    published_at = video["published_at"]
    result = {}
    samples = {}
    for metric in METRICS:
        eligible = [v for v in window if v[metric] is not None and v["video_id"] != exclude_video_id]
        assert all(v["video_id"] != exclude_video_id for v in eligible), (
            f"{exclude_video_id} was not excluded from its own era baseline"
        )
        if len(eligible) < BASELINE_MIN_VIDEOS:
            result[metric] = None
            samples[metric] = None
            continue
        sample = nearest_balanced_sample(eligible, published_at)
        result[metric] = median(v[metric] for v in sample)
        samples[metric] = sample
    return result, samples


def build_sorted_pool(pool):
    sorted_pool = sorted(pool, key=lambda v: v["published_at"])
    dates = [v["published_at"] for v in sorted_pool]
    return sorted_pool, dates


def window_slice(sorted_pool, dates, lo, hi):
    return sorted_pool[bisect_left(dates, lo):bisect_right(dates, hi)]


def compute_era_baseline(video, sorted_pool, dates, cutoff_180, current_baseline):
    """Returns (baseline_dict, baseline_kind, widened, resolved_samples) for one mature
    video of known format. `current_baseline` is the channel+format's already-computed
    current baseline, reused as the fallback source rather than recomputed.

    resolved_samples[metric] is the pool the median was actually taken over, for metrics
    that resolved at the 6- or 12-month tier (None for a metric that used the fallback or
    stayed unscored). It costs nothing extra to compute -- the sample already exists as
    part of the median -- and it's what --compare-video shows instead of just a number.
    """
    published_at = video["published_at"]
    video_id = video["video_id"]

    result = {}
    tiers = {}
    resolved_samples = {}
    widened = False

    for window_months in (ERA_WINDOW_MONTHS, ERA_WIDENED_WINDOW_MONTHS):
        remaining = [m for m in METRICS if m not in result]
        if not remaining:
            break
        if window_months == ERA_WIDENED_WINDOW_MONTHS:
            widened = True

        lo = shift_months(published_at, -window_months)
        hi = min(shift_months(published_at, window_months), cutoff_180)
        window = window_slice(sorted_pool, dates, lo, hi)
        window_metrics, window_samples = compute_era_metrics_from_window(window, video, exclude_video_id=video_id)

        for metric in remaining:
            if window_metrics[metric] is not None:
                result[metric] = window_metrics[metric]
                tiers[metric] = "era"
                resolved_samples[metric] = window_samples[metric]

    for metric in METRICS:
        if metric not in result:
            fallback_value = current_baseline.get(metric)
            if fallback_value is not None:
                result[metric] = fallback_value
                tiers[metric] = "current"

    if any(tier == "era" for tier in tiers.values()):
        kind = "era"
    elif any(tier == "current" for tier in tiers.values()):
        kind = "current"
    else:
        kind = "insufficient"

    baseline_dict = {metric: result.get(metric) for metric in METRICS}
    return baseline_dict, kind, widened, resolved_samples


def update_with_retry(payload, video_ids):
    """A real UPDATE, not an upsert -- see the module docstring. Retried: a run touching
    all 342 channels is long enough to hit the occasional transient DB error, as
    classify_shorts.py did in practice."""
    last_error = None
    for attempt in range(1, DB_WRITE_MAX_ATTEMPTS + 1):
        try:
            get_write_client().table("videos").update(payload).in_("video_id", video_ids).execute()
            return
        except Exception as error:
            last_error = error
            if attempt < DB_WRITE_MAX_ATTEMPTS:
                time.sleep(DB_WRITE_RETRY_DELAY_SECONDS)
    raise last_error


def numeric_equal(existing, computed):
    """existing: a baseline_* value read back from videos (confirmed empirically to come
    back as a plain int or float, not a string -- checked against the installed client
    directly rather than assumed). computed: a Python int/float from median(). Both
    normalised to float before comparing: an int 9832 and a float 9832.0 are the same
    stored value, and comparing them unnormalised would make every such row look
    'changed' and get rewritten for no reason.
    """
    if existing is None or computed is None:
        return existing is None and computed is None
    return float(existing) == float(computed)


def baseline_unchanged(existing_row, payload):
    """True if `payload` (the freshly computed baseline_views/likes/comments/kind) is
    identical to what's already stored for this video. existing_row is None for a video
    fetch_channel_videos didn't have a stored baseline for yet (e.g. a video written
    this same run) -- never call this unchanged, so a first-time write always happens.
    """
    if existing_row is None:
        return False
    return (
        numeric_equal(existing_row.get("baseline_views"), payload["baseline_views"])
        and numeric_equal(existing_row.get("baseline_likes"), payload["baseline_likes"])
        and numeric_equal(existing_row.get("baseline_comments"), payload["baseline_comments"])
        and existing_row.get("baseline_kind") == payload["baseline_kind"]
    )


def apply_group(payload, video_ids, existing_by_id, test_mode, executor, futures):
    """Submits each chunk's write to the shared executor rather than writing inline: era
    baselines produce far more distinct payloads than step 7 did, so writes need to
    overlap rather than run one at a time. Futures are collected, not awaited here --
    the caller waits for all of them once, after every channel has been processed, so a
    write failure surfaces clearly instead of being silently outrun by the next channel.

    video_ids whose stored baseline already matches `payload` are left alone entirely --
    not written, not counted as written -- so a monthly run doesn't rewrite all 98,300
    rows every time most of them are frozen and could not have changed. Returns
    (changed, unchanged) counts.
    """
    if not video_ids:
        return 0, 0
    changed_ids = [vid for vid in video_ids if not baseline_unchanged(existing_by_id.get(vid), payload)]
    unchanged_count = len(video_ids) - len(changed_ids)
    if not changed_ids:
        return 0, unchanged_count
    if not test_mode:
        for chunk in chunked(changed_ids, UPDATE_CHUNK_SIZE):
            futures.append(executor.submit(update_with_retry, payload, chunk))
    return len(changed_ids), unchanged_count


def metrics_summary(baseline):
    scored = [metric for metric in METRICS if baseline[metric] is not None]
    return ", ".join(scored) if scored else "none"


def fetch_stored_baseline(video_id):
    """The video's currently-stored baseline, read fresh right before it would be
    overwritten -- used only by --compare-video, to print old vs. new."""
    rows = (
        supabase.table("videos")
        .select("video_id, title, published_at, is_short, baseline_views, baseline_likes, baseline_comments, baseline_kind")
        .eq("video_id", video_id)
        .execute()
        .data
    )
    return rows[0] if rows else None


def print_compare_video(video_id, old_row, baseline_dict, kind, resolved_samples, subject_published_at):
    """--compare-video's report: old stored baseline next to the new one, and -- for
    whichever metrics resolved at the 6- or 12-month tier -- the actual pool dates the
    new median was taken over, so the fix (nearest, not most recent) can be seen
    directly rather than inferred from the number alone."""
    print(f"\n--- --compare-video {video_id} ---")
    print(f"  Subject published: {subject_published_at.date()}")
    if old_row is None:
        print("  Not found in the database (nothing stored yet).")
    else:
        print(f"  Title: {old_row['title']}")
        print(f"  Published: {old_row['published_at']}")
        print(
            f"  OLD  baseline_views={old_row['baseline_views']} "
            f"baseline_likes={old_row['baseline_likes']} baseline_comments={old_row['baseline_comments']} "
            f"kind={old_row['baseline_kind']}"
        )
    print(
        f"  NEW  baseline_views={baseline_dict['views']} baseline_likes={baseline_dict['likes']} "
        f"baseline_comments={baseline_dict['comments']} kind={kind}"
    )
    for metric in METRICS:
        sample = resolved_samples.get(metric)
        if sample is None:
            print(f"  NEW pool ({metric}): none at the 6- or 12-month tier (fallback or insufficient)")
            continue
        dates = sorted(v["published_at"] for v in sample)
        before_count = sum(1 for d in dates if d < subject_published_at)
        after_count = len(dates) - before_count
        print(
            f"  NEW pool ({metric}): {len(dates)} video(s), {dates[0].date()} to {dates[-1].date()} "
            f"-- {before_count} before subject, {after_count} on/after"
        )


def process_channel(channel, cutoff_180, cutoff_24mo, test_mode, era_only, executor, futures, compare_video_id=None):
    channel_id = channel["channel_id"]
    name = channel["name"]

    videos = fetch_channel_videos(channel_id)
    if not videos:
        print(f"{name} ({channel_id}): no videos")
        return dict(
            format_missing=False, young_written=0, young_unchanged=0, young_insufficient=0,
            era_6mo=0, era_12mo=0, era_fallback=0, era_insufficient=0, era_written=0, era_unchanged=0,
        )

    existing_by_id = {v["video_id"]: v for v in videos}
    stats_by_video = fetch_latest_stats([v["video_id"] for v in videos])

    # Mature, known-format videos with a stats row: candidates for any baseline pool.
    mature_pool_candidates = {True: [], False: []}
    # Mature videos needing their own era baseline, by format (stats not required: a
    # baseline is about the pool, not the subject's own numbers).
    mature_subjects_by_format = {True: [], False: []}
    mature_unknown_format_ids = []
    write_targets = []

    for v in videos:
        is_mature = v["published_at"] < cutoff_180
        if not is_mature:
            write_targets.append(v)
            continue

        if v["is_short"] not in (True, False):
            mature_unknown_format_ids.append(v["video_id"])
            continue

        mature_subjects_by_format[v["is_short"]].append(v)

        stats = stats_by_video.get(v["video_id"])
        if stats is not None:
            mature_pool_candidates[v["is_short"]].append({
                "video_id": v["video_id"],
                "published_at": v["published_at"],
                "views": stats["views"],
                "likes": stats["likes"],
                "comments": stats["comments"],
            })

    write_target_ids = {v["video_id"] for v in write_targets}
    assert write_target_ids.isdisjoint(
        {c["video_id"] for c in mature_pool_candidates[True]} |
        {c["video_id"] for c in mature_pool_candidates[False]}
    ), f"{channel_id}: a write-target video is also a mature baseline candidate"

    # Current baseline: the 180-day-to-24-month slice of the mature candidates.
    pools = {
        is_short: [c for c in mature_pool_candidates[is_short] if c["published_at"] >= cutoff_24mo]
        for is_short in (True, False)
    }
    baselines = {is_short: compute_metrics_from_pool(pools[is_short]) for is_short in (True, False)}
    format_missing = any(metrics_summary(baselines[fmt]) == "none" for fmt in (True, False))

    # --- Current baseline: write targets (videos 180 days old or younger) ---
    groups = {"shorts": [], "long_form": [], "unknown_format": []}
    for v in write_targets:
        if v["is_short"] is True:
            groups["shorts"].append(v["video_id"])
        elif v["is_short"] is False:
            groups["long_form"].append(v["video_id"])
        else:
            groups["unknown_format"].append(v["video_id"])

    def current_payload_for(is_short):
        baseline = baselines[is_short]
        has_any = any(baseline[metric] is not None for metric in METRICS)
        return {
            "baseline_views": baseline["views"],
            "baseline_likes": baseline["likes"],
            "baseline_comments": baseline["comments"],
            "baseline_kind": "current" if has_any else "insufficient",
        }

    unknown_current_payload = {
        "baseline_views": None, "baseline_likes": None, "baseline_comments": None, "baseline_kind": "insufficient",
    }

    young_written = 0
    young_unchanged = 0
    young_insufficient = 0
    if not era_only:
        for payload, ids in (
            (current_payload_for(True), groups["shorts"]),
            (current_payload_for(False), groups["long_form"]),
            (unknown_current_payload, groups["unknown_format"]),
        ):
            written, unchanged = apply_group(payload, ids, existing_by_id, test_mode, executor, futures)
            young_written += written
            young_unchanged += unchanged

        if current_payload_for(True)["baseline_kind"] == "insufficient":
            young_insufficient += len(groups["shorts"])
        if current_payload_for(False)["baseline_kind"] == "insufficient":
            young_insufficient += len(groups["long_form"])
        young_insufficient += len(groups["unknown_format"])

    # Fetched once, before this channel's own writes are submitted below -- see
    # print_compare_video and --compare-video's help text.
    compare_old_row = fetch_stored_baseline(compare_video_id) if compare_video_id else None

    # --- Era baseline: mature videos (older than 180 days) ---
    sorted_pools = {is_short: build_sorted_pool(mature_pool_candidates[is_short]) for is_short in (True, False)}

    era_write_groups = {}  # (views, likes, comments, kind) -> [video_id, ...]
    era_6mo = era_12mo = era_fallback = era_insufficient = 0

    for is_short in (True, False):
        sorted_pool, dates = sorted_pools[is_short]
        current_baseline = baselines[is_short]
        for v in mature_subjects_by_format[is_short]:
            baseline_dict, kind, widened, resolved_samples = compute_era_baseline(
                v, sorted_pool, dates, cutoff_180, current_baseline
            )
            key = (baseline_dict["views"], baseline_dict["likes"], baseline_dict["comments"], kind)
            era_write_groups.setdefault(key, []).append(v["video_id"])

            if compare_video_id and v["video_id"] == compare_video_id:
                print_compare_video(
                    compare_video_id, compare_old_row, baseline_dict, kind, resolved_samples, v["published_at"]
                )

            if kind == "era":
                era_12mo += widened
                era_6mo += not widened
            elif kind == "current":
                era_fallback += 1
            else:
                era_insufficient += 1

    era_insufficient += len(mature_unknown_format_ids)

    era_written = 0
    era_unchanged = 0
    for (views, likes, comments, kind), video_ids in era_write_groups.items():
        payload = {"baseline_views": views, "baseline_likes": likes, "baseline_comments": comments, "baseline_kind": kind}
        written, unchanged = apply_group(payload, video_ids, existing_by_id, test_mode, executor, futures)
        era_written += written
        era_unchanged += unchanged
    written, unchanged = apply_group(
        unknown_current_payload, mature_unknown_format_ids, existing_by_id, test_mode, executor, futures
    )
    era_written += written
    era_unchanged += unchanged

    total_mature = sum(len(mature_subjects_by_format[f]) for f in (True, False)) + len(mature_unknown_format_ids)
    write_group_count = len(era_write_groups) + (1 if mature_unknown_format_ids else 0)

    written_word = "would write" if test_mode else "written"
    print(
        f"{name} ({channel_id}): pool shorts={len(pools[True])} long-form={len(pools[False])}; "
        f"current baseline shorts=[{metrics_summary(baselines[True])}] "
        f"long-form=[{metrics_summary(baselines[False])}]; "
        f"young {written_word} {young_written}, unchanged {young_unchanged} "
        f"(shorts={len(groups['shorts'])}, long-form={len(groups['long_form'])}, "
        f"unknown-format={len(groups['unknown_format'])})"
    )
    print(
        f"  era: {total_mature} mature video(s) -- 6mo={era_6mo}, 12mo={era_12mo}, "
        f"fallback={era_fallback}, insufficient={era_insufficient}; "
        f"{written_word} {era_written}, unchanged {era_unchanged}, in {write_group_count} write group(s)"
    )

    return dict(
        format_missing=format_missing,
        young_written=young_written, young_unchanged=young_unchanged, young_insufficient=young_insufficient,
        era_6mo=era_6mo, era_12mo=era_12mo, era_fallback=era_fallback,
        era_insufficient=era_insufficient, era_written=era_written, era_unchanged=era_unchanged,
    )


def parse_args():
    parser = argparse.ArgumentParser(description="Computes the current and era baselines for every channel.")
    parser.add_argument(
        "--test",
        action="store_true",
        help="Process 5 channels and print what would be written, without touching the database.",
    )
    parser.add_argument(
        "--channel",
        metavar="CHANNEL_ID",
        help="Restrict to a single channel, so a result can be checked by hand.",
    )
    parser.add_argument(
        "--era-only",
        action="store_true",
        help="Skip writing the current baseline to young videos (step 7's work); still computes "
             "it in memory, since era videos use it as their fallback.",
    )
    parser.add_argument(
        "--compare-video",
        metavar="VIDEO_ID",
        help="Print the video's old stored baseline next to the newly computed one, plus the "
             "actual pool dates the new median was taken over. Diagnostic only -- combine with "
             "--test and --channel to check a single video by hand before a real run.",
    )
    return parser.parse_args()


def run(channel_id=None, test_mode=False, era_only=False, compare_video_id=None, sample_size=None):
    """Callable core, reused by this script's own CLI main() and by refresh.py. Prints
    the same per-channel and summary lines either way, and returns the totals dict
    (including write_failures) rather than deciding what to do about a failure --
    that's the caller's call: main() exits non-zero, refresh.py treats it as a hard
    gate before the refresh (NEXT_STEPS.md step 6).

    Raises ValueError if channel_id is given and doesn't exist, so a caller can
    distinguish "no such channel" from "channel exists but has 0 videos".
    """
    channels = fetch_channels(channel_id)
    if channel_id and not channels:
        raise ValueError(f"No channel found with channel_id={channel_id}")
    if sample_size and not channel_id:
        channels = channels[:sample_size]

    cutoff_180, cutoff_24mo = compute_window_boundaries()
    print(
        f"Computing baselines for {len(channels)} channel(s). "
        f"Mature cutoff: {cutoff_180.isoformat()}. Current-baseline window start: {cutoff_24mo.isoformat()}."
        + (" Era pass only." if era_only else "")
        + (" No database writes." if test_mode else ""),
        flush=True,
    )

    totals = dict(
        channels_processed=0, channels_format_missing=0,
        young_written=0, young_unchanged=0, young_insufficient=0,
        era_6mo=0, era_12mo=0, era_fallback=0, era_insufficient=0, era_written=0, era_unchanged=0,
    )

    futures = []
    with ThreadPoolExecutor(max_workers=WRITE_CONCURRENCY) as executor:
        for channel in channels:
            stats = process_channel(
                channel, cutoff_180, cutoff_24mo, test_mode, era_only, executor, futures,
                compare_video_id=compare_video_id,
            )
            totals["channels_processed"] += 1
            if stats["format_missing"]:
                totals["channels_format_missing"] += 1
            for key in (
                "young_written", "young_unchanged", "young_insufficient",
                "era_6mo", "era_12mo", "era_fallback", "era_insufficient", "era_written", "era_unchanged",
            ):
                totals[key] += stats[key]

        # Writes were submitted, not awaited, as each channel was processed. Wait for all
        # of them now, so a write failure (after its own retries) is surfaced here rather
        # than silently outrun by the script reaching the end.
        write_failures = 0
        for future in futures:
            try:
                future.result()
            except Exception as error:
                write_failures += 1
                print(f"Write failed: {error}")

    written_word = "would write" if test_mode else "written"
    print("\n--- Summary ---")
    if write_failures:
        print(f"WRITE FAILURES: {write_failures} of {len(futures)} write call(s) failed -- counts below include them as attempted, not confirmed.")
    print(f"Channels processed: {totals['channels_processed']}")
    print(f"Channels where a format had no current baseline: {totals['channels_format_missing']}")
    print(
        f"Current baseline -- {written_word}: {totals['young_written']}, unchanged: {totals['young_unchanged']}, "
        f"left insufficient: {totals['young_insufficient']}"
    )
    print(
        f"Era baseline -- 6-month window: {totals['era_6mo']}, 12-month window: {totals['era_12mo']}, "
        f"fallback to current: {totals['era_fallback']}, insufficient: {totals['era_insufficient']}, "
        f"{written_word}: {totals['era_written']}, unchanged: {totals['era_unchanged']}"
    )

    totals["write_failures"] = write_failures
    return totals


def parse_args():
    parser = argparse.ArgumentParser(description="Computes the current and era baselines for every channel.")
    parser.add_argument(
        "--test",
        action="store_true",
        help="Process 5 channels and print what would be written, without touching the database.",
    )
    parser.add_argument(
        "--channel",
        metavar="CHANNEL_ID",
        help="Restrict to a single channel, so a result can be checked by hand.",
    )
    parser.add_argument(
        "--era-only",
        action="store_true",
        help="Skip writing the current baseline to young videos (step 7's work); still computes "
             "it in memory, since era videos use it as their fallback.",
    )
    parser.add_argument(
        "--compare-video",
        metavar="VIDEO_ID",
        help="Print the video's old stored baseline next to the newly computed one, plus the "
             "actual pool dates the new median was taken over. Diagnostic only -- combine with "
             "--test and --channel to check a single video by hand before a real run.",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    try:
        totals = run(
            channel_id=args.channel,
            test_mode=args.test,
            era_only=args.era_only,
            compare_video_id=args.compare_video,
            sample_size=TEST_SAMPLE_SIZE if args.test else None,
        )
    except ValueError as error:
        print(str(error))
        return

    if totals["write_failures"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
