# nocccd-streamlit

**NOCCCD Data Hub** — Streamlit dashboards for NOCCCD data reporting and analytics. Supports two data modes:

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
│   │   ├── config.py             # Dataset definitions and acyrs
│   │   ├── extract.py            # Query Oracle, write .hyper files
│   │   ├── publish.py            # Upload/download Hyper to/from Tableau Cloud
│   │   ├── run.py                # CLI entry point for pipeline
│   │   ├── mail/                 # Mass mailing system
│   │   │   ├── mail_config.py    # Campaign definitions + report registry
│   │   │   ├── report_generator.py  # Fetch → filter → PDF → send orchestrator
│   │   │   ├── sender.py         # Gmail SMTP/TLS email sender
│   │   │   └── run.py            # CLI entry point for mail
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
│   │   ├── home_config.py        # Project card config (descriptions, metrics)
│   │   ├── admin_config.py       # Protected tabs configuration
│   │   ├── auth.py               # Admin authentication gate
│   │   ├── theme.py              # Light/dark theme CSS overrides
│   │   └── tabs/                 # Tab modules (one per dashboard)
│   │       ├── __init__.py       # Tab registry
│   │       ├── home.py           # Home landing page with project cards
│   │       ├── fast_facts.py
│   │       ├── seat_count_report.py
│   │       ├── class_schedule_heatmap.py
│   │       ├── persistence_by_styp.py
│   │       ├── coi_nhrdist_val.py
│   │       ├── mis_sp_submitted_scff.py
│   │       ├── mis_sp_current_scff.py
│   │       ├── mis_fa_submitted_scff.py
│   │       ├── cte_sx_submitted_scff.py
│   │       └── mail_admin.py     # Mail Admin tab (password-protected)
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
| `fast_facts_stu` | `fast_facts_stu.sql` | Student demographics by academic year |
| `fast_facts_emp` | `fast_facts_emp.sql` | Employee demographics by fiscal year |
| `seat_count_report` | `seat_count_report.sql` | Section seat counts and fill rates |
| `class_schedule_heatmap` | `class_schedule_heatmap.sql` | Class schedule by day/time for heatmap |
| `persistence_by_styp` | `persistence_by_styp.sql` | Persistence rates by student type |
| `coi_nhrdist_val` | `coi_nhrdist_val.sql` | COI vs NHRDIST payroll validation |
| `deg_scff` | `deg_scff.sql` | SCFF financial aid awards |
| `deg_sp_submitted` | `deg_sp_submitted.sql` | Degree SP submitted vs SCFF match |
| `deg_sp_current` | `deg_sp_current.sql` | Degree SP current vs SCFF match |
| `deg_fa_scff` | `deg_fa_scff.sql` | SCFF FA financial aid awards |
| `deg_fa_submitted` | `deg_fa_submitted.sql` | FA submitted vs SCFF match |
| `cte_scff` | `cte_scff.sql` | SCFF CTE awards |
| `cte_sx_submitted` | `cte_sx_submitted.sql` | CTE SX submitted vs SCFF match |

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

### Scheduled daily refresh (macOS launchd)

A launch agent runs the pipeline daily at noon in the background (no terminal window). Requires VPN connection to reach Oracle. If VPN is not connected, it fails silently and logs to `~/Library/Logs/nocccd-pipeline.log`.

Plist location: `~/Library/LaunchAgents/com.nocccd.pipeline.refresh.plist`

```bash
# Check the log
cat ~/Library/Logs/nocccd-pipeline.log

# Run it right now (to test)
launchctl start com.nocccd.pipeline.refresh

# Disable it
launchctl unload ~/Library/LaunchAgents/com.nocccd.pipeline.refresh.plist

# Re-enable it
launchctl load ~/Library/LaunchAgents/com.nocccd.pipeline.refresh.plist
```

## Mass Mailing: Filtered PDF Reports

The mail system generates filtered PDF reports and emails them to specific recipients. Each recipient gets a PDF filtered to their campus/division/department. Data is fetched from **Tableau Cloud Hyper files** (same pre-extracted data the Streamlit Cloud app uses), not Oracle directly.

### Configure credentials

Add to `.streamlit/secrets.toml`:

```toml
# Tableau Cloud credentials (already present for the pipeline)
SERVER = "https://..."
SITE_NAME = "nocccd"
PAT_NAME = "..."
PAT_VALUE = "..."

# Gmail SMTP for mass mailing
[email]
smtp_server = "smtp.gmail.com"
smtp_port = 587
smtp_username = "nocccd.reports@gmail.com"
smtp_password = "your-gmail-app-password"
from_email = "nocccd.reports@gmail.com"
from_name = "NOCCCD ESIE Data Team"
```

The Gmail account requires 2-Step Verification enabled and an App Password generated (Google Account > Security > App Passwords).

### Define campaigns

Edit `src/pipeline/mail/mail_config.py` to configure campaigns with report types, parameters, and recipient lists.

### CLI usage

```bash
# List available campaigns
python -m src.pipeline.mail

# Dry run — generate PDFs without sending
python -m src.pipeline.mail seat_count_fall2025_by_campus --dry-run

# Send to a single recipient for testing
python -m src.pipeline.mail seat_count_fall2025_by_campus --recipient "Test Recipient"

# Send to all recipients
python -m src.pipeline.mail seat_count_fall2025_by_campus
```

### Scheduled delivery (GitHub Actions)

The workflow `.github/workflows/mail-reports.yml` sends reports automatically at **9am PDT weekdays**. It can also be triggered manually from the Actions tab with a campaign name and optional dry-run flag.

To adjust the schedule, edit the cron line in `.github/workflows/mail-reports.yml`. GitHub Actions cron uses **UTC only** and does not auto-adjust for daylight saving:

| Schedule | Cron | Notes |
|----------|------|-------|
| 9am PDT (default) | `0 16 * * 1-5` | Mar–Nov (daylight saving) |
| 9am PST | `0 17 * * 1-5` | Nov–Mar (standard time) |
| 8am PDT | `0 15 * * 1-5` | One hour earlier |
| Noon PDT | `0 19 * * 1-5` | |

The `1-5` means Monday–Friday. During the DST/PST switch, the schedule shifts by 1 hour.

GitHub Actions secrets required (Settings > Secrets and variables > Actions):
- `TABLEAU_SERVER`, `TABLEAU_SITE_NAME`, `TABLEAU_PAT_NAME`, `TABLEAU_PAT_VALUE` — Tableau Cloud credentials
- `GMAIL_USERNAME`, `GMAIL_APP_PASSWORD` — Gmail SMTP credentials

### Streamlit UI

The **Mail Admin** tab in the Streamlit app provides an interactive interface to preview campaigns, dry-run PDF generation, and send emails with a progress bar.

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
   - Use `:t1, :t2, ...` placeholders for acyr filtering: `WHERE acyr_id IN (:t1)`
2. Register in `src/pipeline/config.py`:
   ```python
   DATASETS = {
       ...
       "your_dataset": {
           "sql_file": "your_dataset.sql",
           "acyrs": ["220", "230", "240", "250"],
       },
   }
   ```
3. Add a fetch function in `data_provider.py`:
   ```python
   @st.cache_data(ttl=600, show_spinner="Loading data...")
   def fetch_your_dataset(acyrs: tuple[str, ...]) -> pd.DataFrame:
       if _is_cloud():
           return _download_and_read("your_dataset", "acyr_id", acyrs)
       return _query_oracle(_SQL_DIR / "your_dataset.sql", acyrs)
   ```
4. Run `python -m src.pipeline.run your_dataset` to extract and publish
