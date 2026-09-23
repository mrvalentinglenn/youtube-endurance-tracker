# NEXT_STEPS.md — YouTube Endurance Tracker

Working document. Tick off what is done and add new questions as they come up.

## Open questions

- [ ] **Does "last year" work as the default date filter?** Chosen provisionally. Check once real
      data is in the database whether it gives a good first impression.


- [ ] **A per-channel cutoff for channels onboarded later.** New-video discovery uses the fixed
      floor `BACKFILL_CUTOFF` (2023-09-19). A channel backfilled later gets a later cutoff from
      `compute_cutoff()`, so its discovery walk could reach further back than its own backfill did.
      Fixing it needs a per-channel cutoff column. Only matters once a channel is added.

- [ ] **Small refresh.py fixes.** The "pending Shorts classification" count is off by one against
      the classified total (723 vs 725, 11 vs 12); the data is fine, 0 are NULL. Avatars re-upload
      all 342 every run, about 2.5 minutes; skipping unchanged ones would shorten the run.

## Data issues in data/channels_complete.xlsx

- [x] **15 channels are marked `no youtube`** and have no ID. Skip them on import.


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
6. [x] **Refresh script — the 30-day run.** `ingestion/refresh.py`, an orchestrator over the
       existing scripts. Phase order: channels, new videos, re-measurement, Shorts check,
       baselines, avatars, checks, refresh. Baselines write only rows that changed. Hard gates stop
       the run before the refresh; avatar failures and Shorts-check aborts do not. Channels never
       backfilled are skipped and reported. RPC mode removed from `refresh_scoring_view.py`.
       First real run, 2026-09-22, found two bugs: 981 videos older than the cutoff imported from
       channels with almost no known videos, and 7,887 young videos not re-measured because
       paginated reads had no order. Fixed with a date floor (`BACKFILL_CUTOFF`, 2023-09-19) and an
       order on every paginated read; the 981 were deleted as a one-off exception. Second real run:
       20,730 re-measured + 2 no longer available = 20,732 under 180 days, 0 videos before the
       cutoff, 0 `is_short` NULL, sentinel matches. About 12 minutes, 787 quota units, refresh
       33 seconds. Database 294 MB. See DECISIONS.md, 2026-09-22.
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
7d. [x] **Shrink the database.** Carried out on Pro, 2026-09-22. `videos_scored_live` now computes
        `fts` itself; `videos.fts` dropped; 52,112 descriptions truncated to 500 characters;
        `VACUUM FULL` of `videos`, plain refresh, `ANALYZE`. `backfill.py` truncates on write.
        Database 566 → 280 MB, `videos` 273 → 66 MB, `videos_scored` 260 → 181 MB. Plain refresh
        now 38 seconds. Row counts unchanged at 98,300; keyword search verified in a real browser.
        See DECISIONS.md, 2026-09-22.             
8. [x] **Era baselines.** Extended `ingestion/compute_baselines.py` with the era baseline for mature
       videos: 6-month window centred on the video's own date, widening to 12 months, falling back to
       the current baseline, then `'insufficient'`. Done: 342/342 channels, 0 write failures, every one
       of the 98,300 videos now has a `baseline_kind` (76,404 `'era'`, 20,247 `'current'`, 1,649
       `'insufficient'`, 0 still `NULL`). See the verification finding below — real improvement, not a
       complete fix for the steepest-growth channels.
8b. [x] **Era baseline: nearest neighbours instead of most recent.** The era baseline took the 20
        *most recent* videos in its ±6-month window, which always samples the window's late end:
        FloTrack's top video, published 2024-04-01, had its baseline drawn from a single week,
        2024-09-24 to 30. Changed in `compute_baselines.py` to up to 10 nearest videos before and 10
        after, by publication date, filling from the other side when one runs short, tie-broken by
        `video_id`. The current baseline is unchanged. Old baselines snapshotted to
        `ingestion/baseline_snapshot.csv` (gitignored) and compared with
        `ingestion/compare_baselines.py`.
        Results: FloTrack's top video 2,739.7× → 1,017.5× (baseline 1,922.5 → 5,176.5).
        `baseline_kind` barely moved (era +83, current −56, insufficient −27). 50,362 of 96,643
        comparable videos' views baselines changed by more than 20%, led by event-coverage channels
        (FloTrack 89%, USA Swimming 87%, supertri, Aravaipa Running, Epic Series), whose output is
        seasonal. Castelli's oldest-quartile median score rose 0.38 → 0.59 against an unchanged
        1.14, so late-end sampling was a real cause of the residual growth bias, though not the only
        one. FloTrack's share of the default top 60 fell 11 → 8. The Feed was not checked: its
        YouTube name differs from "The Feed". View refreshed over the direct connection in 358
        seconds and verified.       
9. [x] **Front-end: results list.** `frontend/src/lib/videos.js` (`fetchVideos`), `frontend/src/
       components/VideoCard.jsx`, `frontend/src/App.jsx`. Video cards with thumbnail, title, channel,
       publication date, views, likes and comments. Outlier Score shown under Relative only. "Still
       growing" label on videos younger than 180 days, shown alongside the score. Verified in a real
       headless browser (Playwright), not just against Python/the secret key: cards render, both
       toggles work across all 6 metric/comparison combinations, sort order and top score match
       step 7b's own verification numbers exactly (TrainingPeaks, 21.6K). The intermittent timeout hit during that verification was the cold-cache problem fixed in step 7c.
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
9c. [x] **Channel avatars on the card.** Public Storage bucket `channel-avatars` created by hand. It
        is not a SQL object, so a rebuild of the project needs it recreated, or the site comes up
        with no avatars and no error. `avatar_url` added to `channels`; `ingestion/sync_avatars.py`
        fetches each thumbnail from `channels.list`, uploads it as `{channel_id}.jpg` and writes the
        public URL: 342/342 uploaded, 0 skipped, 7 quota units. Uploads must use storage3's
        `.upload()`, not `.update()`, which strips the upsert header in version 2.31.0.
        `avatar_url` appended to `videos_scored_live`; `videos_scored` rebuilt through a one-off
        `rebuild_scoring_view()` function called over RPC, since the SQL editor timed out, and the
        function dropped afterwards. A drop-and-recreate of the view loses its grants — reissue
        SELECT to `anon` and `service_role`. The card shows a small round avatar before the channel
        name, hidden when NULL or when the image fails to load.      
9d. [x] **Apply the influencer sport correction to the database.** Spreadsheet edited, import
        re-run (357 read, 15 skipped, 342 written, 0 orphans, 7 quota units), `videos_scored`
        refreshed. Verified: the five channels have `is_cycling = false` and `is_triathlon = true`
        in both `channels` and the view.             
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
10b. [x] **Front-end polish.** The paid-promotion mark is a warning triangle drawn as SVG. Score
         badges are purple by default and red when the video is flagged — by the video-level flag,
         not the displayed number. Dark mode with a header toggle, dark on a first visit,
         remembered in `localStorage`, and applied by an inline script in `index.html` before React
         renders; Tailwind 4's `dark:` variant switched to class-based. Homepage sections are
         framed: a bordered container, a centred header bar, and "Show more" inside at the bottom.
         See DECISIONS.md, 2026-09-21.
10c. [x] **Category, subcategory and channel filter.** Built as one hierarchical control rather than
         a separate channel list: five dropdowns, one per category, identical on both routes, with
         three-state checkboxes, a channel search, and a new `nochan` param. The category pills are
         gone. The tree comes from a new view, `channels_public`, granted to `anon`, which retires
         the hardcoded subcategory list. Prerequisite done first: the "Incluencer Cycling" typo fixed
         in the spreadsheet, `filters.js` and the database (27 channels, 21,887 videos). Verified in
         a real browser across six scenarios. See DECISIONS.md, 2026-09-21.     
10d. [x] **Category-page timeouts fixed.** `videos_scored` compacted from 556 to 240 MB with a plain
         refresh; the six plain sort indexes replaced by six format-first and six category-first
         ones; merged rankings fetched one category at a time and merged in the browser. The failing
         query went from 8,353 pages to 156 (about 250 ms cold), and a two-category merge from 4,204
         pages and 5.3 seconds to 339 pages. Slowest remaining: Influencers at about 800 pages,
         roughly 1.6 seconds cold — watch it as the archive grows. Selecting all four sports now
         removes the `sports` param. See DECISIONS.md, 2026-09-21.
10e. [x] **Card and filter-bar polish.** Warning triangle before the paid-promotion body line; sport
         buttons all shown active by default, with a click switching one off and the last one
         disabled; a tooltip on "still growing".
10f. [x] **Category page: one page of 180, and narrow filters fixed.** Pagination dropped: the
         category page shows 180 videos, no page controls. Measuring it exposed a live bug: narrow
         filters timed out cold at any page size (Influencers, triathlon only: 12,487 pages, a
         timeout confirmed in the browser after a fast reboot). Postgres walked the views-sorted
         index and discarded ~57 of every 58 rows; extra indexes and statistics could not make it
         choose better. Fixed by filtering on slim copies instead of the wide view, in two steps:
         step 1 collects and sorts all matching rows from a slim, category-ordered materialised view
         and takes the top ids (tie-broken by `video_id`); step 2 fetches those rows from
         `videos_scored` by id, reordered in the browser. `videos_slim` (18 MB) serves every
         non-keyword request; `videos_search` (117 MB, with `fts`) serves keyword search. Step 1 now
         costs the same whatever the filters: 441 pages for Influencers, narrow or broad. Keyword
         search runs on a Search button or Enter, never while typing; stopwords are stripped only
         from phrases of two or more words, and a word that is also a channel name ("On") is never
         stripped. "tour de france" went from 7,984 pages to 2,010. Verified: old and new routes
         return identical rankings; triathlon loads immediately cold after a reboot. Both slim views
         refresh plain, always, after `videos_scored`, with a row-count check across all three.
         Database 294 → 430 MB. See DECISIONS.md, 2026-09-22.
10g. [x] **Video duration filter.** A multi-select dropdown on `duration_seconds`: under 1 min,
         1–3, 3–20, 20–45 and 45+ min. Long-form only: hidden under Shorts, where the query ignores
         it but `nodur` stays in the URL. Videos with an unknown duration (NULL or 0) are excluded
         whenever at least one bucket is off. Applied in step 1 only. See DECISIONS.md, 2026-09-23.
10h. [x] **Slim down `videos_scored`.** 15 of its 16 indexes dropped; only the unique `video_id`
         index remains. Definitions saved in `ingestion/dropped_indexes_10h.sql`. Database
         430 → 374 MB, `videos_scored` 182 → 126 MB. Refresh of `videos_scored` 36 → 14 seconds.
         Verified in a real browser across all scenarios. The `fts` column stays: removing it
         would win about 71 MB, not needed for the planned months on the free plan. See
         DECISIONS.md, 2026-09-23.   
10i. [x] **Filter bar layout.** Rearranged into four lines on laptop and wide screens: category
         dropdowns; Sport, Published and Duration; Metric, Comparison and Format; search. Hover
         tooltips on Absolute and Relative. No filter behaviour changed.
10j. [x] **Suggest a channel.** A header button opens a modal with a channel name and a category,
         sent by email through Web3Forms. Access key in `VITE_WEB3FORMS_ACCESS_KEY`. Tested with
         intercepted requests plus one real submission. See DECISIONS.md, 2026-09-23.                         
11. [ ] **Deploy to Vercel** and add the environment variables there: `VITE_SUPABASE_URL`,
        `VITE_SUPABASE_PUBLISHABLE_KEY` and `VITE_WEB3FORMS_ACCESS_KEY`. Afterwards, in the
        Web3Forms dashboard, replace the form's website URL `localhost` with the real address,
        and send one test suggestion from the live site.
11b. [ ] **Move Supabase to the free plan.** Planned for roughly 7 to 9 months, then back to a
         paid plan. Before switching: check Supabase's current policy on pausing inactive free
         projects, since a paused database takes the site down, and check that the database
         (374 MB after step 10h) fits the free limits. After switching: note the database size
         after each monthly run, to measure the real growth.
12. [ ] **GitHub Actions workflow.** Schedule `ingestion/refresh.py` monthly, with the keys in
        GitHub Secrets, modelled on the Cycling Content Tracker's workflow. Secrets:
        `YOUTUBE_API_KEY`, the Supabase secret key, `SUPABASE_DB_URL`, and the publishable key for
        the sentinel check, which reads as `anon`. `psycopg[binary]` is in `requirements.txt`. A run takes about 14 minutes: three views are refreshed since step 10f. Trigger it manually once to confirm it works.
        Verify the Shorts HEAD check from the runner before trusting it: YouTube's consent redirect
        is regional, and GitHub's runners sit in US data centres, not in Spain. Run
        `calibrate_shorts.py` or a known-status set from the runner once, and compare.
12b. [ ] **Daily Shorts reclassify workflow.** A short script selecting videos with `is_short`
        NULL, re-running the HEAD check and writing back the result. Scheduled daily via GitHub
        Actions. Same script as backfill phase two (`ingestion/classify_shorts.py`). This is also
        what makes NULL-format videos visible in the app again: the format filter is a required
        choice, so a video with no format matches neither side and is unreachable until this job
        resolves it. See DECISIONS.md, 2026-09-20. The same runner check as step 12 applies. `fetch_pending_work()` now orders on `video_id`.
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
