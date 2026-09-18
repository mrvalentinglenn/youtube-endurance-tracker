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