# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

Streamlit dashboards for NOCCCD (North Orange County Community College District) ad-hoc data validation. The app runs in two modes:
- **Local**: queries Oracle EDW directly via `oracledb` + SQLAlchemy
- **Cloud** (Streamlit Cloud): downloads pre-extracted `.hyper` files from Tableau Cloud

A pipeline (`src/pipeline/`) handles the ETL: Oracle → Hyper → Tableau Cloud.

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

1. **`config.py`** — defines datasets: name → SQL file + term list
2. **`extract.py`** — reads SQL, substitutes `:t1, :t2, ...` term placeholders, queries Oracle, writes `.hyper` via `pantab.frame_to_hyper()`
3. **`publish.py`** — uploads `.hyper` to "Streamlit Data" project on Tableau Cloud; also has `download_hyper()` which downloads `.tdsx`, extracts `.hyper` from the ZIP
4. **`run.py`** — CLI orchestrator, reads Tableau credentials from `.streamlit/secrets.toml`

### Tab system (`src/scripts/tabs/`)

`tabs/__init__.py` has a `TABS` list of `(label, render_fn)` tuples. `streamlit_app.py` renders whichever tab is selected in the sidebar. To add a tab: create a module with a `render()` function and register it in `__init__.py`.

### SQL parameterization

SQL files use `:t1` placeholder convention. Both `extract.py` and `data_provider.py` dynamically expand `IN (:t1...)` to match the number of terms via regex substitution.

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
