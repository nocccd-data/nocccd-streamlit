# Deferred / Backlog

Ranked, actionable work. Everything here is something to do — a problem that is real and
understood but deliberately left alone, with enough context to act on later without
re-deriving the analysis.

Something that is merely unfinished belongs in a branch or a plan, not here. An entry earns
a place when the fix needs a decision, is out of scope for the change that surfaced it, or
has a cost nobody has weighed yet.

**When an item is done, delete it here** and let the git history carry the record. Do not
leave a checkmark behind — a heading that announces a fix while still holding live items is
how a file like this goes wrong.

**Cite `file.py::symbol`, never `file.py:NN`.** Line numbers rot.

**Cluster numbers are stable IDs, not positions.** When a cluster closes, delete it and leave
the gap — never renumber.

| axis | values |
|---|---|
| Type | `Bug` · `Feature` · `Chore` · `Nit` · `Validation` |
| Severity | `High` (data loss, silently wrong output) · `Med` (user-visible defect with a workaround) · `Low` (cosmetic or latent) |
| Effort | `XS` (<1h) · `S` (one sitting) · `M` (one change cycle) · `L` · `XL` (needs its own design cycle) |
| State | `ready` · `spec'd` · `needs-decision` · `not-scoped` |

`needs-decision (N)` — N open decisions in the cluster body.

| # | Cluster | Type | Sev | Effort | State |
|---|---|---|---|---|---|
| 1 | [Persistence projections fit through provisional points](#1-persistence-projections-fit-through-provisional-points) | Bug | Med | S | needs-decision (1) |
| 2 | [The persistence PDF cache key does not track term-calendar republishes](#2-the-persistence-pdf-cache-key-does-not-track-term-calendar-republishes) | Bug | Low | XS | ready |

---

## 1. Persistence projections fit through provisional points

**[Bug · Med · S · needs-decision (1)]**

Surfaced by `/code-review-custom` (xhigh fleet, CONFIRMED) on PR #19, 2026-08-05. Correctly
tagged **PRE-EXISTING** — not introduced by that PR.

**Symptom:** with *Show Projection* enabled, the forecast is fitted through a data point the
same chart annotates as `provisional`. The fitted trend line and the R² printed on the PDF's
methodology page are both pulled downward.

**Root cause:** `kpi_persistence.py::_compute_projections` receives the frame straight from
`kpi_persistence.py::_views_for_mode` with no filter on `is_provisional`. A cohort whose
follow-up term is still enrolling has a necessarily depressed rate — not all follow-up
registrations have posted — and it feeds `_project_rate`'s `np.polyfit` as an equal
observation. The point carries a caveat; the projection drawn through it does not.

**To observe:** enable *Show Projection* → *Linear Regression* on `Fall → Next Fall` while a
follow-up term is mid-enrollment (any time before mid-December for the current fall). The
final grey diamond is fitted through the annotated point.

**Severity, checked in both directions.** Not `High`: the projection is captioned as an
estimate in three places, the offending point is visibly annotated, and the underlying rates
are correct — nothing here is silently wrong *data*. Not `Low`: the skew itself is invisible,
so a reader cannot tell the forecast was dragged, and the whole point of the provisional flag
shipped in PR #19 was to stop presenting partial counts as settled. Landed at `Med` — a
user-visible defect whose workaround is to turn projections off.

**Why deferred:** `main` already projected through the newest point before PR #19. What
changed is that `is_provisional` became a *reliable* signal — previously the flag was
unconditional, so filtering on it would have been wrong. That makes this a pre-existing issue
newly worth fixing, not a regression to block a merge on.

**Open decision — the fix is a product call, not a patch.** Excluding provisional points
makes the forecast honest but costs the most recent year:

- **Linear Regression** would fit 2 points instead of 3 in the common case. Still valid, but
  R² stops carrying much meaning at n=2.
- **Weighted Moving Average** requires 3 points — `kpi_persistence.py::_project_rate` returns
  `None` below that — so dropping one means projecting from a window ending *two* years back,
  or offering no projection at all for a campus with short history.

Three directions:
- **(a) Exclude provisional rows** from the fit. Honest, cheapest, and costs recency.
- **(b) Include them but mark the projection provisional too** — carry the caveat forward
  instead of dropping data.
- **(c) Down-weight rather than drop** — keeps n, reduces the skew, adds a tuning constant
  nobody can defend from first principles.

The right answer depends on how these forecasts are read. A board packet taking a single
number argues for (a); an analyst watching a trend may prefer (b). Decide before starting.

---

## 2. The persistence PDF cache key does not track term-calendar republishes

**[Bug · Low · XS · ready]**

Surfaced by `/code-review-custom` (xhigh fleet, PLAUSIBLE) on PR #19, 2026-08-05. Not among
the eight fixes applied on that PR; recorded here so it is not lost.

**Symptom:** within a single day, a downloaded PDF's provisional footnote can disagree with
the on-screen chart for the same cohort.

**Root cause:** the `cached_pdf_bytes("pbs", ...)` key in `kpi_persistence.py::render`
includes `today`, which covers a date rollover, but nothing identifying the `term_calendar`
snapshot the footnote was rendered from. That extract refreshes on its own cadence — a 600 s
`st.cache_data` TTL on `data_provider.py::fetch_term_calendar`, plus the scheduled daily
pipeline publish (see [macos-scheduling.md](macos-scheduling.md), noon).

**To observe:** download the PDF while a term is missing from the calendar (footnoted
provisional), let the noon job republish with that term now present and already ended. The
chart updates when the TTL expires; the cached PDF keeps the stale footnote until midnight.

**Severity:** `Low` — it needs a same-day calendar change to bite, which happens at most once
a day and only when Banner gains or edits a term. The rates are never affected; only the
caveat is. Self-correcting at the next date rollover.

**Fix:** add a cheap fingerprint of the calendar to the cache key — row count plus
`max(stvterm_end_date)` is enough to catch a republish, and both are already in the frame the
caller holds. Alternatively key on the extract's published timestamp, if
`publish.py::download_hyper` can be made to surface it.
