# DECISIONS.md — YouTube Endurance Tracker

A log of settled decisions, newest at the bottom. Each entry records what was decided and why, so
the reasoning is still available months from now. Once a question is answered, it moves out of
NEXT_STEPS.md and lands here.

Entries are chronological. A heading starting with "Rejected:" records an option that was
considered and dropped, with the reasoning, so it does not get proposed again. A heading starting
with "SUPERSEDED:" records a decision that was later replaced; it is kept for its reasoning and must
not be implemented. The replacement is named in the first line of the entry.

---

## 2026-09-18 — Backfill window: 36 months

**Decision.** The initial backfill imports all videos published in the last 36 months. Videos older
than that are not imported.

**Why.** Three years gives enough history for trend analysis without inflating the first run. With
`playlistItems.list` at 1 quota unit per 50 videos, the extra cost over a shorter window is
negligible.

## 2026-09-18 — SUPERSEDED: Outlier Score baseline stays at 24 months

**Superseded on 2026-09-18** by "Baseline window: 180 days to 24 months" and "Baseline sample: all
videos in the window, capped at 20, minimum 10". Kept for the reasoning; do not implement this.

## 2026-09-18 — Videos are never deleted for being old

**Decision.** Nothing is removed from the database because of its age. After 180 days a video is
frozen, meaning it gets no new measurements, but it stays stored and searchable.

**Why.** The 36-month window is a one-off boundary at import time, not a moving window. The archive
therefore keeps growing: a year from now it holds four years of videos, and in three years, six.

## 2026-09-18 — Date filter options

**Decision.** The publication-date filter offers: last 6 months, last year, last 2 years, last 3
years, all time, or a custom period. "All time" means no date restriction on the query.

**Why.** Because the archive keeps growing, "all time" really does keep reaching further back, so it
is an honest label rather than a synonym for the backfill window.

## 2026-09-18 — Videos are frozen at 180 days, not 150

**Decision.** Stats are refreshed every 30 days for videos younger than 180 days, so measurements
land at roughly 30, 60, 90, 120, 150 and 180 days. After 180 days a video is frozen.

**Why.** Working assumption: after 180 days most videos have around 95% of their eventual views.
The extra measurement costs almost no quota and makes the cutoff line up with the baseline window.
This is an estimate, not a measured fact, and evergreen videos are the exception: for those, 180
days may be closer to 60% of their eventual total.

## 2026-09-18 — Baseline window: 180 days to 24 months

**Decision.** The baseline is the median views of a channel's videos published between 180 days and
24 months ago, instead of between 30 days and 24 months.

**Why.** Videos younger than 180 days are still accumulating views, which makes them an unreliable
reference.

## 2026-09-18 — Baseline sample: all videos in the window, capped at 20, minimum 10

**Decision.** Use every video in the baseline window, but at most the 20 most recent. A channel
needs at least 10 videos in the window, per format, to get a baseline.

**Why.** Channels differ hugely in output. Without a cap, a high-frequency channel's baseline is
dominated by 18-month-old videos, so the score would mainly measure channel growth. With a strict
last-15 rule, low-frequency channels would throw away usable data. The cap gives both groups a
baseline that reflects their current level. Twenty is slightly more stable than fifteen, which
matters because Shorts and long-form each need their own baseline.

## 2026-09-18 — The baseline is fixed, not dependent on the filters

**Decision.** The Outlier Score is computed against a stored baseline. Filters chosen by the user
change which videos are shown, never how they are scored.

**Why.** A dynamic baseline would make the same video score differently in different filters, so the
number could not be quoted or bookmarked. It would also break down on small samples: a narrow custom
period can leave a channel with three videos, where a median is noise. A dynamic comparison remains
possible later as a clearly labelled secondary view.

## 2026-09-18 — No estimated watch time

**Decision.** Estimated watch time (views × duration) is not part of this app. Removed from
CLAUDE.md.

**Why.** It was carried over from the Cycling Content Tracker. Real watch time is not available via
the API for channels you don't own, so the metric could only ever be an estimate, and it adds a
number that needs explaining without adding a signal the Outlier Score doesn't already give.

## 2026-09-18 — Rejected: dynamic baseline dependent on the date filter

**Rejected.** Computing the baseline over the period the user selected, so the median follows the
date filter.

**Why not.** The same video would score differently in different filters, so the number could not be
quoted or bookmarked. On narrow custom periods a channel can have three videos in the window, where
a median is noise, and with one video the score is 1.0 by construction. A dynamic comparison stays
possible later as a clearly labelled secondary view, next to the fixed score.

## 2026-09-18 — Era baseline: videos are scored against their own period

**Decision.** A video older than 180 days is scored against the median all-time views of its own
channel's videos published in a window centred on that video: 6 months before to 6 months after its
publication date. If that window holds fewer than 10 mature videos of the same format, widen to 12
months before and after. If it is still under 10, the video gets no score. The cap of the 20 most
recent videos in the window still applies, and the video is never part of its own baseline.

Videos younger than 180 days have no era of mature videos yet. They keep using the fixed baseline
(180 days to 24 months) and carry the "still growing" label.

**Why.** With a single fixed baseline, every video older than 24 months is compared against a period
it was not part of. A channel that grew makes all its older videos look like flops; a channel that
shrank makes them look like outliers. The score then measures the channel's trajectory instead of
the video's performance. Comparing a video to its contemporaries removes channel growth from the
score.

**Why centred on the video and not a calendar year.** A calendar year would compare a January video
mostly against videos published after it, which have had less time to accumulate, so it scores
structurally high, while a December video scores structurally low. It also creates a hard edge:
videos a week apart on either side of New Year land in different buckets. A centred window has
roughly as many older as younger neighbours, so the age effect largely cancels out.

**Why not anchored to today.** Anchoring the window to the current date reintroduces the reference
point the era baseline is meant to remove, and a 2025 video's baseline would then shift with every
run.

**Rejected alternative: scoring against the subscriber count at the time of publication.** The API
only returns today's subscriber count, so the history does not exist.

## 2026-09-18 — A separate Supabase project

**Decision.** The app gets its own new Supabase project, not the one used by the Cycling Content
Tracker.

**Why.** Keeps the two apps independent: a schema change or a mistake in one cannot affect the
other.

## 2026-09-18 — SUPERSEDED: The 30-day run is scheduled, via a daily cron with chunking

**Superseded on 2026-09-18** by "The 30-day run is scheduled via GitHub Actions", after it turned
out the front end is a static Vite site with no serverless functions. Kept for the reasoning; do not
implement this.



## 2026-09-18 — Same stack as the Cycling Content Tracker

**Decision.** Vite + React 19 + React Router 7 with Tailwind 4, Supabase as the database, deployed
to Vercel as a static site with `frontend/` as the project root, and Python for the ingestion.

**Why.** Familiar ground, and the front end needs no server: it reads from Supabase through a view
with the publishable key.

## 2026-09-18 — The 30-day run is scheduled via GitHub Actions

**Decision.** The refresh runs automatically through a scheduled GitHub Actions workflow that
executes the Python ingestion script. Supabase credentials and the YouTube API key live in GitHub
Secrets. The Cycling Content Tracker uses the same setup, and its workflow serves as the template.

**Why.** The front end is a static Vite site on Vercel, so there are no serverless functions to host
a Vercel cron job. GitHub Actions has no practical runtime limit, so all 342 channels are handled in
one pass without chunking, and the data pipeline stays independent of the website deployment.

**Requirements.** The workflow logs how many channels were processed and how much API quota was
used, and a failed run must be visible. Never print the keys. Note that GitHub disables scheduled
workflows in a repository that has seen no activity for 60 days.

## 2026-09-18 — No view modes, only a date filter

**Decision.** The concept of a view mode disappears. The Cycling Content Tracker had a 7-day and a
90-day view; this app has neither. Time is controlled solely through the publication-date filter,
which opens on "last year" by default.

**Why.** A view mode made sense when the app only tracked a rolling 90-day window. With a 36-month
archive that keeps growing, a fixed window next to a date filter would be two controls for the same
thing.

## 2026-09-18 — Rejected: comparing videos at a comparable age

**Rejected.** Scoring a video on its views at 30 days against the channel's median views at 30 days,
which would remove the age advantage from the score entirely.

**Why not.** For the 36 months of backfilled videos, only today's total is available. The API does
not give historical view counts, so there is no way to know what a 2024 video had at 30 days.
Waiting for this data to build up would take years. The era baseline solves the same problem in a
different way, by comparing videos with their contemporaries. The age-based approach remains
possible later for videos published from now on, once the maturation curve exists.


## 2026-09-18 — Baselines for all three metrics; the metric toggle selects a stored column

**Decision.** `videos` stores `baseline_views`, `baseline_likes` and `baseline_comments`, plus a
single `baseline_kind` covering all three. The user picks a metric in the filter bar (views, likes
or comments) and the Outlier Score is then computed against that metric's baseline.

**Why one `baseline_kind` and not three.** The era-versus-current choice depends on the video's age,
not on the metric, so the window logic is identical for all three. Three copies of the same value
would be three things that can disagree.

**Why store all three rather than compute on demand.** They come from the same `videos.list`
response and the same window logic, so the marginal cost is three columns instead of one. Computing
a baseline at read time would make it depend on user input, which the fixed-baseline decision
rules out.

**The minimum of 10 is checked per metric independently.** A channel can have 15 videos in the
window but only 9 with visible like counts. A video may therefore have a views score and no likes
score, and under that metric it shows "no score" and sorts last.

**Rejected: one combined engagement score.** Likes and comments track views closely, so a separate
like-outlier would mostly repeat what the views score already said — three numbers on a card, all
saying the same thing, with the user left to work out why they differ slightly. The metric toggle
avoids this by only ever showing one.

## 2026-09-18 — Metric and Comparison are two controls that combine

**Decision.** Metric (views / likes / comments) and Comparison (absolute / relative) are separate
filters, following the Cycling Content Tracker's filter bar. Together they decide the sort:
absolute sorts on the raw count of the selected metric, relative sorts on the Outlier Score against
that metric's baseline. Defaults are views and absolute.

**Why both.** They answer different questions. Absolute is "what got the most attention in this
sector", which large channels dominate by construction. Relative is "what punched above its weight",
where a small channel's breakout video surfaces. A marketer wants both, at different moments.

**Consequence for unscored videos.** The "sorts last, never dropped" rule only bites under Relative.
Under Absolute every video has a raw number, so nothing sorts anomalously and nothing needs a
fallback.

**Consequence for the card.** The Outlier Score is shown under Relative only. Under Absolute there
is no baseline in play, so a score on the card would be qualifying a number that is not on screen.

## 2026-09-18 — Videos with hidden likes or disabled comments are excluded from that metric's baseline

**Decision.** The YouTube API omits `likeCount` when a creator hides likes and `commentCount` when
comments are disabled. Both are stored as NULL, and such videos are left out of that metric's
baseline rather than counted as zero. They still appear in the results and still have a views score.

**Why not zero.** Zero records a disabled feature as an absence of engagement. It would drag the
median down for every other video on that channel and make the video itself look like a failure
when nothing was measured at all.

**Why this matters more here than it looks.** Hidden likes are common on brand product launches,
and this dataset is 170 brands. Postgres arithmetic propagates NULL, so such videos drop out of a
likes ranking rather than appearing at the bottom of it.

## 2026-09-18 — Shorts classification: duration is a pre-filter, the HEAD check decides

**Decision.** Videos longer than 180 seconds are long-form with no further check. Videos of 180
seconds or less get a HEAD request to `youtube.com/shorts/{video_id}`: 200 means Short, 303 with a
`Location` pointing at `/watch?v=` means regular video. This corrects CLAUDE.md, which specified
duration alone.

**Why.** The Cycling Content Tracker started with duration alone on the basis that it was ~95%
accurate, and reversed it on 2026-08-19 after manual inspection found regular videos well under
three minutes on Red Bull Bike and Decathlon — on Decathlon, roughly one in four of those was under
60 seconds. There is no duration floor that separates the two. Measured impact there: 42 of 90
videos reclassified per daily run, and 375 of 1,982 existing Shorts rows corrected. The figure does
not hold for brand channels that publish short product videos as ordinary uploads, and this dataset
is 170 brands against that project's smaller set.

**Why it is not cosmetic.** `is_short` splits every baseline. A regular video filed as a Short is
measured against the wrong median and pollutes both pools.

**Send no custom User-Agent.** YouTube routes `/shorts/` through a regional GDPR consent redirect
and decides eligibility on the User-Agent alone. A realistic Chrome string — the obvious thing to
send, on the reasoning that it would be treated more normally — funnels every request into the
consent redirect and returns 302 for everything, with zero discriminating power. It looks like a
working script returning a consistent answer. Non-browser clients get the real answer.

**Verify before trusting it.** The check is validated against a set of videos of known status before
it runs over the table. In the Cycling Content Tracker this cost a minute and was the only reason a
naive implementation did not confidently mislabel 3,000 rows.

**Failures are skipped, not guessed.** A failed HEAD check, and a video with no
`contentDetails.duration` at all (distinct from `P0D`), both take the skip path and are logged.

## 2026-09-18 — Rejected: comments-per-view as an engagement-rate signal

**Rejected.** A secondary metric of comments or likes per 1,000 views, measuring how hard a video
landed relative to its reach rather than how far it reached.

**Why not.** Genuinely a different signal from the views score, and declined as scope rather than as
a bad idea. The metric toggle already gives the user three views of the data, and a fourth number
with its own interpretation rules is more to explain on a card that is already carrying a score, a
"still growing" label and four counts.

## 2026-09-19 — A failed Shorts check stores the video with is_short NULL

**Decision.** A video whose HEAD check fails is written to the database with `is_short` NULL,
not omitted. It appears in the results, is excluded from both the Shorts and the long-form
baseline, and is retried later. `is_short` is therefore a nullable column.

**Why.** Omitting the video means refetching and re-checking it on every run, at quota cost,
and a video that consistently fails would never enter the archive at all. NULL records "format
unknown" honestly, and gives a retry job something to find: the work queue is simply
`is_short IS NULL`, which needs no extra columns.

**Consequence for the UI.** These videos match neither side of the Shorts vs long-form filter.
They are visible only when that filter is off.

## 2026-09-19 — Retrying a failed Shorts check: in-run, plus a daily job

**Decision.** Two layers. The ingestion scripts retry a failed HEAD check two or three times
within the same run, with a short delay. Whatever still fails is picked up by a separate daily
GitHub Actions workflow that selects videos with `is_short` NULL and re-checks them.

**Why.** The HEAD check hits youtube.com, not the API, so a retry costs no quota. Most failures
are transient — connection resets and 429s from Google's CDN, both seen in the Cycling Content
Tracker. Waiting 30 days for the next refresh to correct a transient failure is unnecessary.

**Not done for now.** No attempt counter. A permanently failing video is retried daily forever;
with a small set that is harmless. Add a counter only if it becomes a real problem.

## 2026-09-19 — Full-text search uses the 'simple' configuration

**Decision.** The `videos.fts` generated column uses `to_tsvector('simple', title || description)`.
No stemming, no stopword removal.

**Why.** One configuration has to serve all channels, and the set publishes in English, Spanish,
German, Dutch, French and Italian. English stemming would apply English rules to words that do not
fit them. Marketers search for brand, product and race names, which are exactly the words a stemmer
handles worst. The cost is that "running" does not match "run".

**Reversible.** Changing it means rebuilding one generated column and its GIN index.

## 2026-09-19 — video_stats.captured_at is a date, not a timestamp

**Decision.** `captured_at` is a `date`, defaulting to the current UTC date. The unique constraint
is on `(video_id, captured_at)`.

**Why.** CLAUDE.md requires a re-run on the same day to update rather than duplicate. With a
timestamp, two runs on one day produce two different values, the constraint never fires, and the
measurement history silently doubles. The only thing lost is measuring one video twice in a day,
which this app never wants.