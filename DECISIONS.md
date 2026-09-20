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

**SUPERSEDED — Consequence for the UI.** Superseded on 2026-09-20 by "Shorts vs long-form is a
required choice, not an optional filter". Kept for the reasoning; do not implement.

> These videos match neither side of the Shorts vs long-form filter. They are visible only when
> that filter is off.

**Consequence for the UI (2026-09-20).** The format filter is a required choice, so these videos
are not reachable in the app at all until the reclassify job resolves them. The database currently
holds none, and the daily job exists to keep it that way.

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


## 2026-09-19 — channels.name comes from the API, not the spreadsheet

**Decision.** The `name` column is filled with the channel title returned by `channels.list`, not
with column A of the spreadsheet. The spreadsheet name is used only to recognise a row during
import and to report problems; it is not stored.

**Why.** Channel names in this sector change while the channel ID stays the same. Cycling teams
rename when a title sponsor changes — Jumbo-Visma became Visma-Lease a Bike on the same channel —
and the set holds 36 professional teams and 33 race organisers. A stored spreadsheet name would
slowly fill with sponsors that no longer exist, and the name on a card would not match what the
user sees after clicking through to YouTube.

**Consequence.** The name is only as current as the last channel fetch, so the refresh run must
re-fetch it (see below). The API title is sometimes cluttered with taglines or emoji; if that
becomes a problem in the UI, add a separate override column rather than reverting to the
spreadsheet.

## 2026-09-19 — The refresh run also re-fetches channel metadata

**Decision.** The 30-day refresh calls `channels.list` for all channels and updates `name` and
`subscriber_count`, alongside its video work.

**Why.** Names and subscriber counts go stale otherwise, because the import script only runs when
it is run by hand and the refresh otherwise touches videos only. A renamed team then corrects
itself within 30 days with no manual action. The cost is about 7 quota units per run, against a
daily limit of 10,000.

## 2026-09-19 — Channels the API does not recognise are skipped, not stored

**Decision.** If `channels.list` returns nothing for an ID, the channel is not written to the
database. The import script collects these and prints them at the end, with the spreadsheet name
beside each ID so they can be looked up.

**Why.** `name` and `uploads_playlist_id` both come from the API, so a channel with no API response
has no name and no way to find its videos. Storing it would put a permanently broken row in a table
everything else joins against. The API returns missing IDs silently — a batch of 50 simply comes
back with 49 results — so without an explicit report, a dead or mistyped ID disappears unnoticed.

## 2026-09-19 — The import never removes channels

**Decision.** A channel that is in the database but no longer in the spreadsheet is left untouched.
The import script reports these at the end but changes nothing.

**Why.** The foreign key on `videos` is `on delete restrict`, so Postgres refuses to delete a
channel that has videos, and deleting the videos first would contradict the rule that videos are
never deleted. The report is still worth having: it catches a mistyped ID, which otherwise shows up
as a channel that quietly stops updating while a near-duplicate appears next to it.

## 2026-09-19 — The backfill runs in two phases

**Decision.** Phase one does all the YouTube API work: walk each channel's uploads playlist, fetch
details in batches of 50, write the video rows and a first `video_stats` measurement. Anything at
or under 180 seconds is written with `is_short` NULL. Phase two walks the NULL rows and classifies
them with the HEAD check.

**Why.** Nobody knows how many HEAD checks the set needs until the videos are in the database — it
depends on how much of 342 channels' output falls under 180 seconds, and brand channels publish a
lot of it. One pass commits to an unknown runtime before that number is visible. Splitting it means
phase one finishes in under an hour, a single query then gives the exact count, and the throttling
decision is made against a real number.

**Bonus.** Phase two's work queue is `is_short IS NULL`, so it is resumable for free, and it is the
same script as the daily reclassify job (step 12b). It is not written twice.

## 2026-09-19 — The backfill resumes on last_checked_at

**Decision.** Phase one sets `channels.last_checked_at` when a channel finishes without error, and
skips any channel that already has a timestamp. A `--force` flag redoes a channel deliberately.

**Why.** 342 channels of network calls will eventually break halfway, and restarting from zero
wastes quota on work already done. Setting the timestamp at the end rather than the start is the
point: a channel that crashed mid-way keeps its NULL and is retried on the next run. Deriving
progress from "does this channel have videos" cannot tell a finished channel from a half-finished
one, and would leave the latter permanently incomplete.

## 2026-09-19 — Playlist paging stops after 5 consecutive videos outside the window

**Decision.** Walking a channel's uploads playlist stops once 5 videos in a row fall outside the
36-month window, not at the first one. Publication dates are read from
`contentDetails.videoPublishedAt`, never `snippet.publishedAt`.

**Why.** The uploads playlist is usually newest-first but not strictly: a video made private and
later restored, or re-uploaded, sits out of order. Stopping at the first old video lets one stray
entry truncate a channel's history silently, with no error to notice. Five consecutive costs at
most one extra API call per channel, and usually none, since 50 videos arrive per call.

**Why videoPublishedAt.** `snippet.publishedAt` is when the video was added to the playlist. For
most videos these match, but they diverge on exactly the restored and re-uploaded videos that cause
the disorder in the first place.

## 2026-09-20 — Shorts HEAD checks run at concurrency 20, no delay

**Decision.** Phase two of the backfill, and the future daily reclassify job (same script,
`ingestion/classify_shorts.py`), fire HEAD requests at `youtube.com/shorts/{id}` at concurrency 20
with no artificial delay between requests.

**Why.** Two calibration runs (`ingestion/calibrate_shorts.py`) against real videos: 500 requests
sequential came back 0 failures, 0 429s, 409/91 Shorts-to-video split, median 1,505ms / p95 2,399ms.
500 requests at concurrency 20 came back 0 failures, 0 429s, a 406/94 split (0.6 points from the
sequential run), and statistically unchanged response times (median 1,447ms / p95 2,416ms) — meaning
20 requests in flight weren't queuing behind each other or any server-side gate. A delay would have
bought nothing either way: the 1.5-second response time is network latency, not throttling, so there
was no idle gap to add one to.

The real backfill run (62,215 videos) confirmed it at full scale: 0 failures, 0 429s, no trip of the
drift guard (rolling 1,000-video window, 10-point tolerance from the ~82/18 baseline), effective rate
~14.4 req/s.

**Guardrails kept for the real run, not just the calibration.** Abort immediately on any 429; abort
on more than 50 consecutive request failures; abort if the rolling 1,000-video 200/303 split drifts
more than 10 points from baseline (a sign of a consent/interstitial redirect that returns plausible
but uninformative status codes — see the User-Agent decision above). The work queue is shuffled
before processing so that window is a cross-section of channels, not one Shorts-heavy brand's
contiguous run.

**Two real bugs hit and fixed while building this, both worth remembering for future scripts that
write is_short or similar columns in bulk:**

1. **Never `.upsert()` a partial column set to update existing rows.** `.upsert()` goes through
   Postgres's `INSERT ... ON CONFLICT DO UPDATE`, and Postgres checks NOT NULL constraints on the
   *proposed insert row* before it even checks for a conflict — so upserting just `{video_id,
   is_short}` fails on `channel_id NOT NULL`, even though the row already exists and would only be
   updated. `.update({...}).in_("video_id", ids)` has no INSERT path and cannot hit this. The
   `last_checked_at` write in the backfill (phase one) already used `.update()` for the same reason;
   phase two initially didn't, and it crashed on the very first batch, before writing anything.
2. **A ~74-minute run needs DB write retries even when the HTTP requests deliberately have none.**
   The YouTube HEAD checks are retry-free on purpose, so the failure and 429 counts stay real signal
   for the abort guards. But a long run also does hundreds of Supabase writes, and one hit a
   transient Postgres statement timeout (`57014`) after 47,500 clean requests. Retrying the DB write
   (3 attempts, 2s apart) doesn't hide anything the abort conditions care about, so phase two retries
   those specifically. Resumability (`is_short IS NULL`) meant the crash cost nothing beyond needing
   a second invocation — the ~500 videos in the failed batch simply stayed NULL and were reclassified
   on the next run.

   ## 2026-09-20 — A video's current value is read from the latest video_stats row

**Decision.** The front-end view joins each video to its most recent `video_stats` row, computed on
read. `videos` does not carry denormalised `latest_views`, `latest_likes` or `latest_comments`
columns. An index on `video_stats (video_id, captured_at desc)` supports this.

**Why.** `video_stats` is the source of truth, and a derived copy can silently disagree with it: if
a refresh run fails after writing the measurement but before updating the copy, the site shows a
stale number and the score computed from it looks exactly like a real score. Both backfill phases
already crashed mid-run — once on a Unicode error, once on a statement timeout — so this is a
realistic failure, not a theoretical one.

**Why the cost is acceptable.** Most of the archive is frozen: a video older than 180 days has
exactly one measurement forever. Only videos under 180 days accumulate rows, and they cap at six.

**Reversible in the right direction.** If the results list turns out to be slow, adding
denormalised columns later is an ALTER TABLE plus a change to the refresh. Going the other way,
after reading a column that may have drifted, means none of the stored values can be trusted.

## 2026-09-20 — Baselines are computed in Python, not in SQL

**Decision.** The baseline computation runs in Python as part of the monthly refresh, reading
videos per channel, computing medians in code, and writing the four baseline columns back.

**Why.** The computation is a median per channel, per format, per metric, over a window, capped at
20. In SQL that is one dense statement; in Python it is a readable loop that can be stepped
through, printed, and checked by hand for a single channel. CLAUDE.md asks for boring solutions
over clever ones, and this is the part of the project where the owner most needs to verify the
answer personally. The cost is moving 98,300 videos over the network twice, once a month.

**Also.** Step 8's era baselines use a different window per video with a widening fallback, which
is awkward in a single SQL statement and straightforward in a loop.

**Reversible.** The output is four columns, so moving the computation into SQL later changes
nothing downstream.

## 2026-09-20 — A video without a baseline gets NULL, with baseline_kind = 'insufficient'

**Decision.** When a channel has fewer than 10 mature videos of the right format in the window for
a given metric, that metric's baseline column is NULL and `baseline_kind` is set to
`'insufficient'`. The check constraint on `baseline_kind` is extended to allow that third value.

**Why.** NULL alone cannot distinguish "not enough history" from "never computed". With 342
channels of very uneven output, the share of videos that cannot be scored needs to be queryable
before deciding how the card presents it, and the UI can then explain the absence rather than
showing a bare dash. `baseline_kind` already exists, so this costs one ALTER TABLE.

## 2026-09-20 — Extreme scores on Brand channels carry a paid-promotion note

**Decision.** A video on a channel in the `Brand` category with an Outlier Score of 100 or higher
shows a note that the score may reflect paid promotion. Wording: "Extreme outlier scores may
indicate this video was used for paid advertising." It appears as a tooltip on the score, not as
body text on the card. Other categories get no note.

**Why only Brands.** The extreme scorers outside Brand are dominated by FloTrack (57 videos) and
Tour de France (25), whose top scores are world records and marquee races — real organic hits on
channels with lopsided output. Labelling those as possibly paid would be wrong. Inside Brand the
pattern is unmistakable: New Balance's top videos are 15 to 37 seconds, On's are an entire Zendaya
campaign published in one week, adidas's are World Cup spots.

**Why hedged wording.** The API exposes nothing about promotion — `viewCount` is the same number
whether the views came from search, recommendation or a million euros of media spend, and that data
lives only in the advertiser's Google Ads account. The note also has a real counterexample: VAUDE's
top scorer is a 22-minute documentary, not an ad. So it says the score may indicate advertising,
never that it does.

**Threshold.** 100x, where the tail genuinely begins: 165 videos above it against 533 in the 20-100
band.

**Amended 2026-09-20** by "Paid-promotion threshold raised from 100 to 500", "The paid-promotion
note is visible, not hover-only", and "The paid-promotion trigger reads all three score columns".
The reasoning below stands; the threshold, the placement and the single-metric trigger do not.
Implement the amendments.

## 2026-09-20 — Scores of 1,000 and above are displayed as 2.4K

**Amended 2026-09-20** by "The Outlier Score is displayed as a multiple, with K above 1,000". The K
abbreviation stands; the format gains an explicit `×`.

**Decision.** Outlier Scores below 1,000 show one decimal (1.2, 27.4). From 1,000 up they are
abbreviated: 2,447.8 becomes 2.4K.

**Why.** Most scores are small, so the decimal matters at the low end. A raw "2447.8" on a card
visually dominates a "1.2" beside it and is harder to read than the shorter form.


## 2026-09-20 — Era baseline members must also be older than 180 days

**Decision.** Only videos older than 180 days may be part of an era baseline, the same rule that
governs the current baseline. A video's era window is truncated at the 180-day line if it extends
past it.

**Why.** The condition is trivially true for a window sitting deep in the past, but it bites at the
recent edge: a video published 200 days ago has a window running to 20 days ago, whose second half
is full of videos still accumulating views. Including them drags the median down and inflates the
video's score. CLAUDE.md already lists "a baseline is never built from videos younger than 180
days" as a hard rule; this states the consequence explicitly.

**Expected consequence.** Videos between roughly 180 days and a year old will routinely fail to
find 10 qualifying videos in the 6-month window and fall through to the widened window or the
fallback below. That is expected behaviour, not a bug.

## 2026-09-20 — A video with no usable era window falls back to the current baseline

**Decision.** If neither the 6-month nor the 12-month era window holds 10 mature videos of the same
format, the video is scored against the current baseline (180 days to 24 months) instead, and
`baseline_kind` records `'current'`. Only if that also fails does it become `'insufficient'`.

**Why.** The alternative was a third widening step to 24 months either side, which stops being an
"era" in any meaningful sense — comparing a video to things published two years apart reintroduces
exactly the channel-growth effect the era baseline exists to remove. The fallback is explicit
rather than silent: `baseline_kind` says which comparison was used, so the share of videos affected
is queryable and the UI can say so.

**Rejected: nearest-20 instead of a calendar window.** Taking the 20 mature videos closest in
publication date always produces a baseline where one exists, and adapts to each channel's output
rate. Declined for the same reason as the 24-month widening: on a low-frequency channel those 20
can span years, with no cutoff to make that visible.

## 2026-09-20 — One-sided era windows are accepted, not flagged

**Decision.** If a video's era window holds 10 qualifying videos, the median is computed regardless
of how they are distributed around it. A channel's oldest videos are therefore compared mostly to
videos published after them. No flag records this.

**Why.** All members are mature and have essentially finished accumulating views, so the comparison
is not unfair in the way comparing a young video to an old one would be. The residual bias — an
older video had a smaller channel behind it, so it scores slightly low — pushes affected videos
down, not up, so they do not pollute the top of a Relative ranking.

**Why no flag.** The backfill stopped at 36 months, so a channel's "oldest video" is the oldest one
imported, not the oldest that exists. The left side of the window is empty because of the import
boundary, not because of the channel's history. A flag would record an artefact of the dataset
rather than a property of the data.

## 2026-09-20 — Era baseline_kind, when metrics resolve at different tiers, is by precedence

**Decision.** A video's three metrics can each resolve at a different tier (6-month window,
12-month window, current-baseline fallback, or none). `baseline_kind` is a single value per video,
set by precedence: `'era'` if *any* metric resolved from the 6- or 12-month window, else `'current'`
if *any* metric used the fallback, else `'insufficient'`.

**Why not a 3-way vote.** A literal majority has no answer when a video's three metrics split one
each way. Precedence is unambiguous to compute and to explain: a video with even one genuinely
era-quality metric is labelled `'era'`, since that is the more specific and more trustworthy of the
two comparisons. The failure mode to avoid is the reverse: quietly labelling a video with a real era
result as merely `'current'`.

## 2026-09-20 — Each write thread needs its own Supabase client

**Decision.** `compute_baselines.py` writes with `WRITE_CONCURRENCY = 10` worker threads (era
baselines produce far more distinct payloads per channel than step 7's current baseline did, so
writes can't collapse to one call per format the way step 7's did). Every worker thread builds its
own Supabase client via `create_client`, kept in thread-local storage. The single shared client from
`config.py` is still used for this script's reads, which stay single-threaded.

**Why.** The first concurrent run crashed with `httpx.ReadError` / `WinError 10035` ("a non-blocking
socket operation could not be completed immediately") on a plain read in the main thread, while
writer threads were concurrently using the same client in the background. `classify_shorts.py`'s
concurrency never hit this because it uses a `requests.Session` for the YouTube calls, not the
Supabase/httpx client, for its concurrent work. httpx.Client is documented as thread-safe, but
sharing it across threads produced a real, repeatable failure on Windows in this setup regardless of
what the documentation says. Giving each writer thread its own client removed the crash entirely,
verified by a full 342-channel run completing with 0 write failures.

**Consequence.** Any future script in this project that mixes concurrent writes with the shared
`supabase` client from `config.py` should use the same thread-local pattern rather than assuming the
shared client is safe under concurrency on this platform.


## 2026-09-20 — Residual growth bias in era baselines is accepted

**Decision.** On channels whose publishing cadence accelerated alongside their growth, old videos
still score somewhat lower than new ones. This is accepted as a known limitation rather than fixed.
It belongs in the "how it works" page (step 13), not in a redesign.

**The mechanism.** A calendar-centred window is only balanced when output rate is roughly constant.
When cadence accelerates, a 6-month window around an old video is dominated by videos from its
later, more prolific, higher-performing half. The window is balanced in time and lopsided in
content. Traced by hand on Castelli against raw data: the stored baseline matched a manual
recomputation exactly, so this is a property of the method, not an implementation error.

**Measured on the three highest-growth channels.** adidas (13.5x growth) is healthy: oldest
quartile 0.85 against newest 0.59. Castelli Cycling (21.8x) gives 0.57 against 2.05, The Feed
(28.7x) 0.44 against 0.99. The same old videos under the previous current-baseline-only approach
scored 0.20 and 0.03 — improvements of 2.85x and 14.7x. The Feed's 0.03 said "catastrophic
failure" about videos that were probably fine; 0.44 does not.

**Why not fix it.** The obvious remedy is a count-based window (the 10 videos before and 10 after
in publication order) instead of a calendar one. That trades a known, mild, bounded bias for an
unknown one: on a channel with a four-month publishing gap, the "contemporaries" are a year apart.
Redesigning a working system against three data points is the wrong trade. The three channels also
show residual bias in different directions, which suggests the noise floor of a 20-video median
rather than a systematic error still to be found. These are the most extreme growth cases out of
342 channels; a typical channel's residual is much smaller.

## 2026-09-20 — Concurrent writers each get their own Supabase client

**Decision.** Any script writing to Supabase from multiple threads creates a client per thread via
thread-local storage, never sharing one client across threads.

**Why.** Sharing a single client between the main thread's reads and worker threads' writes crashed
the first concurrent era-baseline run with a Windows socket error (httpx.ReadError / WinError
10035). The underlying HTTP connection is not safe to use from several threads at once.

## 2026-09-20 — Paid-promotion threshold raised from 100 to 500

**Decision.** The paid-promotion tooltip appears on `Brand` videos with an Outlier Score of 500 or
higher, not 100. Everything else about the note is unchanged: wording, tooltip-only placement, and
Brand-only scope.

**Why.** The original 100 came from the shape of the distribution, not from looking at the videos
either side of the line. Inspecting the actual titles per band: of the six highest-scoring videos in
the 100–500 band, one reads like advertising. In the 500–1000 band, four of six do. Since those six
sit at the very top of their band, the rest of 100–500 is less ad-like still, so the band as a whole
does not earn the note.

**What this trades.** More real ads go unlabelled. Accepted: the note is a hedge on a tooltip, and
labelling genuine content as possibly-paid is the worse error of the two — DECISIONS.md already
names VAUDE's 22-minute documentary as a case the note would be wrong about.

## 2026-09-20 — Paid-promotion threshold raised from 100 to 500

**Decision.** The paid-promotion note appears on `Brand` videos with an Outlier Score of 500 or
higher, not 100. The wording and the Brand-only scope are unchanged.

**Why.** The original 100 came from the shape of the distribution, not from looking at the videos
on either side of the line. Inspecting titles per band: of the six highest-scoring videos in the
100-500 band, one reads like advertising. In the 500-1000 band, four of six do. Those six sit at
the very top of their band, so the rest of 100-500 is less ad-like still — the band does not earn
the note.

**What this trades.** More real ads go unlabelled. Accepted: labelling genuine content as
possibly-paid is the worse of the two errors, and this entry's parent already names VAUDE's
22-minute documentary as a case the note would be wrong about.

## 2026-09-20 — The paid-promotion note is visible, not hover-only

**Decision.** The note has three parts. The score badge turns red and carries an exclamation mark.
The tooltip on the badge holds the fuller wording: "Extreme outlier scores may indicate this video
was used for paid advertising." A line in the card body, below the counts, reads "Metrics on this
video may reflect paid advertising rather than organic reach." This replaces the original
"tooltip only, not body text on the card".

**Why.** A hover-only note is invisible to anyone who does not happen to hover over that exact
element, and unreachable on touch devices entirely. The caveat then reaches nobody while appearing
to have been handled — worse than not having it, because the project believes it is covered.

**Why the colour as well as the mark.** Red is what makes the badge readable at a glance in a grid
of 60 cards; the mark alone would be a small glyph inside a badge the eye is reading as a number.

**Why a body line and not only the badge.** The badge qualifies the score. The body line qualifies
the counts, which is where a marketer's eye goes when deciding whether a video is worth copying —
9M views against 47 likes is the tell, and that pattern sits in the body, not in the score.

**Why hedged wording throughout.** The API exposes nothing about promotion. `viewCount` is the same
number whether the views came from search, recommendation or media spend, and that data lives only
in the advertiser's Google Ads account. Both texts therefore say "may".

## 2026-09-20 — Shorts vs long-form is a required choice, not an optional filter

**Decision.** The format filter always has a value. The user sees either Shorts or long-form, never
both in one grid. Default on opening: long-form. Shorts view counts are inflated by autoplay, so opening on them sets
a misleading scale for the whole page, and long-form is where the Outlier Score comparison is most
useful to a marketer looking for something to imitate. The Cycling Content Tracker defaults the
same way.

**Why.** The two formats have different thumbnail aspect ratios, so a mixed grid is ragged or
forces one format into the other's shape. Their view scales are not comparable either — the
baselines are already computed separately per format for exactly that reason — so a mixed ranking
invites a comparison the scoring deliberately refuses to make.

**Consequence for is_short NULL videos.** They are not reachable in the app at all until their
format is resolved. Accepted: the database currently holds none, in-run retries handle the
transient failures that cause almost all of them, and the daily reclassify job (NEXT_STEPS.md 12b)
is the second net. One unreachable video out of 98,300 does not change what the app is worth.

**Note that the second net does not exist yet.** Step 12b is unbuilt, so a video that goes NULL
today stays NULL indefinitely. The first thing that can create one is the refresh script (step 6),
which runs HEAD checks on newly published videos. Until 12b ships, that is the gap.

## 2026-09-20 — Card layout follows the Cycling Content Tracker

**Decision.** The video card adopts the visual conventions of the Cycling Content Tracker rather
than the plain first-pass layout of step 9: Outlier Score in a badge on the top left of the
thumbnail, "still growing" as a badge on the top right in the style of that project's "Provisional"
label, icons for views, comments and likes, and 4 cards per row at full width rather than 5.

**Why.** The conventions are proven in a working app the owner has used, so they need no fresh
design decisions. Score and status belong on the thumbnail because they qualify the image; in body
text they read as one more statistic beside the counts. Four per row rather than five because this
app's cards carry more information than that project's.

## 2026-09-20 — The paid-promotion trigger reads all three score columns

**Decision.** A `Brand` video is flagged when any of `score_views`, `score_likes` or
`score_comments` is 500 or higher. The rule reads all three columns and the outcome is fixed per
video: it does not follow the metric toggle, so a flagged video carries the note under Views, Likes
and Comments alike.

**Why not views alone.** Views alone was the obvious reading, and it was calibrated on views — but
inspecting the data showed advertising takes two distinct shapes here, and views alone catches only
one of them.

*The bought-reach shape.* TrainingPeaks: 9.05M views against 47 likes. Reach is bought, engagement
stays flat. Across the 125 Brand videos scoring 500x+ on views, the median likes score is 14.1 and
the median comments score 6.7 — a ratio of roughly 35:1 between views and likes. Views alone finds
these.

*The celebrity-campaign shape.* On's Zendaya videos, WHOOP's Ronaldo video, adidas Backyard
Legends. A celebrity brings a fanbase that genuinely likes and comments, so engagement scales with
the views instead of lagging. Their views scores sit at 212 to 422 — under the threshold — while
their likes scores run to 1,782x. **Views alone misses these entirely.** Nine videos, all of them
campaigns from On, adidas, WHOOP and Salomon.

**What it costs.** A genuinely viral organic Brand video with high engagement and modest reach
would be flagged wrongly. All nine candidates matching that description were inspected and every
one turned out to be a campaign, so on this data the cost is near zero. Two more videos are added
by the comments column.

**Why the outcome does not follow the metric toggle.** A warning that appears and disappears as the
user switches metric reads as a bug rather than as information about the video. The flag is a
property of the video, so it is computed once from all three columns and displayed consistently.

**Rejected: a separate threshold per metric.** Likes and comments scores run on a different scale
from views, so 500 does not mean the same thing across them. Calibrating three thresholds needs
three rounds of the band inspection that produced the first one, and the single threshold already
catches both shapes. Revisit only if the note turns out to fire on videos that are plainly organic.

## 2026-09-20 — The Outlier Score is displayed as a multiple, with K above 1,000

**Decision.** One decimal and an explicit `×`: `1.2×`, `27.4×`. From 1,000 up the number is
abbreviated and keeps the multiplier: `2.4K×`, `21.6K×`.

**Why the multiplier.** CLAUDE.md bans presenting the score as a percentage, because "180% of
normal" invites reading a ratio as a share rather than as a multiple of a median. A bare number
satisfies the ban only by omission; `×` satisfies it directly, and a badge reading `21.6K×` is
legible without its caption — which matters once the score is a badge on a thumbnail rather than a
labelled line of body text. Taken from the Cycling Content Tracker, where it is a settled
convention.

**Why K is still needed here.** That project's top score was about 75, so abbreviation never arose.
This dataset reaches 21,553.9, and a raw `21,553.9×` beside a `1.2×` dominates the grid and is
harder to read than the shorter form.

## 2026-09-20 — The "still growing" badge appears under both comparisons

**Decision.** The badge shows on every video younger than 180 days, under Absolute as well as
Relative.

**Why not gate it on Relative.** The obvious precedent says gate it: the Cycling Content Tracker
gated its Provisional badge to Relative on 2026-09-01, because Provisional qualifies a baseline and
Absolute has no baseline in it — the badge was caveating a number that was not on screen.

That reasoning does not transfer. Provisional is a statement about the measurement. "Still growing"
is a statement about the video: it is under 180 days old, which is true whatever is being ranked.

**Why it earns its place under Absolute.** It changes meaning rather than losing it. Under Relative
it explains a low score. Under Absolute it marks a video that reached a high raw count without the
head start every mature video in the ranking had — which makes the result more impressive, not
less. Same badge, opposite implication, useful in both.

## 2026-09-20 — Thumbnail aspect ratios and grid columns, adapted from the Cycling Content Tracker

**Decision.** Long-form 16:9, Shorts 9:16. Columns: long-form 1 / 2 / 3 / 4 across mobile / tablet /
laptop / wide, Shorts 3 / 4 / 5 / 5. One page size of 60 for both formats.

**Why two column sets rather than one.** The formats have different shapes, so a single set cannot
serve both. The Cycling Content Tracker measured the binding case: a 16:9 thumbnail at a third of a
375px screen is about 110px wide, too small to read a title against, while a portrait Short at the
same width is still legible. Hence long-form stacking on mobile and Shorts running three across.

**Why one column fewer than that project at every breakpoint.** Their numbers are long-form
1 / 2 / 4 / 5 and Shorts 3 / 4 / 6 / 6. This app's cards carry more — a score badge, a "still
growing" badge, a paid-promotion note and three counts — so they need more width to stay readable.

**Why one page size where that project has two.** They run 20 for long-form and 24 for Shorts
because at that size the divisibility mismatch shows: 20 leaves a ragged last row on 3, 4 and 6
columns. 60 divides cleanly into every column count in both sets, so the split is unnecessary and
there is one fewer number to keep in sync between the query and the display.

**Hard rule that comes with this.** The card is never given a fixed width. That project spent a
session on three symptoms — no gap between cards, a clipped duration badge, a badge cut off by its
neighbour — that turned out to be one cause: a hardcoded `w-56` does not shrink into a narrower grid
cell, so the card overflowed its own cell and later grid items painted over it. `w-full` plus
aspect-ratio classes; the cell decides the width.

## 2026-09-20 — The card carries a duration badge

**Decision.** Bottom-right of the thumbnail, formatted as YouTube does it (`0:39`, `22:14`), read
from `duration_seconds`, which is added to the `videos_scored` view for this. A NULL duration shows
no badge rather than a placeholder.

**Why.** It is standard YouTube vocabulary, so it needs no explaining, and it separates two kinds of
content the card otherwise cannot distinguish. This dataset makes that concrete: VAUDE's top scorer
is a 22-minute documentary and the extreme Brand scorers are 15 to 37 seconds — the same grid, the
same score range, entirely different work to imitate. Without the badge the only cue is the
thumbnail.

**Cost.** One column on the view and a formatter on the card.
**Two things the formatter must handle.** 4,400 videos (4.5% of the archive) run over an hour, so
`H:MM:SS` is a normal case rather than a guard — Race Organizer channels publish full-race
coverage, the longest being just under 12 hours. And 53 videos carry a duration of 0 from the API's
`P0D`, which means unavailable rather than zero-length; they take the no-badge path alongside NULL.

## 2026-09-20 — Rank is shown on the card and derived positionally

**Decision.** Each card shows `#1`, `#2`, `#3` above the thumbnail, derived from the row's position
in the returned set plus the page offset. No rank column exists on the view or in the database.

**Why show it.** Without it the grid is 60 videos in an order the user has to infer. The top-left
card and the twelfth look equally weighted, so the ranking — which is what the filters actually
produce — is invisible. The Cycling Content Tracker numbers its cards for the same reason.

**Why positional and not stored.** A video's rank is a property of the current query, not of the
video: #1 under Views Absolute and possibly #340 under Comments Relative. Storing it would mean six
columns, all recomputed on every ingestion run, all capable of disagreeing with what the page
actually returned.

**One thing the helper must get right.** It takes an offset, so the first row of page 2 is #61
rather than #1. Pagination does not exist yet, but building the offset in now means it is not a
rewrite later. The Cycling Content Tracker records the matching failure on its own page-size
helper: when the number used for the query and the number used for the rank diverge, videos are
silently skipped or repeated between pages and the list still looks entirely plausible.

## 2026-09-20 — Scoring moves to a materialised view

**Decision.** Two objects. `videos_scored_live` holds the query exactly as it is today — the join,
the `DISTINCT ON`, the three divisions — and remains the only place the scoring logic exists.
`videos_scored` becomes a materialised view over it and takes the existing name, so nothing in
`frontend/` changes: no query, no column, no contract. The refresh run refreshes it as its final
step, after its own checks pass.

**Why.** Measured with `explain analyze` on the app's default query — Views, Absolute, last year,
60 rows. Cold: 7,255ms. Warm: 370ms. A later run that would not warm up: 3,780ms. `anon` carries a
3-second statement timeout, so a visitor arriving on a cold cache gets a failure — and that visitor
is precisely someone opening the link for the first time, which is the whole audience for a
portfolio piece.

**Where the time goes.** Reading rows from `videos`: about 6,500 heap blocks for 18,136 rows, 2.5s
of the total. The `DISTINCT ON` walks all 98,300 `video_stats` rows regardless of how few videos the
date filter leaves, adding roughly 1s, and the merge sort then spills to disk. The free tier does
not hold this working set in memory, so the cold cost recurs rather than being a first-load tax.

**Why not the cheaper levers.** Dropping `fts` from the view was tested and made no measurable
difference — the heap blocks were unchanged — and it would have complicated step 10's keyword
search, so it was restored. Denormalising the latest stats onto `videos` was rejected on 2026-09-20
and that reasoning stands: a derived copy can silently disagree with `video_stats`, and a score
computed from a stale number is indistinguishable from a real one. It would also remove only the
1s, leaving the 2.5s heap scan. Upgrading Supabase fixes it for $25 a month and is the wrong answer
for a portfolio project — "I measured it and moved the computation" is a better account than "I
bought more memory".

**The objection, and its answer.** A materialised view can go stale silently: a refresh that stops
working leaves the site serving old numbers with no error and no visible difference. That is the
failure mode this project works hardest to avoid everywhere else. The answer is to make the refresh
part of the run's success criteria — it runs last, only after the run's checks pass, and a failed
refresh fails the run. A broken refresh is then exactly as loud as a broken ingestion. The Cycling
Content Tracker reached the same conclusion by the same route: it chose a live view first, measured
it once real data existed, and switched when the measurement said so.

**Access-control consequence, stated rather than glossed.** RLS does not apply to materialised
views, and they cannot be `security_invoker` — they read the underlying tables as their owner. This
exposes nothing new here, since the current view is deliberately `security_invoker = false` for the
same reason and everything in it is public YouTube data. But it is a real deviation from the
tables-sealed model and needs re-examining if any table it reads ever holds something `anon` should
not see.

**Indexes are the point.** A live view cannot be indexed on its own output; a materialised one can.
It needs a unique index on `video_id` — both because the view guarantees one row per video and
because `REFRESH MATERIALIZED VIEW CONCURRENTLY` requires one — plus an index per sort column with
`nulls last` written into the definition, so it matches what the front end actually asks for. A
DESC index defaults to NULLS FIRST, and without the match Postgres sorts on top of the index rather
than reading rows out in final order.

**Reversible.** The rename is the rollback: `videos_scored_live` is the current view unchanged, so
pointing the front end back at it is one statement and nothing is deleted at any stage.

**Built and measured, 2026-09-20.** 0.885ms on the query that was timing out, against 7,255ms cold.
The plan is the reason rather than the number: an index scan on `videos_scored_views_idx` reading
218 entries and stopping at 60, where the live view joined two tables, ran a `DISTINCT ON` over all
98,300 `video_stats` rows and sorted 18,136 results. The `nulls last` written into the index
definitions is what lets it read rows out in final order — without the match Postgres would have
sorted on top of the index and won back little.

**One thing worth knowing for future checks.** `information_schema.role_table_grants` does not
report grants on materialised views, so a query against it shows `anon` with no SELECT even when
the grant is correct. Read `pg_class.relacl` instead: `anon=r` is the SELECT. Checking the wrong
catalog here would look exactly like a missing grant.

## 2026-09-20 — The homepage is category sections; "Show more" is navigation

**Decision.** Two routes. `/` shows one section per category in fixed order — Brands, Influencers,
Professional Athletes, Professional Teams, Race Organizers — each with that category's top videos
under the current filters. `/category/:category` shows one category's full ranking, 60 videos,
reached by a "Show more" button inside each section that carries the current filters. This replaces
the flat 60-video list built in step 9.

**Why sections rather than one merged ranking.** The cross-category comparison is the product. A
marketer wants to see what teams are doing beside what brands are doing, and a single merged list
buries the smaller categories — Brands has 170 channels against Race Organizers' 33, so a flat
ranking is mostly Brands. Sections give every category the same three slots regardless of size.

**Why each section fetches independently.** One query per section rather than one gathering query,
so a section renders and fails on its own and a slow or broken one cannot blank the page. Parallel
by construction rather than by a Promise.all that has to be kept parallel deliberately. Taken from
the Cycling Content Tracker.

**Why "Show more" navigates rather than expanding.** The category page repeats the ranking from #1,
so the videos already seen appear again at the top. Nothing is on screen twice, because the
homepage is gone. It also keeps the page boundaries on round numbers.

## 2026-09-20 — What each filter does, now that the homepage is sectioned

**Decision.** Category, subcategory and sport each act at a different level.

*Category* decides which sections exist. All selected by default; deselecting one removes its
section. The last remaining category cannot be deselected.

*Subcategory* filters videos inside the sections and never removes a section. The control is
grouped by category, because subcategories are per category in the data — deselecting `Brand >
Nutrition` must not affect `Race Organizer > Running Races`.

*Sport* is global: one set of four toggles applying to every section, not one set per category. A
channel is shown if it carries at least one selected sport.

**Why the last category cannot be deselected.** Zero sections is a blank page, which reads as a
broken site rather than as a filter returning nothing. The same rule the Cycling Content Tracker
applies to its category button row.

**Why sport matches on "at least one" rather than "all".** Channels carry multiple sports, and the
overlap is the useful part: a helmet brand tagged both cycling and triathlon should survive cycling
being deselected, because the user is still interested in triathlon. Requiring every selected sport
would instead show only channels tagged with all of them, which is almost nothing.

**Why sport is global and not per category.** Twenty toggles against four, for a use case nobody
could name — wanting cycling under Brands but not under Teams. The saving in control surface is
large and the loss is hypothetical.

## 2026-09-20 — Five triathlon influencers were wrongly tagged as cycling

**Decision.** The Triathlon Hour, The Daily Tri, Global Triathlon Network, Pro Tri News and
Jenna & Miguel - Freestyle Tri had column H (cycling) cleared in
`data/channels_complete.xlsx`; column J (triathlon) is unchanged. Sheet-wide non-empty column H
went 215 → 210.

**Why this is recorded as a decision.** CLAUDE.md says the spreadsheet is read-only input and no
script may modify it. This was a deliberate, one-off exception, requested explicitly, and the
script used to make the edit was deleted afterwards so nothing in the repo can repeat it. The rule
stands.

**Consequence.** Sport tags are filter metadata, not scoring inputs, so no baseline changes and
nothing is recomputed. But the flags live in three places: the spreadsheet, the `channels` table,
and the materialised `videos_scored`. The edit only touched the first. Until the import script
re-runs and the view is refreshed, the app still filters on the old tags — which is the first real
instance of the refresh obligation this file records elsewhere.