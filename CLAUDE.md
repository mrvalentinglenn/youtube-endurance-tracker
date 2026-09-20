# CLAUDE.md — YouTube Endurance Tracker

Instructions for Claude Code working in this repository. Read this file before making changes.

## What this project is

A web app that shows which YouTube videos are performing best in the endurance sports sector
(swimming, cycling, running, triathlon). The audience is marketing teams at brands in this
sector who want inspiration and want to follow trends.

It is a successor to the Cycling Content Tracker, with a wider channel set and richer filtering.
It also serves as a portfolio project, so the code should be readable and the UI presentable.

The owner is a marketer, not a professional developer. Explain decisions in plain language,
avoid unnecessary abstraction, and prefer boring, well-documented solutions over clever ones.

## Data source

`data/channels_complete.xlsx`, sheet `Channels Youtube`. Headers are in row 1, data starts at row 2.

| Column | Meaning |
|---|---|
| A | Channel / brand name (used to recognise a row during import; NOT stored — `channels.name` comes from the API) |
| B | Website (leftover from an earlier script, not used by this app) |
| C | YouTube channel URL, or the text `no youtube` |
| D | YouTube channel ID (starts with `UC`) |
| E | Category |
| F | Subcategory |
| G | `swimming` if the channel is relevant for swimming, else empty |
| H | `cycling` if relevant for cycling, else empty |
| I | `running` if relevant for running, else empty |
| J | `triathlon` if relevant for triathlon, else empty |
| K | Leftover status column from an earlier scraper, not used by this app |

Sport columns G-J: treat any non-empty cell as true, regardless of capitalisation or stray spaces.
Never match on the exact text.

Contents: 357 channels, of which 342 have a channel ID. The 15 rows without an ID say `no youtube`
in column C and must be skipped during import.

Categories: `Brand` (170), `Influencer` (70), `Professional athlete` (48), `Professional Team` (36),
`Race Organizer` (33). Every channel has a category, a subcategory and at least one sport.

Subcategories exist per category, for example `Brand > Nutrition`, `Brand > Retailer`,
`Race Organizer > Running Races`.

**The spreadsheet is an import source, not the runtime database.** Channels live in a `channels`
table so that adding a channel is a data change, not a code change. The import script can be
re-run to add or update channels, and it must never delete videos.

## Tech stack

Same stack as the Cycling Content Tracker, so the owner stays on familiar ground:

- Vite + React 19 + React Router 7, styled with Tailwind CSS 4
- Supabase (Postgres) as the database, in a new project of its own
- Vercel for hosting, deployed as a static site with `frontend/` as the project root, and a
  `vercel.json` that rewrites all routes to `index.html` for SPA routing
- Python for the ingestion scripts (backfill and refresh)
- GitHub Actions on a schedule to run the ingestion, following the same pattern as the Cycling
  Content Tracker. Reuse that project's workflow in `.github/workflows/` as a model.

**Key handling, following the pattern of the Cycling Content Tracker.** The front end uses only the
publishable key and reads through a database view, never the tables directly. The secret key exists
only in the ingestion environment and never appears anywhere under `frontend/`.

Environment variables: `VITE_SUPABASE_URL` and `VITE_SUPABASE_PUBLISHABLE_KEY` for the front end,
read via `import.meta.env`, with an explicit error if either is missing. The ingestion scripts use
the Supabase secret key and `YOUTUBE_API_KEY`, stored in GitHub Secrets for the scheduled run and in
a local `.env` for manual runs.

`.gitignore` must exclude `.env*`, `node_modules`, `__pycache__`, and any spreadsheet working copies
other than the one in `data/`.

**Watch out: GitHub disables scheduled workflows in a repository with no activity for 60 days.**
With a monthly job this is a real risk, and the job simply goes quiet. Check once after the first
scheduled run that it actually fired, and keep it in mind after quiet periods.

## Data model (minimum)

- `channels` — channel_id (PK), name, category, subcategory, is_swimming, is_cycling, is_running,
  is_triathlon, uploads_playlist_id, subscriber_count, last_checked_at
- `videos` — video_id (PK), channel_id (FK), title, description, published_at, duration_seconds,
  is_short, thumbnail_url. `duration_seconds` and `is_short` are both nullable. `is_short` NULL
  means the Shorts check has not succeeded yet, which is distinct from false: such videos are
  excluded from both format baselines and match neither side of the Shorts vs long-form filter.
- `videos` also has a generated `fts` column (tsvector over title + description). Postgres
  maintains it; ingestion scripts never write to it.
- `videos` also stores `baseline_views`, `baseline_likes`, `baseline_comments` and `baseline_kind`
  ("era", "current" or "insufficient"), computed during the 30-day run. One `baseline_kind` covers
  all three, because the window logic is identical for each metric. Storing them keeps the score
  stable between runs and makes it explainable in the UI. When a channel has too few mature videos
  in the window, the baseline columns are NULL and `baseline_kind` is "insufficient", so that "not
  enough history" is distinguishable from "never computed".
- `video_stats` — id (identity, PK), video_id (FK), captured_at (date, not timestamp), age_days,
  views, likes, comments (one row per measurement moment, never overwritten). Unique constraint on
  (video_id, captured_at), so a re-run on the same day updates instead of duplicating.
  `captured_at` is a date precisely for that reason: with a timestamp, two runs on one day are two
  different values, the constraint never fires, and the history silently doubles.
- A video's current value for a metric is always the most recent `video_stats` row for that video,
  read on demand. `videos` deliberately holds no denormalised `latest_views` columns: a derived
  copy can silently disagree with the source, and a score computed from a stale number is
  indistinguishable from a real one. Index: `video_stats (video_id, captured_at desc)`.  

Keep the raw measurements in `video_stats` and never overwrite an older measurement: the history is
what makes growth visible later. Baselines are computed during the 30-day run and stored on the
video; the score itself is derived on read, in a view.

`likes` and `comments` are nullable. The API omits `likeCount` when a creator hides likes and
`commentCount` when comments are disabled, both common on brand channels. NULL is the honest value;
writing 0 would record a disabled feature as an absence of engagement.

Foreign keys have no cascade delete. Videos are never deleted, so a database that refuses to delete
a channel while videos reference it is the safer default.

Indexes: `videos.channel_id`, `videos.published_at`, `videos.is_short`, and a full-text index over
title plus description. Without them the filters slow down badly once the archive holds tens of
thousands of videos.

## Ingestion rules

**Backfill.** Import all videos of every channel published in the last 36 months. Videos older
than 36 months are not imported. Use the channel's uploads playlist via `playlistItems.list`,
then fetch details in batches of 50 with `videos.list`.

**Never use `search.list`.** It costs 100 quota units per call and returns unreliable results.
`playlistItems.list` and `videos.list` cost 1 unit per call of up to 50 items.

**Refresh cadence.** No daily or weekly job. Every 30 days, refresh the stats of videos that are
younger than 180 days. A video is therefore measured at roughly 30, 60, 90, 120, 150 and 180 days
of age. After 180 days a video is frozen: its last measurement is final. New videos published since
the previous run are added in the same job. The refresh also re-fetches all channels via
`channels.list` and updates `name` and `subscriber_count` (~7 quota units), so a renamed channel
corrects itself within 30 days.

**Retention.** Videos are never deleted for being old. After 180 days a video is frozen, but it stays in the database and remains searchable.

**Descriptions.** Store the full video description. The front-end keyword search runs over title
plus description, using Postgres full-text search with the `'simple'` configuration: no stemming,
no stopword removal. The channel set is multilingual, so a language-specific stemmer would apply
one language's rules to all of them. Any script that rebuilds the `fts` column must use the same
configuration.

**Shorts vs long-form.** Duration is a pre-filter, not the classification. The Cycling Content
Tracker started with duration alone and abandoned it: manual inspection found regular videos well
under three minutes on brand channels, and a correction run reclassified 42 of 90 videos per daily
run — the heuristic was wrong on nearly half of everything under 180 seconds. Brand channels publish
short product videos as ordinary uploads, and this dataset is 170 brands.

The rule:
- Longer than 180 seconds → long-form, no further check.
- 180 seconds or less → a HEAD request to `youtube.com/shorts/{video_id}` decides.
  200 means it is a Short. 303, with a `Location` header pointing at `/watch?v=`, means it is a
  regular video.

**Send no custom User-Agent on that request.** YouTube routes `/shorts/` through a regional GDPR
consent redirect and decides eligibility on the User-Agent alone. A realistic browser string sends
every request into the consent redirect, which returns 302 for Shorts and regular videos alike —
zero discriminating power, and it looks like a working script returning a consistent answer.
Non-browser clients get the real answer.

Verify the check against a set of videos of known status before running it over the table. In the
Cycling Content Tracker this cost a minute and was the only reason a naive implementation did not
confidently mislabel 3,000 rows.

A video whose HEAD check fails is stored with `is_short` NULL rather than guessed at, and the
failure is logged. The same holds for a video with no `contentDetails.duration` at all, which is
distinct from `P0D`. Retry a failed check two or three times within the same run, with a short
delay: the check hits youtube.com and not the API, so retries cost no quota, and most failures are
transient connection resets or 429s from Google's CDN. Anything still NULL afterwards is picked up
by the daily reclassify job.

Store both `duration_seconds` and the resulting `is_short` flag, so the rule can be changed later
without refetching.

**API key handling.** The YouTube API key lives in the environment, is never logged, never printed
and never committed. Log quota usage per run so the owner can see how close a run is to the
10,000 units per day limit.

## Scoring: the Outlier Score

The score compares a video's performance on the selected metric to the normal level of its own
channel. Baselines are computed and stored for all three metrics — views, likes and comments — and
the user's metric choice decides which stored column is read. That is a display choice, not a
recalculation.

**Where the computation runs.** Baselines are computed in Python during the 30-day run, not in SQL.
A readable loop that can be stepped through and checked by hand for a single channel is worth more
here than one dense statement, and the era windows in particular are awkward to express in SQL. The
view does only the division: current value over stored baseline.


**Two baselines, depending on the age of the video.**

*Mature videos (older than 180 days) use an era baseline.* The median all-time value of the selected metric of the
channel's videos published in a window centred on the video: 6 months before to 6 months after its
publication date. If that window holds fewer than 10 mature videos of the same format, widen to 12
months before and after. If it is still under 10, the fallback below applies.

*Young videos (180 days or younger) use the current baseline.* The median all-time value of the selected metric of the
channel's videos published between 180 days and 24 months ago. Minimum 10 videos of the same
format, otherwise no score. These videos carry the "still growing" label in the UI.

*Fallback.* If neither the 6-month nor the 12-month era window holds 10 mature videos of the same
format, the video is scored against the current baseline instead and `baseline_kind` records
"current". Only if that also fails does it become "insufficient". When metrics disagree,
`baseline_kind` is "era" if any metric resolved from a real era window, else "current" if any used
the fallback, else "insufficient".

**The minimum of 10 is checked per metric independently.** A channel may have 15 videos in the
baseline window but only 9 with visible like counts, because videos with hidden likes or disabled
comments are excluded from that metric's baseline rather than counted as zero. A video can therefore
have a views score and no likes score. Under a metric with no baseline it shows "no score" and sorts
last, exactly like any other unscored video.

**Baseline members are always mature.** Only videos older than 180 days at the time of computation
may be part of any baseline. Videos that are still growing would drag the median down.

**Cap of 20.** Both baselines use at most the 20 most recent videos in their window.

**Why 180 days.** Videos younger than 180 days are still accumulating views and are not a reliable
reference. Baselines are therefore built only from mature videos.

**Why a cap of 20.** High-frequency channels would otherwise have a baseline dominated by
18-month-old videos, which measures channel growth instead of video performance. Low-frequency
channels simply use every video they have in the window.

**Split by format.** Baselines are computed separately for Shorts and long-form, because their view
scales differ. Each format needs its own minimum of 10 videos.

**Fixed, not dynamic.** The baseline is computed during the 30-day run and stored. It never depends
on the filters the user selects, not on the date filter, not on the keyword search, not on category
or sport. A filter changes which videos are shown, never how they are scored.

**Hard rules to avoid known bugs:**
- A video is never part of its own baseline.
- Never compute a baseline over a filtered result set; always over the channel's full history in the
  baseline window.
- A channel without a baseline shows "no score", and is never silently dropped from the results.
- Videos without a score never sort to the top; they sort last. This only applies under Relative —
  under Absolute every video has a raw number and sorts normally.
- A median of exactly 0 is stored as 0, never discarded — it is a real fact about the channel. The
  divide-by-zero guard lives in the view: a zero baseline yields a NULL score.
- Compute the window boundaries in UTC, so videos do not shift in and out of the window.
- A baseline is never built from videos younger than 180 days.
- The era window is anchored to the video's own publication date, never to the current date. A frozen
  video's score must not change between runs unless new videos from its era were added.
- When the window is widened from 6 to 12 months, the widening applies to both sides.
- A video at the edge of the dataset has a one-sided window. This is accepted: if 10 qualifying
  videos exist, the median is computed regardless of how they sit around the video, and nothing
  flags it. The left edge is an artefact of the 36-month import boundary, not the channel's real
  history. See DECISIONS.md, 2026-09-20.
- A video with a null likes or comments count is excluded from that metric's baseline, never counted
  as zero. Postgres arithmetic propagates NULL, so such videos drop out of that ranking rather than
  appearing artificially poor.  

**Presentation.** Present the number as "Outlier Score", never as a percentage.

**Videos younger than 180 days are still growing.** They are compared against mature videos, so they
structurally score low. The UI must label them "still growing", so a low score is not read as
failure.


## Front-end

**No view modes.** The app has no fixed time windows like the 7-day and 90-day views of the Cycling
Content Tracker. Time is controlled entirely through the publication-date filter below.

Filters the user can combine:

1. Metric: views, likes or comments. Default: views.
2. Comparison: absolute or relative. Default: absolute.
3. Keyword search over title + description
4. Category and subcategory (multi-select)
5. Sport: swimming, cycling, running, triathlon (multi-select)
6. Publication date: last 6 months, last year, last 2 years, last 3 years, all time, or a custom
   period. "All time" means no date restriction on the query: everything in the database.
   Default on opening the app: last year.
7. Shorts vs long-form

Metric and Comparison together decide the sort order:

| Metric | Comparison | Sorted by |
|---|---|---|
| Views | Absolute | raw view count, highest first |
| Views | Relative | Outlier Score against the views baseline |
| Comments | Absolute | raw comment count |
| Comments | Relative | Outlier Score against the comments baseline |
| Likes | Absolute | raw like count |
| Likes | Relative | Outlier Score against the likes baseline |

Absolute answers "what got the most attention in this sector"; relative answers "what punched above
its weight". Large channels dominate the first, small channels surface in the second.

Each video card shows: thumbnail, title, channel name, **publication date**, views, likes and
comments. Under Relative it also shows the Outlier Score for the selected metric; under Absolute
no score is shown, because there is no baseline in play. Videos younger than 180 days carry a
"still growing" label. Clicking through opens the video on YouTube.

## Working conventions

- Explain the plan before writing code, and wait for approval on anything that changes the
  database schema or an ingestion job.
- Never write ad-hoc scripts that modify the spreadsheet in `data/`. It is read-only input.
- Ingestion scripts must be re-runnable without creating duplicates (upsert on the primary key).
  But a script writing only some columns of an existing row uses `.update()`, never `.upsert()`:
  Postgres checks NOT NULL on the proposed insert row before checking for a conflict, so a partial
  payload fails on `channels.videos.channel_id` even when the row already exists.
- Never write SQL that drops or recreates a table. The initial schema used `CREATE TABLE IF NOT
  EXISTS`; every change after it is a deliberate `ALTER TABLE`, shown to the owner before it runs.
- Every script gets a `--test` mode that processes a handful of channels and prints results without
  writing to the database.
- Keep `NEXT_STEPS.md` up to date: check off what is done, and add newly discovered open questions.
- Record settled decisions in `DECISIONS.md`, with the date and the reasoning, and remove the
  question from `NEXT_STEPS.md`. Never put decisions in `NEXT_STEPS.md`.
- A script writing to Supabase from multiple threads creates one client per thread via thread-local
  storage. Sharing a client across threads crashes on Windows (httpx.ReadError / WinError 10035).  

