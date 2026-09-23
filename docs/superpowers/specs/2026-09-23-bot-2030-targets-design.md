# BOT Vision 2030 targets — Actual vs Target chart + Excel target columns

**Date:** 2026-09-23
**Status:** Design — awaiting review
**Source request:** Manager's Trello card + reference workbook
`docs/specification_docs_2/2022-23 to 2029-30 Target Charts as of 25-26 Actuals.xlsx`

## 1. Goal

Let the BOT tabs carry the district's Vision 2030 targets so the manager can re-run
"progress toward target" every year from Streamlit instead of rebuilding her workbook.

Three deliverables:

1. **Actual vs Target line chart** (district-wide) as the **first** chart on 7 BOT tabs.
2. **Excel export** — the chart's data as a new table, plus a **Target** column on the
   existing count tables (campus, race, gender, first-gen).
3. **PDF export** — the new chart as a new page 1; bulk exporters produce the same.

### Out of scope (decided)

- **No target markers on the existing charts.** Race / gender / first-gen charts plot
  *rates* (earners ÷ enrolled students in that group); targets are *counts*. A count
  target on a rate chart gives misleading verdicts (see §9). Existing charts are unchanged.
- **No show/hide toggle** — follows from the above.
- **Excluded tabs:** Transfers (`bot_goal2_xfer` — the manager's "Xfer 4-Year" sheet was
  built from other data), Goal 1 Students, Living Wage, Financial Aid. The workbook's
  "Xfer Ready vs Xfer", "Xfer 4-Year (CCCCO)" and "Equity Analysis" sheets are reference only.
- **No Variance / Met–Not Met columns** in the subgroup tables.

## 2. In-scope tabs

| Workbook sheet | Streamlit tab module | Dataset | Target rule |
|---|---|---|---|
| AA | `bot_goal2_assoc` | `bot_goal2_assoc` | +30% by 2029-30 |
| ADT | `bot_goal2_adt` | `bot_goal2_adt` | +30% |
| Credit Cert | `bot_goal2_cert` | `bot_goal2_cert` | +30% |
| Noncredit Cert | `bot_goal2_cert_nc` | `bot_goal2_cert_nc` | +30% |
| Bach | `bot_goal2_bac` | `bot_goal2_bac` | +30%, **rounded up** |
| Units Completed | `bot_goal3_units` | `bot_goal3_units` | **−20% of units over 60** (lower is better) |
| Xfer Ready | `bot_goal4_xfer_ready` | `bot_goal4_xfer_ready` | +30% |

Verified 2026-09-23: the app's district-wide actuals already equal the workbook's
"Actual" column for all 7 (e.g. AA 1669 / 1731 / 1762 / 1985 vs workbook
1669 / 1731 / 1761 / 1984 — the ±1 is a later data refresh; Units 82.64 / 83.00 /
83.48 / 82.12 match to 4 decimals). The district actual is the existing "NOCCCD
(Unduplicated)" figure — `pidm.nunique()` per year, or the student-deduplicated mean
for Units — so no new aggregation rule is introduced.

## 3. Target math (from the workbook formulas)

Let `k` = years since baseline (2022-23 → k=0 … 2029-30 → k=7), `N = 7`,
`B` = the group's actual value in the baseline year.

- **Growth metrics** (`growth` = 0.30):
  `target(k) = B × (1 + growth × k / N)`
  — workbook `C3 = $G$2*(1+$G$3*(ROW()-ROW($C$2))/$G$4)`; AA: 1669 → 2169.7 at k=7.
- **Reduction metric — Units** (`reduce_over` = 60, `growth` = 0.20):
  `target(k) = B − (B − 60) × growth × k / N`
  — workbook `C3 = $G$2-(($G$2-60)*$G$3*(ROW()-ROW($C$2))/$G$4)`; 82.64 → 78.12 at k=7.
  If `B ≤ 60` the target is `B` (nothing over 60 to reduce).
- **Round up** (Bach only, `round_up: True`): `ceil(target(k))` for k ≥ 1; the baseline
  itself is not rounded. Mirrors the workbook note "Manually updated benchmark numbers to
  round up" (1 → 2). *Note:* the workbook leaves 2023-24 unrounded (1.04) — an
  inconsistency in the hand edit; we round every post-baseline year.
- **Subgroups** apply the same formula to the subgroup's **own** baseline value
  (workbook column D, "Target (same as overall)"). Applies to campus rows, race, gender,
  and first-gen groups.
- **No baseline → no target.** A group with no baseline-year value (absent, or 0 for a
  growth metric) gets a blank target, never 0.
- Target values are kept **unrounded** in data; formatting rounds for display
  (whole numbers for counts, 2 decimals for Units).
- The baseline is **live** — computed from the extract on each run, not hard-coded
  (decided with the user: subgroup baselines have to be live anyway, and the 2022-23
  data is effectively closed).

## 4. Configuration (`src/pipeline/config.py`)

```python
# Vision 2030 target plan — FIXED. Does not roll with the 5-year metrics window.
BOT_TARGET_BASELINE_ACYR = "2022"   # 2022-23
BOT_TARGET_END_ACYR = "2029"        # 2029-30  (N = 7)

"bot_goal2_assoc":      {..., "target": {"growth": 0.30}},
"bot_goal2_adt":        {..., "target": {"growth": 0.30}},
"bot_goal2_cert":       {..., "target": {"growth": 0.30}},
"bot_goal2_cert_nc":    {..., "target": {"growth": 0.30}},
"bot_goal2_bac":        {..., "target": {"growth": 0.30, "round_up": True}},
"bot_goal3_units":      {..., "target": {"growth": 0.20, "reduce_over": 60}},
"bot_goal4_xfer_ready": {..., "target": {"growth": 0.30}},
```

- `N` is derived (`END − BASELINE`), not stored separately.
- A dataset without a `target` key gets no target chart and no target columns.
- Re-basing the plan (if management ever does) = change the two constants.

## 5. Keeping the baseline in the extract as the window rolls

The 5-year window (`acyr_code`) drops acyr 2022 on the **2028** run; the chart needs
2022-23 → latest (8 years by 2029-30). So:

- **Extract** (`extract.py`): for a dataset with `target`, the pulled values become
  `ref ∪ target_years ∪ window`, where
  `target_years = BASELINE … min(END, max(window))` (de-duplicated, sorted).
  Today that adds nothing (2022–2025 are already in the window); from 2028 it adds the
  years that rolled out. Future years beyond the latest window year are never pulled.
- **In-app fetch** (`data_provider._download_and_read`): unchanged. It already filters to
  the sidebar selection (+ reference when the selection is the full window), so extra
  target years never reach the existing charts.
- **New fetch** `fetch_bot_target_frame(dataset_name)`: returns the extract filtered to
  `acyr_code ≥ BASELINE`, ignoring the sidebar. The target chart is a fixed plan view, so
  **it does not respond to the Academic Years sidebar** (a caption says so).
- **Bulk exporters** read the extract **whole**, so they must split it: existing charts get
  the frame filtered to `ref ∪ window` (new helper `display_acyrs(name)` in `config.py`,
  also used to express the fetch rule), the target chart/columns get `≥ BASELINE`.
  Without this, from 2028 acyr 2022 would appear as a stray column on existing charts.
- Base-population datasets (`bot_goal1_students`, denominators) are **not** extended —
  targets are counts, never rates.

## 6. Components

New module **`src/scripts/tabs/bot_targets.py`** (keeps `bot_helpers.py`, already 1.3k
lines, from growing):

| Function | Purpose |
|---|---|
| `target_cfg(dataset)` | the dataset's `target` dict, or `None` |
| `plan_years()` | labels `2022-2023 … 2029-2030` (matches extract `academic_year` format) |
| `target_value(baseline, k, cfg)` | §3 math, one value |
| `district_actual_vs_target(df_target, dataset)` | frame `academic_year, actual, target` over all plan years (actual NaN for years not yet in the data) |
| `add_group_targets(df_agg, *, key_col, value_col, df_target_agg, cfg)` | adds a `target` column to an aggregated long frame, keyed by group + year, from the group's baseline in the target frame |
| `build_target_chart(df_avt, titles)` | Plotly line chart (§7) |
| `mpl_target_chart(fig, bbox, df_avt, titles)` | matplotlib twin for the PDF |

Subgroup targets are computed from the **target frame** (baseline year always present),
then joined onto the display-year aggregates, so a narrowed sidebar selection still gets
correct targets.

## 7. The Actual vs Target chart

Modelled on the manager's AA chart:

- **Title:** `"{metric}: Progress Toward 2029-30 Target"` — new `_TITLES["target_title"]`
  per tab (e.g. "Associate Degrees", "Transfer Ready Students", "Average Units Completed
  by ADT Earners"), plus `target_caption` stating the rule
  ("Target: 30% increase from the 2022-23 baseline by 2029-30, in equal annual steps.").
- **X-axis:** all 8 plan years; first labelled `2022-23 (Baseline)`.
- **Actual:** solid grey line, square markers, value labels — only years with data.
- **Target:** dashed gold line, diamond markers, spanning all 8 years; value labels on the
  baseline and the 2029-30 endpoint (as in the workbook chart), hover shows every value.
- Colours from existing theme tokens (`docs/theme.md`); legend "Actual" / "Target".
- Layout: full width, placed above the Headcount section, with the standard
  title block + "Source: Banner" footer.
- **Units:** y-axis in units, 1-decimal labels; lower is better, so the caption says so.

## 8. Exports

### Excel (tab download *and* bulk `bot_excel_export.py`)

1. **New first section** "`{target_title}`": `Academic Year | Actual | Target` for all 8
   plan years (Actual blank where no data yet).
2. **Headcount by Campus:** add `{last window year} Target` after the last year column —
   one target per campus row (Cypress, Fullerton, NOCE, NOCCCD (Unduplicated), as present).
3. **Race / Gender / First-gen — Summary Counts:** add `{last window year} Target` after
   `{last window year} Count`.
4. **Race / Gender / First-gen — Rate Detail:** add `Target Count` after
   `Numerator Count`, per row-year; blank for years before the baseline (2018-19, 2021-22).
5. **% matrix tables unchanged** (mixing a count into a percent grid would mislead).
6. **Units:** `{last window year} Target` on its campus / race / gender / first-gen
   summary tables (values are averages, formatted 2 decimals).

Suppressed groups stay suppressed — targets are added only to rows already shown.
If the sidebar is narrowed so the last displayed year precedes the baseline
(e.g. 2021-22 only), the `{year} Target` column is present but blank.

**Bulk Excel consolidation (prerequisite).** `bot_excel_export.py` carries private
copies of every table builder (`_count_summary`, `_rate_detail`, `_headcount_table`,
`_standard_chart_sections`, its own `ExcelSection`) that duplicate `bot_excel_helpers.py`.
Rather than add the target columns twice, first switch the bulk exporter to the shared
builders — **gated by a parity check**: on the current Hyper files, every section frame
from the old and new paths must be equal (`pd.testing.assert_frame_equal`). If they are
not identical, stop and report the difference before going further.
`tests/test_bot_excel_export.py` imports the private builders; those tests move to the
shared helpers.

### PDF (tab download *and* bulk `bot_export.py`)

- New **page 1**: section header (org, target title, "2022-23 to 2029-30", caption) +
  the target chart in the top half + Source footer. Existing pages become 2–3 with
  **no coordinate changes** (paper coordinates in `docs/bot-tabs.md` stay valid).
- Only when the dataset has a `target`; other tabs' PDFs are unchanged. Bach (`headcount_only`) becomes 2 pages. Remember the `PdfPages` early-return
  gotcha — no `return` inside the `with` block.
- Units gets the same page via its own `generate_pdf`, reusing `mpl_target_chart`.
- `generate_bot_pdf(df, titles, base_df=None, target_df=None)` — new optional argument;
  `None` → no target page (callers without targets unchanged).

## 9. Why subgroup targets are counts, not rates (decision record)

AA, Hispanic/Latino: 928 earners of 22,370 (4.15%) in 2022-23; 1,117 of 27,878 (4.01%) in
2025-26. Count target for 2025-26 = 928 × (1 + 0.3 × 3/7) = 1,047 → **met** (the
workbook's own Equity Results agrees). Growing the *rate* instead: 4.15% × 1.129 = 4.68% →
**not met**. Enrollment grew 25%, so the verdicts diverge. The manager's method is counts,
so targets live next to the counts (Numerator, Summary Counts), never on the rate charts.

## 10. Testing

Unit tests (synthetic frames, no Streamlit/Hyper/Oracle):

- `target_value` reproduces the workbook: AA k=1 → 1740.53, k=7 → 2169.7; Units k=7 →
  78.1158; Bach k≥1 → 2; `B ≤ 60` Units → B; missing/zero baseline → NaN.
- `district_actual_vs_target`: 8 rows, labels, actual NaN for future years; Units uses the
  deduplicated mean.
- `add_group_targets`: correct per-group baseline; blank before baseline; narrowed
  display years still resolve targets from the target frame.
- Extract value list: `ref ∪ target_years ∪ window` for target datasets; unchanged for
  others; simulate the 2028 window (`2023…2027`) → 2022 added.
- Bulk split: with a simulated 2028 config, existing-chart frames exclude acyr 2022,
  target frame includes it.
- Excel: new first section; Target columns present with expected headers; % matrices
  unchanged; parity test for the bulk consolidation.
- PDF: page count = old + 1 for target tabs, unchanged for others (count pages via
  `pypdf`/regex on `/Type /Page`).
- Existing `tests/test_bot_window_years.py` invariants still pass.

Manual: run the app, check the 7 tabs against the workbook's AA/ADT/… charts; open the
downloaded PDF and Excel; run both bulk exporters locally.

## 11. Docs to update

- `docs/bot-tabs.md` — new "Vision 2030 targets" section (config, math, baseline-year
  vs reference-year vs window, the chart, PDF page 1).
- `docs/exports.md` — bulk exporters split the frame; target columns.
- `docs/pipeline.md` — extract now pulls `target_years`.

## 12. Open points for review

- Chart legend/title wording: "Target" (used throughout) vs the workbook chart's
  "Benchmark". Spec uses **Target** to match the Excel columns.
- Per-tab `target_title` wording — proposed defaults in §7; adjust if the manager uses
  different names.
