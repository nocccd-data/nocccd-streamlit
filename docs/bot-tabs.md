# BOT (Board of Trustees) tabs

`bot_goal*_*.py` — Streamlit tabs that recreate charts from the annual Board of Trustees Excel report. Each Excel tab becomes one Streamlit tab. The SQL returns enrollment-level records (one row per pidm+crn) with demographic columns; all charts aggregate from this raw data.

## Standard chart set per tab

4 charts, reuse this pattern for each new BOT goal tab:
1. **Headcount by Campus** — grouped bar chart (`px.bar`, `barmode="group"`) with NOCCCD unduplicated total + 5-yr % change horizontal bar chart. Layout: `st.columns([3, 1])`.
2. **Proportion by Race/Ethnicity** — HTML data-bar table (inline `<div>` bars proportional to percentage, colored per race) + summary HTML table with counts and 5-yr % change. Layout: `st.columns([3, 2])`.
3. **Proportion by Gender** — horizontal grouped bar chart (`px.bar`, `orientation="h"`, academic year on y-axis) + summary HTML table. Layout: `st.columns([3, 2])`.
4. **First-Generation Status** — line chart (`px.line`, markers + text labels) for **Credit colleges only** (excludes NOCE) + summary HTML table. Layout: `st.columns([3, 2])`.

## Key patterns

- Raw DataFrame stored in `st.session_state["bg1_df"]` — all 4 charts aggregate from it, no re-querying
- NOCCCD unduplicated count: `df.groupby("academic_year")["pidm"].nunique()` (cross-campus dedup, NOT sum of per-campus counts)
- Credit-only filter for first-gen: `df[df["site"] == "Credit"]` (NOCE excluded due to survey data gaps)
- Deduplication: `df.drop_duplicates(subset=["pidm", "academic_year"])` before counting
- 5-yr % change: `(last_year - first_year) / first_year * 100`
- Each chart section has: title block (subheader + markdown + caption), chart+table columns, "Source: Banner" footer
- Summary HTML tables use race/gender/first-gen colored backgrounds on all cells

## Small-sample category suppression

Race and gender categories are hidden when EITHER the first-year OR last-year count falls below `CATEGORY_MIN_COUNT` (default 10). Both boundary years must have ≥ 10 for the category to be shown (middle years are ignored). The rule targets first/last years specifically because the summary table's 5-yr % change is computed from those two values, so small counts on either side make the change unreliable. Implemented via `_visible_categories(df, key_col, order, threshold)` in `bot_helpers.py` with thin wrappers `_visible_races` and `_visible_genders`. An equivalent helper exists in `bot_goal3_units.py` for the average-metric tab. The filter is applied consistently in the interactive chart, the summary table, and the PDF export.

## Rate metrics (Goal 2+ tabs)

Charts 2-4 (race, gender, first-gen) compute proportions relative to a **base population** dataset, not within the tab's own dataset. For example, "Hispanic certificate rate" = Hispanic cert earners / total Hispanic students. This is implemented via `base_df` parameter:
- Each Goal 2+ tab fetches both its own data AND a base population dataset
- `render_bot_charts(df, titles, base_df=base)` passes the base population
- Aggregation functions (`aggregate_race`, `aggregate_gender`, `aggregate_firstgen`) use `base_df` for the per-group denominator when provided
- Goal 1 Students tab passes `base_df=None` — proportions are within its own population (composition metric)
- Chart 1 (headcount) always shows absolute counts regardless of `base_df`

## Base population per tab

Most Goal 2+ tabs use `bot_goal1_students` as the denominator. Exceptions use specialized denominator datasets (no standalone tab — used purely via a fetch function):

- **BOT Goal 2 - Living Wage** (`bot_goal2_wage.py`): uses `bot_goal2_wage_denom` (SQL at `src/pipeline/sql/bot_goal2_wage_denom.sql`). Excludes students who enrolled at any NOCCCD campus in the next academic year or transferred to a 4-year (since living wage is measured for students who leave the system). Covers all three campuses (1/Cypress, 2/Fullerton, 3/NOCE); the `next_acyr_not_exist` CTE returns distinct PIDMs only and the outer NOT EXISTS matches on PIDM alone, so a student enrolled at any campus in the next year is excluded regardless of where.

- **Wage tab year label shift**: Living-wage data is reported 1 year in arrears — when querying `acyr_code = '2023'` (the 2023-24 cohort), the wage outcome is measured in 2024-25. `bot_goal2_wage.py` applies `_shift_academic_year()` to both `df` and `base_df` after fetching so the displayed `academic_year` labels align with how other BOT tabs label the same cohort year. Both DataFrames are shifted together because the rate-metric merge in `aggregate_race`/`aggregate_gender`/`aggregate_firstgen` joins on `academic_year`; shifting only one side would break the merge.
- **BOT Goal 2 - Noncredit Certificates** (`bot_goal2_cert_nc.py`): uses `bot_goal2_cert_nc_denom` (SQL at `src/pipeline/sql/bot_goal2_cert_nc_denom.sql`). The general Goal 1 NOCE population includes many non-CTE students; this specialized denominator restricts to CTE-relevant subjects/divisions that are eligible for noncredit certificates.

**Base_df must match tab's campus scope**: After fetching `bot_goal1_students` as `base`, the tab must filter it to match its own campus scope BEFORE passing to `render_bot_charts()`. Otherwise the proportion denominator includes populations the tab's numerator can never reach (e.g., a credit-only cert tab divided by a district-wide Goal 1 population). Pattern:
- Credit-only tabs (cert, assoc, adt, xfer, finaid): `base = base[base["site"] == "Credit"]`
- Noncredit-only tabs (cert_nc): `base = base[base["site"] == "Noncredit"]`
- All-campus tabs (wage): uses its own denom, no filtering needed

## Campus scope per tab

Some BOT tabs are scoped to credit colleges only (Cypress + Fullerton, excluding NOCE). The filter is applied at the **SQL level** (e.g., `WHERE a.site = 'Credit'` in the SQL), not in Python. Credit-only tabs currently include:
- Goal 2: Certificates, Associate Degrees, ADT, Bachelor's, Transfers
- Goal 3: Financial Aid, Average Units

Noncredit-only (NOCE) tabs: Goal 2 Noncredit Certificates. All-campus tabs (credit + noncredit): Goal 1 Students, Goal 2 Living Wage.

## Average-metric tabs (Goal 3 Average Units)

Unlike other BOT tabs which use count/proportion metrics via `render_bot_charts()` and `generate_bot_pdf()`, the Average Units tab computes **mean of a value column** (`sum_hours_earned`) per demographic group. It has its own self-contained implementation in `bot_goal3_units.py` — imports only the shared constants (COLOR_MAP, RACE_COLORS, etc.) and label maps from `bot_helpers.py`, but uses its own aggregation/chart/PDF functions. Same 4-section layout (campus / race / gender / first-gen) but values display as decimal numbers (e.g., "67.5") instead of percentages. No `base_df` denominator — average is computed within the tab's own data (ADT recipients).

When adding a new tab, align the titles dict (`org`, captions) with the SQL's actual scope. "NOCCCD Credit Colleges" vs "NOCE" vs "NOCCCD" as appropriate.

## Configurable flags in titles dict

- `include_nocccd` (default `True`): set `False` for single-campus tabs (e.g., NOCE noncredit) to skip the NOCCCD unduplicated bar. Credit-only tabs keep it since "NOCCCD (Unduplicated)" meaningfully represents Cypress+Fullerton combined.
- `credit_only_firstgen` (default `True`): set `False` for noncredit tabs so first-gen data isn't filtered out. Redundant (but harmless) for tabs already filtered to credit at the SQL level.
- `headcount_only` (default `False`): set `True` to skip charts 2-4 (race, gender, first-gen). Used by Bachelor's tab where the population is too small for meaningful demographic breakdowns.
- `headcount_note`, `race_note`, `gender_note`, `firstgen_note` (default `None`): per-section grey footer note rendered just below that section's "Source: …" line. Used for the small-sample confidentiality disclaimer (most often on race) and the NOCE survey-data caveat (first-gen on Goal 1). When a note is present, that section's chart and Source line shift up by `0.01` (paper coords) in the PDF to make room.
- `source` (default `"Banner"`): suffix after `Source: ` in every section footer (Streamlit and PDF). Override for tabs whose data comes from somewhere besides Banner — e.g., the Transfers and Living Wage tabs use `"CCCCO Supplemental & Success Data for the SCFF files; Banner"` because their headcount comes from `scff_xfer`/`scff_living_wage`.

**Plotly horizontal grouped bar gotcha**: Bars render in reverse legend order. To get the desired top-to-bottom order, pass `category_orders` with the reversed label list.

Widget prefix: `"bg1_"` (Goal 1), use `"bg2_"`, `"bg3_"`, etc. for subsequent goals.

## BOT PDF generator (`bot_helpers.py`)

**BOT tabs share a single PDF generator**: `generate_bot_pdf(df, titles, base_df=None)` in `bot_helpers.py` produces a portrait 8.5×11 PDF with 2 sections per page. Page 1 has Headcount + Race, Page 2 has Gender + First-Gen. Sections use paper-coordinate positioning via `fig.add_axes([left, bottom, width, height])`. Each tab sets `tab_title` in its `_TITLES` dict for the PDF header. Titles-dict flags (`include_nocccd`, `credit_only_firstgen`, `headcount_only`, per-section `*_note` keys, `source`) apply to PDF the same way as to the interactive charts. HTML data-bar tables are rendered using matplotlib `Rectangle` patches; HTML summary tables become `ax.table()` with colored cell facecolors.

**BOT tabs share Excel helpers**: `generate_bot_excel(df, titles, base_df=None)` in `bot_excel_helpers.py` writes the table data behind the Streamlit charts, using the same aggregation and denominator rules as the interactive view and PDF. Goal 3 Average Units uses `bot_goal3_units._generate_excel(df)` because that tab computes average values rather than counts/rates.

**PDF always renders in light theme**: The PDF is always meant to print on white paper, so `generate_bot_pdf()` explicitly sets color-related `matplotlib.rcParams` (`figure.facecolor`, `axes.facecolor`, `text.color`, `xtick.color`, `ytick.color`, etc.) to light-theme values. This prevents Streamlit's dark-theme context from leaking into the matplotlib global state. Data-bar and summary table text is hardcoded **black** on colored cells — contrast-aware white text would become invisible when it overflows past a narrow bar onto the white page background.

**BOT section layout gotcha**: The gender section's horizontal bar chart has long y-axis labels (e.g. "2024-2025") that extend left of the axes box. When placed at `left=0.06` (the default section margin), matplotlib clips them at the page edge. The gender section uses `left=0.12` with width `0.48` instead to leave room for tick labels. Sections with labels on the x-axis (headcount, first-gen) don't hit this issue.

**PdfPages early-return gotcha**: In `generate_bot_pdf()`, when `headcount_only=True` (Bachelor's tab), it's tempting to `return buf.getvalue()` right after saving page 1 to skip page 2. That produces a **truncated PDF** that Acrobat refuses to open, because `PdfPages.__exit__` writes the PDF trailer/xref table only when the `with` block exits. Instead, wrap the page 2 code in an `if not headcount_only:` branch inside the `with PdfPages(buf) as pdf:` block, and return `buf.getvalue()` only after the block finishes.

**BOT PDF paper coordinates** (constant across all tabs, including Units):
- Page 1 Section 1 (Headcount): chart_bbox bottom=0.58, Source at y=0.54 (below the chart's legend).
- Page 1 Section 2 (Race): header top=0.50 with tight caption padding (`pad=0.005` on `_draw_section_header`, since the race data-bar table renders on an `axis("off")` axes and doesn't need the 0.025 gap Section 1 needs for its "5-Yr % Change" axis title). Chart+table bbox bottom=0.06. Source at y=0.04.
- Page 2 Section 3 (Gender): chart_bbox left=0.12, width=0.48, bottom=0.56. Source at y=0.52.
- Page 2 Section 4 (First-Gen): chart_bbox bottom=0.13 (raised so the legend has room above the Source footer). Source at y=0.085.

**Per-section optional note**: Each of the 4 sections accepts an optional `_note` titles key (`headcount_note`, `race_note`, `gender_note`, `firstgen_note`). When present, the section's chart bottom and Source line shift up by `NOTE_OFFSET` (currently `0.01` paper coords — uniform across every section) so the wrapped note can be drawn just below the new Source position. When absent, the section keeps its baseline coordinates (above). The note is written via `_draw_section_note(fig, y, text)`, which uses `textwrap.fill(width=140)` and `fontsize=6, color="grey"` (upright — italic is reserved for the section header caption). The first-gen section is the exception: it doesn't apply the offset (chart bottom and Source y are already fixed); when `firstgen_note` is present it renders at y=0.075, exactly 0.01 below Source y=0.085 so the gap matches the other sections. The Goal 3 Average Units tab has its own self-contained PDF generator that mirrors this offset logic for `race_note` only (the only section in that tab that currently has a note).

**First-gen line chart y-axis zoom**: Both the Plotly interactive chart and the matplotlib PDF chart zoom the y-axis to `[max(0, min - 0.25×range), max + 0.25×range]` (with a small minimum pad) so clustered values (e.g. 3-5%) are visually separated instead of compressed at the bottom of a wide 0-100% range.

**BOT chart font sizes** (uniform across all BOT tabs, including Units):
- Plotly interactive charts: value labels use `textfont=dict(size=12)` — matches the race HTML data-bar table's 12px and keeps all four charts visually consistent.
- Matplotlib PDF charts: value labels use `fontsize=6`; axis tick labels use `fontsize=6-7`; summary tables and headers use `fontsize=7`.
