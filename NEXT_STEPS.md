# NEXT_STEPS.md — YouTube Endurance Tracker

Working document. Tick off what is done and add new questions as they come up.

## Open questions

- [ ] **Does "last year" work as the default date filter?** Chosen provisionally. Check once real
      data is in the database whether it gives a good first impression.
- [ ] **`videos_scored` intermittently times out under a plain `order by views desc`.** Found while
      verifying step 9 in a real browser (2026-09-20): a fresh load of Absolute/Views (the app's
      default state) failed roughly 1 in 3 tries with "canceling statement due to statement timeout"
      (Postgres `57014`) — the same transient error hit repeatedly during ingestion. Querying the
      underlying `videos` table directly with an equivalent filter+sort is consistently fast (under
      0.3s), which points at the view itself, likely computing all three score columns for every
      row even when only the raw `views` column is being sorted on. Not something I could fix or
      even query directly to investigate further — the secret key gets `permission denied for view
      videos_scored` (the view is granted to `anon` only, correctly), and this task's rules excluded
      any database change. Worth a look at the view's query plan before step 10 adds more query
      shapes on top of it.


## Data issues in data/channels_complete.xlsx

- [ ] **15 channels are marked `no youtube`** and have no ID. Skip them on import.


## Build order

1. [x] **Project setup.** Vite + React + Tailwind in `frontend/`, `.gitignore`, `.env` files for the
       front end and the ingestion, Git repository, initial commit.
2. [x] **Supabase setup.** Create the project, create the `channels`, `videos` and `video_stats`
       tables as described in CLAUDE.md, and store the connection details in the `.env` files.
3. [x] **Channel import script.** Read the spreadsheet from row 2, skip rows without an ID, write the
       channels into the `channels` table. Re-runnable, upsert on channel_id. Also fetch each
       channel's uploads playlist ID and subscriber count via `channels.list`.
4. [x] **Verify the Shorts HEAD check.** Assemble a set of videos of known status — real Shorts and
       regular videos under 180 seconds, taken from brand channels — and confirm the check returns
       200 and 303 correctly, with no custom User-Agent. Do this before any classification runs over
       the table.       
5. [x] **Backfill, phase one.** For each channel, walk the uploads playlist back to the agreed
       window, fetch details in batches of 50, and store videos plus a first measurement in
       `video_stats`. YouTube API work only, no HEAD checks (see DECISIONS.md, 2026-09-19, "The
       backfill runs in two phases"). Done: 342/342 channels, 98,300 videos written, 0 failures.
       62,215 videos left with `is_short` NULL for phase two.
5b. [x] **Backfill, phase two.** Walk the videos with `is_short` NULL and classify them with the
       Shorts HEAD check verified in step 4. Same script as the daily reclassify job (step 12b), so
       it is written once (`ingestion/classify_shorts.py`). Throttling settled at concurrency 20, no
       delay (see DECISIONS.md, 2026-09-20). Done: 62,215/62,215 classified, 48,925 Shorts / 49,375
       long-form total in the database, 0 left NULL, 0 request failures, 0 429s, no drift-guard trip.
6. [ ] **Refresh script.** Adds new videos and re-measures videos younger than 180 days. Also
       re-fetches all channels via `channels.list` and updates `name` and `subscriber_count`
       (~7 quota units). This is the script the 30-day run calls.
7. [x] **Outlier Score, current baseline.** Compute the current baseline per channel, split by
       Shorts and long-form, for all three metrics (views, likes, comments) — `ingestion/
       compute_baselines.py`. Videos with null likes or comments are excluded from that metric's
       baseline, and the minimum of 10 is checked per metric independently. Scope: current baseline
       only (videos 180 days old or younger); era baselines are step 8. Done: 342/342 channels,
       20,687 videos updated (19,964 `'current'`, 723 `'insufficient'`), 77,613 left `NULL` for step 8.
7b. [x] **Outlier Score, database view.** `public.videos_scored`, granted to `anon`. Joins each
        video to its latest `video_stats` row via `DISTINCT ON`, exposes all three scores
        (current ÷ stored baseline, `nullif(baseline, 0)` as the divide-by-zero guard),
        plus filter fields, `fts` and `is_still_growing`. Left at `security_invoker = false`
        deliberately: the tables have RLS on with no policies, so the view is the only read path.
        Verified: 98,300 rows (no duplication, no drops), 0 videos scored despite
        `baseline_kind = 'insufficient'`, ordering logic tested against a synthetic multi-row
        dataset since no video has a second measurement yet. Top score 21,553.9 (TrainingPeaks,
        9.05M views against a baseline of 420) — real, not a corrupt baseline.
8. [x] **Era baselines.** Extended `ingestion/compute_baselines.py` with the era baseline for mature
       videos: 6-month window centred on the video's own date, widening to 12 months, falling back to
       the current baseline, then `'insufficient'`. Done: 342/342 channels, 0 write failures, every one
       of the 98,300 videos now has a `baseline_kind` (76,404 `'era'`, 20,247 `'current'`, 1,649
       `'insufficient'`, 0 still `NULL`). See the verification finding below — real improvement, not a
       complete fix for the steepest-growth channels.
9. [x] **Front-end: results list.** `frontend/src/lib/videos.js` (`fetchVideos`), `frontend/src/
       components/VideoCard.jsx`, `frontend/src/App.jsx`. Video cards with thumbnail, title, channel,
       publication date, views, likes and comments. Outlier Score shown under Relative only. "Still
       growing" label on videos younger than 180 days, shown alongside the score. Verified in a real
       headless browser (Playwright), not just against Python/the secret key: cards render, both
       toggles work across all 6 metric/comparison combinations, sort order and top score match
       step 7b's own verification numbers exactly (TrainingPeaks, 21.6K). See the open question below
       about an intermittent database error hit during that verification.
9a. [ ] **Card layout and score formatting.** Outlier Score in a badge on the top left of the
        thumbnail, "still growing" as a badge on the top right, icons for views/comments/likes,
        4 cards per row, thumbnail aspect ratio and breakpoints taken from the Cycling Content
        Tracker. Scores below 1,000 show one decimal (1.2, 27.4); from 1,000 up they are
        abbreviated (2,447.8 becomes 2.4K). See DECISIONS.md, 2026-09-20.
9b. [ ] **Paid-promotion note.** A video on a `Brand` channel with an Outlier Score of 500 or
        higher: red score badge with an exclamation mark, tooltip "Extreme outlier scores may
        indicate this video was used for paid advertising.", and a line in the card body below the
        counts reading "Metrics on this video may reflect paid advertising rather than organic
        reach." No other category gets this. See DECISIONS.md, 2026-09-20.
9c. [ ] **Card restyling.** Move the Outlier Score to a badge on the top left of the thumbnail,
        "still growing" to a badge on the top right, icons for views/comments/likes, 4 cards per
        row, and the thumbnail aspect ratio and breakpoints taken from the Cycling Content Tracker.
        See DECISIONS.md, 2026-09-20.        
10. [ ] **Front-end: filters.** Metric (views/likes/comments) and Comparison (absolute/relative),
        keyword search on title + description, category and subcategory, sports, publication date,
        Shorts vs long-form. Metric and Comparison together decide the sort order.
       sports, publication date, Shorts vs long-form.
11. [ ] **Deploy to Vercel** and add the environment variables there.
12. [ ] **GitHub Actions workflow.** Schedule the refresh script monthly, with the keys in GitHub
        Secrets, modelled on the Cycling Content Tracker's workflow. Trigger it manually once to
        confirm it works.
12b. [ ] **Daily Shorts reclassify workflow.** A short script selecting videos with `is_short`
        NULL, re-running the HEAD check and writing back the result. Scheduled daily via GitHub
        Actions. Same script as backfill phase two (`ingestion/classify_shorts.py`). This is also
        what makes NULL-format videos visible in the app again: the format filter is a required
        choice, so a video with no format matches neither side and is unreachable until this job
        resolves it. See DECISIONS.md, 2026-09-20.
13. [ ] **Polish for the portfolio.** A short "how it works" page explaining the Outlier Score —
        including the known limitation that on channels which grew explosively, older videos still
        score somewhat low — plus a README with screenshots.

## Ideas for later

- Transcript summaries per video.
- Saving or exporting a selection of videos.
- Sending a monthly email with the biggest outliers, via n8n.
- **Age correction via a maturation curve.** Once the 30/60/90/120/150/180-day measurements have run
  for a year, compute per format and category what share of the 180-day total is reached at each
  age. A young video's views can then be scaled up to an expected mature level before being compared
  to the baseline. This is not possible for backfilled videos, which only have one measurement, but
  it works for everything published from now on. This is the fix that would make the score fair
  across ages.
- **"Compare within selected period" as a secondary score.** A dynamic baseline over the selected
  date range, shown next to the fixed Outlier Score and clearly labelled as a different comparison.
  Only available when a channel has enough videos in the window.
