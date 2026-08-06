# Deferred issues

Known problems we have decided **not** to fix yet, with enough context to act on later
without re-deriving the analysis.

An entry belongs here when the issue is real and understood but deferred — usually because
the fix needs a product decision, is out of scope for the change that surfaced it, or has a
cost that has not been weighed yet. Things that are simply unfinished belong in a branch or
a plan, not here.

**Format.** Newest first. Each entry states what is wrong, how to reproduce or observe it,
why it was deferred, what fixing it involves, and — where relevant — the open question
someone has to answer before the fix can be written. Delete an entry when it is fixed;
the git history keeps the record.

---

## Persistence projections fit through provisional points

**Status:** open · **Surfaced:** 2026-08-05, `/code-review-custom` on PR #19 (CONFIRMED)
**Where:** `src/scripts/tabs/kpi_persistence.py` — `_compute_projections` call sites in
`render()` and `_generate_pdf`

`_compute_projections` receives the frame straight from `_views_for_mode` without excluding
rows where `is_provisional` is True. So when a cohort's follow-up term is still running, its
partial rate — necessarily depressed, because not all follow-up registrations have posted —
is fed into `np.polyfit` as if it were final. It pulls the fitted trend line down and skews
the R² printed on the PDF's methodology page. The chart annotates that point as
`provisional`, but the projection drawn through it carries no matching caveat, so the least
trustworthy point silently steers the forecast.

**To observe:** enable *Show Projection* → *Linear Regression* on `Fall → Next Fall` while a
follow-up term is mid-enrollment (e.g. any time before mid-December for the current fall).
The final grey diamond is fitted through the provisional point.

**Why deferred.** Not introduced by PR #19 — `main` already projected through the newest
point. What changed is that `is_provisional` is now a *reliable* signal, so the fix is newly
possible; before, the flag was unconditional and excluding on it would have been wrong. That
makes this a pre-existing issue newly worth fixing, not a regression to block a merge on.

**Open question (needs a decision, not just code).** Excluding provisional points makes the
forecast honest but costs the most recent year of data:

- **Linear Regression** would fit on 2 points instead of 3 in the common case — still valid,
  but R² becomes far less meaningful.
- **Weighted Moving Average** needs 3 points minimum (`_project_rate` returns `None` below
  that), so dropping one means projecting from a window ending *two* years back, or no
  projection at all for campuses with short history.

Three options worth weighing: exclude provisional rows entirely; include them but label the
projection as provisional too; or weight them down rather than dropping them. The right
answer depends on how these forecasts get used — a board packet reading a single number
argues for exclusion, a trend-watching analyst may prefer the recency.

---

## PDF cache key does not track term-calendar republishes

**Status:** open · **Surfaced:** 2026-08-05, `/code-review-custom` on PR #19 (PLAUSIBLE)
**Where:** `src/scripts/tabs/kpi_persistence.py` — `cached_pdf_bytes("pbs", ...)` key

The PDF cache key includes `today`, which covers a day rollover. It does not include
anything identifying the `term_calendar` snapshot the footnote was rendered from, and that
extract refreshes on its own cadence: a 600-second `st.cache_data` TTL plus the scheduled
daily pipeline publish (`docs/macos-scheduling.md`, noon).

So within a single day the on-screen chart and a cached PDF can disagree. A user downloads
the PDF in the morning while a term is missing from the calendar (footnoted provisional);
the noon job republishes with that term now present and already ended; the chart picks the
change up when the TTL expires, but the cached PDF keeps the stale footnote until the date
rolls over.

**Why deferred.** Narrow and self-correcting — it needs a same-day calendar change to bite,
which happens at most once a day and only when Banner gains or edits a term. The numbers are
never wrong, only the caveat. It was not part of the eight fixes applied on PR #19 and is
recorded here so it is not lost.

**Fix sketch.** Add a cheap fingerprint of the calendar to the cache key — row count plus
max `stvterm_end_date` would be enough to catch a republish, and both are already in the
frame. Alternatively key on the extract's published timestamp if `download_hyper` can
surface it.
