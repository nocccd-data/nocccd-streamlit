# Persistence — term completeness detection

**Date:** 2026-08-05
**Status:** Approved, not implemented
**Repos touched:** `nocccd-sql` (MV), `nocccd-streamlit` (pipeline + tab)

## Problem

The KPI - Persistence tab used to mark the newest cohort `provisional`, warning that its
follow-up term was still enrolling and the rate would rise. The label was produced by
`_provisional_term()`, which returned the newest surviving cohort **unconditionally** — it never
tested whether that term had actually finished.

So it fired on cohorts whose follow-up term was long over. Viewed on 2026-08-05, the
Fall 2025 → Spring 2026 point was still marked provisional even though Spring 2026 ended in
May 2026. The Fall → Next Fall reading was correct at the same moment (Fall 2026 was genuinely
mid-enrollment), which is why the defect went unnoticed: the label is right roughly half the
time by construction.

The note was removed on 2026-08-05 rather than left in a state that mislabels final numbers.
This spec covers putting it back, driven by a real test.

## Decision

Detect completeness from Banner term dates. The MV emits the **follow-up term codes**; a new
standalone `term_calendar` extract carries the **dates**; the tab joins them and compares
against the render date.

### Why not the alternatives

**Dates in the MV.** The MV could join `stvterm` itself and emit `spring_end_date` /
`next_fall_end_date` directly — one change, no new dataset, no join. Rejected because it bakes a
*mutable* fact into a `REFRESH COMPLETE ON DEMAND` materialized view. A corrected term date in
Banner would require a full DROP/CREATE rebuild to surface. Term *codes* never change; term
*dates* do.

**Calendar extract alone.** A `term_calendar` dataset with no MV change. Rejected because the
persistence extract carries no Banner term code — only `mis_term_id` and `camp_code` — so there
is nothing to join on. The tab would have to reconstruct the follow-up term code in Python from
the district suffix conventions, duplicating a rule that already lives (and is already proven
correct) in the MV.

The chosen split puts the stable fact where it is already computed and the volatile fact in a
cheap, independently refreshed extract that any other tab can reuse.

## `mis_term_id` is not a join key

One `mis_term_id` maps to **two** Banner term codes — the credit term (suffix `0`) and the NOCE
term (suffix `5`). The MV's own `cte_params` demonstrates this, grouping by `stvterm_mis_term_id`
and pivoting the two tracks into separate columns:

```sql
MAX(CASE WHEN SUBSTR(stvterm_code, 6, 1) = '0' THEN stvterm_code END) AS base_fall_term,
MAX(CASE WHEN SUBSTR(stvterm_code, 6, 1) = '5' THEN stvterm_code END) AS base_fall_term_ce
```

Joining `mis_term_id` against `stvterm` therefore fans every row out 2:1 and attaches the wrong
track's calendar to half of them. This is the same failure mode the district CLAUDE.md warns
about for `substr(levl_code, 1, 1)`: fine for grouping, silently wrong for joining.

**All joins are on `stvterm_code`, which is unique.** The MV resolves the track before the data
leaves Oracle, because it already knows `camp_code` per row.

## Component 1 — MV emits follow-up term codes

**File:** `nocccd-sql/district/views/mv_persistence_by_styp.sql`

Two columns added to the final `SELECT`:

```sql
TO_CHAR(CASE WHEN a.camp_code IN ('1','2') THEN p.base_fall_term    + 10
             ELSE                               p.base_fall_term_ce + 20 END) AS spring_term_code,
TO_CHAR(CASE WHEN a.camp_code IN ('1','2') THEN p.base_fall_term    + 100
             ELSE                               p.base_fall_term_ce + 100 END) AS next_fall_term_code,
```

Both expressions must also be added to `GROUP BY`. Oracle will not infer that
`p.base_fall_term` is functionally dependent on the grouped `p.mis_term_id`.

These are the **same expressions** `cte_next_spring` and `cte_next_fall` already use to locate
the follow-up registrations, so the emitted codes cannot drift from the counts they describe.
The `TO_CHAR(base_fall_term + n)` pattern is already proven in this MV — `cte_curr_fall` uses it
for the spring-award join.

### Verification of the arithmetic

Every code these expressions produce appears in the `seat_count_report` term list in
`src/pipeline/config.py`, confirming them against real NOCCCD term codes:

| mis_term_id | camp | fall term | `spring_term_code` | `next_fall_term_code` |
|---|---|---|---|---|
| 237 | 1, 2 | 202310 | 202320 | 202410 |
| 237 | 3 | 202315 | 202335 | 202415 |
| 247 | 1, 2 | 202410 | 202420 | 202510 |
| 247 | 3 | 202415 | 202435 | 202515 |
| 257 | 1, 2 | 202510 | 202520 | 202610 |
| 257 | 3 | 202515 | 202535 | 202615 |

**Cost:** one more DROP/CREATE rebuild. It is the last one this feature needs.

## Component 2 — `term_calendar` dataset

**New file:** `src/pipeline/sql/term_calendar.sql`

```sql
-- Banner term calendar. Join key is stvterm_code ONLY.
-- stvterm_mis_term_id is deliberately NOT selected: it is 1:many against this
-- table (one MIS term = one credit term + one NOCE term), so exposing it here
-- invites a join that silently doubles rows. Add it back only with that caveat.
SELECT
    stvterm_code,
    stvterm_start_date,
    stvterm_end_date
FROM stvterm
WHERE stvterm_acyr_code >= '2023'
```

**Config** in `src/pipeline/config.py` — note the absence of `param_name`:

```python
"term_calendar": {
    "sql_file": "term_calendar.sql",
    "db_section": "rept",
},
```

No `skip_refresh`: the calendar joins the daily refresh. `run.py` iterates `DATASETS` and
publishes each, so a config entry is all a new dataset requires.

### On the filter

The reference query also carried `stvterm_mis_term_id >= '237'`, matching the MV's floor. That
predicate is **dropped**. The calendar must be a superset of every term the MV can point at; a
floor duplicated in two places turns a lowered MV floor into silently missing dates rather than
an error. The acyr filter alone yields roughly 30 rows a year, so generosity is free.

## Component 3 — parameterless datasets

**File:** `src/pipeline/extract.py`

All 29 existing datasets carry a `param_name`, and `extract_dataset` hard-indexes it
(`cfg["param_name"]`, then `cfg[param_name]`). A calendar is naturally unparameterized.

```python
param_name = cfg.get("param_name")
if param_name is None:
    if re.search(r":\w+", base_sql):
        raise RuntimeError(
            f"{sql_path.name} has bind placeholders but no param_name in config"
        )
    with engine.connect() as conn:
        df = pd.read_sql(base_sql, conn)
    return _write_hyper(name, df)
```

The bind-placeholder guard is not optional. Without it, a SQL file that *should* be
parameterized silently ships a literal `:t1` to Oracle. This mirrors the existing assertion that
catches a no-op `IN (:t1)` expansion.

**File:** `src/scripts/data_provider.py`

`_download_and_read` takes `filter_col: str | None = None`, returning the frame unfiltered when
`None`. Plus:

```python
@st.cache_data(ttl=600, show_spinner="Loading data...")
def fetch_term_calendar() -> pd.DataFrame:
    return _download_and_read("term_calendar")
```

## Component 4 — tab completeness

**File:** `src/scripts/tabs/kpi_persistence.py`

`RATE_OPTIONS` gains `term_code_col` per mode (`spring_term_code` / `next_fall_term_code`).
`_REQUIRED_COLS` gains both new MV columns.

One pure, testable function:

```python
def _attach_completeness(
    df: pd.DataFrame,
    calendar: pd.DataFrame,
    term_code_col: str,
    today: pd.Timestamp,
) -> pd.DataFrame:
    """Add an ``is_provisional`` column: True while the follow-up term is unfinished."""
```

- Join on the term code. Both sides `.astype(str).str.strip()` — one side is Oracle `VARCHAR2`,
  the other arrives via `TO_CHAR`.
- **Rule:** complete iff `end_date < today`. A term is provisional through its own end date
  inclusive.
- `today` is a **parameter**, never `Timestamp.today()` inline — otherwise the function cannot
  be tested and the PDF cache cannot key on it.

### Three properties this must have

**Provisional is per campus, not global.** NOCE's spring (`'35'`) ends on a different calendar
than the credit spring (`'20'`), so Cypress and Fullerton can be settled while NOCE is still in
flight. The old global label could not express this. The annotation is applied per campus chart.

**A missing calendar row means provisional, never complete.** An unmatched term code yields
`NaT`, and `NaT < today` evaluates False, so the row lands on provisional by default. This is
the correct fail-safe, but it must be asserted deliberately rather than relied on as an accident
of pandas: surface a caption naming any unmatched term codes so a calendar gap is visible rather
than quiet.

**The PDF cache key must include `today`.** `cached_pdf_bytes("pbs", ...)` currently keys on
frame identity, persistence type, and projection controls. Without the date, a cached PDF
carries a stale caveat across the day a term ends.

### Display

Restore all four surfaces, now driven by the real test and applied per campus: the `st.caption`,
the grey Plotly annotation below the marker, the matplotlib annotation, and the PDF footnote.

## Testing

`_attach_completeness` is pure, so it is tested directly with a pinned `today` and a synthetic
calendar:

| Case | Expected |
|---|---|
| `end_date` in the past | complete |
| `end_date` equals `today` | provisional |
| `end_date` in the future | provisional |
| no calendar row for the term code | provisional, term code reported |
| same `mis_term_id`, credit ended, NOCE not | credit complete, NOCE provisional |

Then end-to-end against the real extract: charts, Excel, and PDF render for both modes with
projections on and off, and the annotation appears on exactly the campuses whose follow-up term
is unfinished.

## Rollout order

1. Rebuild the MV with the two term-code columns.
2. Add `term_calendar.sql`, the config entry, the `extract.py` change, and the `data_provider`
   change.
3. Run both extracts: `python -m src.pipeline.run kpi_persistence term_calendar`.
4. Land the tab changes.
5. Update `docs/tabs.md` — the "Incomplete cohorts" section currently documents the removal and
   what re-adding would require. Replace that with how the restored check works, and update the
   PDF export bullet, which no longer mentions the footnote.

The tab lands last and reuses the existing `_REQUIRED_COLS` guard in `render()`, so an extract
predating the MV rebuild produces a named `st.error` with the refresh command rather than a
`KeyError`.

## Out of scope

- **Census-date threshold.** The count is final at census, well before the term ends, so
  "ended" holds the caveat on a number that has stopped moving. Accepted deliberately: it is the
  conservative reading and the easier one to defend. No census *date* exists anywhere in the
  pipeline today — only section-level census enrollment counts in `seat_count_report`.
- **Reusing `term_calendar` in other tabs.** It is built to be reusable, but no other tab is
  changed here.
