# NEXT_STEPS.md — YouTube Endurance Tracker

Working document. Tick off what is done and add new questions as they come up.

## Open questions

- [ ] **Does "last year" work as the default date filter?** Chosen provisionally. Check once real
      data is in the database whether it gives a good first impression.
- [ ] **`"Incluencer Cycling"` is a typo in `data/channels_complete.xlsx`, column F.** Found while
      building step 10's subcategory filter (2026-09-20): every other Influencer subcategory reads
      "Influencer ___" (Running, Swimming, Triathlon); Cycling alone reads "Incluencer Cycling". The
      front end now hardcodes this exact string in `frontend/src/lib/filters.js` because it must
      match the database, which makes the misspelling visible in the subcategory filter's checkbox
      label. Fixing it means the same kind of one-off spreadsheet edit as the triathlon-tagging fix
      earlier (channels.subcategory in the DB, then the front end's hardcoded string, then a
      re-import) — flagging rather than doing it, since the spreadsheet is read-only input.
- [ ] **Database is over the Free Plan size limit.** Measured 2026-09-21: 0.65 GB against a 0.5 GB
      per-project limit. Breakdown at the time: `videos` 329 MB, `videos_scored` 244 MB including
      its indexes, `video_stats` 21 MB, `channels` 200 kB. The 56 MB GIN index on `videos.fts` was
      unused since step 7c and has been dropped, bringing the total to roughly 0.59 GB. The main
      remaining cause is `fts` stored twice — on `videos` and inside the materialised view — plus
      long descriptions feeding it. The archive grows ~18 MB a month by design, since videos are
      never deleted.
      **Plan: shrink the database first (step 7d), which should reach ~320 MB and buy a year or
      more on the free tier. Upgrading to Supabase Pro ($25/month) remains the fallback if the
      measurements after 7d come in higher, or if growth outpaces them.** No grace-period notice
      received yet in email or the dashboard as of 2026-09-21 — check both regularly until 7d is
      done. When restrictions apply, every request returns 402, so the front end goes down as well
      as ingestion, and community reports suggest it can affect every project in the organisation,
      including the live Cycling Content Tracker. Cleaning up afterwards has not reliably lifted
      restrictions without a support ticket.

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
        fails the run.         Must raise its own HTTP read timeout above 60 seconds before calling
        `refresh_scoring_view()` — the refresh takes over a minute, and the default client timeout
        reports a failure on a run that succeeded. See DECISIONS.md, 2026-09-20.
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
7d. [ ] **Shrink the database to stay on the free tier.** Measured 2026-09-21 on a 10% sample:
        truncating descriptions to 500 characters takes them from ~62 MB to ~36 MB, and `fts` —
        built from the description and stored twice — from ~115 MB to ~68 MB per copy. Two parts:
        (1) truncate every description to 500 characters, (2) remove the duplicate `fts` from
        `videos`, keeping only the copy in the materialised view. Estimated total ~320 MB, against
        ~540 MB today and a 500 MB limit. Median description is 535 characters, p90 1,649 — the
        tail is mostly sponsor links, timestamps and social handles.
        **Do this before step 6**, which must truncate descriptions on write or the archive fills
        back up. Needs a direct database connection: an update writes new row versions, so the
        table grows before it shrinks, and only `VACUUM FULL` reclaims the space — which cannot
        run inside a function, so the RPC route used elsewhere does not work. Changes CLAUDE.md's
        "Store the full video description" rule; record the decision in DECISIONS.md first.
        Reversible: descriptions can be re-fetched from the API for ~2,000 quota units.              
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
9d. [x] **Apply the influencer sport correction to the database.** The spreadsheet edit is done
        (DECISIONS.md, 2026-09-20). Re-run `ingestion/import_channels.py` so the five channels'
        `is_cycling` flag updates in the `channels` table, then
        `refresh materialized view concurrently public.videos_scored;` so the app sees it. Verify
        with a query that the five channels have `is_cycling = false` and `is_triathlon = true` in
        both the table and the view.              
10. [x] **Front-end: routes and filters.** `react-router-dom` v7 added. `frontend/src/lib/filters.js`
        (the single-sourced category mapping, subcategory taxonomy, sport/date definitions,
        `DEFAULT_FILTERS`, `resolveFilters`), `frontend/src/lib/videos.js` (one shared `fetchVideos`
        for both routes), `frontend/src/components/{VideoGrid,CategorySection,CategoryPills,
        FilterBar,HomeCategoryToggles}.jsx`, `frontend/src/pages/{HomePage,CategoryPage}.jsx`.
        `VideoCard.jsx` untouched, as expected.

        Subcategory collision check: none — 22 distinct subcategory names across the 5 categories,
        all unique, so `nosub` stores bare subcategory strings rather than a qualified
        `category > subcategory` key. One data quirk found along the way, not fixed: the Influencer
        > Cycling subcategory is spelled `"Incluencer Cycling"` in the source data; used as-is since
        the front end must match the database exactly.

        Two gaps in the original spec, resolved and flagged rather than guessed at: the homepage's
        category selection had no listed param, added as `nocat` (deselected slugs, mirroring
        `nosub`'s pattern exactly); "a custom period" had no param names, added as `from`/`to`
        (ISO UTC dates, two native date inputs shown only when `date=custom`).

        Verified in a real browser (not Python — the secret key has no grant on `videos_scored` at
        all): all 5 homepage sections render and fetch independently; "Show more" carries filters
        correctly; category pills add/remove and the last one is genuinely non-interactive; a
        13-param URL (category pair + 7 filters including a sport pair and a subcategory exclusion)
        fully reconstructs from one fresh navigation; the sport filter's "at least one" semantics
        confirmed three ways (swimming-only on a cycling+triathlon channel → 0 results; that
        channel's own sports selected → 60; cycling deselected, triathlon kept → still 60); a
        subcategory exclusion removed exactly the expected channels (AG1, Maurten, NAMEDSPORT) and
        nothing else; the search box's debounce collapsed an entire typed phrase into one history
        entry (replace) while Clear added a new one (push), confirmed by walking `window.history`
        directly, not just watching the URL bar; Shorts format renders a real 9:16 grid. Zero
        console errors and zero `57014`s across the whole session — the materialised view (step 7c)
        holding under real query variety, not just the one shape it was measured against.

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
