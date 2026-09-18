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
| A | Channel / brand name |
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
  is_short, thumbnail_url
- `videos` also stores `baseline_views` and `baseline_kind` ("era" or "current"), computed during the
  30-day run. Storing it keeps the score stable between runs and makes it explainable in the UI.  
- `video_stats` — video_id (FK), captured_at, age_days, views, likes, comments
  (one row per measurement moment, never overwritten)

Keep the raw measurements in `video_stats` and never overwrite an older measurement: the history is
what makes growth visible later. Baselines are computed during the 30-day run and stored on the
video; the score itself is derived on read, in a view.

## Ingestion rules

**Backfill.** Import all videos of every channel published in the last 36 months. Videos older
than 36 months are not imported. Use the channel's uploads playlist via `playlistItems.list`,
then fetch details in batches of 50 with `videos.list`.

**Never use `search.list`.** It costs 100 quota units per call and returns unreliable results.
`playlistItems.list` and `videos.list` cost 1 unit per call of up to 50 items.

**Refresh cadence.** No daily or weekly job. Every 30 days, refresh the stats of videos that are
younger than 180 days. A video is therefore measured at roughly 30, 60, 90, 120, 150 and 180 days
of age. After 180 days a video is frozen: its last measurement is final. New videos published since
the previous run are added in the same job.

**Retention.** Videos are never deleted for being old. After 180 days a video is frozen, but it stays in the database and remains searchable.

**Descriptions.** Store the full video description. The front-end keyword search runs over title
plus description, so use Postgres full-text search on both fields.

**Shorts vs long-form.** Classify with the same mechanism as the Cycling Content Tracker:
duration from `videos.list` (`contentDetails.duration`, ISO 8601). Treat videos up to 3 minutes as
Shorts, longer ones as long-form. Store both `duration_seconds` and the resulting `is_short` flag,
so the rule can be changed later without refetching.

**API key handling.** The YouTube API key lives in the environment, is never logged, never printed
and never committed. Log quota usage per run so the owner can see how close a run is to the
10,000 units per day limit.

## Scoring: the Outlier Score

The score compares a video's views to the normal level of its own channel.

**Two baselines, depending on the age of the video.**

*Mature videos (older than 180 days) use an era baseline.* The median all-time views of the
channel's videos published in a window centred on the video: 6 months before to 6 months after its
publication date. If that window holds fewer than 10 mature videos of the same format, widen to 12
months before and after. If it is still under 10, the video gets no score.

*Young videos (180 days or younger) use the current baseline.* The median all-time views of the
channel's videos published between 180 days and 24 months ago. Minimum 10 videos of the same
format, otherwise no score. These videos carry the "still growing" label in the UI.

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
- Videos without a score never sort to the top; they sort last.
- Guard against a median of zero (no division by zero).
- Compute the window boundaries in UTC, so videos do not shift in and out of the window.
- A baseline is never built from videos younger than 180 days.
- The era window is anchored to the video's own publication date, never to the current date. A frozen
  video's score must not change between runs unless new videos from its era were added.
- When the window is widened from 6 to 12 months, the widening applies to both sides.
- A video at the edge of the dataset (the channel's oldest or newest videos) has a one-sided window.
  Handle this explicitly: either accept it or give no score, but never silently compare against a
  half window without noting it.

**Presentation.** Present the number as "Outlier Score", never as a percentage.

**Videos younger than 180 days are still growing.** They are compared against mature videos, so they
structurally score low. The UI must label them "still growing", so a low score is not read as
failure.


## Front-end

**No view modes.** The app has no fixed time windows like the 7-day and 90-day views of the Cycling
Content Tracker. Time is controlled entirely through the publication-date filter below.

Filters the user can combine:

1. Keyword search over title + description
2. Category and subcategory (multi-select)
3. Sport: swimming, cycling, running, triathlon (multi-select)
4. Publication date: last 6 months, last year, last 2 years, last 3 years, all time, or a custom
   period. "All time" means no date restriction on the query: everything in the database.
   Default on opening the app: last year.
5. Shorts vs long-form

Each video card shows: thumbnail, title, channel name, **publication date**, views, likes,
comments and the Outlier Score. Videos younger than 180 days carry a "still growing" label.
Clicking through opens the video on YouTube.

## Working conventions

- Explain the plan before writing code, and wait for approval on anything that changes the
  database schema or an ingestion job.
- Never write ad-hoc scripts that modify the spreadsheet in `data/`. It is read-only input.
- Ingestion scripts must be re-runnable without creating duplicates (upsert on the primary key).
- Every script gets a `--test` mode that processes a handful of channels and prints results without
  writing to the database.
- Keep `NEXT_STEPS.md` up to date: check off what is done, and add newly discovered open questions.
- Record settled decisions in `DECISIONS.md`, with the date and the reasoning, and remove the
  question from `NEXT_STEPS.md`. Never put decisions in `NEXT_STEPS.md`.
