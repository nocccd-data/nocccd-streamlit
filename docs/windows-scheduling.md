# Windows Task Scheduler — daily pipeline refresh (handoff)

**This file is a task prompt for a fresh Claude Code session on the Windows machine.**
It is self-contained: it assumes only that you have read the project `CLAUDE.md`, that
this repo is cloned locally, and that you are on a machine permanently connected to the
district network (no VPN needed). Do not assume any of the author's Mac context.

## Goal

Move the daily refresh of `python -m src.pipeline.run` off the author's MacBook (a
launchd job that needs the VPN and the laptop to be awake) onto this always-on Windows
box, using **Windows Task Scheduler** — the Windows equivalent of macOS launchd. There
is no AppleScript to port; the Mac side is a launchd plist and the entrypoint is the
same plain Python module you will schedule here.

What the daily run does: for every dataset in `src/pipeline/config.py` that is **not**
marked `skip_refresh: True`, it queries Oracle, writes a local `.hyper` extract, and
publishes it to Tableau Cloud. ~28 datasets, **normally 143–197 minutes end to end.**

## Before you schedule anything: prerequisites this repo does NOT contain

Four things are required at runtime and are **not** in the git clone. Verify each one
before doing anything else. Treat the two credential files as secrets — confirm they
exist and are structurally valid, but never print their values.

1. **Python 3.13** (the repo pins `3.13` in `.python-version`) and a populated venv at
   `.venv\` (note Windows layout: `.venv\Scripts\python.exe`, not `bin/`). If missing:
   ```powershell
   py -3.13 -m venv .venv
   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
   ```

2. **`src\pipeline\libs\config.ini`** — Oracle DB credentials (gitignored). Must have
   two sections matching `config.ini.template`:
   ```ini
   [dwhdb]
   username = ...
   password = ...
   dsn = DWHDB_DB
   [rept]
   username = ...
   password = ...
   dsn = REPT_DB
   ```
   The `dsn` values (`DWHDB_DB`, `REPT_DB`) are **TNS aliases**, resolved from
   `tnsnames.ora` (see #4). The author must copy this file over from the Mac (or
   recreate it) — it cannot be generated from the repo.

3. **`.streamlit\secrets.toml`** — Tableau Cloud credentials (gitignored). `run.py`
   reads `SERVER`, `SITE_NAME`, `PAT_NAME`, `PAT_VALUE`. Also copied over by the author.
   (Only needed for the publish step; a `--extract-only` test run does not read it.)

4. **Oracle Instant Client** (this project runs Oracle **thick** mode). Requirements:
   - Instant Client installed, e.g. `C:\Oracle\instantclient_23_x`.
   - The matching **Microsoft Visual C++ Redistributable** installed — the Instant
     Client DLLs fail to load without it. This is the #1 Windows-only gotcha.
   - `tnsnames.ora` containing `REPT_DB` and `DWHDB_DB` entries, placed in
     `%ORACLE_HOME%\network\admin\` (or a dir pointed to by `TNS_ADMIN`). Copy it from
     the Mac's `network/admin/tnsnames.ora`.
   - The connector (`src/pipeline/libs/oracle_db_connector.py`) already resolves the
     client from the `ORACLE_HOME` (or `ORA_HOME`) environment variable, so you do not
     edit code — you set that env var in the wrapper script below.

## Step 1 — prove connectivity manually before scheduling

Do **not** register a scheduled task until a manual run connects. This mirrors what the
author verified on the Mac and catches the four prerequisites above.

```powershell
$env:ORACLE_HOME = "C:\Oracle\instantclient_23_x"   # your actual path
$env:TNS_ADMIN   = "$env:ORACLE_HOME\network\admin"
$env:PATH        = "$env:ORACLE_HOME;$env:PATH"
cd C:\path\to\nocccd-streamlit

# Smallest possible real check: one tiny dataset, no Tableau upload.
.\.venv\Scripts\python.exe -m src.pipeline.run kpi_dual_enrollment --extract-only
```

Expected tail:
```
[preflight] dwhdb: reachable
[kpi_dual_enrollment] Extracting from Oracle...
  Wrote ...\kpi_dual_enrollment.hyper (6 rows)
Done. 1 succeeded, 0 failed, 0 skipped of 1.
```
`echo $LASTEXITCODE` → `0`.

Common failures and what they mean:
- `DPY-4027: no configuration directory specified` → `ORACLE_HOME` not set in this shell.
- `DPI-1047 ... cannot locate ... Oracle Client` → Instant Client not found, or the VC++
  redistributable is missing.
- `ORA-12154 / ORA-12545` → `tnsnames.ora` missing or not found (`TNS_ADMIN` wrong), or
  no network route to the DB host.

Only once this is green, do a full dry run of the real thing:
```powershell
.\.venv\Scripts\python.exe -m src.pipeline.run --extract-only    # all 28, no upload; ~2–3h
```
Expect `Done. 28 succeeded, 0 failed, 0 skipped of 28.` and exit `0`.

### Exit codes `run.py` returns (you will key alerting off these)
| Code | Meaning |
|------|---------|
| 0 | all datasets succeeded |
| 1 | some datasets failed or were skipped (run still completed) |
| 2 | unknown dataset name on the command line |
| 3 | no database section was reachable (e.g. network down) — nothing ran |
| 75 | watchdog abort: the run exceeded its `--timeout` and was force-killed |

`run.py` already isolates per-dataset failures, preflights each DB section once, and has
an in-process watchdog (`--timeout`, default 5h) that hard-kills a wedged run so it can
never block the next day's run. You do not need to add any of that; you are only wiring
up the scheduler. See `docs/pipeline.md` → "Scheduled refresh & failure isolation".

## Step 2 — create a wrapper script

Task Scheduler, unlike launchd, does not capture stdout/stderr or set env vars for you.
Put both in a wrapper. Create `run_pipeline.ps1` somewhere stable (it contains
machine-specific paths, so keep it **out of the repo** — e.g. `C:\Scripts\`):

```powershell
# run_pipeline.ps1 — daily NOCCCD Streamlit data refresh
$ErrorActionPreference = "Stop"

# ---- EDIT: machine-specific paths ----
$Repo       = "C:\path\to\nocccd-streamlit"
$OracleHome = "C:\Oracle\instantclient_23_x"
$LogDir     = "C:\Logs\nocccd"
# --------------------------------------

$env:ORACLE_HOME = $OracleHome
$env:TNS_ADMIN   = Join-Path $OracleHome "network\admin"
$env:PATH        = "$OracleHome;$env:PATH"

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$Log    = Join-Path $LogDir "nocccd-pipeline.log"
$Python = Join-Path $Repo ".venv\Scripts\python.exe"

Set-Location $Repo
Add-Content $Log "==== run started $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ===="

& $Python -m src.pipeline.run *>> $Log      # *>> redirects ALL streams (stdout+stderr)
$code = $LASTEXITCODE

Add-Content $Log "==== run finished $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') exit=$code ===="
exit $code
```

Test the wrapper by itself once (it will do a full ~3h run and log to `$LogDir`):
```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\Scripts\run_pipeline.ps1
```

## Step 3 — register the scheduled task

Use `Register-ScheduledTask` (more capable than `schtasks` for the settings that
actually matter here). Run this in an **elevated** PowerShell:

```powershell
$action  = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument '-NoProfile -ExecutionPolicy Bypass -File "C:\Scripts\run_pipeline.ps1"'

$trigger = New-ScheduledTaskTrigger -Daily -At 12:00pm

$settings = New-ScheduledTaskSettingsSet `
    -ExecutionTimeLimit (New-TimeSpan -Hours 6) `  # hard stop; > the app's 5h watchdog
    -MultipleInstances IgnoreNew `                 # never overlap two runs
    -StartWhenAvailable `                          # catch up if the box was off at noon
    -WakeToRun                                     # wake from sleep to run (if it sleeps)

# LogonType Password = "Run whether user is logged on or not" — REQUIRED, or the task
# will silently not fire when the machine is locked / no one is logged in.
$principal = New-ScheduledTaskPrincipal -UserId "DOMAIN\youruser" `
    -LogonType Password -RunLevel Limited

Register-ScheduledTask -TaskName "NOCCCD Pipeline Refresh" `
    -Action $action -Trigger $trigger -Settings $settings -Principal $principal
# You will be prompted for the account password (stored by Windows to run headless).
```

Why these settings — each maps to a lesson from the Mac side:
- **`-ExecutionTimeLimit 6h`** is Task Scheduler's own "stop if it runs longer than."
  It is a *backstop* above `run.py`'s in-process 5h watchdog, so the app's clean
  abort (exit 75, with a flushed summary) fires first and this only triggers if even
  that wedges. On the Mac, a hung run with no such limit blocked the schedule for 4
  days — do not omit this.
- **`-MultipleInstances IgnoreNew`** — like launchd, Task Scheduler will not start a
  second copy while one is running. Combined with the timeout above, a stuck run clears
  well before the next noon fire instead of blocking it indefinitely.
- **`-LogonType Password`** — the single most common Windows Task Scheduler mistake is
  leaving it "run only when logged on," so it never runs on a locked/headless box.
- **`-StartWhenAvailable`** — if the machine happens to be off at noon, run at next wake.

## Step 4 — verify

```powershell
Get-ScheduledTask -TaskName "NOCCCD Pipeline Refresh" | Get-ScheduledTaskInfo
Start-ScheduledTask -TaskName "NOCCCD Pipeline Refresh"   # kick it off now as a live test
```
Then watch the log grow: `Get-Content C:\Logs\nocccd\nocccd-pipeline.log -Wait -Tail 20`.
A healthy run ends with `Done. 28 succeeded, 0 failed, 0 skipped of 28.` and the wrapper
appends `exit=0`. `Get-ScheduledTaskInfo` shows `LastTaskResult 0`.

## Step 5 — tell the author to disable the Mac scheduler

**Do not skip this.** Once the Windows task has produced one clean run, the Mac launchd
job must be turned off, or **both machines will publish to the same Tableau site every
day** (wasteful, and the two runs can interleave). The author does this on the Mac, not
you:
```bash
launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.nocccd.pipeline.refresh.plist
```
Report back that Windows is live so they can run that.

## Notes / out of scope
- The daily refresh does **not** run the bulk PDF/Excel export scripts
  (`bot_excel_export.py`, `seat_count_export.py`, `bot_export.py`). Those contain
  hardcoded macOS iCloud paths and are irrelevant to scheduling. If you are ever asked
  to run those on Windows too, they need their output paths fixed first — flag it then.
- `enrollment_dashboard` is intentionally `skip_refresh: True` (its source MV was
  dropped); the no-arg run already excludes it. Leave it alone.
