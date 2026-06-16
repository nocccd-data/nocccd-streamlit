# nocccd-streamlit

**NOCCCD Data Hub** — Streamlit dashboards for NOCCCD data reporting and analytics. The app reads pre-extracted Hyper files from Tableau Cloud at runtime; Oracle access is limited to the pipeline that refreshes and publishes those Hyper files.

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
├── .github/
│   └── workflows/
│       └── mail-reports.yml      # Manual GitHub Actions workflow for mail dry-runs/sends
├── .streamlit/
│   ├── config.toml               # Streamlit theme settings
│   └── secrets.toml              # Local Tableau/email secrets (gitignored)
├── src/
│   ├── pipeline/                 # ETL: Oracle → Hyper → Tableau Cloud
│   │   ├── config.py             # Dataset definitions, parameters, and value lists
│   │   ├── extract.py            # Query Oracle, write .hyper files
│   │   ├── publish.py            # Upload/download Hyper to/from Tableau Cloud
│   │   ├── run.py                # CLI entry point for pipeline
│   │   ├── seat_count_export.py  # Bulk Seat Count Report PDF export to OneDrive
│   │   ├── bot_export.py         # Combined BOT tabs PDF export to OneDrive
│   │   ├── bot_excel_export.py   # BOT chart-table Excel export
│   │   ├── equity_export.py      # Equity Analysis (PPG-1) Excel export to OneDrive
│   │   ├── mail/                 # Mass mailing system
│   │   │   ├── __main__.py       # `python -m src.pipeline.mail` entry point wrapper
│   │   │   ├── mail_config.py    # Campaign definitions + report registry
│   │   │   ├── report_generator.py # Fetch → filter → PDF → send orchestrator
│   │   │   ├── sender.py         # Gmail SMTP/TLS email sender
│   │   │   └── run.py            # CLI entry point for mail
│   │   ├── sql/                  # SQL query files (one per dataset)
│   │   ├── hyper/                # Generated local .hyper files (gitignored)
│   │   └── libs/
│   │       ├── sql.py            # SQLAlchemy engine factory
│   │       ├── oracle_db_connector.py      # Oracle thick/thin client init
│   │       ├── config.ini        # Oracle credentials (gitignored)
│   │       └── config.ini.template
│   ├── scripts/                  # Streamlit app
│   │   ├── streamlit_app.py      # Main entry point
│   │   ├── data_provider.py      # Cloud-only data access (Hyper from Tableau)
│   │   ├── home_config.py        # Project card config (descriptions, metrics)
│   │   ├── admin_config.py       # Protected tabs configuration
│   │   ├── auth.py               # Admin authentication gate
│   │   ├── pdf_cache.py          # Stable Streamlit PDF/Excel download-byte cache
│   │   ├── theme.py              # Light/dark theme CSS overrides
│   │   └── tabs/                 # Tab modules (one per dashboard)
│   │       ├── __init__.py       # Tab registry
│   │       ├── home.py           # Home landing page with project cards
│   │       ├── fast_facts.py
│   │       ├── seat_count_report.py
│   │       ├── class_schedule_heatmap.py
│   │       ├── kpi_persistence.py
│   │       ├── kpi_applied_to_enrolled.py
│   │       ├── coi_nhrdist_val.py
│   │       ├── mis_sp_submitted_scff.py
│   │       ├── mis_sp_current_scff.py
│   │       ├── mis_fa_submitted_scff.py
│   │       ├── cte_sx_submitted_scff.py
│   │       ├── bot_helpers.py
│   │       ├── bot_excel_helpers.py
│   │       ├── bot_goal1_students.py
│   │       ├── bot_goal2_adt.py
│   │       ├── bot_goal2_assoc.py
│   │       ├── bot_goal2_bac.py
│   │       ├── bot_goal2_cert.py
│   │       ├── bot_goal2_cert_nc.py
│   │       ├── bot_goal2_wage.py
│   │       ├── bot_goal2_xfer.py
│   │       ├── bot_goal3_finaid.py
│   │       ├── bot_goal3_units.py
│   │       ├── equity_analysis.py # Equity Analysis (PPG-1) tab + workbook download
│   │       └── mail_admin.py     # Mail Admin tab (password-protected)
│   └── static/
│       └── NOCCCD Logo.jpg
├── requirements.txt
├── .python-version               # Pins Python 3.13 for Streamlit Cloud
├── docs/
│   ├── agent-guidance.md         # Overview, architecture, commands, deployment
│   ├── workflow.md               # Cross-repo workflow (notebooks → streamlit)
│   ├── pipeline.md               # Pipeline flow, SQL parameterization, gotchas
│   ├── tabs.md                   # Tab system, filters, downloads, PDF rendering
│   ├── bot-tabs.md               # BOT goal/metric tabs, PDF generator, Excel helpers
│   ├── exports.md                # Bulk PDF/Excel exports
│   ├── mail.md                   # Mass mailing system
│   └── theme.md                  # Theme system, color palettes, NOCCCD brand colors
├── AGENTS.md                     # Thin Codex entrypoint
├── CLAUDE.md                     # Thin Claude Code entrypoint
└── README.md
```

## Datasets

Datasets are defined in `src/pipeline/config.py`. Each entry maps a dataset name to its SQL file, parameter key, value list, and Oracle connection section. The pipeline writes one Hyper extract per dataset and publishes it to Tableau Cloud under the same dataset name.

| Dataset | SQL File | Parameter | DB | Used For |
|---------|----------|-----------|----|----------|
| `fast_facts_emp` | `fast_facts_emp.sql` | `fisc_year` | `rept` | Fast Facts employee demographics |
| `fast_facts_stu` | `fast_facts_stu.sql` | `acyr_code` | `rept` | Fast Facts student demographics |
| `coi_nhrdist_val` | `coi_nhrdist_val.sql` | `mis_term_id` | `dwhdb` | COI vs NHRDIST payroll validation |
| `deg_scff` | `deg_scff.sql` | `mis_acyr_id` | `dwhdb` | SCFF degree award source comparison |
| `deg_sp_submitted` | `deg_sp_submitted.sql` | `mis_acyr_id` | `dwhdb` | MIS SP submitted degree comparison |
| `deg_sp_current` | `deg_sp_current.sql` | `mis_acyr_id` | `rept` | MIS SP current degree comparison |
| `deg_fa_scff` | `deg_fa_scff.sql` | `mis_acyr_id` | `dwhdb` | SCFF financial-aid award source comparison |
| `deg_fa_submitted` | `deg_fa_submitted.sql` | `mis_acyr_id` | `dwhdb` | MIS FA submitted award comparison |
| `cte_scff` | `cte_scff.sql` | `mis_acyr_id` | `dwhdb` | SCFF CTE award source comparison |
| `cte_sx_submitted` | `cte_sx_submitted.sql` | `mis_acyr_id` | `dwhdb` | MIS SX submitted CTE comparison |
| `class_schedule_heatmap` | `class_schedule_heatmap.sql` | `mis_term_id` | `dwhdb` | Class Schedule Heatmap tab |
| `kpi_persistence` | `kpi_persistence.sql` | `mis_term_id` | `dwhdb` | KPI - Persistence tab |
| `kpi_applied_to_enrolled` | `kpi_applied_to_enrolled.sql` | `mis_term_id` | `dwhdb` | KPI - Applied to Enrolled tab |
| `enrollment_dashboard` | `enrollment_dashboard.sql` | `banner_term_code` | `dwhdb` | Two-term enrollment-by-date extract enriched with instructional mode + demographics (Banner joins, sliced from the 5-year MV); published to Tableau Cloud only (no app tab yet) |
| `seat_count_report` | `seat_count_report.sql` | `banner_term_code` | `rept` | Seat Count Report tab, mail reports, and bulk PDF export |
| `bot_goal1_students` | `bot_goal1_students.sql` | `acyr_code` | `rept` | BOT Goal 1 Students tab and shared BOT denominator |
| `bot_goal2_cert` | `bot_goal2_cert.sql` | `acyr_code` | `rept` | BOT Goal 2 Certificates tab |
| `bot_goal2_cert_nc` | `bot_goal2_cert_nc.sql` | `acyr_code` | `rept` | BOT Goal 2 Noncredit Certificates tab |
| `bot_goal2_cert_nc_denom` | `bot_goal2_cert_nc_denom.sql` | `acyr_code` | `rept` | Denominator for noncredit certificate rates |
| `bot_goal2_assoc` | `bot_goal2_assoc.sql` | `acyr_code` | `rept` | BOT Goal 2 Associate Degrees tab |
| `bot_goal2_adt` | `bot_goal2_adt.sql` | `acyr_code` | `rept` | BOT Goal 2 ADT tab |
| `bot_goal2_bac` | `bot_goal2_bac.sql` | `acyr_code` | `rept` | BOT Goal 2 Bachelor's Degrees tab |
| `bot_goal2_xfer` | `bot_goal2_xfer.sql` | `acyr_code` | `rept` | BOT Goal 2 Transfers tab |
| `bot_goal2_wage` | `bot_goal2_wage.sql` | `acyr_code` | `rept` | BOT Goal 2 Living Wage tab |
| `bot_goal2_wage_denom` | `bot_goal2_wage_denom.sql` | `acyr_code` | `dwhdb` | Denominator for living-wage rates |
| `bot_goal3_finaid` | `bot_goal3_finaid.sql` | `acyr_code` | `rept` | BOT Goal 3 Financial Aid tab |
| `bot_goal3_units` | `bot_goal3_units.sql` | `acyr_code` | `rept` | BOT Goal 3 Average Units tab |

## Setup

### Prerequisites

- Python 3.13+
- Oracle Instant Client (for pipeline extraction from Oracle)

### Install dependencies

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Configure Oracle credentials (pipeline extraction)

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

## Bulk PDF Export: Seat Count Report → OneDrive

For the Seat Count Report, an on-demand bulk export writes one PDF per (term × campus × division) combination to a local OneDrive folder. The output PDFs match what the Streamlit tab produces when the same filters are selected interactively.

```bash
python -m src.pipeline.seat_count_export
```

- **Source**: reads `src/pipeline/hyper/seat_count_report.hyper` directly. Run the pipeline first if the Hyper file is missing or stale.
- **Destination**: `~/Library/CloudStorage/OneDrive-NorthOrangeCountyCommunityCollegeDistrict/Documents - EST Data/Seat Count Report/<YYYYMMDD>/<Campus>/<Season>/`
- **Filename**: `<term_title>_<campus>_<season>_<division>.pdf` (lowercase, non-alphanumerics collapsed to underscores), e.g. `fall_2025_cypress_fall_business.pdf`. The term portion uses the human-readable `term_title` from the data (e.g. "Fall 2025", "NOCE Spring 2024"), not the numeric Banner term code.
- **Term → season**: term-code suffixes `10`/`15` → Fall, `20`/`35` → Spring, `30`/`05` → Summer
- **Daily snapshots**: each run nests its output under a `YYYYMMDD` folder based on the run date. Same-day re-runs overwrite that day's PDFs; the next calendar day creates a new snapshot directory, so historical exports accumulate naturally.

The destination root is set in the `EXPORT_ROOT` constant at the top of `src/pipeline/seat_count_export.py` — change it there if your OneDrive path differs.

## Bulk PDF Export: BOT Tabs → OneDrive

For the BOT (Board of Trustees) tabs, an on-demand bulk export renders every BOT tab's report into a **single combined PDF** and writes it to a local OneDrive folder. The output pages match what each Streamlit BOT tab produces when its full default academic-year range is selected.

```bash
python -m src.pipeline.bot_export
```

- **Source**: reads `src/pipeline/hyper/bot_*.hyper` directly. Run the pipeline first if any BOT Hyper file is missing or stale.
- **Destination**: `~/Library/CloudStorage/OneDrive-NorthOrangeCountyCommunityCollegeDistrict/Documents - EST Data/BOT Reports/PDF Export/<max_acyr_label>/`, e.g. `PDF Export/2024-25/`. The label comes from the max `acyr_code` in `bot_goal1_students` (`2024` → `2024-25`).
- **Filename**: `bot_<YYYYMMDD>.pdf`, e.g. `bot_20260501.pdf`, using the run date.
- **Combined PDF**: pages from all 10 BOT tabs are concatenated in this order — Goal 1 Students, Goal 2 ADT, Associate Degrees, Bachelor's, Certificates, Noncredit Certificates, Living Wage, Transfers, Goal 3 Financial Aid, Average Units.
- **Snapshots**: each academic-year folder accumulates date-stamped exports. Same-day re-runs overwrite that day's PDF; the next calendar day creates a new file in the same academic-year folder.

The destination root is set in the `EXPORT_ROOT` constant at the top of `src/pipeline/bot_export.py` — change it there if your OneDrive path differs.

## Excel Export: BOT Chart Tables → OneDrive

For the BOT tabs, an on-demand Excel export writes one workbook containing one chart-table sheet per Streamlit BOT tab. The chart-table sheets use the same aggregation and denominator logic as the Streamlit/PDF views, including the noncredit-certificate and living-wage denominator extracts, without exporting the student-level raw Hyper data.

```bash
python -m src.pipeline.bot_excel_export
```

- **Source**: reads `src/pipeline/hyper/bot_*.hyper` directly to build chart tables. Run the pipeline first if any BOT Hyper file is missing or stale.
- **Destination**: `~/Library/CloudStorage/OneDrive-NorthOrangeCountyCommunityCollegeDistrict/Documents - EST Data/BOT Reports/Streamlit Data Export/<max_acyr_label>/`, e.g. `Streamlit Data Export/2024-25/`. The label comes from the max `acyr_code` in `bot_goal1_students` (`2024` → `2024-25`).
- **Filename**: `bot_<YYYYMMDD>.xlsx`, e.g. `bot_20260501.xlsx`, using the run date.
- **Workbook layout**: 10 chart-table sheets, one per displayed BOT metric tab, in the same order as the combined BOT PDF. The denominator extracts are used only for percentage calculations, not exported as raw sheets.
- **Snapshots**: each academic-year folder accumulates date-stamped exports. Same-day re-runs overwrite that day's workbook; the next calendar day creates a new file in the same academic-year folder.

The destination root is set in the `EXPORT_ROOT` constant at the top of `src/pipeline/bot_excel_export.py` — change it there if your OneDrive path differs.

## Excel Export: Equity Analysis (PPG-1) → OneDrive

For internal equity reporting, an on-demand export builds the NOCCCD Equity Gap workbook applying the CCCCO **Percentage Point Gap Minus One (PPG-1)** methodology to the BOT report metrics (Financial Aid excluded per the May 2026 program review). The workbook disaggregates each metric by Race/Ethnicity, Gender, and First-Generation Status, and flags disproportionate impact.

```bash
python -m src.pipeline.equity_export
```

- **Source**: reads the same BOT Hyper extracts as the other BOT exports (`src/pipeline/hyper/bot_*.hyper`). Run the pipeline first if any BOT Hyper file is missing or stale.
- **Destination**: `~/Library/CloudStorage/OneDrive-NorthOrangeCountyCommunityCollegeDistrict/Documents - EST Data/BOT Reports/Equity Analysis/<max_acyr_label>/`, e.g. `Equity Analysis/2024-25/`. The label comes from the max `acyr_code` in `bot_goal1_students` (`2024` → `2024-25`).
- **Filename**: `equity_<YYYYMMDD>.xlsx`, e.g. `equity_20260512.xlsx`, using the run date.
- **Workbook layout**: 6 sheets — `Instructions`, `Summary` (1/2/3 heatmap with race/gender/first-gen sections), `Overall_Inputs` (district totals + thresholds), `Data_Entry` (numerator/denominator values per metric × subgroup × year), `Heatmap_Summary` (PPG-1 result labels), `PPG-1` (full methodology calculation sheet).
- **Methodology**: PPG-1 adjusted gap = Others − Subgroup; SE = `1.96 × √(p̂(1 − p̂)/n)` (CCCCO one-proportion); MOE = `MAX(1.96·SE, 0.02)` (2% floor); DI flagged when `Gap ≥ MOE` per CCCCO Table 1. Subgroups with denominator or numerator below 10 are suppressed as "Insufficient data." Reduce Units to Completion is an average, not a rate — subgroup average compared against district overall using a five-bucket flag (Better / Moderate (Better) / Minimal Difference / Moderate (Worse) / Disparity).
- **Hybrid value/formula strategy**: numerator and denominator cells are **values** from the BOT pipeline that refresh on every re-run. All derived calculations (rates, gaps, SE, MOE, DI flags, heatmap colors) are **live Excel formulas** that recompute on open and stay auditable for analysts who hand-edit denominators.
- **Snapshots**: each academic-year folder accumulates date-stamped exports. Same-day re-runs overwrite that day's workbook via the `.tmp.xlsx` → atomic-rename pattern.
- **Streamlit alternative**: the **Equity Analysis (PPG-1)** tab in the Streamlit app exposes the same workbook behind a Generate/Download button — CLI and tab produce byte-identical output for the same data snapshot.

The destination root is set in the `EXPORT_ROOT` constant at the top of `src/pipeline/equity_export.py` (override via the `BOT_EXPORT_ROOT_EQUITY` env var if your OneDrive path differs).

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

### GitHub Actions workflow

The workflow `.github/workflows/mail-reports.yml` can be triggered manually from the Actions tab with a campaign name and optional dry-run flag.

To confirm whether any automatic delivery schedule is enabled, inspect `.github/workflows/mail-reports.yml` or the GitHub Actions UI.

GitHub Actions secrets required (Settings > Secrets and variables > Actions):
- `TABLEAU_SERVER`, `TABLEAU_SITE_NAME`, `TABLEAU_PAT_NAME`, `TABLEAU_PAT_VALUE` — Tableau Cloud credentials
- `GMAIL_USERNAME`, `GMAIL_APP_PASSWORD` — Gmail SMTP credentials

### Streamlit UI

The **Mail Admin** tab in the Streamlit app provides an interactive interface to preview campaigns, dry-run PDF generation, and send emails with a progress bar.

## Running the Streamlit App

The app reads pre-extracted Hyper files from Tableau Cloud — no Oracle access needed at runtime. Tableau Cloud credentials must be present in `.streamlit/secrets.toml` (or in the Streamlit Cloud Secrets dashboard for the deployed app).

```bash
streamlit run src/scripts/streamlit_app.py
```

To refresh the data the app sees, run the pipeline:

```bash
python -m src.pipeline.run            # all datasets
python -m src.pipeline.run <dataset>  # one dataset
```

The pipeline is the only path that touches Oracle.

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

See `docs/theme.md` for detailed gotchas, the color palette reference, and the NOCCCD brand color table.

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
   - For multi-value extraction, use the pipeline's expandable placeholder pattern: `WHERE acyr_id IN (:t1...)`
   - For single-value extraction, use one named bind such as `WHERE acyr_id = :acyr_code`; the runner loops over configured values
2. Register in `src/pipeline/config.py`:
   ```python
   DATASETS = {
       ...
       "your_dataset": {
           "sql_file": "your_dataset.sql",
           "acyr_code": ["2021", "2022", "2023", "2024"],
           "param_name": "acyr_code",
           "db_section": "dwhdb",
       },
   }
   ```
3. Add a fetch function in `data_provider.py`:
   ```python
   @st.cache_data(ttl=600, show_spinner="Loading data...")
   def fetch_your_dataset(acyr_codes: tuple[str, ...]) -> pd.DataFrame:
       return _download_and_read("your_dataset", "acyr_code", acyr_codes)
   ```
4. Run `python -m src.pipeline.run your_dataset` to extract and publish
