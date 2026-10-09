# Agent Guidance — Overview

Shared engineering guidance for agents working in `nocccd-streamlit`.

This file is loaded on demand from `AGENTS.md` or `CLAUDE.md`; it is not imported automatically so Codex and Claude Code do not both load duplicate instruction files. Read only the sections relevant to the task. For deeper detail on any topic, follow the index below to a topic-specific doc.

## Topic Index

| File | When to read |
|------|--------------|
| `docs/agent-guidance.md` (this file) | Architecture overview, commands, deployment, hard constraints |
| `docs/workflow.md` | Cross-repo workflow (notebooks → streamlit), what gets ported from `nocccd-scff` / `nocccd-sql` |
| `docs/pipeline.md` | `src/pipeline/`: dataset config, extract.py shapes, SQL parameterization, bind-variable + db_section gotchas, scheduled refresh & failure isolation |
| `docs/windows-scheduling.md` | The daily refresh: Windows Task Scheduler (the current setup, live since 2026-08-01) |
| `docs/macos-scheduling.md` | The retired macOS launchd job (fallback / historical) |
| `docs/tabs.md` | Tab system, adding-a-tab checklist, cascading filters, per-campus Seat Count layout, KPI tabs (Persistence projections, NOCE excl. credit chart + difference table, Applied-to-Enrolled, Dual Enrollment), Class Schedule Heatmap, admin auth, sidebar download patterns, PDF rendering rules |
| `docs/bot-tabs.md` | All BOT goal/metric tabs, base population rules, `_TITLES` flags, BOT PDF generator + paper coordinates, Excel helpers, BOT-specific gotchas |
| `docs/exports.md` | Bulk exports: `seat_count_export.py`, `bot_export.py`, `bot_excel_export.py`, `equity_export.py` (Equity Analysis PPG-1) |
| `docs/mail.md` | Mass mailing system, REPORT_REGISTRY, CAMPAIGNS, sender, GitHub Actions workflow |
| `docs/theme.md` | Theme system, light-dark CSS, Streamlit 1.55 gotchas, color palette + NOCCCD brand colors |
| `docs/deferred.md` | Known issues deliberately left unfixed, and the decision each one is waiting on |

## What This Is

Streamlit dashboards for NOCCCD (North Orange County Community College District) data reporting and analytics — the **NOCCCD Data Hub**. The app reads pre-extracted `.hyper` files from Tableau Cloud at runtime; it never queries Oracle directly. Oracle access is confined to the pipeline (`src/pipeline/`), which extracts data from Oracle EDW and publishes Hyper files to Tableau Cloud on a daily schedule.

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

# Equity Analysis (PPG-1) workbook to OneDrive (on demand; same output as the tab's download)
python -m src.pipeline.equity_export
```

Use `.venv/` unless told otherwise. Use `ruff` for Python linting.

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

## Configuration

- **Oracle credentials**: `src/pipeline/libs/config.ini` (gitignored; copy from `config.ini.template`)
- **Tableau Cloud PAT**: `.streamlit/secrets.toml` (keys: `SERVER`, `SITE_NAME`, `PAT_NAME`, `PAT_VALUE`)
- **Admin password**: `.streamlit/secrets.toml` under `[admin]` section (key: `password`)
- **Email credentials**: `.streamlit/secrets.toml` under `[email]` section (Gmail SMTP for mass mailing)
- **Python version**: pinned to 3.13 in `.python-version` (pantab wheels unavailable for 3.14)

## Deployment

Deployed to Streamlit Cloud at `nocccd.streamlit.app`. Pushes to `main` trigger automatic redeploy. Tableau secrets are configured in the Streamlit Cloud dashboard. The daily refresh of the Hyper files on Tableau Cloud runs on a Windows box under Task Scheduler and pulls `main` itself before each run (non-fatal; a changed `requirements.txt` is flagged, not installed — see `docs/windows-scheduling.md`); to refresh sooner after Oracle data changes, run the pipeline by hand (`python -m src.pipeline.run [dataset]`).

## Key Constraints

- `pantab` must stay pinned to `==5.2.2` (API differences between major versions)
- **`requirements.txt` is a full lock**: the 14 direct dependencies plus every transitive one (77 packages), at the exact versions the local `.venv` runs. While it was unpinned, the live app picked up a newer Streamlit whose selectbox no longer matches the theme CSS, and the sidebar dropdowns went white-on-white in light mode (noticed 2026-10-09; reproduced on 1.65.0, see `docs/theme.md`). An unpinned rebuild would also pull untested majors such as pandas 3, plotly 7 and pyarrow 26.
  - **Who installs it:**
    - Streamlit Cloud, on every rebuild. Its Python version is set in the Cloud app settings, not in this repo. The lock assumes **3.13** (as in `.python-version`), and numpy/pandas need ≥ 3.11.
    - `.github/workflows/mail-reports.yml` (Python 3.13).
    - The Windows refresh box only *flags* a changed file. Run `pip install -r requirements.txt` there by hand to match.
  - **Test-only packages** (pytest, PyMuPDF, openpyxl) live in `requirements-dev.txt`, listed alone so Dependabot doesn't count every locked package twice. Install both files: `pip install -r requirements.txt -r requirements-dev.txt`. Cloud never installs the dev file.
  - **Dependabot alerts watch the lock.** Pinning makes them visible, and a locked version stays vulnerable until someone bumps it, so leave the alerts on. For a security bump, take each package's **highest** first patched version across all its open advisories, the smallest version that clears every one of them. For example, cryptography's advisories were patched in 46.0.6, 46.0.7, 48.0.1, 49.0.0 and 50.0.0, so it goes to 50.0.0, not 46.0.6. Bump those in `.venv` and regenerate (step 2 below). Check the diff: only the bumped packages should move.
  - **To upgrade**, in its own PR:
    1. Bump the direct pin(s) in `.venv` (`pip install <pkg>==<new>`).
    2. Regenerate the lock from a fresh venv: install the direct pins with `-c <(.venv/bin/pip freeze)`, then `pip freeze`. Keep the direct/transitive sections.
    3. Run `pytest` in a fresh venv with both files installed.
    4. Check every tab in both themes.
    5. Reinstall on the Windows box.
- `streamlit_app.py` inserts repo root into `sys.path` at startup — required for Streamlit Cloud where only the script's directory is on the path
- SQL files live in `src/pipeline/sql/` (tracked in git); `.hyper` files are gitignored in `src/pipeline/hyper/`
- Oracle Instant Client: `/Users/hoonywise/Oracle/instantclient` with `lib -> .` symlink (macOS SIP workaround)
