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
| 4 | [One flag label is applied to all of a campus's held-out terms](#4-one-flag-label-is-applied-to-all-of-a-campuss-held-out-terms) | Bug | Low | XS | ready |
| 5 | [The PDF methodology page renders when no page carries a projection](#5-the-pdf-methodology-page-renders-when-no-page-carries-a-projection) | Bug | Low | XS | ready |
| 2 | [The persistence PDF cache key does not track term-calendar republishes](#2-the-persistence-pdf-cache-key-does-not-track-term-calendar-republishes) | Bug | Low | XS | ready |
| 6 | [The persistence x axis spaces terms evenly regardless of the gaps between them](#6-the-persistence-x-axis-spaces-terms-evenly-regardless-of-the-gaps-between-them) | Bug | Low | M | needs-decision (1) |

---

## 4. One flag label is applied to all of a campus's held-out terms

**[Bug · Low · XS · ready]**

Surfaced by `/code-review` on PR #22, 2026-08-05. **PRE-EXISTING** — introduced by PR #21,
not by the closed PR that surfaced it.

**Symptom:** on a PDF page for a campus that has both a still-running follow-up term *and* one
missing from the calendar, the footnote calls both **unverified** and says they "may already be
final" — while the chart directly above labels each point correctly and separately.

**Root cause:** `kpi_persistence.py::_generate_pdf` picks a single label for the whole
comma-joined list — `label = _FLAG_UNVERIFIED if gaps else _FLAG_RUNNING` — so the presence of
any gap term relabels every held-out term on that page. The per-point annotations come from
`kpi_persistence.py::_flag_text`, which decides per row and is therefore right.

**Severity:** `Low` — it needs one campus to carry both kinds at once, which takes a calendar
gap and an in-flight term in the same view. The rates are unaffected; only the footnote's
explanation is wrong, and the chart on the same page contradicts it.

**Fix:** group the terms by their own flag and emit one clause each, reusing `_flag_text`'s
per-row decision rather than re-deriving a page-level one.

---

## 5. The PDF methodology page renders when no page carries a projection

**[Bug · Low · XS · ready]**

Surfaced by `/code-review` on PR #22, 2026-08-05. **PRE-EXISTING** — the gate dates to
`ed0a8aa`, long before this line of work.

**Symptom:** a PDF can end with a full "Projection Methodology" page describing a forecast that
appears nowhere in the document.

**Root cause:** the page is gated on `proj_overall is not None`, but
`kpi_persistence.py::_compute_projections` returns an **empty DataFrame**, not `None`, when no
campus qualifies — so an empty frame passes the gate.

**To observe:** select two terms and enable *Show Projection* → *Weighted Moving Average*
(which needs 3 completed cohorts). The export comes out as three campus charts with no dashed
line, followed by a methodology page for a projection that was never drawn.

**Severity:** `Low` — a spurious page, no wrong number. Reachable only when every campus falls
below the method's minimum.

**Fix:** gate on `proj_overall is not None and not proj_overall.empty`, matching how the campus
pages already decide whether to draw a projection.

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

---

## 6. The persistence x axis spaces terms evenly regardless of the gaps between them

**[Bug · Low · M · needs-decision (1)]**

Noticed while fixing cluster 3 (PR #24, 2026-08-06) — the visual twin of that defect, left
open because the fix changes every chart rather than only the broken case.

**Symptom:** with a gapped term selection, a two-year gap is drawn the same width as a
one-year gap, so the visual slope of one segment is not comparable to another's. Cluster 3
made the projected *number* correct; the picture still implies uniform spacing.

**Root cause:** both surfaces plot against ordinal position rather than time.
`kpi_persistence.py::_build_campus_fig` passes `x="term_short"` with
`category_orders={"term_short": _term_order(df_types)}` — a categorical axis keyed on the
label string — and `kpi_persistence.py::_mpl_line_chart` does the matplotlib equivalent with
`ax.set_xticks(range(len(tickvals)))`. Neither consults `term_sort` for placement, only for
ordering.

**To observe:** select Fall 2020, 2022, 2024 and read the chart. The three points sit at equal
intervals, then the projected Fall 2025 point sits one more equal interval out — but that last
step is one year where the others are two. The tick labels name the real terms, so the
information is on screen; only the geometry misleads.

**Severity:** `Low` — no number is wrong anywhere, on screen or in the PDF, and it takes a
deliberately gapped selection to reach. What it costs is the reader's ability to judge a trend
by eye, which is most of why the chart exists.

**Decision (1): should the default view change?** A numeric axis is the correct rendering, but
it repositions every point on every chart including the contiguous default, where today's
spacing is already accurate and the current look is what people are used to. The alternatives
are (a) numeric axis always, (b) numeric only when the selection has gaps — which makes the
chart silently change shape based on a sidebar toggle, arguably worse — or (c) keep the
categorical axis and annotate the gaps instead. This is a judgement about the audience, not
about the code, and belongs to whoever owns the dashboard's presentation.

**Counter-argument worth weighing:** an evenly-spaced categorical axis is the conventional
choice for a cohort series, every tick is labelled with its actual term, and users who never
deselect terms will never encounter a misleading gap. Doing nothing is a defensible answer.

**Fix (if (a)):** place points at `term_sort` and keep `_axis_ticks` supplying the labels via
explicit tickvals, in both `_build_campus_fig` and `_mpl_line_chart` so the screen and the PDF
cannot diverge. The projected point already carries a real `term_sort`
(`_compute_next_term`), so it needs no special case. Verify the PDF's rotated two-line tick
labels still fit at uneven spacing — they are the tightest constraint on that page.
