# Windows Task Scheduler — daily pipeline refresh (handoff)

**This file is a task prompt for a fresh Claude Code session on the Windows machine.**
It is self-contained: it assumes only that you have read the project `CLAUDE.md`, that
this repo is cloned locally, and that you are on a machine permanently connected to the
district network (no VPN needed). Do not assume any of the author's Mac context.

> **Status:** set up and **live on the office Windows box since 2026-08-01** (the Mac
> launchd job is retired). This doc is now both the record of how it was done and the
> guide to rebuild it on a new machine. Every "Common failures" / "Trap" note below is a
> real failure hit during that cutover, not a hypothetical.

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
   reads `SERVER`, `SITE_NAME`, `PAT_NAME`, `PAT_VALUE` at startup for the publish step.
   Copy it over from the Mac, same as `config.ini` — it is the *second* hand-copied
   credentials file, and the easy one to forget. **Trap:** it is only read on a real
   publish, so a `--extract-only` sanity check passes even when this file is missing —
   the failure (`FileNotFoundError ... secrets.toml`, at startup, before any dataset)
   only surfaces on the first full run. Validate it explicitly with a single-dataset
   *publish*, not just an extract (Step 1).

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
- `DPY-3001: Native Network Encryption and Data Integrity is only supported in ...
  thick mode` → the client fell back to **thin** mode because `ORACLE_HOME`/`ORA_HOME`
  was not set, so it never loaded the Instant Client. The log shows the tell one line
  above: `No Oracle client path resolved from ORA_HOME/ORACLE_HOME; attempting thin
  mode`. The district DB requires Native Network Encryption, which only works in thick
  mode. **Fix: set `ORACLE_HOME`** (see #4). This is the most likely first error on this
  network — it is not `DPI-1047`, because thin mode never tries to load a DLL.
- `DPY-4027: no configuration directory specified` → `ORACLE_HOME` not set in this shell.
- `DPI-1047 ... cannot locate ... Oracle Client` → `ORACLE_HOME` *is* set and the client
  was found, but the DLLs won't load — the VC++ redistributable is missing. (A later,
  different failure than `DPY-3001`: you only reach the DLL-load step once thick mode is
  actually attempted.)
- `ORA-12154 / ORA-12545` → `tnsnames.ora` missing or not found (`TNS_ADMIN` wrong), or
  no network route to the DB host.

Then confirm the **publish path** — the `--extract-only` check above never touched
`secrets.toml` or Tableau, so a full single-dataset run is what actually validates your
credentials (seconds; publishes one tiny dataset):
```powershell
.\.venv\Scripts\python.exe -m src.pipeline.run kpi_dual_enrollment
```
Note: **no** `--extract-only` this time. You want `Done. 1 succeeded` again, but the log
should now also show `Signed into ... Tableau Cloud` and `Published kpi_dual_enrollment`.
A `FileNotFoundError ... secrets.toml` here means prerequisite #3 is missing — the most
common reason the full run fails after the extract-only check passed.

Only once *both* are green, do a full dry run of the real thing:
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
Put both in a wrapper. Create `run_streamlit_pipeline.ps1` at a **plain local path** —
e.g. `C:\Users\<you>\scripts\` — and note the exact path, because the task registration
(Step 3) must point its `-File` at *this same path*; a mismatch makes every scheduled run
fail with "the argument … does not exist". Two rules for where it goes:
- **Not in OneDrive** (or any synced folder). OneDrive Files On-Demand can leave the
  script as a cloud-only placeholder, and when the task fires headless with you logged
  off, OneDrive may not be running to hydrate it — so the task can't find its own script.
  If you keep an authoring copy in OneDrive, the copy the *task* runs must still be the
  local one, and it is the authoritative one to edit.
- **Out of the repo** — it holds machine-specific paths.

```powershell
# run_streamlit_pipeline.ps1 — daily NOCCCD Streamlit data refresh
$ErrorActionPreference = "Stop"

# ---- EDIT: machine-specific paths ----
$Repo       = "C:\path\to\nocccd-streamlit"
$OracleHome = "C:\Oracle\instantclient_23_x"
$LogDir     = "C:\Users\<you>\logs\streamlit-pipeline"   # LOCAL disk — NOT OneDrive (see note)
# --------------------------------------

$env:ORACLE_HOME = $OracleHome
$env:TNS_ADMIN   = Join-Path $OracleHome "network\admin"
$env:PATH        = "$OracleHome;$env:PATH"

New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$Log    = Join-Path $LogDir "nocccd-pipeline.log"
$Python = Join-Path $Repo ".venv\Scripts\python.exe"

Set-Location $Repo
Add-Content $Log "==== run started $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') ===="

# Python's logging writes INFO lines to stderr. On Windows PowerShell 5.1,
# $ErrorActionPreference='Stop' treats the FIRST stderr line a native command emits as
# a terminating error and aborts the wrapper the instant Python logs anything. Native
# stderr is NOT a failure here -- the exit code is the real signal -- so drop to
# Continue for the run. ("Stop" still guarded the setup commands above it.)
$ErrorActionPreference = "Continue"

# run.py returns meaningful non-zero exit codes (1 = partial, 75 = watchdog).
# On PowerShell 7.4+ a native command's non-zero exit throws under
# $ErrorActionPreference='Stop', which would skip the exit-code logging below.
# Disable that so we capture and log the code. (Harmless no-op on PS 5.1.)
$PSNativeCommandUseErrorActionPreference = $false

& $Python -m src.pipeline.run *>> $Log      # *>> redirects ALL streams (stdout+stderr)
$code = $LASTEXITCODE

Add-Content $Log "==== run finished $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') exit=$code ===="
exit $code
```

Three things in that wrapper are deliberate — each fixes a failure hit during the real
cutover:
- **`$ErrorActionPreference = "Continue"` before the Python call.** This is the one that
  will bite you on **Windows PowerShell 5.1** (the default). Python's `logging` writes
  its `INFO` lines to *stderr*, and under the file-top `Stop`, PowerShell treats the
  first stderr line as a fatal error and aborts the wrapper — you'll see
  `python.exe : … - INFO - …` + `NativeCommandError` and the script stops the instant the
  run logs anything. Native stderr is not a failure (the exit code is), so Continue lets
  the run proceed. `Stop` still guards the setup commands above it. *(Note: even with
  Continue, PS 5.1 wraps the very first stderr line as one `NativeCommandError` block at
  the top of the log — cosmetic, harmless; every line after it is clean.)*
- **Keep `$LogDir` on local disk, not in OneDrive / a synced folder.** OneDrive holds a
  file open while syncing it; with `$ErrorActionPreference = "Stop"`, the first
  `Add-Content` could then throw on a sync lock and abort the whole refresh before it
  starts — your logging destination must never be able to kill the run. A synced,
  ever-growing log also churns uploads and spawns conflict copies.
- **`$PSNativeCommandUseErrorActionPreference = $false`** — the PowerShell **7.4+**
  counterpart of the first fix: there, a non-zero native *exit code* throws under `Stop`,
  which would skip the `exit=$code` line and surface a PowerShell exception to Task
  Scheduler instead of a clean `exit=1`/`exit=75`. Harmless no-op on 5.1. (Belt and
  suspenders across both PowerShell versions.)

Test the wrapper by itself once (it will do a full ~3h run and log to `$LogDir`):
```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File C:\Users\<you>\scripts\run_streamlit_pipeline.ps1
```
Watch it in a second window — the launching window sits silent for the whole run
(everything goes to the log), so an early failure won't show there:
```powershell
Get-Content "C:\Users\<you>\logs\streamlit-pipeline\nocccd-pipeline.log" -Wait -Tail 30
```

## Step 3 — register the scheduled task

Use `Register-ScheduledTask` (more capable than `schtasks` for the settings that
actually matter here). Run this in an **elevated** PowerShell (registering a
store-the-password task requires it):

```powershell
# --- MUST match the exact local path where you saved the wrapper in Step 2 ---
# (if these disagree, every scheduled run fails "the argument … does not exist")
$Script = "C:\Users\<you>\scripts\run_streamlit_pipeline.ps1"

$action  = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$Script`""

$trigger = New-ScheduledTaskTrigger -Daily -At "12:00PM"

# One line on purpose: a `#` comment after a line-continuation backtick breaks the
# continuation, and PowerShell then parses each -Parameter as its own command
# ("The term '-WakeToRun' is not recognized..."). See the settings explained below.
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Hours 6) -MultipleInstances IgnoreNew -StartWhenAvailable -WakeToRun -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries

# "Run whether user is logged on or not" needs the account password stored, so the task
# can create a logon session with no interactive user. Supplying -Password does exactly
# that. Get-Credential prompts securely instead of putting the password in the command.
$cred = Get-Credential -UserName "DOMAIN\youruser" -Message "Password for the scheduled-task account"

Register-ScheduledTask -TaskName "NOCCCD Pipeline Refresh" `
    -Action $action -Trigger $trigger -Settings $settings `
    -User $cred.UserName `
    -Password $cred.GetNetworkCredential().Password `
    -RunLevel Limited
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
- **`-User`/`-Password` (stored credential)** — makes it "run whether user is logged on
  or not." The single most common Task Scheduler mistake is leaving it "run only when
  logged on," so it never fires on a locked/headless box. **Run as the human user, not
  `SYSTEM`** — `ORACLE_HOME` is a *User* env var and the venv, `config.ini`, and
  `.streamlit\secrets.toml` all live in that user's profile, which `SYSTEM` cannot see.
- **`-RunLevel Limited`** — the run needs no elevation (Oracle read, `.hyper` write,
  Tableau upload are all user-level); least privilege even if the account is an admin.
- **`-StartWhenAvailable`** — if the machine happens to be off at noon, run at next wake.

> **Password rotation gotcha.** The stored password is a snapshot. If district policy
> forces the account's password to change, the task starts failing to launch
> (`0x8007052E` "password expired" / logon failure) and silently stops running — the
> same silent-outage class we designed against. When you change the password, re-run the
> block above (or update it in Task Scheduler → task → Properties → OK, re-enter). Note it
> if the account is on a rotation policy.

## Step 4 — verify

First confirm it registered, without running it:
```powershell
Get-ScheduledTask     -TaskName "NOCCCD Pipeline Refresh"    # State: Ready (or Disabled)
Get-ScheduledTaskInfo -TaskName "NOCCCD Pipeline Refresh"    # NextRunTime, LastTaskResult
```

**A registered task is enabled and will auto-fire at the next noon.** Do not let that
happen until (a) this box has pulled the resilience code and (b) the Mac scheduler is
out of the way — otherwise you get a stale-code run and/or two machines publishing to the
same Tableau site. Until you are ready, park it:
```powershell
Disable-ScheduledTask -TaskName "NOCCCD Pipeline Refresh"
# ...after the code is pulled and a manual wrapper run is green...
Enable-ScheduledTask  -TaskName "NOCCCD Pipeline Refresh"
```

When you do want a live end-to-end test (full ~3h run that publishes to Tableau):
```powershell
Start-ScheduledTask -TaskName "NOCCCD Pipeline Refresh"
Get-Content "C:\Users\<you>\logs\streamlit-pipeline\nocccd-pipeline.log" -Wait -Tail 20
```
A healthy run ends with `Done. 28 succeeded, 0 failed, 0 skipped of 28.` and the wrapper
appends `exit=0`. `Get-ScheduledTaskInfo` then shows `LastTaskResult 0`.

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
