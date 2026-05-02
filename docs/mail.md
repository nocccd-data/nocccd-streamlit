# Mass Mailing System (`src/pipeline/mail/`)

Generates filtered PDF reports and emails them to recipients via Gmail SMTP (`nocccd.reports@gmail.com`).

## Modules

1. **`mail_config.py`** — `REPORT_REGISTRY` maps report types to fetch/filter/PDF functions. `CAMPAIGNS` defines mail jobs with parameters, subject/body templates, and recipient lists with per-recipient filter overrides. Data is fetched from **Tableau Cloud Hyper files** (same source as Streamlit Cloud), not Oracle — this avoids Oracle dependencies and uses pre-extracted data. The `_fetch_from_hyper()` helper loads Tableau credentials directly from `secrets.toml` (no `st.secrets`).
2. **`report_generator.py`** — orchestrator: fetches data **once** from Tableau Cloud, then for each recipient applies filters, generates PDF, sends email. Returns `list[SendResult]` with success/failure per recipient. Accepts a `progress_callback` for UI integration.
3. **`sender.py`** — sends a single email with PDF attachment via Gmail SMTP/TLS (`nocccd.reports@gmail.com`, port 587, app password auth). Rate-limited with `time.sleep(2)` between sends.
4. **`run.py`** — CLI entry point (`python -m src.pipeline.mail`). Supports `--dry-run` and `--recipient` flags. The package `__main__.py` wrapper must call `sys.exit(main())` so GitHub Actions receives non-zero failure codes.

## Adding a new report type to the mail system

1. Add a `generate_report_pdf(df, params) -> bytes` function in the tab module
2. Add a `_fetch_<report>()` function in `mail_config.py` using `_fetch_from_hyper()`
3. Register in `REPORT_REGISTRY` with fetch_fn, filter_columns, pdf_fn
4. Create campaigns in `CAMPAIGNS` dict with recipients and filters

## Email credentials

Stored in `.streamlit/secrets.toml` under `[email]` section. Uses a dedicated Gmail account (`nocccd.reports@gmail.com`) with App Password (2-Step Verification must be enabled on the Google account). Tableau Cloud credentials in the same file are used to download Hyper data.

## GitHub Actions workflow

`.github/workflows/mail-reports.yml` supports manual triggers from the Actions tab and maps GitHub repo secrets into `secrets.toml` at runtime. Do not describe any automatic mail schedule as active unless the workflow's `schedule:` block is currently enabled.
