# Tabs (`src/scripts/tabs/`)

How tabs are wired up, registered, and how they handle filters, downloads, and PDF rendering.

## Tab system

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

## Cascading sidebar filters

The Seat Count Report tab (`seat_count_report.py`) uses cascading dynamic filters: Term Code → Campus → Division → Department. The approach:
1. Query button fetches **all** rows for the selected term into `st.session_state`
2. Campus/Division/Department `st.sidebar.selectbox()` widgets each include an "All" option
3. Each filter's options list is derived from the **already-filtered** DataFrame (filtered by parent selections)
4. When a parent filter changes, Streamlit reruns the script; child options update and reset to "All" if the previous selection is no longer valid
5. No additional database calls — all filtering is local pandas operations

This pattern is suitable for any tab where the full dataset fits in memory and users need hierarchical drill-down.

## Per-campus column layout (Seat Count Report)

The Seat Count Report shows a different column set per campus, in both the banded HTML table and the PDF (interactive download + bulk export):

- **Cypress, Fullerton** (credit colleges, campus codes 1/2): 13 columns. **Census 2 count + % are hidden** — these campuses don't run a second census.
- **NOCE** (campus code 3): 16 columns. **Building column is added** between End Time and XList — names like "Anaheim Campus" or "NOCE Cypress Tech Ed 2" come from `dim_section_meeting.building_desc`, picked from the lowest `meeting_category` whose value is non-null (see `building_pick` CTE in `seat_count_report.sql`).
- **"All"** (mixed-campus filter): does **not** show a union. Instead, `_resolve_layout_mode(campus, term_code)` looks at the term-code suffix and picks credit vs NOCE — Banner term codes ending in `0` (e.g. 202310, 202320, 202330) are credit-only, codes ending in `5` (e.g. 202315, 202335, 202405) are NOCE-only, and the two never overlap. This is what you want for "All" because the data only contains one set of campuses for any given term.

`_layout_for_campus(campus_mode)` returns the per-mode metadata (`html_labels`, `pdf_cols` with widths summing to 1.0, rate-color indices, alignment sets, and visibility flags) used by `_build_banded_html` and `_generate_pdf`. PDF widths differ between credit (13 cols, INSM 0.27, no Building) and NOCE (16 cols, INSM 0.14, Building 0.19); both sum to 1.000. The bulk export passes the per-PDF campus directly so each `<Campus>/<Season>/*.pdf` lands in its correct layout automatically.

## Persistence projections (`kpi_persistence.py`)

The KPI - Persistence tab shows one overall ("all students") persistence line chart per campus (Cypress, Fullerton, NOCE), with a `Fall → Spring` / `Fall → Next Fall` radio. It also supports forecasting the next academic year's persistence rates. Two methods are available via a sidebar toggle:

- **Linear Regression**: `np.polyfit(x, y, 1)` — extrapolates a least-squares trend line. Reports R² (goodness of fit) per campus. Minimum 2 data points.
- **Weighted Moving Average**: last 3 data points weighted [1×, 2×, 3×]. Minimum 3 data points.

Projected values are clipped to [0, 1]. The next term label is derived from MIS term ID pattern (IDs increment by 10 per year: 207→217→…→257→267).

**PDF export**: One overall page per campus with projected dashed lines, plus a final methodology page (method description, caveat, R² table for linear regression) when projections are active.

**Excel export**: One `chart_data` sheet with overall persistence rates + counts (Fall→Spring and Fall→Next Fall) per campus/term. Independent of the projection/persistence-type toggles, so its cache key is just `(id(df_overall),)`.

Widget prefix: `"pbs_"`

## 1st-time applied-to-enrolled yield (`kpi_applied_to_enrolled.py`)

The KPI - 1st Time Applied to Enrolled tab shows one line chart per campus (Cypress, Fullerton, NOCE) of the application-to-enrollment yield (`% enrolled` = enrolled ÷ applied), **each chart followed by its own change-vs-baseline table**. Unlike the single-line Persistence tab, each chart carries **multiple lines — one per student type** (`first_time`, `first_time_trans`, `concurrent`, `adult`) plus a bold black dashed **Overall** line. The tab is titled "1st Time" because the four student types are all entry types — returning and continuing students are out of scope.

- The source MV (`dwh.mv_applied_to_enrolled`) has no overall/all-types row, so **Overall is computed in Python** in `_build_overall()` as `SUM(enrl_pidm_count) / SUM(app_pidm_count)` per campus/term — a count-weighted rate, **not** an average of the per-type rates (matches the repo's weighted-% rule in the parent `CLAUDE.md`).
- Per-type rates are recomputed from the raw counts (not the pre-rounded `pct_enrolled` column) so per-type lines and the Overall line share one unrounded methodology. NULL/zero denominators yield NaN, never `inf`.
- Per-type lines come from `px.line(color="styp_label")`; the Overall line is added as a separate `go.Scatter` so it renders distinctly. Term labels (`Fall 2024`…) are derived from `mis_term_id` (`year = 2000 + mis_term_id // 10`). NOCE only has the `adult` student type, so its Overall line coincides with the Adult line.
- The Overall line is **black on light themes, white on dark themes** — Plotly traces don't honor the app's CSS `light-dark()`, so the color is picked at render time from `_is_dark_theme()` (falls back to light until the frontend reports the theme; corrects on the next rerun). The matplotlib PDF stays black because it always renders on a white background.
- **Change tables** (`TABLE_SPECS` + `_build_change_table()`): under each chart, **two** tables — one row per student type present at that campus with **Overall** last (bold), then exactly three columns: the fixed Fall 2024 baseline, the latest selected term, and their change. Intermediate terms (Fall 2025, …) are deliberately *not* columns; they stay on the chart, so the tables never widen as years accumulate — Fall 2028 still renders three columns, just with a `5-Yr` header. Declines read negative and are colored red; gains green (`_delta_colors()` picks the pair per theme, same reason as the Overall line).
- **The two tables measure change in different units, and that distinction is load-bearing.** `% Enrolled (Yield)` subtracts two *rates*, so its change is in **percentage points** (`3-Yr Change vs Fall 2024 (pts)`, `-6.5` = the yield fell 6.5 points). `Applied (Headcount)` divides two *counts*, so its change is a **relative percent** (`3-Yr % Change vs Fall 2024`, `-22.6%`). Reading one as the other badly misstates the movement, so each surface labels and formats them differently — including Excel, where the relative change is stored as a fraction under `percent_cols` and the point change as a plain number under `decimal_cols`. Adding a third table means appending a `_TableSpec`; screen, PDF, and Excel all iterate `TABLE_SPECS`.
- A zero baseline in the Applied table yields `NaN`, never `inf` — `baseline.where(baseline != 0)` guards the division.
- **The baseline is fixed at Fall 2024** (`BASELINE_TERM_ID = 247`), *not* the earliest selected term — Fall 2027 will still be measured against Fall 2024. The column header counts years inclusively (`3-Yr Change vs Fall 2024 (pts)` for Fall 2024→2026, `4-Yr` once Fall 2027 lands). When Fall 2024 is not in the term selection the change column is dropped and only the latest term column remains (the tab shows an `st.info` explaining why); when Fall 2024 *is* the latest selected term the table collapses to that one column. Missing cells render as `—`, never as a bogus 0.
- **PDF export**: one matplotlib page per campus — chart on top (explicit `fig.add_axes`, not `subplots`, so the blocks can be positioned), then both change tables stacked beneath it via `_mpl_change_table()` with the same bold-Overall and red/green styling. The three bboxes are hand-tuned to fit an 11×8.5 landscape page; adding a fourth block means re-tuning them.
- **Excel export**: one `chart_data` sheet — a tidy table of per-student-type rows plus the computed Overall rows (Campus, Term, Student Type, Applied, Enrolled, % Enrolled), then both change tables per campus.

Widget prefix: `"ate_"`

## Dual enrollment (`kpi_dual_enrollment.py`)

The KPI - Dual Enrollment tab shows one line chart per **credit campus** (Cypress, Fullerton) of the dual-enrollment headcount by academic year. The source MV (`dwh.mv_dual_enrollment`) has no NOCE row, so `CAMP_MAP` only maps codes `1`/`2`.

- Filtered on `acyr_code` (one of the few KPI tabs on academic year, not term). Year labels (`2024-25`) are derived from `acyr_code` via `_acyr_label()`, matching `config.max_acyr_label()`.
- The MV also carries `concurrent_enroll_count`, but the tab plots **only `dual_enroll_count`** — one line per chart, no second series.
- It's a raw count, not a rate, so the y-axis uses `rangemode="tozero"` (Plotly) / `set_ylim(bottom=0)` (PDF) for an honest trend, with the count printed at each point.
- **PDF export**: one matplotlib page per campus.
- **Excel export**: one `chart_data` sheet — dual-enrollment count pivoted by academic year × campus.

Widget prefix: `"kde_"`

## Admin authentication (`auth.py`, `admin_config.py`)

Protected tabs (currently Mail Admin) require a password before access. The system:

1. **`admin_config.py`** — `PROTECTED_TABS` set defines which tab labels require authentication
2. **`auth.py`** — `render_admin_hub()` shows the admin tab selector after password check. Password stored in `.streamlit/secrets.toml` under `[admin]` section: `password = "your-password"`
3. **`streamlit_app.py`** — splits `TABS` into public and admin lists. Admin button appears in the sidebar below the author line. `on_change` callback on the project dropdown exits admin mode automatically.

Session state keys: `_admin_mode`, `_admin_authenticated`, `_admin_selected_tab`

**Adding a new admin-protected tab**: Add the tab label string to `PROTECTED_TABS` in `admin_config.py`.

## Class Schedule Heatmap drill-down

The heatmap tab (`class_schedule_heatmap.py`) shows section counts by day/time. Below each heatmap, an expander with dropdown selectors (Campus+Day or Day+Hour depending on chart type) lets users drill into a specific cell combination. `_render_drilldown()` shows 4 tables: top 10 Divisions, top 10 Departments, top 10 Subjects, and full Modality breakdown — each with enrollment count and percentage. CRN deduplication (`drop_duplicates(subset=["crn"])`) is applied before aggregation to avoid inflated counts from multiple meeting rows per section.

Widget prefix: `"csh_"`

## Sidebar download exports

Tabs with PDF export (Fast Facts, Class Schedule Heatmap, Seat Count Report, KPI - Persistence, KPI - 1st Time Applied to Enrolled, KPI - Dual Enrollment, all BOT tabs) use `st.sidebar.download_button()` to offer a PDF download. The BOT tabs and all three KPI tabs also show a `Download Excel` button directly below `Download PDF`; each button downloads only the current tab as one `.xlsx` workbook with a single `chart_data` worksheet, not the all-BOT workbook produced by `src.pipeline.bot_excel_export`.

The KPI tabs build their Excel from the underlying chart data via the generic `ExcelSection` / `sections_to_excel_bytes` / `EXCEL_MIME` building blocks in `bot_excel_helpers.py` (these are not BOT-specific — only `generate_bot_excel` and `standard_bot_excel_sections` are). Each KPI tab has a small `_build_excel_sections()` + `_generate_excel()` pair and follows the same `cached_excel_bytes("<prefix>", (id(df),), ...)` / `clear_excel_cache("<prefix>")` pattern as the PDF cache. The exported tables: Persistence → overall rates + counts per campus/term; 1st Time Applied to Enrolled → per-student-type rows plus the computed Overall rows; Dual Enrollment → count by academic year × campus.

For BOT-specific PDF/Excel generator details (paper coordinates, layout gotchas, font sizes), see `docs/bot-tabs.md`.

**Critical ordering rule**: The download button block **must run after the query block**, not before it. Streamlit executes top-to-bottom; if the download check (`if "key" in st.session_state`) runs before the query block that sets that key, the buttons won't appear on the same run as the query — they only show after navigating away and back.

```python
# CORRECT — download block after query block
query_btn = st.sidebar.button("Query", key="xx_query_btn")

if query_btn:
    # ... fetch data, store in st.session_state["xx_data"] ...

if "xx_data" in st.session_state:
    st.sidebar.download_button("Download PDF", data=..., key="xx_pdf_btn")
    st.sidebar.download_button("Download Excel", data=..., key="xx_excel_btn")
```

**Memoize download bytes per filter combination**: `st.download_button` registers `data` in an in-memory media-file store keyed by a content hash, then hands the browser a URL like `/media/<hash>.pdf`. Matplotlib **embeds a creation timestamp in every PDF**, so calling the generator on each rerun (every sidebar widget change triggers one) yields different bytes → different hash → the URL the browser is about to fetch is already invalid. The browser then silently saves Streamlit's 404 HTML response under the `.pdf` filename, producing the "downloaded an HTML file" symptom. Use `cached_pdf_bytes()` / `clear_pdf_cache()` and `cached_excel_bytes()` / `clear_excel_cache()` from `src/scripts/pdf_cache.py` for new download-enabled tabs; the Query handler should clear the cache so a fresh fetch triggers fresh download files. `seat_count_report.py` has an equivalent custom cache pattern because its PDF key depends on cascading filter state.

**PDF rendering approach**: Use matplotlib (not kaleido/plotly `to_image()`). Kaleido 1.x launches a Chrome process to render images, which is slow and causes a visible Chrome window to flash on macOS. Matplotlib renders natively with no browser dependency. Two patterns exist:
- **Table-based**: `ax.table()` renders a DataFrame as a table on a matplotlib axes. Good for small/medium tables. See `fast_facts.py` and `class_schedule_heatmap.py`.
- **Row-by-row drawing**: For long banded reports that span many pages, draw each row with `ax.text()` and `Rectangle` patches directly on a full-page axes (`ax.set_xlim(0, PAGE_W)`). This avoids clipping — rows flow continuously across pages. See `seat_count_report.py` (`_generate_pdf`).

**Page layout**: Use a fixed page size (e.g. `8.5 x 11` portrait for tables, `11 x 8.5` landscape for charts) and position content with `fig.subplots_adjust()` margins. Do **not** use `tight_layout()` or `bbox_inches="tight"` — these shrink-wrap the figure to the content, leaving no room for headers/footers and causing overlaps. Content should fit within the page margins, not fill the entire page.

**Tab title header**: Every exported PDF must include the tab title (e.g. "Fast Facts", "Class Schedule Heatmap") as a `fig.suptitle()` on the first page. This makes it clear which tab the PDF came from when printed or shared.

**Page footer**: Every PDF page must include a footer via `_add_pdf_footer(fig)` called before each `pdf.savefig()`. The footer has the app URL (`https://nocccd.streamlit.app/`) left-justified and the author (`Author: Jihoon Ahn  jahn@nocccd.edu`) right-justified, both in small grey font (`fontsize=7, color="grey"`).
