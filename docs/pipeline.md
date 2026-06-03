# Pipeline (`src/pipeline/`)

ETL flow that extracts Oracle data, writes local `.hyper` files, and publishes them to Tableau Cloud.

## Pipeline flow

1. **`config.py`** — defines datasets: name → SQL file + value list + `param_name` + `db_section`. Each dataset stores its values under a semantic key (e.g. `mis_acyr_id`, `acyr_code`, `fisc_year`) and `param_name` tells extract.py which key to read. **Parameterless datasets** omit `param_name` (and the value list) entirely — e.g. `enrollment_5yrs`, whose MV defines its own 5-year window from `SYSDATE`.
2. **`extract.py`** — reads SQL, resolves values via `cfg[param_name]`, expands `IN (:t1...)` or loops single-param SQL, queries Oracle, writes `.hyper` via `pantab.frame_to_hyper()`
3. **`publish.py`** — uploads `.hyper` to "Streamlit Data" project on Tableau Cloud; also has `download_hyper()` which downloads `.tdsx`, extracts `.hyper` from the ZIP
4. **`run.py`** — CLI orchestrator, reads Tableau credentials from `.streamlit/secrets.toml`

## SQL parameterization

Three patterns are supported by `extract.py`:
- **Parameterless**: the dataset config has no `param_name`. The SQL runs once with no binds and the result is written straight to `.hyper`. Use this when the query is self-contained (e.g. an MV that windows itself off `SYSDATE`).
- **Multi-acyr**: SQL uses `IN (:t1...)`. The placeholder list is expanded to match the number of acyrs via case-insensitive regex substitution (`re.IGNORECASE`). SQL files may use uppercase `IN` or lowercase `in` — both work.
- **Single-acyr**: SQL uses a single named bind like `:mis_acyr_id`. The runner detects this (no `IN` expansion match) and loops over each acyr, concatenating results.

`extract.py` dispatches by first checking for a `param_name` (parameterless → run once), then for the `IN (:t1` pattern (multi vs single). A SQL file's parameterization style plus its config entry are the single source of truth — no per-caller flag.

**Large extracts — `chunksize`**: A parameterless dataset whose query returns millions of rows (e.g. `enrollment_5yrs`, ~3.7M rows × 49 cols) sets `"chunksize"` in its config. `extract.py` then streams the result via `pd.read_sql(..., chunksize=N)` and appends each chunk to the `.hyper` with `pantab.frame_to_hyper(..., table_mode="a")`, keeping peak memory bounded instead of materializing the whole result in one DataFrame (which OOM-kills the process — a silent SIGKILL with no traceback). To keep pantab's strict per-chunk column-type matching happy, `_stream_schema()` fixes the schema from the first chunk and coerces every chunk to it: plain `int64` → nullable `Int64` (so a NULL appearing only in a later chunk doesn't break the append) and `object` → nullable `string` (so a column that is entirely NULL *within a chunk* still maps to a concrete Hyper TEXT type rather than an unsupported `na` Arrow type). Don't run two heavy extracts of the same dataset concurrently — a non-chunked run holding the full frame in RAM alongside a chunked run can exhaust memory and get one killed mid-stream.

**Bind variable arithmetic gotcha**: Avoid `:acyr_code + 1` when the target column is VARCHAR2. The Python-bound `:acyr_code` is VARCHAR2; `+ 1` forces an implicit conversion to NUMBER, and Oracle then applies another implicit conversion to the compared column — **disabling index use and causing full table scans**. Use `TO_CHAR(TO_NUMBER(:acyr_code) + 1)` to keep both sides VARCHAR2 explicitly. See `bot_goal2_wage_denom.sql` for a working example.

**Choosing db_section for performance**: When a query joins tables across REPT and DWHDB, prefer the `db_section` that **minimizes dblink traversal**. For example, `bot_goal2_wage_denom` uses `db_section: "dwhdb"` because it needs `dwh.scff_xfer` (local to DWHDB) plus Banner tables (accessible via `@banner.nocccd.edu` dblink). Running it from REPT with `@dwhdb.nocccd.edu` for the fact table ran for 17+ hours before timing out; running from DWHDB with the dblinks pointing to Banner ran in minutes. The dblink direction matters because Oracle's filter pushdown is sometimes one-way.
