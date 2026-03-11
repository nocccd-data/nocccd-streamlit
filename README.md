# nocccd-streamlit

Streamlit dashboards for NOCCCD ad-hoc data validation. Supports two data modes:

- **Local mode** — queries Oracle EDW directly
- **Cloud mode** — reads pre-extracted Hyper files from Tableau Cloud (used on Streamlit Cloud)

## Architecture

```
Oracle EDW ──► extract.py ──► .hyper files ──► publish.py ──► Tableau Cloud
                                                                   │
                                              Streamlit Cloud ◄────┘
                                              (downloads .hyper at runtime)
```

## Project Structure

```
nocccd-streamlit/
├── src/
│   ├── pipeline/                 # ETL: Oracle → Hyper → Tableau Cloud
│   │   ├── config.py             # Dataset definitions and terms
│   │   ├── extract.py            # Query Oracle, write .hyper files
│   │   ├── publish.py            # Upload/download Hyper to/from Tableau Cloud
│   │   ├── run.py                # CLI entry point for pipeline
│   │   ├── sql/                  # SQL query files (one per dataset)
│   │   ├── hyper/                # Generated .hyper files (gitignored)
│   │   └── libs/
│   │       ├── sql.py            # SQLAlchemy engine factory
│   │       ├── oracle_db_connector.py      # Oracle thick/thin client init
│   │       ├── config.ini        # Oracle credentials (gitignored)
│   │       └── config.ini.template
│   ├── scripts/                  # Streamlit app
│   │   ├── streamlit_app.py      # Main entry point
│   │   ├── data_provider.py      # Dual-mode data access (Oracle / Cloud)
│   │   ├── home_config.py        # Project card config (descriptions, due dates, milestones)
│   │   ├── theme.py              # Light/dark theme CSS overrides
│   │   └── tabs/                 # Tab modules (one per dashboard)
│   │       ├── __init__.py       # Tab registry
│   │       ├── home.py           # Home landing page with project cards
│   │       ├── coi_nhrdist_val.py
│   │       ├── mis_sp_submitted_scff.py
│   │       └── mis_sp_current_scff.py
│   └── static/
│       └── NOCCCD Logo.jpg
├── .streamlit/
│   ├── config.toml              # Theme color palette (light/dark)
│   └── secrets.toml              # Tableau Cloud PAT credentials
├── requirements.txt
├── .python-version               # Pins Python 3.13 for Streamlit Cloud
└── CLAUDE.md
```

## Datasets

| Name | SQL File | Description |
|------|----------|-------------|
| `coi_nhrdist_val` | `coi_nhrdist_val.sql` | COI vs NHRDIST payroll validation |
| `deg_scff` | `deg_scff.sql` | SCFF financial aid awards |
| `deg_sp_submitted` | `deg_sp_submitted.sql` | Degree SP submitted vs SCFF match |
| `deg_sp_current` | `deg_sp_current.sql` | Degree SP current vs SCFF match |

## Setup

### Prerequisites

- Python 3.13+
- Oracle Instant Client (for local Oracle access)

### Install dependencies

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Configure Oracle credentials (local mode)

Copy the template and fill in your Oracle credentials:

```bash
cp src/pipeline/libs/config.ini.template src/pipeline/libs/config.ini
```

Edit `config.ini`:

```ini
[dwh]
username = YOUR_USERNAME
password = YOUR_PASSWORD
dsn = YOUR_DSN

[rept]
username = YOUR_USERNAME
password = YOUR_PASSWORD
dsn = YOUR_DSN
```

### Configure Tableau Cloud credentials

Create `.streamlit/secrets.toml`:

```toml
SERVER = "https://us-west-2b.online.tableau.com"
SITE_NAME = "nocccd"
PAT_NAME = "your-pat-name"
PAT_VALUE = "your-pat-value"
```

These secrets are also used by the pipeline CLI and by Streamlit Cloud at runtime.

## Pipeline: Oracle to Tableau Cloud

The pipeline extracts data from Oracle into `.hyper` files and publishes them to the **Streamlit Data** project on Tableau Cloud.

### Extract and publish all datasets

```bash
python -m src.pipeline.run
```

### Extract and publish a single dataset

```bash
python -m src.pipeline.run coi_nhrdist_val
```

### Extract only (skip Tableau Cloud upload)

```bash
python -m src.pipeline.run --extract-only
python -m src.pipeline.run coi_nhrdist_val --extract-only
```

Hyper files are written to `src/pipeline/hyper/`.

## Running the Streamlit App

### Local mode (Oracle)

Queries Oracle directly using `config.ini` credentials:

```bash
streamlit run src/scripts/streamlit_app.py
```

### Local mode with forced cloud data path

Reads from Tableau Cloud instead of Oracle, useful for testing the cloud data path end-to-end:

```bash
FORCE_CLOUD=1 streamlit run src/scripts/streamlit_app.py
```

### How mode detection works

`data_provider.py` decides which mode to use:

1. If `FORCE_CLOUD=1` env var is set, use cloud mode
2. If `src/pipeline/libs/config.ini` does not exist, use cloud mode (Streamlit Cloud)
3. Otherwise, use local Oracle mode

## Streamlit Cloud Deployment

The app is deployed at [nocccd.streamlit.app](https://nocccd.streamlit.app).

- Python version is pinned to 3.13 via `.python-version`
- Tableau Cloud secrets are configured in the Streamlit Cloud dashboard (Settings > Secrets)
- On each push to `main`, Streamlit Cloud redeploys automatically
- The app downloads `.hyper` files from Tableau Cloud at runtime (no Oracle access needed)

### Updating cloud data

When underlying Oracle data changes, re-run the pipeline to refresh the Hyper files on Tableau Cloud:

```bash
python -m src.pipeline.run
```

The Streamlit Cloud app caches data for 10 minutes (`ttl=600`), so changes appear within that window.

## Theme

The app supports light/dark mode via Streamlit 1.55's built-in theme toggle (visible in the app menu).

- **`.streamlit/config.toml`** defines the color palette — backgrounds, text, sidebar, and dataframe styling for both light and dark modes
- **`src/scripts/theme.py`** injects CSS overrides using the `light-dark()` CSS function, plus a JS `MutationObserver` that syncs the color scheme to portaled elements (e.g., selectbox dropdowns rendered outside the main app container)
- `apply_theme()` is called once from `streamlit_app.py` — no per-tab setup needed

See `CLAUDE.md` for detailed theme gotchas, color reference table, and guidance on adding new themed elements.

## Adding a New Tab

1. Create `src/scripts/tabs/your_tab.py` with a `render()` function
2. Register it in `src/scripts/tabs/__init__.py`:
   ```python
   from .your_tab import render as your_tab_render

   TABS = [
       ...
       ("Your Tab Label", your_tab_render),
   ]
   ```
3. Add a corresponding fetch function in `data_provider.py` if it needs new data
4. Add the dataset config in `src/pipeline/config.py` and SQL in `src/pipeline/sql/`
5. Run the pipeline to extract and publish the new dataset

## Adding a New Dataset

1. Add the SQL query to `src/pipeline/sql/your_dataset.sql`
   - Use `:t1, :t2, ...` placeholders for term filtering: `WHERE term_id IN (:t1)`
2. Register in `src/pipeline/config.py`:
   ```python
   DATASETS = {
       ...
       "your_dataset": {
           "sql_file": "your_dataset.sql",
           "terms": ["220", "230", "240", "250"],
       },
   }
   ```
3. Add a fetch function in `data_provider.py`:
   ```python
   @st.cache_data(ttl=600, show_spinner="Loading data...")
   def fetch_your_dataset(terms: tuple[str, ...]) -> pd.DataFrame:
       if _is_cloud():
           return _download_and_read("your_dataset", "term_id", terms)
       return _query_oracle(_SQL_DIR / "your_dataset.sql", terms)
   ```
4. Run `python -m src.pipeline.run your_dataset` to extract and publish
