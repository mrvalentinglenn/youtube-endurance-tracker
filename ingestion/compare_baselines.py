"""Compares baselines before vs. after the 2026-09-21 fix to compute_baselines.py's era
baseline sampling (nearest-balanced pool instead of most-recent-20 -- see that script's
module docstring). Read-only: no writes, nothing recomputed that gets stored. Takes the
CSV snapshot_baselines.py wrote before the real run and compares it against the live
database after the run and the videos_scored refresh.

Five things reported, in this order:
  1. FloTrack's flagship example video: old vs. new baseline_views, the new pool's dates,
     and old vs. new score_views.
  2. baseline_kind counts, old (CSV) vs. new (DB).
  3. Count of videos whose views baseline changed by more than 20% (either format), then
     the five channels with the highest SHARE of their long-form videos crossing that
     threshold, among channels with at least 20 long-form videos -- a share, not a raw
     count, so the ranking isn't just "which channel has the most videos".
  4. The residual growth-bias check from DECISIONS.md (2026-09-20, "Residual growth bias
     in era baselines is accepted"), recomputed for adidas, Castelli Cycling and The Feed
     -- old and new figures both produced by the same growth_bias_quartiles() function,
     so the comparison isn't skewed by two different methods.
  5. FloTrack's share of the top 60 across all categories, long-form, views, Relative,
     last 365 days -- the app's actual default query shape with Relative substituted for
     Absolute, unfiltered by category (this is how the "11" baseline figure was measured).

Usage:
    python compare_baselines.py [--snapshot baseline_snapshot.csv]
"""

import argparse
import csv
import sys
from datetime import datetime, timedelta, timezone
from statistics import median

sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
sys.stderr.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

from config import supabase

FETCH_PAGE_SIZE = 1000
CHANGED_THRESHOLD = 0.20
MIN_LONG_FORM_FOR_RANKING = 20
TOP_N_CHANGED_CHANNELS = 5
TOP_N_LIMIT = 60
TOP_N_WINDOW_DAYS = 365

FLOTRACK_CHANNEL_ID = "UC1Fp52XJH8UKaa_gHMZrckw"
FLOTRACK_VIDEO_ID = "t2WuAgJMlbs"

GROWTH_BIAS_CHANNEL_NAMES = ["adidas", "Castelli Cycling", "The Feed"]
# DECISIONS.md, 2026-09-20, "Residual growth bias in era baselines is accepted":
# (oldest-quartile median score_views, newest-quartile median score_views).
GROWTH_BIAS_ORIGINAL = {
    "adidas": (0.85, 0.59),
    "Castelli Cycling": (0.57, 2.05),
    "The Feed": (0.44, 0.99),
}


def to_float(value):
    return float(value) if value not in (None, "") else None


def load_snapshot(path):
    """video_id -> old baseline row."""
    snapshot = {}
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            snapshot[row["video_id"]] = {
                "baseline_views": to_float(row["baseline_views"]),
                "baseline_likes": to_float(row["baseline_likes"]),
                "baseline_comments": to_float(row["baseline_comments"]),
                "baseline_kind": row["baseline_kind"] or None,
            }
    return snapshot


def fetch_all_new_videos():
    """video_id, channel_id, is_short, published_at (parsed), baseline_views,
    baseline_kind for every video, as it stands now (after the real run)."""
    rows = []
    start = 0
    while True:
        response = (
            supabase.table("videos")
            .select("video_id, channel_id, is_short, published_at, baseline_views, baseline_kind")
            .order("video_id")
            .range(start, start + FETCH_PAGE_SIZE - 1)
            .execute()
        )
        page = response.data
        for row in page:
            row["published_at"] = datetime.fromisoformat(row["published_at"].replace("Z", "+00:00"))
        rows.extend(page)
        if len(page) < FETCH_PAGE_SIZE:
            break
        start += FETCH_PAGE_SIZE
    return rows


def fetch_channels_by_name(names):
    """name -> channel_id, for a short explicit list of channels."""
    result = {}
    for name in names:
        rows = supabase.table("channels").select("channel_id, name").eq("name", name).execute().data
        if not rows:
            print(f"WARNING: no channel found with name exactly '{name}'")
            continue
        result[name] = rows[0]["channel_id"]
    return result


def fetch_channel_names(channel_ids):
    names = {}
    for id_chunk_start in range(0, len(channel_ids), FETCH_PAGE_SIZE):
        chunk = channel_ids[id_chunk_start:id_chunk_start + FETCH_PAGE_SIZE]
        rows = supabase.table("channels").select("channel_id, name").in_("channel_id", chunk).execute().data
        for row in rows:
            names[row["channel_id"]] = row["name"]
    return names


def fetch_views_for_channel_longform(channel_id):
    """video_id -> (published_at, views) for a channel's long-form videos, from
    videos_scored (already joined to each video's latest measurement). Used for the
    growth-bias recompute, where the raw view count is the same whether we're scoring it
    against the old or the new baseline -- this run never touched video_stats."""
    rows = []
    start = 0
    while True:
        response = (
            supabase.table("videos_scored")
            .select("video_id, published_at, views")
            .eq("channel_id", channel_id)
            .eq("is_short", False)
            .order("video_id")
            .range(start, start + FETCH_PAGE_SIZE - 1)
            .execute()
        )
        page = response.data
        for row in page:
            row["published_at"] = datetime.fromisoformat(row["published_at"].replace("Z", "+00:00"))
        rows.extend(page)
        if len(page) < FETCH_PAGE_SIZE:
            break
        start += FETCH_PAGE_SIZE
    return rows


def compute_score(views, baseline):
    """Mirrors videos_scored's own division and zero guard (NULLIF(baseline, 0)), so old
    and new scores are produced by the identical rule -- see module docstring, item 4."""
    if views is None or baseline is None or baseline == 0:
        return None
    return views / baseline


def growth_bias_quartiles(published_and_scores):
    """published_and_scores: list of (published_at, score), score already non-None, any
    order. Returns (oldest_quartile_median, newest_quartile_median), or (None, None) if
    there are too few to quarter meaningfully. Quartile size is len // 4, matching the
    plain floor-division split; the two quartiles are the first and last slice of that
    size, so they cannot overlap even when 4 doesn't divide the count evenly."""
    ordered = sorted(published_and_scores, key=lambda pair: pair[0])
    n = len(ordered)
    if n < 4:
        return None, None
    quarter = n // 4
    oldest = [s for _, s in ordered[:quarter]]
    newest = [s for _, s in ordered[-quarter:]]
    return median(oldest), median(newest)


def report_flotrack_video(snapshot):
    print("=" * 70)
    print("1. FloTrack's flagship example video")
    print("=" * 70)

    old = snapshot.get(FLOTRACK_VIDEO_ID)
    new_row = (
        supabase.table("videos")
        .select("video_id, title, published_at, baseline_views, baseline_kind")
        .eq("video_id", FLOTRACK_VIDEO_ID)
        .execute()
        .data
    )
    scored_row = (
        supabase.table("videos_scored")
        .select("views, score_views")
        .eq("video_id", FLOTRACK_VIDEO_ID)
        .execute()
        .data
    )

    if not old or not new_row or not scored_row:
        print("  Could not find the video in the snapshot, videos, or videos_scored -- skipping.")
        return

    new_row = new_row[0]
    views = scored_row[0]["views"]
    new_score = scored_row[0]["score_views"]
    old_score = compute_score(views, old["baseline_views"])

    print(f"  {new_row['title']}")
    print(f"  Published: {new_row['published_at']}")
    print(f"  Current views: {views}")
    print(f"  OLD baseline_views: {old['baseline_views']}   OLD score_views: {old_score}")
    print(f"  NEW baseline_views: {new_row['baseline_views']}   NEW score_views (from videos_scored): {new_score}")
    print(f"  NEW baseline_kind: {new_row['baseline_kind']}")


def report_baseline_kind_counts(snapshot, new_videos):
    print("\n" + "=" * 70)
    print("2. baseline_kind counts, old vs. new")
    print("=" * 70)

    old_counts = {}
    for row in snapshot.values():
        old_counts[row["baseline_kind"]] = old_counts.get(row["baseline_kind"], 0) + 1

    new_counts = {}
    for row in new_videos:
        new_counts[row["baseline_kind"]] = new_counts.get(row["baseline_kind"], 0) + 1

    for kind in sorted(set(old_counts) | set(new_counts)):
        old_n = old_counts.get(kind, 0)
        new_n = new_counts.get(kind, 0)
        print(f"  {kind or '(null)'}: old={old_n}  new={new_n}  delta={new_n - old_n:+d}")


def report_changed_videos(snapshot, new_videos):
    print("\n" + "=" * 70)
    print("3. Videos whose views baseline changed by more than 20%")
    print("=" * 70)

    changed_total = 0
    comparable_total = 0

    # Per-channel long-form tallies, for the share-based ranking.
    longform_total_by_channel = {}
    longform_changed_by_channel = {}

    for row in new_videos:
        old = snapshot.get(row["video_id"])
        if old is None:
            continue
        old_baseline = old["baseline_views"]
        new_baseline = row["baseline_views"]

        if row["is_short"] is False:
            channel_id = row["channel_id"]
            longform_total_by_channel[channel_id] = longform_total_by_channel.get(channel_id, 0) + 1

        if old_baseline is None or new_baseline is None or old_baseline == 0:
            continue
        comparable_total += 1

        pct_change = abs(new_baseline - old_baseline) / old_baseline
        if pct_change > CHANGED_THRESHOLD:
            changed_total += 1
            if row["is_short"] is False:
                channel_id = row["channel_id"]
                longform_changed_by_channel[channel_id] = longform_changed_by_channel.get(channel_id, 0) + 1

    print(f"  Comparable videos (had a baseline_views both before and after): {comparable_total}")
    print(f"  Changed by more than {CHANGED_THRESHOLD:.0%}: {changed_total} (both formats)")

    shares = []
    for channel_id, total in longform_total_by_channel.items():
        if total < MIN_LONG_FORM_FOR_RANKING:
            continue
        changed = longform_changed_by_channel.get(channel_id, 0)
        shares.append((channel_id, changed, total, changed / total))

    shares.sort(key=lambda t: t[3], reverse=True)
    top = shares[:TOP_N_CHANGED_CHANNELS]
    channel_ids = [channel_id for channel_id, *_ in top]
    names = fetch_channel_names(channel_ids)

    print(
        f"\n  Top {TOP_N_CHANGED_CHANNELS} channels by SHARE of long-form videos changed >20% "
        f"(channels with >= {MIN_LONG_FORM_FOR_RANKING} long-form videos, {len(shares)} eligible):"
    )
    for channel_id, changed, total, share in top:
        name = names.get(channel_id, channel_id)
        print(f"    {name}: {changed}/{total} long-form videos changed ({share:.1%})")


def report_growth_bias(snapshot):
    print("\n" + "=" * 70)
    print("4. Residual growth-bias recheck (oldest vs. newest quartile, long-form views score)")
    print("=" * 70)

    channel_ids_by_name = fetch_channels_by_name(GROWTH_BIAS_CHANNEL_NAMES)

    for name in GROWTH_BIAS_CHANNEL_NAMES:
        channel_id = channel_ids_by_name.get(name)
        if channel_id is None:
            continue

        videos = fetch_views_for_channel_longform(channel_id)

        old_pairs = []
        new_pairs = []
        for v in videos:
            old_row = snapshot.get(v["video_id"])
            old_baseline = old_row["baseline_views"] if old_row else None
            old_score = compute_score(v["views"], old_baseline)
            if old_score is not None:
                old_pairs.append((v["published_at"], old_score))

        # New baseline + score come straight from videos_scored's own score_views, via a
        # second small fetch, so "new" is exactly what the app shows -- not a
        # recomputation from videos.baseline_views that could drift from the view's own
        # NULLIF guard.
        scored_rows = (
            supabase.table("videos_scored")
            .select("video_id, published_at, score_views")
            .eq("channel_id", channel_id)
            .eq("is_short", False)
            .execute()
            .data
        )
        for row in scored_rows:
            if row["score_views"] is not None:
                published_at = datetime.fromisoformat(row["published_at"].replace("Z", "+00:00"))
                new_pairs.append((published_at, row["score_views"]))

        old_oldest, old_newest = growth_bias_quartiles(old_pairs)
        new_oldest, new_newest = growth_bias_quartiles(new_pairs)
        orig_oldest, orig_newest = GROWTH_BIAS_ORIGINAL[name]

        print(f"\n  {name}:")
        print(f"    DECISIONS.md (2026-09-20): oldest={orig_oldest}  newest={orig_newest}")
        print(f"    Recomputed OLD (from snapshot): oldest={old_oldest}  newest={old_newest}  (n={len(old_pairs)})")
        print(f"    Recomputed NEW (post-fix):      oldest={new_oldest}  newest={new_newest}  (n={len(new_pairs)})")
        if old_oldest is not None and orig_oldest is not None:
            matches = abs(old_oldest - orig_oldest) < 0.02 and abs(old_newest - orig_newest) < 0.02
            print(f"    OLD matches DECISIONS.md: {matches}")


def report_flotrack_top60_share():
    print("\n" + "=" * 70)
    print("5. FloTrack's share of the top 60 (all categories, long-form, views, Relative, last 365 days)")
    print("=" * 70)

    cutoff = (datetime.now(timezone.utc) - timedelta(days=TOP_N_WINDOW_DAYS)).isoformat()
    rows = (
        supabase.table("videos_scored")
        .select("video_id, channel_id")
        .eq("is_short", False)
        .gte("published_at", cutoff)
        .order("score_views", desc=True, nullsfirst=False)
        .limit(TOP_N_LIMIT)
        .execute()
        .data
    )
    flotrack_count = sum(1 for row in rows if row["channel_id"] == FLOTRACK_CHANNEL_ID)
    print(f"  FloTrack videos in the top {TOP_N_LIMIT}: {flotrack_count} (of {len(rows)} rows returned)")


def parse_args():
    parser = argparse.ArgumentParser(description="Compares baselines before vs. after the nearest-pool fix.")
    parser.add_argument("--snapshot", default="baseline_snapshot.csv", help="Path to the pre-run CSV snapshot.")
    return parser.parse_args()


def main():
    args = parse_args()

    print(f"Loading snapshot from {args.snapshot}...", flush=True)
    snapshot = load_snapshot(args.snapshot)
    print(f"Loaded {len(snapshot)} old baseline row(s).")

    print("Fetching current videos table...", flush=True)
    new_videos = fetch_all_new_videos()
    print(f"Fetched {len(new_videos)} current row(s).\n")

    report_flotrack_video(snapshot)
    report_baseline_kind_counts(snapshot, new_videos)
    report_changed_videos(snapshot, new_videos)
    report_growth_bias(snapshot)
    report_flotrack_top60_share()


if __name__ == "__main__":
    main()
