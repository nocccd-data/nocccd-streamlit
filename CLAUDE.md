# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

Streamlit dashboards for NOCCCD (North Orange County Community College District) ad-hoc data validation. The app runs in two modes:
- **Local**: queries Oracle EDW directly via `oracledb` + SQLAlchemy
- **Cloud** (Streamlit Cloud): downloads pre-extracted `.hyper` files from Tableau Cloud

A pipeline (`src/pipeline/`) handles the ETL: Oracle → Hyper → Tableau Cloud.

## Workflow: nocccd-scff → nocccd-streamlit

New SCFF analyses start as Jupyter notebooks in **nocccd-scff**, where SQL queries and visualization logic are prototyped and validated with stakeholders. Once validated, the analysis is ported here as a production Streamlit tab.

**What gets ported:**
- **SQL queries**: `nocccd-scff/sql/` → `src/pipeline/sql/` (adapted for pipeline extraction with acyr placeholders)
- **SQL parameterization**: `expand_in_clause()` originated in `nocccd-scff/libs/notebook_utils.py` — the same multi-acyr `IN (:t1...)` regex expansion is used in `data_provider.py` and `extract.py`
- **Crosstab tables**: `build_expandable_crosstab()` in notebook_utils was ported to `_build_expandable_crosstab()` in tab modules for expandable HTML pivot tables
- **Funding status categories**: `derive_funding_status()` (Pell/CCPG/Both/Neither) — same logic in both repos

When starting a new analysis, prototype in nocccd-scff first, then follow the "Adding a new dataset + tab" checklist below.

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
```

## Architecture

```
Oracle EDW ──► extract.py ──► .hyper files ──► publish.py ──► Tableau Cloud
                                                                   │
                                              Streamlit Cloud ◄────┘
                                              (downloads .hyper at runtime)
```

### Dual-mode data access (`data_provider.py`)

`_is_cloud()` decides the mode: returns `True` if `FORCE_CLOUD=1` env var is set OR `config.ini` doesn't exist (Streamlit Cloud has no Oracle access). Each public `fetch_*()` function branches on this to either query Oracle or download from Tableau Cloud. All fetch functions are cached with `@st.cache_data(ttl=600)`.

### Pipeline flow (`src/pipeline/`)

1. **`config.py`** — defines datasets: name → SQL file + value list + `param_name` + `db_section`. Each dataset stores its values under a semantic key (e.g. `mis_acyr_id`, `acyr_code`, `fisc_year`) and `param_name` tells extract.py which key to read.
2. **`extract.py`** — reads SQL, resolves values via `cfg[param_name]`, expands `IN (:t1...)` or loops single-param SQL, queries Oracle, writes `.hyper` via `pantab.frame_to_hyper()`
3. **`publish.py`** — uploads `.hyper` to "Streamlit Data" project on Tableau Cloud; also has `download_hyper()` which downloads `.tdsx`, extracts `.hyper` from the ZIP
4. **`run.py`** — CLI orchestrator, reads Tableau credentials from `.streamlit/secrets.toml`

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

### SQL parameterization

Two patterns are supported:
- **Multi-acyr**: SQL uses `IN (:t1...)`. Both `extract.py` and `data_provider.py` dynamically expand the placeholder list to match the number of acyrs via case-insensitive regex substitution (`re.IGNORECASE`). Use `_query_oracle()` in `data_provider.py`. SQL files may use uppercase `IN` or lowercase `in` — both work.
- **Single-acyr**: SQL uses a single named bind like `:mis_acyr_id`. `extract.py` detects this (no `IN` expansion match) and loops over each acyr, concatenating results. Use `_query_oracle_single_acyr()` in `data_provider.py`.

### Sidebar PDF export

Tabs with PDF export (Fast Facts, Class Schedule Heatmap) use `st.sidebar.download_button()` to offer a PDF download.

**Critical ordering rule**: The PDF download button block **must run after the query block**, not before it. Streamlit executes top-to-bottom; if the PDF check (`if "key" in st.session_state`) runs before the query block that sets that key, the button won't appear on the same run as the query — it only shows after navigating away and back.

```python
# CORRECT — PDF block after query block
query_btn = st.sidebar.button("Query", key="xx_query_btn")

if query_btn:
    # ... fetch data, store in st.session_state["xx_data"] ...

if "xx_data" in st.session_state:
    st.sidebar.download_button("Download PDF", data=..., key="xx_pdf_btn")
```

**PDF rendering approach**: Use matplotlib (not kaleido/plotly `to_image()`). Kaleido 1.x launches a Chrome process to render images, which is slow and causes a visible Chrome window to flash on macOS. Matplotlib renders natively with no browser dependency. See `fast_facts.py` (`_generate_pdf`) and `class_schedule_heatmap.py` (`_generate_pdf` + `_mpl_heatmap`) for examples.

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
