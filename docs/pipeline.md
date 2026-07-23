# Pipeline (`src/pipeline/`)

ETL flow that extracts Oracle data, writes local `.hyper` files, and publishes them to Tableau Cloud.

## Pipeline flow

1. **`config.py`** — defines datasets: name → SQL file + value list + `param_name` + `db_section`. Each dataset stores its values under a semantic key (e.g. `mis_acyr_id`, `acyr_code`, `fisc_year`) and `param_name` tells extract.py which key to read.
2. **`extract.py`** — reads SQL, resolves values via `cfg[param_name]`, expands `IN (:t1...)` or loops single-param SQL, queries Oracle, writes `.hyper` via `pantab.frame_to_hyper()`
3. **`publish.py`** — uploads `.hyper` to "Streamlit Data" project on Tableau Cloud; also has `download_hyper()` which downloads `.tdsx`, extracts `.hyper` from the ZIP
4. **`run.py`** — CLI orchestrator, reads Tableau credentials from `.streamlit/secrets.toml`

## Scheduled refresh & failure isolation

The daily refresh is a **launchd agent** (`~/Library/LaunchAgents/com.nocccd.pipeline.refresh.plist`), not cron and not AppleScript. It runs `python -m src.pipeline.run` with no arguments at 12:00, which selects every dataset whose config lacks `skip_refresh: True`. Runs normally take 143–197 min.

`run.py` has three guards, all added after a July 2026 post-mortem:

- **Preflight** — probes each distinct `db_section` once with `SELECT 1 FROM dual` before extracting. Off VPN the DSN does not resolve and every dataset fails identically; probing once turns 28 duplicate stack traces into one line per section. A section that fails is skipped while other sections still run. Bypass with `--no-preflight`.
- **Per-dataset isolation** — each dataset runs in its own `try`/`except`; one failure no longer aborts the rest. Failures are reported as one line (Oracle puts the actionable `ORA-xxxxx` first) and summarized at the end. *Before this, a single unreachable DSN on the first dataset meant a run that published nothing at all — which is what happened on 12 of the 24 days from 2026-06-25 to 07-18.*
- **Watchdog** — `--timeout` (default 5h) hard-aborts the process via `os._exit`. This must be `os._exit` from a separate thread: a thread blocked inside the Oracle client's C code never returns to the interpreter, so exceptions and signals are never delivered. On 2026-07-18 a mid-run VPN drop left the process blocked in `recv()` for 93 hours, and because **launchd will not start a second instance of a label that is still running**, the next four scheduled refreshes never fired.

Exit codes: `0` all datasets succeeded · `1` some failed or were skipped · `2` unknown dataset name · `3` no section reachable · `75` watchdog abort.

**Connection timeouts are thick-mode-limited.** `libs/sql.py` passes `tcp_connect_timeout` and `expire_time`, but these only bind in *thin* mode. This project runs thick (an Instant Client is present), and a measured probe against an unroutable host with `tcp_connect_timeout=5` still failed at exactly 60.0s — the client's own default. Connects are therefore bounded at 60s either way, but **reads on an already-established socket are not bounded at all**, which is the hang above. Bounding those needs `SQLNET.RECV_TIMEOUT` in a `sqlnet.ora` (machine config outside this repo) and risks killing legitimate long queries — `bot_goal4_xfer_ready` alone runs 11–12 min between round trips. The watchdog is the guard that actually covers this case.

## SQL parameterization

Two patterns are supported by `extract.py`:
- **Multi-acyr**: SQL uses `IN (:t1...)`. The placeholder list is expanded to match the number of values via case-insensitive regex substitution (`re.IGNORECASE`). SQL files may use uppercase `IN` or lowercase `in` — both work, and the count is rebuilt from the config value list, so the SQL can hardcode any starter count (e.g. `IN (:t1,:t2)`). `enrollment_dashboard` uses this to limit its enrichment query to the two terms being compared.
- **Single-acyr**: SQL uses a single named bind like `:mis_acyr_id`. The runner detects this (no `IN` expansion match) and loops over each value, concatenating results.

`extract.py` dispatches on the `IN (:t1` pattern (multi vs single). A SQL file's parameterization style plus its config entry are the single source of truth — no per-caller flag.

**Bind variable arithmetic gotcha**: Avoid `:acyr_code + 1` when the target column is VARCHAR2. The Python-bound `:acyr_code` is VARCHAR2; `+ 1` forces an implicit conversion to NUMBER, and Oracle then applies another implicit conversion to the compared column — **disabling index use and causing full table scans**. Use `TO_CHAR(TO_NUMBER(:acyr_code) + 1)` to keep both sides VARCHAR2 explicitly. See `bot_goal2_wage_denom.sql` for a working example.

**Choosing db_section for performance**: When a query joins tables across REPT and DWHDB, prefer the `db_section` that **minimizes dblink traversal**. For example, `bot_goal2_wage_denom` uses `db_section: "dwhdb"` because it needs `dwh.scff_xfer` (local to DWHDB) plus Banner tables (accessible via `@banner.nocccd.edu` dblink). Running it from REPT with `@dwhdb.nocccd.edu` for the fact table ran for 17+ hours before timing out; running from DWHDB with the dblinks pointing to Banner ran in minutes. The dblink direction matters because Oracle's filter pushdown is sometimes one-way.
