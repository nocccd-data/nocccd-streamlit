# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

Streamlit dashboards for NOCCCD (North Orange County Community College District) ad-hoc data validation. The app runs in two modes:
- **Local**: queries Oracle EDW directly via `oracledb` + SQLAlchemy
- **Cloud** (Streamlit Cloud): downloads pre-extracted `.hyper` files from Tableau Cloud

A pipeline (`src/pipeline/`) handles the ETL: Oracle → Hyper → Tableau Cloud.

## Workflow: notebooks → nocccd-streamlit

New analyses start as Jupyter notebooks in either **nocccd-scff** (SCFF/funding analyses) or **nocccd-sql** (ad-hoc district queries), where SQL queries and visualization logic are prototyped and validated with stakeholders. Once validated, the analysis is ported here as a production Streamlit tab.

**Source repos:**
- **nocccd-scff**: SCFF degree/award/CTE comparisons — notebooks in `nocccd-scff/notebooks/`, SQL in `nocccd-scff/sql/`
- **nocccd-sql**: Ad-hoc queries (e.g. class schedule heatmap) — notebooks in `nocccd-sql/district/notebooks/`, SQL in `nocccd-sql/district/queries/`

**What gets ported:**
- **SQL queries**: source repo SQL → `src/pipeline/sql/` (adapted for pipeline extraction with acyr/term placeholders)
- **SQL parameterization**: `expand_in_clause()` originated in `nocccd-scff/libs/notebook_utils.py` — the same multi-acyr `IN (:t1...)` regex expansion is used in `data_provider.py` and `extract.py`
- **Crosstab tables**: `build_expandable_crosstab()` in notebook_utils was ported to `_build_expandable_crosstab()` in tab modules for expandable HTML pivot tables
- **Funding status categories**: `derive_funding_status()` (Pell/CCPG/Both/Neither) — same logic in both repos
- **Plotly visualizations**: Interactive charts (e.g. `px.imshow()` heatmaps) are ported directly; PDF export uses matplotlib recreations

When starting a new analysis, prototype in a notebook first, then follow the "Adding a new dataset + tab" checklist below.

## Commands

```bash
# Run the Streamlit app (local/Oracle mode)
streamlit run src/scripts/streamlit_app.py

# Run the app forcing cloud mode (reads from Tableau Cloud instead of Oracle)
FORCE_CLOUD=1 streamlit run src/scripts/streamlit_app.py

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
```

## Architecture

```
Oracle EDW ──► extract.py ──► .hyper files ──► publish.py ──► Tableau Cloud
                                                                   │
                                              Streamlit Cloud ◄────┘
                                              (downloads .hyper at runtime)
```

### Dual-mode data access (`data_provider.py`)

`_is_cloud()` decides the mode: returns `True` if `FORCE_CLOUD=1` env var is set OR `config.ini` doesn't exist (Streamlit Cloud has no Oracle access). Each public `fetch_*()` function is a thin `@st.cache_data(ttl=600)` wrapper around a `_fetch_*_raw()` helper. The `_raw` helpers are un-decorated and can be called without a Streamlit runtime. Note: the mail pipeline does **not** use these `_raw` helpers — it fetches directly from Tableau Cloud Hyper files via `_fetch_from_hyper()` in `mail_config.py` to avoid Oracle and `st.secrets` dependencies.

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
4. **`run.py`** — CLI entry point (`python -m src.pipeline.mail`). Supports `--dry-run` and `--recipient` flags.

**Adding a new report type to the mail system:**
1. Add a `generate_report_pdf(df, params) -> bytes` function in the tab module
2. Add a `_fetch_<report>()` function in `mail_config.py` using `_fetch_from_hyper()`
3. Register in `REPORT_REGISTRY` with fetch_fn, filter_columns, pdf_fn
4. Create campaigns in `CAMPAIGNS` dict with recipients and filters

**Email credentials**: Stored in `.streamlit/secrets.toml` under `[email]` section. Uses a dedicated Gmail account (`nocccd.reports@gmail.com`) with App Password (2-Step Verification must be enabled on the Google account). Tableau Cloud credentials in the same file are used to download Hyper data.

### Tab system (`src/scripts/tabs/`)

`tabs/__init__.py` has a `TABS` list of `(label, render_fn)` tuples. `streamlit_app.py` renders whichever tab is selected in the sidebar.

**Adding a new dataset + tab (full checklist):**
1. Add SQL file to `src/pipeline/sql/`
2. Register dataset in `src/pipeline/config.py` (name, sql_file, param_name, values under semantic key, db_section)
3. Add a `fetch_*()` function in `data_provider.py` — use `_query_oracle()` for multi-acyr SQL or `_query_oracle_single_acyr()` for single-acyr SQL. Pass `db_section=` matching the config entry.
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

### SQL parameterization

Two patterns are supported:
- **Multi-acyr**: SQL uses `IN (:t1...)`. Both `extract.py` and `data_provider.py` dynamically expand the placeholder list to match the number of acyrs via case-insensitive regex substitution (`re.IGNORECASE`). Use `_query_oracle()` in `data_provider.py`. SQL files may use uppercase `IN` or lowercase `in` — both work.
- **Single-acyr**: SQL uses a single named bind like `:mis_acyr_id`. `extract.py` detects this (no `IN` expansion match) and loops over each acyr, concatenating results. Use `_query_oracle_single_acyr()` in `data_provider.py`.

### Sidebar PDF export

Tabs with PDF export (Fast Facts, Class Schedule Heatmap, Seat Count Report) use `st.sidebar.download_button()` to offer a PDF download.

**Critical ordering rule**: The PDF download button block **must run after the query block**, not before it. Streamlit executes top-to-bottom; if the PDF check (`if "key" in st.session_state`) runs before the query block that sets that key, the button won't appear on the same run as the query — it only shows after navigating away and back.

```python
# CORRECT — PDF block after query block
query_btn = st.sidebar.button("Query", key="xx_query_btn")

if query_btn:
    # ... fetch data, store in st.session_state["xx_data"] ...

if "xx_data" in st.session_state:
    st.sidebar.download_button("Download PDF", data=..., key="xx_pdf_btn")
```

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

### Adding themed elements

1. Use `light-dark(light-val, dark-val)` for all color properties
2. Always add `!important` — Streamlit's inline styles have high specificity
3. If colors look wrong, inspect the DOM with Playwright (`browser_snapshot`) to find the actual element and its test-id
4. Portaled elements (dropdowns, dialogs) need rules without ancestor scoping — they live at the document root
5. Add new CSS rules to `THEME_CSS` in `theme.py`; no changes needed to `apply_theme()`

## Configuration

- **Oracle credentials**: `src/pipeline/libs/config.ini` (gitignored; copy from `config.ini.template`)
- **Tableau Cloud PAT**: `.streamlit/secrets.toml` (keys: `SERVER`, `SITE_NAME`, `PAT_NAME`, `PAT_VALUE`)
- **Python version**: pinned to 3.13 in `.python-version` (pantab wheels unavailable for 3.14)

## Deployment

Deployed to Streamlit Cloud at `nocccd.streamlit.app`. Pushes to `main` trigger automatic redeploy. Tableau secrets are configured in the Streamlit Cloud dashboard. After Oracle data changes, re-run the pipeline (`python -m src.pipeline.run`) to refresh Hyper files on Tableau Cloud.

## Key Constraints

- `pantab` must stay pinned to `==5.2.2` (API differences between major versions)
- `streamlit_app.py` inserts repo root into `sys.path` at startup — required for Streamlit Cloud where only the script's directory is on the path
- SQL files and `.hyper` files are gitignored; SQL lives in `src/pipeline/sql/`, hyper output in `src/pipeline/hyper/`
- Oracle Instant Client: `/Users/hoonywise/Oracle/instantclient_23_3` with `lib -> .` symlink (macOS SIP workaround)
