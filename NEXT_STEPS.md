# NEXT_STEPS.md — YouTube Endurance Tracker

Working document. Tick off what is done and add new questions as they come up.

## Open questions

- [ ] **Does "last year" work as the default date filter?** Chosen provisionally. Check once real
      data is in the database whether it gives a good first impression.

## Data issues in data/channels_complete.xlsx

- [ ] **15 channels are marked `no youtube`** and have no ID. Skip them on import.


## Build order

1. [ ] **Project setup.** Vite + React + Tailwind in `frontend/`, `.gitignore`, `.env` files for the
       front end and the ingestion, Git repository, initial commit.
2. [ ] **Supabase setup.** Create the project, create the `channels`, `videos` and `video_stats`
       tables as described in CLAUDE.md, and store the connection details in the `.env` files.
3. [ ] **Channel import script.** Read the spreadsheet from row 2, skip rows without an ID, write the
       channels into the `channels` table. Re-runnable, upsert on channel_id. Also fetch each
       channel's uploads playlist ID and subscriber count via `channels.list`.
4. [ ] **Backfill script.** For each channel, walk the uploads playlist back to the agreed window,
       fetch details in batches of 50, and store videos plus a first measurement in `video_stats`.
       Log quota usage. Test mode on 5 channels first.
5. [ ] **Refresh script.** Adds new videos and re-measures videos younger than 180 days. This is the
       script the 30-day run calls.
6. [ ] **Outlier Score.** Compute baselines per channel, split by Shorts and long-form, and expose the
       score through a database view or an API route.
7. [ ] **Era baselines.** Extend the score computation with the era baseline for mature videos,
       including the widening fallback and the edge cases at the start and end of a channel's
       history. Verify on a handful of channels that grew strongly: their old videos should no longer
       score systematically low.       
8. [ ] **Front-end: results list.** Video cards with thumbnail, title, channel,
       publication date, views, likes, comments and Outlier Score.
9. [ ] **Front-end: filters.** Keyword search on title + description, category and subcategory,
       sports, publication date, Shorts vs long-form.
10. [ ] **Deploy to Vercel** and add the environment variables there.
11. [ ] **GitHub Actions workflow.** Schedule the refresh script monthly, with the keys in GitHub
        Secrets, modelled on the Cycling Content Tracker's workflow. Trigger it manually once to
        confirm it works.
12. [ ] **Polish for the portfolio.** A short "how it works" page explaining the Outlier Score, plus a
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
