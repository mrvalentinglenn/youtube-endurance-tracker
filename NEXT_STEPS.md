# NEXT_STEPS.md — YouTube Endurance Tracker

Working document. Tick off what is done and add new questions as they come up.

## Open questions

- [ ] **Does "last year" work as the default date filter?** Chosen provisionally. Check once real
      data is in the database whether it gives a good first impression.
- [ ] **`videos_scored` is too slow on a cold cache.** Measured 2026-09-20 with `explain analyze`
      on the app's default query (Views, Absolute, last year, 60 rows): 7,255ms on a cold run,
      370ms warm, then 3,780ms again on a later run that would not warm up. `anon` has a 3-second
      statement timeout, so a visitor arriving when the cache is cold gets a failure — which is
      precisely the case of someone opening the link for the first time. The cost is reading rows
      from `videos`: about 6,500 heap blocks for 18,136 rows, 2.5s of the total. The `DISTINCT ON`
      over all 98,300 `video_stats` rows adds a further 1s, and the merge sort spills to disk.
      Dropping `fts` from the view was tested and made no measurable difference; it has been
      restored. Real options are a materialised view with its own indexes (what the Cycling Content
      Tracker did, for the same reason), or denormalising the latest stats onto `videos` to remove
      the join. Both are decisions with trade-offs — see DECISIONS.md, 2026-09-20, which argues
      against a denormalised copy. Do this before step 10 adds more query shapes.


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
       (~7 quota units). This is the script the 30-day run calls. Refreshes `videos_scored` as its final step, after its own checks pass; a failed refresh
        fails the run. See DECISIONS.md, 2026-09-20.
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
7c. [x] **Materialise `videos_scored`.** Renamed the live view to `videos_scored_live` (SELECT
        revoked from `anon`, so there is one read path), created `videos_scored` as a materialised
        view over it, added ten indexes: unique on `video_id`, six sort columns `desc nulls last`,
        `published_at`, `is_short`, and GIN on `fts`. Measured on the app's default query: 0.885ms
        against 7,255ms cold and 370ms warm — an index scan on `videos_scored_views_idx` that reads
        218 entries and stops, with no join, no `DISTINCT ON` and no sort. Cold versus warm is no
        longer a distinction: the query reads index pages, not 52MB of heap. 98,300 rows in both
        objects. Verified in the browser after an idle period.        
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
9a. [x] **Card layout and score formatting.** Outlier Score in a badge on the top left of the
        thumbnail, "still growing" as a badge on the top right (shown under both Absolute and
        Relative), duration badge bottom-right (`M:SS` / `H:MM:SS`, absent on NULL or 0), positional
        rank above the thumbnail, icons for views/comments/likes, long-form grid 1/2/3/4 and Shorts
        3/4/5 by breakpoint (Shorts column set built but unreachable until step 10, per the hardcoded
        format filter), `w-full` + aspect-ratio classes, no fixed card width. Scores: one decimal with
        an explicit `×` (1.2×, 27.4×), abbreviated with `K` from 1,000 up (2,447.8 → 2.4K×). See
        DECISIONS.md, 2026-09-20. Verified in a real browser: an 11:55:01 video renders `11:55:01`
        (confirms the `H:MM:SS` path — DECISIONS.md's "just under 12 hours" case), no overlap or
        clipping at any breakpoint checked.
9b. [x] **Paid-promotion note.** A video on a `Brand` channel is flagged when *any* of
        `score_views`, `score_likes` or `score_comments` is 500 or higher (not views alone — see
        DECISIONS.md, 2026-09-20, "The paid-promotion trigger reads all three score columns"): red
        score badge with an exclamation mark (exclamation alone under Absolute, since no score is
        shown there), tooltip "Extreme outlier scores may indicate this video was used for paid
        advertising.", and a body line below the counts reading "Metrics on this video may reflect
        paid advertising rather than organic reach." Both the badge and body line are always visible,
        not hover-only. No other category gets this. Verified against two of DECISIONS.md's own
        celebrity-campaign examples (adidas "Backyard Legends", La Sportiva "Exodia") flagged via
        likes/comments while their views score sits under 500, staying flagged and red across every
        metric toggle including Absolute.
9c. [ ] **Channel avatars on the card.** A small round channel logo beside the channel name. Needs
        an `avatar_url` column on `channels`, the ingestion scripts fetching it from
        `channels.list`, and the images served from a Supabase Storage bucket rather than hotlinked
        — the Cycling Content Tracker hotlinked Google's CDN first and hit 429s. A Storage bucket is
        not a SQL object, so it lives outside the repo and a rebuild needs it created by hand, or
        the site comes up with no avatars and no error. Cards must render without an avatar
        regardless, since a newly added channel has none until the next refresh.        
9d. [ ] **Apply the influencer sport correction to the database.** The spreadsheet edit is done
        (DECISIONS.md, 2026-09-20). Re-run `ingestion/import_channels.py` so the five channels'
        `is_cycling` flag updates in the `channels` table, then
        `refresh materialized view concurrently public.videos_scored;` so the app sees it. Verify
        with a query that the five channels have `is_cycling = false` and `is_triathlon = true` in
        both the table and the view.              
10. [ ] **Front-end: routes and filters.** Two routes: `/` with one section per category in fixed
        order (Brands, Influencers, Professional Athletes, Professional Teams, Race Organizers),
        each showing that category's top videos and a "Show more" button; and `/category/:category`
        with that category's full ranking, 60 videos. Filters: metric, comparison, keyword search on
        title + description, category (controls which sections appear), subcategory (filters within
        sections, grouped by category), sport (global, matches on at least one), publication date,
        and format. The filter bar is active on both routes and carries through "Show more". See
        DECISIONS.md, 2026-09-20.

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
