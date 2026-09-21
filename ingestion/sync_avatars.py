"""Fetches a small channel avatar for every channel and stores it in Supabase Storage.

Reads channels from the channels table, never the spreadsheet. Calls channels.list in
batches of 50 (part=snippet, ~7 quota units for 342 channels), picks the medium thumbnail
(falling back to high, then default), downloads it, and uploads it to the channel-avatars
bucket at {channel_id}.jpg, overwriting any existing file. The public URL is then written
to channels.avatar_url.

Uploads with bucket.upload(), not bucket.update(): storage3 (checked in the installed
2.31.0 source, ingestion/.venv/Lib/site-packages/storage3/_sync/file_api.py) only honours
the x-upsert header on a POST, which is what .upload() sends -- .update() sends a PUT and
strips x-upsert entirely, so it would 404 on any channel with no avatar yet, which on the
first run is every channel. The upsert flag itself must be the string "true", not the
Python bool True: it becomes an HTTP header value, and httpx rejects a non-string header.

Writes to channels.avatar_url with .update().eq(), never .upsert(): Postgres checks NOT
NULL on the proposed insert row before checking for a conflict, so a partial payload of
{channel_id, avatar_url} fails even though the row already exists.

A failed download, a non-200 response, or a failed upload skips that channel without
calling .update() -- a stale avatar beats a broken image, and beats overwriting a working
URL with nothing. No retries: one failure is logged and the run moves on. A channel whose
API response has no thumbnail at all is also skipped, not written as NULL -- a missing
avatar is an absence, not a recorded fact.

Usage:
    python sync_avatars.py            # writes to the database and to Storage
    python sync_avatars.py --test     # processes 5 channels, uploads and writes nothing
"""

import argparse
import sys

# Channel names can contain any Unicode character. On Windows, stdout otherwise defaults
# to the system codepage (e.g. cp1252) and crashes on anything outside it, so this must
# run before any print() call.
sys.stdout.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)
sys.stderr.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)

import requests

from config import YOUTUBE_API_KEY, supabase

YOUTUBE_CHANNELS_URL = "https://www.googleapis.com/youtube/v3/channels"
BUCKET_NAME = "channel-avatars"
BATCH_SIZE = 50
FETCH_PAGE_SIZE = 1000
DOWNLOAD_TIMEOUT_SECONDS = 10
QUOTA_COST_PER_CALL = 1
TEST_SAMPLE_SIZE = 5

THUMBNAIL_PREFERENCE = ["medium", "high", "default"]


def chunked(items, size):
    for i in range(0, len(items), size):
        yield items[i:i + size]


def fetch_channels():
    """All channels from the DB: channel_id, name. Never the spreadsheet."""
    channels = []
    start = 0
    while True:
        response = (
            supabase.table("channels")
            .select("channel_id, name")
            .order("name")
            .range(start, start + FETCH_PAGE_SIZE - 1)
            .execute()
        )
        rows = response.data
        channels.extend(rows)
        if len(rows) < FETCH_PAGE_SIZE:
            break
        start += FETCH_PAGE_SIZE
    return channels


def fetch_thumbnails(channel_ids):
    """Calls channels.list in batches of 50. Returns (channel_id -> thumbnails dict, quota_used).
    A channel_id the API doesn't recognise is simply absent from the result."""
    thumbnails_by_id = {}
    quota_used = 0

    for batch in chunked(channel_ids, BATCH_SIZE):
        response = requests.get(YOUTUBE_CHANNELS_URL, params={
            "part": "snippet",
            "id": ",".join(batch),
            "maxResults": BATCH_SIZE,
            "key": YOUTUBE_API_KEY,
        })
        response.raise_for_status()
        quota_used += QUOTA_COST_PER_CALL

        for item in response.json().get("items", []):
            thumbnails_by_id[item["id"]] = item["snippet"].get("thumbnails", {})

    return thumbnails_by_id, quota_used


def pick_thumbnail_url(thumbnails):
    for key in THUMBNAIL_PREFERENCE:
        if key in thumbnails:
            return thumbnails[key]["url"], key
    return None, None


def sync_channel(channel, thumbnails, test_mode):
    """Returns a dict describing what happened: status is 'uploaded', 'no_thumbnail', or 'failed'."""
    channel_id = channel["channel_id"]
    name = channel["name"]

    if thumbnails is None:
        return {"status": "failed", "channel": channel, "reason": "not found in API response"}

    thumbnail_url, quality = pick_thumbnail_url(thumbnails)
    if thumbnail_url is None:
        return {"status": "no_thumbnail", "channel": channel}

    try:
        response = requests.get(thumbnail_url, timeout=DOWNLOAD_TIMEOUT_SECONDS)
        if response.status_code != 200:
            return {
                "status": "failed", "channel": channel,
                "reason": f"download returned status {response.status_code}",
            }
        image_bytes = response.content
    except requests.RequestException as error:
        return {"status": "failed", "channel": channel, "reason": f"download failed: {error}"}

    storage_path = f"{channel_id}.jpg"

    if test_mode:
        return {
            "status": "would_upload", "channel": channel,
            "thumbnail_url": thumbnail_url, "quality": quality,
            "storage_path": storage_path, "image_bytes": len(image_bytes),
        }

    try:
        supabase.storage.from_(BUCKET_NAME).upload(
            storage_path, image_bytes, file_options={"content-type": "image/jpeg", "upsert": "true"}
        )
        public_url = supabase.storage.from_(BUCKET_NAME).get_public_url(storage_path)
        supabase.table("channels").update({"avatar_url": public_url}).eq("channel_id", channel_id).execute()
    except Exception as error:
        return {"status": "failed", "channel": channel, "reason": f"upload/write failed: {error}"}

    return {"status": "uploaded", "channel": channel, "public_url": public_url}


def parse_args():
    parser = argparse.ArgumentParser(description="Fetches and stores a channel avatar for every channel.")
    parser.add_argument(
        "--test",
        action="store_true",
        help="Process 5 channels and print what would happen, without uploading or writing to the database.",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    channels = fetch_channels()
    if args.test:
        channels = channels[:TEST_SAMPLE_SIZE]
        print(f"--test: processing {len(channels)} channel(s), no uploads and no database writes.\n")

    channel_ids = [c["channel_id"] for c in channels]
    thumbnails_by_id, quota_used = fetch_thumbnails(channel_ids)

    uploaded = []
    no_thumbnail = []
    failed = []

    for channel in channels:
        thumbnails = thumbnails_by_id.get(channel["channel_id"])
        result = sync_channel(channel, thumbnails, args.test)

        if result["status"] == "uploaded":
            uploaded.append(result)
            print(f"  Uploaded: {channel['name']} ({channel['channel_id']}) -> {result['public_url']}")
        elif result["status"] == "would_upload":
            uploaded.append(result)
            print(
                f"  Would upload: {channel['name']} ({channel['channel_id']}) "
                f"thumbnail={result['quality']} url={result['thumbnail_url']} "
                f"({result['image_bytes']} bytes) -> storage path {result['storage_path']} (not written)"
            )
        elif result["status"] == "no_thumbnail":
            no_thumbnail.append(result)
            print(f"  No thumbnail: {channel['name']} ({channel['channel_id']})")
        else:
            failed.append(result)
            print(f"  FAILED: {channel['name']} ({channel['channel_id']}): {result['reason']}")

    print("\n--- Summary ---")
    print(f"Channels read: {len(channels)}")
    print(f"Avatars {'that would be ' if args.test else ''}uploaded: {len(uploaded)}")
    print(f"Skipped, no thumbnail: {len(no_thumbnail)}")
    for r in no_thumbnail:
        print(f"  {r['channel']['name']} ({r['channel']['channel_id']})")
    print(f"Skipped, failed: {len(failed)}")
    for r in failed:
        print(f"  {r['channel']['name']} ({r['channel']['channel_id']}): {r['reason']}")
    print(f"Quota units used: {quota_used}")


if __name__ == "__main__":
    main()
