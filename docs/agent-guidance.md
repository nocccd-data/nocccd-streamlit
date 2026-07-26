# Agent Guidance — Overview

Shared engineering guidance for agents working in `nocccd-streamlit`.

This file is loaded on demand from `AGENTS.md` or `CLAUDE.md`; it is not imported automatically so Codex and Claude Code do not both load duplicate instruction files. Read only the sections relevant to the task. For deeper detail on any topic, follow the index below to a topic-specific doc.

## Topic Index

| File | When to read |
|------|--------------|
| `docs/agent-guidance.md` (this file) | Architecture overview, commands, deployment, hard constraints |
| `docs/workflow.md` | Cross-repo workflow (notebooks → streamlit), what gets ported from `nocccd-scff` / `nocccd-sql` |
| `docs/pipeline.md` | `src/pipeline/`: dataset config, extract.py shapes, SQL parameterization, bind-variable + db_section gotchas |
| `docs/tabs.md` | Tab system, adding-a-tab checklist, cascading filters, per-campus Seat Count layout, Persistence projections, Class Schedule Heatmap, admin auth, sidebar download patterns, PDF rendering rules |
| `docs/bot-tabs.md` | All BOT goal/metric tabs, base population rules, `_TITLES` flags, BOT PDF generator + paper coordinates, Excel helpers, BOT-specific gotchas |
| `docs/exports.md` | Bulk exports: `seat_count_export.py`, `bot_export.py`, `bot_excel_export.py` |
| `docs/mail.md` | Mass mailing system, REPORT_REGISTRY, CAMPAIGNS, sender, GitHub Actions workflow |
| `docs/theme.md` | Theme system, light-dark CSS, Streamlit 1.55 gotchas, color palette + NOCCCD brand colors |

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

Deployed to Streamlit Cloud at `nocccd.streamlit.app`. Pushes to `main` trigger automatic redeploy. Tableau secrets are configured in the Streamlit Cloud dashboard. After Oracle data changes, re-run the pipeline (`python -m src.pipeline.run`) to refresh Hyper files on Tableau Cloud.

## Key Constraints

- `pantab` must stay pinned to `==5.2.2` (API differences between major versions)
- `streamlit_app.py` inserts repo root into `sys.path` at startup — required for Streamlit Cloud where only the script's directory is on the path
- SQL files live in `src/pipeline/sql/` (tracked in git); `.hyper` files are gitignored in `src/pipeline/hyper/`
- Oracle Instant Client: `/Users/hoonywise/Oracle/instantclient` with `lib -> .` symlink (macOS SIP workaround)
