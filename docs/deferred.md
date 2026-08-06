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
| 2 | [The persistence PDF cache key does not track term-calendar republishes](#2-the-persistence-pdf-cache-key-does-not-track-term-calendar-republishes) | Bug | Low | XS | ready |

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
