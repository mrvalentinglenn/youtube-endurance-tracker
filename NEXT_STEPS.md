# NEXT_STEPS.md — YouTube Endurance Tracker

Working document. Tick off what is done and add new questions as they come up.

## Open questions

- [ ] **Does "last year" work as the default date filter?** Chosen provisionally. Check once real
      data is in the database whether it gives a good first impression.
- [ ] **How the backfill throttles the Shorts HEAD checks.** The Cycling Content Tracker ran ~120
      per daily run across 40 channels. Here it is 342 channels across 36 months, and on Shorts-heavy
      brand channels most videos fall under 180 seconds — plausibly tens of thousands of requests in
      one run. These cost no YouTube API quota, but that project logged two connection resets and a
      429 from Google's CDN. Decide on a delay between requests and a retry rule before the backfill
      runs.
    

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
4. [ ] **Verify the Shorts HEAD check.** Assemble a set of videos of known status — real Shorts and
       regular videos under 180 seconds, taken from brand channels — and confirm the check returns
       200 and 303 correctly, with no custom User-Agent. Do this before any classification runs over
       the table.       
5. [ ] **Backfill script.** For each channel, walk the uploads playlist back to the agreed window,
       fetch details in batches of 50, and store videos plus a first measurement in `video_stats`.
       Classify Shorts with the HEAD check on everything under 180 seconds. Log quota usage and HEAD
       request counts. Test mode on 5 channels first.
6. [ ] **Refresh script.** Adds new videos and re-measures videos younger than 180 days. Also
       re-fetches all channels via `channels.list` and updates `name` and `subscriber_count`
       (~7 quota units). This is the script the 30-day run calls.
7. [ ] **Outlier Score.** Compute baselines per channel, split by Shorts and long-form, for all three
       metrics (views, likes, comments), and expose the scores through a database view. Videos with
       null likes or comments are excluded from that metric's baseline, and the minimum of 10 is
       checked per metric independently.
8. [ ] **Era baselines.** Extend the score computation with the era baseline for mature videos,
       including the widening fallback and the edge cases at the start and end of a channel's
       history. Verify on a handful of channels that grew strongly: their old videos should no longer
       score systematically low.       
9. [ ] **Front-end: results list.** Video cards with thumbnail, title, channel, publication date,
       views, likes and comments. Outlier Score shown under Relative only. "Still growing" label on
       videos younger than 180 days.
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
        Actions. Build this only after the classification is proven working in step 4.        
13. [ ] **Polish for the portfolio.** A short "how it works" page explaining the Outlier Score, plus a
        README with screenshots.

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
