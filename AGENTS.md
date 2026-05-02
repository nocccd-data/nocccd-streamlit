# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## What This Is

Streamlit dashboards for NOCCCD (North Orange County Community College District) data reporting and analytics — the **NOCCCD Data Hub**. The app reads pre-extracted `.hyper` files from Tableau Cloud at runtime; it never queries Oracle directly. Oracle access is confined to the pipeline (`src/pipeline/`), which extracts data from Oracle EDW and publishes Hyper files to Tableau Cloud on a daily schedule.

## Workflow: notebooks → nocccd-streamlit

New analyses start as Jupyter notebooks in either **nocccd-scff** (SCFF/funding analyses) or **nocccd-sql** (ad-hoc district queries), where SQL queries and visualization logic are prototyped and validated with stakeholders. Once validated, the analysis is ported here as a production Streamlit tab.

**Source repos:**
- **nocccd-scff**: SCFF degree/award/CTE comparisons — notebooks in `nocccd-scff/notebooks/`, SQL in `nocccd-scff/sql/`
- **nocccd-sql**: Ad-hoc queries (e.g. class schedule heatmap) — notebooks in `nocccd-sql/district/notebooks/`, SQL in `nocccd-sql/district/queries/`

**What gets ported:**
- **SQL queries**: source repo SQL → `src/pipeline/sql/` (adapted for pipeline extraction with acyr/term placeholders)
- **SQL parameterization**: `expand_in_clause()` originated in `nocccd-scff/libs/notebook_utils.py` — the same multi-acyr `IN (:t1...)` regex expansion is used in `extract.py`
- **Crosstab tables**: `build_expandable_crosstab()` in notebook_utils was ported to `_build_expandable_crosstab()` in tab modules for expandable HTML pivot tables
- **Funding status categories**: `derive_funding_status()` (Pell/CCPG/Both/Neither) — same logic in both repos
- **Plotly visualizations**: Interactive charts (e.g. `px.imshow()` heatmaps) are ported directly; PDF export uses matplotlib recreations

When starting a new analysis, prototype in a notebook first, then follow the "Adding a new dataset + tab" checklist below.

## Commands

```bash
# Run the Streamlit app (reads Hyper files from Tableau Cloud)
streamlit run src/scripts/streamlit_app.py

# Pipeline: extract all datasets from Oracle → .hyper → Tableau Cloud
python -m src.pipeline.run

# Pipeline: single dataset
python -m src.pipeline.run coi_nhrdist_val

# Pipeline: extract only (no Tableau upload)
python -m src.pipeline.run --extract-only

# Install dependencies
pip install -r requirements.txt

# Mail: list campaigns
python -m src.pipeline.mail

# Mail: dry run (generate PDFs, don't send)
python -m src.pipeline.mail seat_count_fall2025_by_campus --dry-run

# Mail: send to single recipient for testing
python -m src.pipeline.mail seat_count_fall2025_by_campus --recipient "Test Recipient"

# Mail: send to all recipients
python -m src.pipeline.mail seat_count_fall2025_by_campus

# Bulk PDF export of the Seat Count Report to OneDrive
# (one PDF per term × campus × division, overwrites existing files)
python -m src.pipeline.seat_count_export

# Combined BOT tabs PDF export to OneDrive
# (single multi-page PDF, all BOT tabs concatenated, overwrites same-day file)
python -m src.pipeline.bot_export

# BOT chart-table Excel export to OneDrive
# (one workbook with one chart-data sheet per BOT metric tab)
python -m src.pipeline.bot_excel_export
```

## Architecture

```
Oracle EDW ──► extract.py ──► .hyper files ──► publish.py ──► Tableau Cloud
                                                                   │
                                              Streamlit Cloud ◄────┘
                                              (downloads .hyper at runtime)
```

### Data access (`data_provider.py`)

Each public `fetch_*()` function is an `@st.cache_data(ttl=600)` wrapper that calls `_download_and_read(dataset_name, filter_col, values)` — which downloads the dataset's Hyper extract from Tableau Cloud, reads it via `pantab.frame_from_hyper()`, and filters in-memory to the requested values. Tableau credentials come from `st.secrets`. The mail pipeline has its own `_fetch_from_hyper()` in `mail_config.py` that loads Tableau credentials directly from `secrets.toml` instead of `st.secrets`, so it can run outside a Streamlit runtime.

Filter columns are part of the Hyper schema contract. `_download_and_read()`, `_fetch_from_hyper()`, and mail recipient filtering should fail loudly if an expected filter column is missing instead of returning unfiltered data.

### Pipeline flow (`src/pipeline/`)

1. **`config.py`** — defines datasets: name → SQL file + value list + `param_name` + `db_section`. Each dataset stores its values under a semantic key (e.g. `mis_acyr_id`, `acyr_code`, `fisc_year`) and `param_name` tells extract.py which key to read.
2. **`extract.py`** — reads SQL, resolves values via `cfg[param_name]`, expands `IN (:t1...)` or loops single-param SQL, queries Oracle, writes `.hyper` via `pantab.frame_to_hyper()`
3. **`publish.py`** — uploads `.hyper` to "Streamlit Data" project on Tableau Cloud; also has `download_hyper()` which downloads `.tdsx`, extracts `.hyper` from the ZIP
4. **`run.py`** — CLI orchestrator, reads Tableau credentials from `.streamlit/secrets.toml`

### Mass mailing system (`src/pipeline/mail/`)

Generates filtered PDF reports and emails them to recipients via Gmail SMTP (`nocccd.reports@gmail.com`).

1. **`mail_config.py`** — `REPORT_REGISTRY` maps report types to fetch/filter/PDF functions. `CAMPAIGNS` defines mail jobs with parameters, subject/body templates, and recipient lists with per-recipient filter overrides. Data is fetched from **Tableau Cloud Hyper files** (same source as Streamlit Cloud), not Oracle — this avoids Oracle dependencies and uses pre-extracted data. The `_fetch_from_hyper()` helper loads Tableau credentials directly from `secrets.toml` (no `st.secrets`).
2. **`report_generator.py`** — orchestrator: fetches data **once** from Tableau Cloud, then for each recipient applies filters, generates PDF, sends email. Returns `list[SendResult]` with success/failure per recipient. Accepts a `progress_callback` for UI integration.
3. **`sender.py`** — sends a single email with PDF attachment via Gmail SMTP/TLS (`nocccd.reports@gmail.com`, port 587, app password auth). Rate-limited with `time.sleep(2)` between sends.
4. **`run.py`** — CLI entry point (`python -m src.pipeline.mail`). Supports `--dry-run` and `--recipient` flags. The package `__main__.py` wrapper must call `sys.exit(main())` so GitHub Actions receives non-zero failure codes.

**Adding a new report type to the mail system:**
1. Add a `generate_report_pdf(df, params) -> bytes` function in the tab module
2. Add a `_fetch_<report>()` function in `mail_config.py` using `_fetch_from_hyper()`
3. Register in `REPORT_REGISTRY` with fetch_fn, filter_columns, pdf_fn
4. Create campaigns in `CAMPAIGNS` dict with recipients and filters

**Email credentials**: Stored in `.streamlit/secrets.toml` under `[email]` section. Uses a dedicated Gmail account (`nocccd.reports@gmail.com`) with App Password (2-Step Verification must be enabled on the Google account). Tableau Cloud credentials in the same file are used to download Hyper data.

**GitHub Actions workflow**: `.github/workflows/mail-reports.yml` supports manual triggers from the Actions tab and maps GitHub repo secrets into `secrets.toml` at runtime. Do not describe any automatic mail schedule as active unless the workflow's `schedule:` block is currently enabled.

### Bulk PDF export (`src/pipeline/seat_count_export.py`)

On-demand bulk export of the Seat Count Report to a local OneDrive folder. Each run reads `src/pipeline/hyper/seat_count_report.hyper` (already produced by the standard pipeline) and writes one PDF per `(term, campus, division)` combination present in the data, into a date-stamped subfolder so each run leaves a daily snapshot. Same-day re-runs overwrite the existing day's PDFs. Run `python -m src.pipeline.seat_count_export` whenever a refresh is wanted; there is no scheduler.

- **Source**: local Hyper only — no Tableau Cloud download, no `secrets.toml` needed. If the Hyper file is missing (rare, e.g. when bringing up a brand-new dataset), the script fails fast and tells you to run `python -m src.pipeline.run seat_count_report` first.
- **Destination layout**: `<EXPORT_ROOT>/<YYYYMMDD>/<Campus>/<Season>/<filename>.pdf`. `EXPORT_ROOT` is a module-level constant pointing to `~/Library/CloudStorage/OneDrive-NorthOrangeCountyCommunityCollegeDistrict/Documents - EST Data/Seat Count Report`. The `<YYYYMMDD>` segment is computed from `date.today()` at the start of each run — every distinct calendar day creates a new snapshot directory; same-day re-runs overwrite. Campus values (`Cypress`, `Fullerton`, `NOCE`) match `campus_desc` from the SQL exactly.
- **Term-code → season**: last two digits of the banner term code drive the season subfolder — `10`/`15` → `Fall`, `20`/`35` → `Spring`, `30`/`05` → `Summer`. Encoded in `_SEASON_BY_SUFFIX` at the top of the module; an unknown suffix logs a warning and skips that term rather than failing the whole run.
- **Filename slug**: `<term_title_slug>_<campus_lower>_<season_lower>_<division_slug>.pdf`, e.g. `fall_2025_cypress_fall_business.pdf`. The term portion uses `term_title` from the data (e.g. "Fall 2025", "NOCE Spring 2024", "Winter/Spring 2024") rather than the numeric `term_code`. Slugging via `_slug()` lowercases and collapses any non-alphanumeric run to a single underscore.
- **Reused code**: imports `_compute_totals` and `_generate_pdf` from `src/scripts/tabs/seat_count_report.py` so the bulk-exported PDFs are byte-identical to what the user sees when they pick the same filters interactively. The Streamlit `@st.cache_data` decorators in `data_provider.py` emit "No runtime found" warnings when imported outside Streamlit; the module sets `logging.getLogger("streamlit").setLevel(logging.ERROR)` *before* the tab import to quiet most of them.
- **Failure handling**: per-PDF errors are caught, logged, and counted; the rest of the run continues. The exit code is non-zero if anything was skipped.

### Bulk PDF export — BOT tabs (`src/pipeline/bot_export.py`)

On-demand bulk export of every BOT (Board of Trustees) tab into a **single combined multi-page PDF** under a local OneDrive folder. Each run reads each `src/pipeline/hyper/bot_*.hyper` file (already produced by the standard pipeline), generates the same PDF each tab's `Download PDF` button produces in the Streamlit app, and concatenates them with `pypdf` into one output PDF. Run `python -m src.pipeline.bot_export` whenever a refresh is wanted; there is no scheduler.

- **Source**: local Hyper only — no Tableau Cloud download, no `secrets.toml` needed. Each per-tab builder reads the relevant `bot_*.hyper` file(s) directly. If a Hyper file is missing, that tab errors out and is reported, but the run continues with the remaining tabs.
- **Destination layout**: `<EXPORT_ROOT>/<max_acyr_label>/bot_<YYYYMMDD>.pdf`. `EXPORT_ROOT` is a module-level constant pointing to `~/Library/CloudStorage/OneDrive-NorthOrangeCountyCommunityCollegeDistrict/Documents - EST Data/BOT Reports/PDF Export`. The folder label is derived from the max `DATASETS["bot_goal1_students"]["acyr_code"]`, e.g. `2024` -> `2024-25`. Same-day re-runs overwrite that day's PDF; later run dates create new files in the same academic-year folder.
- **Academic-year folder label**: derived from `DATASETS["bot_goal1_students"]["acyr_code"]` only — other BOT datasets sometimes cover a different 5-year window (e.g. `bot_goal2_wage` is shifted back by one year), so export organization is anchored to the canonical Goal 1 range.
- **Reused code**: each per-tab builder imports the corresponding tab module's `_TITLES` (and any `_normalize` / `_shift_df` helper, e.g. `bot_goal2_xfer._normalize`, `bot_goal2_wage._shift_df`) and calls `bot_helpers.generate_bot_pdf(df, _TITLES, base_df=…)` — except `bot_goal3_units`, which has its own self-contained `_generate_pdf(df)` since it's an average-metric tab. The `base_df` denominator filtering (e.g. `base[base["site"] == "Credit"]` for the credit-only tabs, `bot_goal2_cert_nc_denom` for noncredit, `bot_goal2_wage_denom` shifted forward by 1 year for living-wage) mirrors each tab's `render()` Query block exactly so the bulk PDF is byte-equivalent to a manual interactive download with the full default acyr range.
- **Tab order**: Goal 1 Students → Goal 2 ADT → Associate Degrees → Bachelor's → Certificates → Noncredit Certificates → Living Wage → Transfers → Goal 3 Financial Aid → Average Units (encoded in `_TAB_BUILDERS`).
- **Merging**: each tab's PDF is rendered to bytes via matplotlib `PdfPages`, then `pypdf.PdfReader` reads the bytes and `PdfWriter.add_page()` appends each page to a single output writer. `pypdf` is added to `requirements.txt` for this purpose.
- **Failure handling**: per-tab errors are caught, logged, and counted; the rest of the run continues. The exit code is non-zero if anything was skipped.

### Excel export — BOT chart tables (`src/pipeline/bot_excel_export.py`)

On-demand Excel export of the table data behind every BOT Streamlit/PDF chart. Each run writes a single `.xlsx` workbook under a local OneDrive folder. Run `python -m src.pipeline.bot_excel_export` whenever a workbook refresh is wanted; there is no scheduler.

- **Source**: local Hyper only — no Tableau Cloud download, no `secrets.toml` needed. The workbook reads `src/pipeline/hyper/bot_*.hyper` extracts to build aggregated chart-table sheets, but does not export raw student-level extract tabs.
- **Destination layout**: `<EXPORT_ROOT>/<max_acyr_label>/bot_<YYYYMMDD>.xlsx`. `EXPORT_ROOT` is a module-level constant pointing to `~/Library/CloudStorage/OneDrive-NorthOrangeCountyCommunityCollegeDistrict/Documents - EST Data/BOT Reports/Streamlit Data Export`. The folder label is derived from the max `DATASETS["bot_goal1_students"]["acyr_code"]`, e.g. `2024` -> `2024-25`. Same-day re-runs overwrite that day's workbook; later run dates create new files in the same academic-year folder.
- **Workbook layout**: 10 chart-table sheets, one per displayed BOT metric tab, in the same order as the combined PDF export. Denominator extracts are used only for percentage calculations, not exported as raw sheets.
- **Reused code**: chart-table sheets use the same `bot_helpers` aggregation functions and the same per-tab preparation rules as `bot_export.py` (`bot_goal1_students` credit-only denominator filters, `bot_goal2_cert_nc_denom`, `bot_goal2_wage_denom` shifted forward, and `bot_goal2_xfer._normalize`). `bot_goal3_units` uses its own average-units aggregators.
- **Dependency**: uses `xlsxwriter` through `pandas.ExcelWriter`; keep `xlsxwriter` in `requirements.txt`.

### Tab system (`src/scripts/tabs/`)

`tabs/__init__.py` has a `TABS` list of `(label, render_fn)` tuples. `streamlit_app.py` renders whichever tab is selected in the sidebar.

**Adding a new dataset + tab (full checklist):**
1. Add SQL file to `src/pipeline/sql/`
2. Register dataset in `src/pipeline/config.py` (name, sql_file, param_name, values under semantic key, db_section)
3. Add a `fetch_*()` function in `data_provider.py` — one line: `return _download_and_read("<dataset_name>", "<filter_col>", values)`, wrapped with `@st.cache_data(ttl=600, show_spinner="Loading data...")`. `<filter_col>` is the column the Hyper file is filtered on (e.g. `"acyr_code"`, `"mis_term_id"`).
4. Create tab module in `src/scripts/tabs/` with a `render()` function
5. **Default values**: Import from `config.py` (`from src.pipeline.config import DATASETS`) — never hardcode value lists in tab files. Look up via the dataset's `param_name`. Example: `cfg = DATASETS["your_dataset"]; _DEFAULT_VALS = cfg[cfg["param_name"]]`
6. **Widget keys**: Use a unique prefix for all `st.session_state` keys and widget `key=` params to avoid collisions between tabs
7. Register in `tabs/__init__.py`
8. Add a project card in `home_config.py` — `tab_label` must exactly match the label string in `tabs.TABS` or the Home "Open" button won't navigate correctly
9. Update `README.md` file tree

### Cascading sidebar filters

The Seat Count Report tab (`seat_count_report.py`) uses cascading dynamic filters: Term Code → Campus → Division → Department. The approach:
1. Query button fetches **all** rows for the selected term into `st.session_state`
2. Campus/Division/Department `st.sidebar.selectbox()` widgets each include an "All" option
3. Each filter's options list is derived from the **already-filtered** DataFrame (filtered by parent selections)
4. When a parent filter changes, Streamlit reruns the script; child options update and reset to "All" if the previous selection is no longer valid
5. No additional database calls — all filtering is local pandas operations

This pattern is suitable for any tab where the full dataset fits in memory and users need hierarchical drill-down.

### Per-campus column layout (Seat Count Report)

The Seat Count Report shows a different column set per campus, in both the banded HTML table and the PDF (interactive download + bulk export):

- **Cypress, Fullerton** (credit colleges, campus codes 1/2): 13 columns. **Census 2 count + % are hidden** — these campuses don't run a second census.
- **NOCE** (campus code 3): 16 columns. **Building column is added** between End Time and XList — names like "Anaheim Campus" or "NOCE Cypress Tech Ed 2" come from `dim_section_meeting.building_desc`, picked from the lowest `meeting_category` whose value is non-null (see `building_pick` CTE in `seat_count_report.sql`).
- **"All"** (mixed-campus filter): does **not** show a union. Instead, `_resolve_layout_mode(campus, term_code)` looks at the term-code suffix and picks credit vs NOCE — Banner term codes ending in `0` (e.g. 202310, 202320, 202330) are credit-only, codes ending in `5` (e.g. 202315, 202335, 202405) are NOCE-only, and the two never overlap. This is what you want for "All" because the data only contains one set of campuses for any given term.

`_layout_for_campus(campus_mode)` returns the per-mode metadata (`html_labels`, `pdf_cols` with widths summing to 1.0, rate-color indices, alignment sets, and visibility flags) used by `_build_banded_html` and `_generate_pdf`. PDF widths differ between credit (13 cols, INSM 0.27, no Building) and NOCE (16 cols, INSM 0.14, Building 0.19); both sum to 1.000. The bulk export passes the per-PDF campus directly so each `<Campus>/<Season>/*.pdf` lands in its correct layout automatically.

### Persistence projections (`persistence_by_styp.py`)

The Persistence by Student Type tab supports forecasting the next academic year's persistence rates. Two methods are available via a sidebar toggle:

- **Linear Regression**: `np.polyfit(x, y, 1)` — extrapolates a least-squares trend line. Reports R² (goodness of fit) per group. Minimum 2 data points.
- **Weighted Moving Average**: last 3 data points weighted [1×, 2×, 3×]. Minimum 3 data points.

Projected values are clipped to [0, 1]. The next term label is derived from MIS term ID pattern (IDs increment by 10 per year: 207→217→…→257→267).

**Plotly facet subplot gotcha**: `px.line(facet_col_wrap=3)` does NOT store traces in categorical order — the trace order matches Plotly's internal subplot layout, which differs from the category order. To add projection traces to the correct facet panel, match each existing trace to its category by comparing y-data with `np.allclose()`, then read the trace's `xaxis`/`yaxis` to determine its subplot. Setting `xaxis="x"` on `go.Scatter()` raises a validator error in some Plotly versions — only set `xaxis`/`yaxis` for non-default subplots (i.e., skip when value is `"x"` or `"y"`).

**PDF export**: Includes projected dashed lines on all charts plus a final methodology page (method description, caveat, R² table for linear regression) when projections are active.

Widget prefix: `"pbs_"`

### Admin authentication (`auth.py`, `admin_config.py`)

Protected tabs (currently Mail Admin) require a password before access. The system:

1. **`admin_config.py`** — `PROTECTED_TABS` set defines which tab labels require authentication
2. **`auth.py`** — `render_admin_hub()` shows the admin tab selector after password check. Password stored in `.streamlit/secrets.toml` under `[admin]` section: `password = "your-password"`
3. **`streamlit_app.py`** — splits `TABS` into public and admin lists. Admin button appears in the sidebar below the author line. `on_change` callback on the project dropdown exits admin mode automatically.

Session state keys: `_admin_mode`, `_admin_authenticated`, `_admin_selected_tab`

**Adding a new admin-protected tab**: Add the tab label string to `PROTECTED_TABS` in `admin_config.py`.

### Class Schedule Heatmap drill-down

The heatmap tab (`class_schedule_heatmap.py`) shows section counts by day/time. Below each heatmap, an expander with dropdown selectors (Campus+Day or Day+Hour depending on chart type) lets users drill into a specific cell combination. `_render_drilldown()` shows 4 tables: top 10 Divisions, top 10 Departments, top 10 Subjects, and full Modality breakdown — each with enrollment count and percentage. CRN deduplication (`drop_duplicates(subset=["crn"])`) is applied before aggregation to avoid inflated counts from multiple meeting rows per section.

Widget prefix: `"csh_"`

### BOT (Board of Trustees) tabs (`bot_goal*_*.py`)

BOT tabs recreate charts from the annual Board of Trustees Excel report. Each Excel tab becomes one Streamlit tab. The SQL returns enrollment-level records (one row per pidm+crn) with demographic columns; all charts aggregate from this raw data.

**Standard chart set per tab** (4 charts, reuse this pattern for each new BOT goal tab):
1. **Headcount by Campus** — grouped bar chart (`px.bar`, `barmode="group"`) with NOCCCD unduplicated total + 5-yr % change horizontal bar chart. Layout: `st.columns([3, 1])`.
2. **Proportion by Race/Ethnicity** — HTML data-bar table (inline `<div>` bars proportional to percentage, colored per race) + summary HTML table with counts and 5-yr % change. Layout: `st.columns([3, 2])`.
3. **Proportion by Gender** — horizontal grouped bar chart (`px.bar`, `orientation="h"`, academic year on y-axis) + summary HTML table. Layout: `st.columns([3, 2])`.
4. **First-Generation Status** — line chart (`px.line`, markers + text labels) for **Credit colleges only** (excludes NOCE) + summary HTML table. Layout: `st.columns([3, 2])`.

**Key patterns:**
- Raw DataFrame stored in `st.session_state["bg1_df"]` — all 4 charts aggregate from it, no re-querying
- NOCCCD unduplicated count: `df.groupby("academic_year")["pidm"].nunique()` (cross-campus dedup, NOT sum of per-campus counts)
- Credit-only filter for first-gen: `df[df["site"] == "Credit"]` (NOCE excluded due to survey data gaps)
- Deduplication: `df.drop_duplicates(subset=["pidm", "academic_year"])` before counting
- 5-yr % change: `(last_year - first_year) / first_year * 100`
- Each chart section has: title block (subheader + markdown + caption), chart+table columns, "Source: Banner" footer
- Summary HTML tables use race/gender/first-gen colored backgrounds on all cells

**Small-sample category suppression**: Race and gender categories are hidden when EITHER the first-year OR last-year count falls below `CATEGORY_MIN_COUNT` (default 10). Both boundary years must have ≥ 10 for the category to be shown (middle years are ignored). The rule targets first/last years specifically because the summary table's 5-yr % change is computed from those two values, so small counts on either side make the change unreliable. Implemented via `_visible_categories(df, key_col, order, threshold)` in `bot_helpers.py` with thin wrappers `_visible_races` and `_visible_genders`. An equivalent helper exists in `bot_goal3_units.py` for the average-metric tab. The filter is applied consistently in the interactive chart, the summary table, and the PDF export.

**Rate metrics (Goal 2+ tabs)**: Charts 2-4 (race, gender, first-gen) compute proportions relative to a **base population** dataset, not within the tab's own dataset. For example, "Hispanic certificate rate" = Hispanic cert earners / total Hispanic students. This is implemented via `base_df` parameter:
- Each Goal 2+ tab fetches both its own data AND a base population dataset
- `render_bot_charts(df, titles, base_df=base)` passes the base population
- Aggregation functions (`aggregate_race`, `aggregate_gender`, `aggregate_firstgen`) use `base_df` for the per-group denominator when provided
- Goal 1 Students tab passes `base_df=None` — proportions are within its own population (composition metric)
- Chart 1 (headcount) always shows absolute counts regardless of `base_df`

**Base population per tab**: Most Goal 2+ tabs use `bot_goal1_students` as the denominator. Exceptions use specialized denominator datasets (no standalone tab — used purely via a fetch function):
- **BOT Goal 2 - Living Wage** (`bot_goal2_wage.py`): uses `bot_goal2_wage_denom` (SQL at `src/pipeline/sql/bot_goal2_wage_denom.sql`). Excludes students who enrolled at any NOCCCD campus in the next academic year or transferred to a 4-year (since living wage is measured for students who leave the system). Covers all three campuses (1/Cypress, 2/Fullerton, 3/NOCE); the `next_acyr_not_exist` CTE returns distinct PIDMs only and the outer NOT EXISTS matches on PIDM alone, so a student enrolled at any campus in the next year is excluded regardless of where.

- **Wage tab year label shift**: Living-wage data is reported 1 year in arrears — when querying `acyr_code = '2023'` (the 2023-24 cohort), the wage outcome is measured in 2024-25. `bot_goal2_wage.py` applies `_shift_academic_year()` to both `df` and `base_df` after fetching so the displayed `academic_year` labels align with how other BOT tabs label the same cohort year. Both DataFrames are shifted together because the rate-metric merge in `aggregate_race`/`aggregate_gender`/`aggregate_firstgen` joins on `academic_year`; shifting only one side would break the merge.
- **BOT Goal 2 - Noncredit Certificates** (`bot_goal2_cert_nc.py`): uses `bot_goal2_cert_nc_denom` (SQL at `src/pipeline/sql/bot_goal2_cert_nc_denom.sql`). The general Goal 1 NOCE population includes many non-CTE students; this specialized denominator restricts to CTE-relevant subjects/divisions that are eligible for noncredit certificates.

**Base_df must match tab's campus scope**: After fetching `bot_goal1_students` as `base`, the tab must filter it to match its own campus scope BEFORE passing to `render_bot_charts()`. Otherwise the proportion denominator includes populations the tab's numerator can never reach (e.g., a credit-only cert tab divided by a district-wide Goal 1 population). Pattern:
- Credit-only tabs (cert, assoc, adt, xfer, finaid): `base = base[base["site"] == "Credit"]`
- Noncredit-only tabs (cert_nc): `base = base[base["site"] == "Noncredit"]`
- All-campus tabs (wage): uses its own denom, no filtering needed

**Campus scope per tab**: Some BOT tabs are scoped to credit colleges only (Cypress + Fullerton, excluding NOCE). The filter is applied at the **SQL level** (e.g., `WHERE a.site = 'Credit'` in the SQL), not in Python. Credit-only tabs currently include:
- Goal 2: Certificates, Associate Degrees, ADT, Bachelor's, Transfers
- Goal 3: Financial Aid, Average Units

Noncredit-only (NOCE) tabs: Goal 2 Noncredit Certificates. All-campus tabs (credit + noncredit): Goal 1 Students, Goal 2 Living Wage.

**Average-metric tabs (Goal 3 Average Units)**: Unlike other BOT tabs which use count/proportion metrics via `render_bot_charts()` and `generate_bot_pdf()`, the Average Units tab computes **mean of a value column** (`sum_hours_earned`) per demographic group. It has its own self-contained implementation in `bot_goal3_units.py` — imports only the shared constants (COLOR_MAP, RACE_COLORS, etc.) and label maps from `bot_helpers.py`, but uses its own aggregation/chart/PDF functions. Same 4-section layout (campus / race / gender / first-gen) but values display as decimal numbers (e.g., "67.5") instead of percentages. No `base_df` denominator — average is computed within the tab's own data (ADT recipients).

When adding a new tab, align the titles dict (`org`, captions) with the SQL's actual scope. "NOCCCD Credit Colleges" vs "NOCE" vs "NOCCCD" as appropriate.

**Configurable flags in titles dict:**
- `include_nocccd` (default `True`): set `False` for single-campus tabs (e.g., NOCE noncredit) to skip the NOCCCD unduplicated bar. Credit-only tabs keep it since "NOCCCD (Unduplicated)" meaningfully represents Cypress+Fullerton combined.
- `credit_only_firstgen` (default `True`): set `False` for noncredit tabs so first-gen data isn't filtered out. Redundant (but harmless) for tabs already filtered to credit at the SQL level.
- `headcount_only` (default `False`): set `True` to skip charts 2-4 (race, gender, first-gen). Used by Bachelor's tab where the population is too small for meaningful demographic breakdowns.
- `headcount_note`, `race_note`, `gender_note`, `firstgen_note` (default `None`): per-section grey footer note rendered just below that section's "Source: …" line. Used for the small-sample confidentiality disclaimer (most often on race) and the NOCE survey-data caveat (first-gen on Goal 1). When a note is present, that section's chart and Source line shift up by `0.01` (paper coords) in the PDF to make room.
- `source` (default `"Banner"`): suffix after `Source: ` in every section footer (Streamlit and PDF). Override for tabs whose data comes from somewhere besides Banner — e.g., the Transfers and Living Wage tabs use `"CCCCO Supplemental & Success Data for the SCFF files; Banner"` because their headcount comes from `scff_xfer`/`scff_living_wage`.

**Plotly horizontal grouped bar gotcha**: Bars render in reverse legend order. To get the desired top-to-bottom order, pass `category_orders` with the reversed label list.

Widget prefix: `"bg1_"` (Goal 1), use `"bg2_"`, `"bg3_"`, etc. for subsequent goals.

### SQL parameterization

Two patterns are supported by `extract.py`:
- **Multi-acyr**: SQL uses `IN (:t1...)`. The placeholder list is expanded to match the number of acyrs via case-insensitive regex substitution (`re.IGNORECASE`). SQL files may use uppercase `IN` or lowercase `in` — both work.
- **Single-acyr**: SQL uses a single named bind like `:mis_acyr_id`. The runner detects this (no `IN` expansion match) and loops over each acyr, concatenating results.

`extract.py` auto-dispatches between these two shapes by checking the SQL for the `IN (:t1` pattern, so a SQL file's parameterization style is the single source of truth — no per-caller flag.

**Bind variable arithmetic gotcha**: Avoid `:acyr_code + 1` when the target column is VARCHAR2. The Python-bound `:acyr_code` is VARCHAR2; `+ 1` forces an implicit conversion to NUMBER, and Oracle then applies another implicit conversion to the compared column — **disabling index use and causing full table scans**. Use `TO_CHAR(TO_NUMBER(:acyr_code) + 1)` to keep both sides VARCHAR2 explicitly. See `bot_goal2_wage_denom.sql` for a working example.

**Choosing db_section for performance**: When a query joins tables across REPT and DWHDB, prefer the `db_section` that **minimizes dblink traversal**. For example, `bot_goal2_wage_denom` uses `db_section: "dwhdb"` because it needs `dwh.scff_xfer` (local to DWHDB) plus Banner tables (accessible via `@banner.nocccd.edu` dblink). Running it from REPT with `@dwhdb.nocccd.edu` for the fact table ran for 17+ hours before timing out; running from DWHDB with the dblinks pointing to Banner ran in minutes. The dblink direction matters because Oracle's filter pushdown is sometimes one-way.

### Sidebar PDF export

Tabs with PDF export (Fast Facts, Class Schedule Heatmap, Seat Count Report, Persistence by Student Type, all BOT tabs) use `st.sidebar.download_button()` to offer a PDF download.

**BOT tabs share a single PDF generator**: `generate_bot_pdf(df, titles, base_df=None)` in `bot_helpers.py` produces a portrait 8.5×11 PDF with 2 sections per page. Page 1 has Headcount + Race, Page 2 has Gender + First-Gen. Sections use paper-coordinate positioning via `fig.add_axes([left, bottom, width, height])`. Each tab sets `tab_title` in its `_TITLES` dict for the PDF header. Titles-dict flags (`include_nocccd`, `credit_only_firstgen`, `headcount_only`, per-section `*_note` keys, `source`) apply to PDF the same way as to the interactive charts. HTML data-bar tables are rendered using matplotlib `Rectangle` patches; HTML summary tables become `ax.table()` with colored cell facecolors.

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

**Critical ordering rule**: The PDF download button block **must run after the query block**, not before it. Streamlit executes top-to-bottom; if the PDF check (`if "key" in st.session_state`) runs before the query block that sets that key, the button won't appear on the same run as the query — it only shows after navigating away and back.

```python
# CORRECT — PDF block after query block
query_btn = st.sidebar.button("Query", key="xx_query_btn")

if query_btn:
    # ... fetch data, store in st.session_state["xx_data"] ...

if "xx_data" in st.session_state:
    st.sidebar.download_button("Download PDF", data=..., key="xx_pdf_btn")
```

**Memoize PDF bytes per filter combination**: `st.download_button` registers `data` in an in-memory media-file store keyed by a content hash, then hands the browser a URL like `/media/<hash>.pdf`. Matplotlib **embeds a creation timestamp in every PDF**, so calling the generator on each rerun (every sidebar widget change triggers one) yields different bytes → different hash → the URL the browser is about to fetch is already invalid. The browser then silently saves Streamlit's 404 HTML response under the `.pdf` filename, producing the "downloaded an HTML file" symptom. Use `cached_pdf_bytes()` and `clear_pdf_cache()` from `src/scripts/pdf_cache.py` for new PDF-enabled tabs; the Query handler should clear the cache so a fresh fetch triggers a fresh PDF. `seat_count_report.py` has an equivalent custom cache pattern because its PDF key depends on cascading filter state.

**PDF rendering approach**: Use matplotlib (not kaleido/plotly `to_image()`). Kaleido 1.x launches a Chrome process to render images, which is slow and causes a visible Chrome window to flash on macOS. Matplotlib renders natively with no browser dependency. Two patterns exist:
- **Table-based**: `ax.table()` renders a DataFrame as a table on a matplotlib axes. Good for small/medium tables. See `fast_facts.py` and `class_schedule_heatmap.py`.
- **Row-by-row drawing**: For long banded reports that span many pages, draw each row with `ax.text()` and `Rectangle` patches directly on a full-page axes (`ax.set_xlim(0, PAGE_W)`). This avoids clipping — rows flow continuously across pages. See `seat_count_report.py` (`_generate_pdf`).

**Page layout**: Use a fixed page size (e.g. `8.5 x 11` portrait for tables, `11 x 8.5` landscape for charts) and position content with `fig.subplots_adjust()` margins. Do **not** use `tight_layout()` or `bbox_inches="tight"` — these shrink-wrap the figure to the content, leaving no room for headers/footers and causing overlaps. Content should fit within the page margins, not fill the entire page.

**Tab title header**: Every exported PDF must include the tab title (e.g. "Fast Facts", "Class Schedule Heatmap") as a `fig.suptitle()` on the first page. This makes it clear which tab the PDF came from when printed or shared.

**Page footer**: Every PDF page must include a footer via `_add_pdf_footer(fig)` called before each `pdf.savefig()`. The footer has the app URL (`https://nocccd.streamlit.app/`) left-justified and the author (`Author: Jihoon Ahn  jahn@nocccd.edu`) right-justified, both in small grey font (`fontsize=7, color="grey"`).

## Theme System

The app supports light/dark mode via Streamlit 1.55's built-in theme toggle. Custom colors are applied in `src/scripts/theme.py` using `apply_theme()`, which injects CSS and a small JS snippet.

### How it works

- **`light-dark()` CSS function**: All custom colors use `light-dark(light-val, dark-val)`. Streamlit sets `color-scheme` on `[data-testid="stApp"]`, and the browser resolves `light-dark()` automatically.
- **`_COLOR_SCHEME_SYNC` JS**: A MutationObserver watches `stApp` for class changes and copies the `color-scheme` value to `<html>`. This is needed because portaled elements (selectbox dropdowns) are rendered outside `stApp` and wouldn't otherwise inherit the scheme.
- **`config.toml`**: Defines light/dark palette (backgrounds, text, sidebar) under `[theme.light]` / `[theme.dark]`. `primaryColor = "#003056"` (NOCCCD navy).
- **Dataframe theming**: Streamlit 1.55 exposes `dataframeBorderColor` and `dataframeHeaderBackgroundColor` in `config.toml`. These feed directly into glide-data-grid's React props — CSS variable overrides or JS monkey-patches will NOT work because the canvas reads from React props, not CSS vars.

### Gotchas (Streamlit 1.55)

- **Portaled dropdowns**: Baseweb selectbox dropdowns are portaled to the document root, outside `stApp`. They don't inherit `color-scheme`, so `light-dark()` won't work without the `_COLOR_SCHEME_SYNC` observer. Dropdown text color needs a separate `stSelectboxVirtualDropdown` rule since it can't be scoped to a sidebar/main ancestor.
- **Selector names**: `stVerticalBlockBorderWrapper` doesn't exist in 1.55. Use `[data-testid="stColumn"] [data-testid="stVerticalBlock"]` for card styling.
- **Progress bar fill**: The fill bar is `[data-testid="stProgress"] [role="progressbar"] > div > div > div` (triple-nested div). Targeting `[role="progressbar"]` itself only styles the container track.
- **Sidebar text color**: Sidebar forces white text via `config.toml`. Selectbox widgets inside the sidebar inherit white, but the dropdown menu is portaled out, so it needs its own color rule.
- **Dataframe canvas**: `st.dataframe()` uses glide-data-grid which renders to a `<canvas>` element. CSS cannot style canvas content. The only way to customize gridline color, header background, and text colors is through `config.toml` theme keys (`dataframeBorderColor`, `dataframeHeaderBackgroundColor`, `textColor`). Header text color and index column text color are derived from `textColor` at 60% and 80% opacity respectively — there is no independent control.
- **Card border scoping**: The `[data-testid="stColumn"] [data-testid="stVerticalBlock"]` selector matches both Home page cards and tab metric columns. Home cards already get borders from `st.container(border=True)`, so adding `border` to this generic selector creates a double border. Use `:has([data-testid="stMetric"])` to scope border/padding/radius to metric columns only. Setting `border-color` alone is insufficient — `border-style` defaults to `none`, so use the full `border: 1px solid ...` shorthand.
- **Expanding crosstab tables**: The MIS SP tabs use `_build_expandable_crosstab()` which renders HTML tables via `st.markdown(unsafe_allow_html=True)`. Header styling uses `var(--secondary-background-color, #555)` but this CSS variable doesn't resolve inside `st.markdown()` HTML, so it falls back to `#555` (dark grey) in both modes. The `theme.py` overrides fix this — `.grid-row.header` and `.sub-table thead th` are globally targeted with `light-dark()` to set proper light/dark backgrounds and text colors. Reuse `_build_expandable_crosstab()` for future tabs that need expandable pivot tables.
- **Banded HTML tables**: The Seat Count Report uses `.sc-banded` CSS class for grouped banded tables rendered via `st.markdown(unsafe_allow_html=True)`. Styled in `theme.py` with `light-dark()` for department headers (`.dept-header`), course headers (`.course-header`), subtotal rows (`.subtotal-row`, `.dept-total`), and fill rate coloring (`.sc-fillrate-high/med/low`). Each division is wrapped in `st.expander()`. Reuse this pattern for future banded/grouped reports.

### Color palette reference

| Element | Light | Dark |
|---------|-------|------|
| Headings | `#003056` (navy) | `#FFFFFF` |
| Card bg | `#E8E8E8` | `#000000` |
| Card border (metrics) | `#AAAAAA` | `rgba(255,255,255,0.2)` |
| Progress fill | `#003056` (navy) | `#3D9DF3` (bright blue) |
| Body text | `#000000` | `#FFFFFF` |
| Dataframe border | `#888888` | (default) |
| Dataframe header bg | `#E8E8E8` | (default) |
| Crosstab header bg | `#E8E8E8` | `#555` |
| Crosstab header text | `#000000` | `#FFFFFF` |
| Dropdown separator | `#444444` | `#AAAAAA` |
| Banded dept header | `#D6E4F0` | `#1A3A5C` |
| Banded course header | `#F0F4F8` | `#2D3748` |
| Fill rate high (>=80%) | `#D4EDDA` | `#1B4D3E` |
| Fill rate med (50-80%) | `#FFF3CD` | `#4D3F00` |
| Fill rate low (<50%) | `#F8D7DA` | `#4D1F24` |

### NOCCCD brand colors

Official district color palette used in BOT charts and reports:

| Color | HEX | RGB | Usage |
|-------|-----|-----|-------|
| Green | `#50b913` | 80, 185, 19 | Cypress College |
| Blue | `#0081b7` | 0, 129, 183 | General accent |
| Light Blue | `#5faed3` | 95, 174, 211 | Male, Multiethnic |
| Dark Teal | `#004062` | 0, 64, 98 | NOCE |
| Teal | `#00b3a0` | 0, 179, 16 | Filipino |
| Teal/Aqua | `#50b9c3` | 80, 185, 195 | NOCCCD Unduplicated, Hispanic, Non-Binary, Not First-Gen |
| Teal Blue | `#007a94` | 0, 122, 148 | Asian, Female, First-Gen, Amer Indian/AK Native |
| Grey | `#575a5d` | 87, 90, 93 | Pacific Islander |
| Sand Yellow | `#fbde81` | 251, 222, 129 | Available accent |
| Golden Yellow | `#ffdd00` | 255, 209, 0 | Available accent |
| Orange | `#f99d40` | 249, 157, 64 | Fullerton College, Black/African American, Unknown (gender) |

### Adding themed elements

1. Use `light-dark(light-val, dark-val)` for all color properties
2. Always add `!important` — Streamlit's inline styles have high specificity
3. If colors look wrong, inspect the DOM with Playwright (`browser_snapshot`) to find the actual element and its test-id
4. Portaled elements (dropdowns, dialogs) need rules without ancestor scoping — they live at the document root
5. Add new CSS rules to `THEME_CSS` in `theme.py`; no changes needed to `apply_theme()`

## Configuration

- **Oracle credentials**: `src/pipeline/libs/config.ini` (gitignored; copy from `config.ini.template`)
- **Tableau Cloud PAT**: `.streamlit/secrets.toml` (keys: `SERVER`, `SITE_NAME`, `PAT_NAME`, `PAT_VALUE`)
- **Admin password**: `.streamlit/secrets.toml` under `[admin]` section (key: `password`)
- **Email credentials**: `.streamlit/secrets.toml` under `[email]` section (Gmail SMTP for mass mailing)
- **Python version**: pinned to 3.13 in `.python-version` (pantab wheels unavailable for 3.14)

## Deployment

Deployed to Streamlit Cloud at `nocccd.streamlit.app`. Pushes to `main` trigger automatic redeploy. Tableau secrets are configured in the Streamlit Cloud dashboard. After Oracle data changes, re-run the pipeline (`python -m src.pipeline.run`) to refresh Hyper files on Tableau Cloud.

## Key Constraints

- `pantab` must stay pinned to `==5.2.2` (API differences between major versions)
- `streamlit_app.py` inserts repo root into `sys.path` at startup — required for Streamlit Cloud where only the script's directory is on the path
- SQL files live in `src/pipeline/sql/` (tracked in git); `.hyper` files are gitignored in `src/pipeline/hyper/`
- Oracle Instant Client: `/Users/hoonywise/Oracle/instantclient_23_3` with `lib -> .` symlink (macOS SIP workaround)
