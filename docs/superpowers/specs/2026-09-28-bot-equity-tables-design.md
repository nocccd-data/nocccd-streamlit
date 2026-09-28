# BOT Vision 2030 equity tables — Baseline vs Benchmark vs Actual by student population

**Date:** 2026-09-28
**Status:** Design — awaiting review
**Source request:** Manager's Trello card (2026-09-28): "how complicated would it be to recreate
the Equity Tables from each Excel sheet? They follow the same rule as the overall metric for the
Benchmark setting (e.g., 30%). However, the actual versus target data would be for a specific
year (e.g., 2025-26 this time around)."
Reference: the "Equity Results" table on each sheet of
`docs/specification_docs_2/2022-23 to 2029-30 Target Charts as of 25-26 Actuals.xlsx`. That
workbook is built from this app's own Excel export, so its row lists are examples of our output,
not a fixed specification.
Builds on: `2026-09-23-bot-2030-targets-design.md` (#27, #28) and the "Benchmark" wording (#29).

## 1. Goal

For each metric, show how every student population is doing against its own Vision 2030
benchmark in the latest year — the same comparison the district chart makes for the whole
district, broken down by race/ethnicity, gender and first-generation status:

| Student Population | 2022-23 Baseline | 2025-26 Benchmark | 2025-26 Actual | Variance | Status |
|---|---|---|---|---|---|
| **Race/Ethnicity** | | | | | |
| Asian | 244 | 275 | 226 | −49 | Progressing |
| Latino/Hispanic | 928 | 1,047 | 1,117 | +70 | On Track |
| … | | | | | |

(AA, live data. Her workbook row reads 244 / 275.37 / 226 / −49.37.)

### Decisions (user, 2026-09-28)

- **Everywhere:** Streamlit tab, tab PDF, tab Excel, and the bulk PDF / Excel exporters.
- **Status wording:** "On Track" / "Progressing" (her latest screenshot), not "Met" / "Not Met".
- **Rows follow our own data rules**, not her screenshot's list (§3.2).
- **A row also needs 10+ students in the 2022-23 baseline** (§3.2).
- **Separate PR** from #29, stacked on it until #29 merges.

### Out of scope

- The workbook's "Equity Analysis" sheet (a pivot across all metrics). Our Excel section's
  columns are laid out so she can paste them into it (§5.3).
- Status colours in Excel — Excel carries values for her to work with.
- Bachelor's (§2), Transfers, Goal 1, Living Wage, Financial Aid.
- The existing Summary Counts / Rate Detail tables and the race / gender / first-gen rate
  charts are unchanged. (The 2026-09-23 spec's "no Variance / Met–Not Met columns in the
  subgroup tables" still holds for those tables; the equity table is a separate table.)

## 2. In-scope tabs (6)

Associate Degrees, ADT, Credit Certificates, Noncredit Certificates, Average Units,
Transfer Ready — the target tabs whose workbook sheet has an Equity Results table.

**Not Bachelor's.** It is a `headcount_only` tab (no race / gender / first-gen breakdown on the
tab), its district counts are 1–6 students, and its workbook sheet has no equity table. Rule in
code: no equity table when `titles["headcount_only"]` is set.

## 3. Data rules

### 3.1 The equity year

The latest academic year in the plan frame (`Targets.frame`), capped at the plan end
(`BOT_TARGET_END_ACYR`, 2029-30). Today 2025-26; after the next refresh 2026-27; from the
2031 run on it stays at 2029-30, the plan's final result. Like the district chart it ignores the
sidebar year selection. No table when the frame has no year after the baseline.

### 3.2 Which rows

Three categories, in the tab's existing order and labels (`RACE_ORDER` / `RACE_SHORT`,
`GENDER_ORDER` / `GENDER_LABELS`, `FIRSTGEN_ORDER` / `FIRSTGEN_LABELS`). First-gen follows the
tab's `credit_only_firstgen` setting (credit students only, except Noncredit, which includes NOCE).

A group gets a row only when it has **at least 10 students (`CATEGORY_MIN_COUNT`) in both
2022-23 and the equity year** — the two counts the table prints. The same floor applies to all
three categories, and to Units (students counted, not averaged).

On live data this reproduces her rows on AA, ADT, Credit Certificates and Noncredit, and differs
in two visible ways, both deliberate:

| Tab | Row | Why |
|---|---|---|
| Noncredit | Filipino **dropped** (2022-23: 2 students) | below the floor in the baseline; the tab's race chart still shows it (its rule uses the 5-year window's first/last year) |
| Transfer Ready | Filipino **shown** (77 → 13, −74, Progressing) | 10+ in both years; the tab's race chart already shows it |
| Average Units | Unknown race, Unknown gender **shown** | 10+ students in both years (e.g. Unknown gender 73 → 69) |

### 3.3 Benchmark, Variance, Status

- **Benchmark:** each group's own 2022-23 value through the tab's rule — the same
  `group_baselines` / `group_target` path that fills the Excel Summary Counts
  `{year} Benchmark` column, so the two can never disagree. Counts: +30% by 2029-30 in equal
  steps (Bach's round-up rule is irrelevant — no Bach table). Units: reduce the amount above 60
  by 20%.
- **Variance** = Actual − Benchmark, from unrounded values.
- **Status:** "On Track" when Variance ≥ 0, else "Progressing". Units (lower is better, the rule
  has `reduce_over`): "On Track" when Variance ≤ 0. Example: Units Latino 80.3 vs benchmark
  80.5 → −0.1 → On Track.
- **Display:** counts as whole numbers, Units to 1 decimal, Variance signed (`+70`, `−49`,
  `−0.1`). A Variance that rounds to 0 shows `0` with the status of its true sign (e.g. actual
  3 vs benchmark 3.39 → `0`, Progressing — AA American Indian, which the floor hides today).
  (Amended 2026-09-28 after review: every printed Variance — tab, PDF and Excel, count tabs
  and Units — is the printed Actual minus the printed Benchmark, with printed numbers rounded
  half up like Excel, so every row adds up; Status still comes from the unrounded Variance.
  The Units example above therefore prints −0.2 (80.3 − 80.5), still On Track.)
- **Note under the table**, generated from the rule like the chart caption:
  "Benchmark: 30% increase over the 2022-23 baseline by 2029-30, in equal annual steps.
  Variance = Actual − Benchmark." Units adds "On Track = at or below the benchmark."
- **Wording constants:** `ON_TRACK`, `PROGRESSING` in one place; headers use `BENCHMARK`.

## 4. Components

New module `src/scripts/tabs/bot_equity.py` — no Streamlit and no `bot_helpers` imports (same
reason as `bot_targets.py`), so `bot_helpers`, `bot_excel_helpers` and `bot_goal3_units` can
all use it.

- `EquitySource(category, agg, key_col, value_col, order, labels)` — one category's aggregate
  of the plan frame (`academic_year`, key, value, `count`). The caller builds it with its own
  aggregation: `aggregate_race` / `aggregate_gender` / `aggregate_firstgen` on the standard
  tabs, `_aggregate_race` / `_aggregate_gender` / `_aggregate_firstgen` on Units (Units'
  first-gen aggregate gains a `count` column).
- `equity_year(targets) -> str | None` (§3.1).
- `build_equity_table(targets, sources) -> pd.DataFrame | None` — columns `category, group,
  baseline, benchmark, actual, variance, status`; applies §3.2 and §3.3. None when there is no
  equity year or no row survives.
- `equity_note(rule) -> str`.
- Renderers of that one DataFrame: `equity_html(table, *, decimals)` (tab),
  `mpl_equity_table(fig, bbox, table, *, decimals)` (PDF), `equity_excel_section(...)` (Excel).

Callers:

- `bot_helpers`: `equity_sources(targets, titles)` builds the three standard sources;
  `render_target_section` and `add_target_page` gain the table.
- `bot_excel_helpers`: `standard_bot_excel_sections` adds the section after
  `actual_vs_target_section`.
- `bot_goal3_units`: its own sources; its render, `_generate_pdf` and `units_excel_sections`
  call the same renderers.
- Bulk exporters need no change — they already call `generate_bot_pdf`,
  `bot_goal3_units.generate_pdf`, `standard_bot_excel_sections` and `units_excel_sections`.

## 5. Outputs

### 5.1 Streamlit tab

Right under the Actual vs Benchmark chart and its Source line, before the divider: a bold
"Equity Results, 2025-26" heading, the HTML table, the note. Category rows are full-width bands
(NOCCCD Dark Teal `#004062`, white bold text); the Status cell is light blue (On Track) or
salmon (Progressing), bold. Colours use `light-dark()` like the tab's other HTML tables, so the
table reads in both themes (mockups 2026-09-28).

### 5.2 PDF (tab and bulk)

The bottom half of page 1, which is empty today, under the chart's Source line: heading, table
(`ax.table`, font 7), note. Page counts do not change. The table's row height scales to fit the
space above the footer, so the tallest possible table (9 race + 4 gender + 3 first-gen groups)
still fits; AA today has 13 rows.

### 5.3 Excel (tab and bulk)

A section titled "Equity Results, 2025-26" right after the Actual vs Benchmark table, one flat
table:

`Category | Student Population | 2022-23 Baseline | 2025-26 Benchmark | 2025-26 Actual | Variance | Status`

Baseline, Benchmark and Actual are unrounded, with whole-number (Units: 1-decimal) formats, like
the existing Benchmark columns; Variance holds the printed difference (§3.3), so each row adds
up in Excel too. The layout matches her "Equity Analysis" sheet (`Metric | Category | Demographic Group
| … | Status`), minus the Metric column.

## 6. Workbook discrepancies to report to the manager

1. The note says "Targets reflect 5% annual growth", but the numbers use 30% by 2029-30 in equal
   steps (≈4.3% of baseline a year): Asian 244 → 275 in 2025-26; 5% a year gives 281. Our note is
   generated from the rule.
2. Noncredit, Gender "Unknown": 29 → benchmark 0 → actual 0 → "Met". Live data: 29 → 33 → 61,
   On Track.
3. Her headers say "Target"; ours say "Benchmark" (#29).
4. Row lists differ where §3.2 says (Noncredit Filipino dropped; Transfer Ready Filipino and the
   Units Unknown rows shown).

## 7. Testing

Synthetic (pytest):

- Rows: a group under 10 in the baseline or the equity year is dropped; 10 in both is kept;
  the floor applies to first-gen and to Units (counted students).
- Values: benchmark equals the Summary Counts `{year} Benchmark` for the same group;
  Variance and Status for a met and a missed group; Units status flips (lower is better);
  Variance exactly 0 is On Track.
- Equity year: latest frame year; capped at 2029-30; None when only the baseline year exists.
- No table on a `headcount_only` tab (Bachelor's) or without targets.
- Excel: section follows the Actual vs Benchmark table, headers as §5.3, formats.
- PDF: page counts unchanged (target tabs still 3 pages; Bachelor's 2); the page-1 text
  contains "Equity Results".
- The "no reader-facing Target" guards cover the new section and HTML.

Real data (manual, recorded in the PR): AA Asian 244 / 275 / 226 / −49 matches her workbook;
live app on AA and Units; tab and bulk PDFs rendered.

## 8. Docs to update

`docs/bot-tabs.md` (Vision 2030 section: the equity table), `docs/exports.md`,
`docs/deferred.md` cluster 7 item 1 (the equity year caps at the plan end, so the table does not
go blank after 2029-30).

## 9. Open points for review

- The heading reads "Equity Results, 2025-26" (her title). The metric is named by the section
  above it on the tab and PDF page, and by the sheet in Excel.
