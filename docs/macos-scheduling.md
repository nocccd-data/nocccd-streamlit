# macOS launchd — daily pipeline refresh (reference)

This documents the **current** macOS scheduling of `python -m src.pipeline.run`, so the
setup is reproducible from git rather than living only on one laptop. Its Windows
counterpart is `docs/windows-scheduling.md`; the two are kept parallel on purpose.

> **Note:** despite being informally called "the AppleScript," there is no AppleScript
> involved. The scheduler is a **launchd** LaunchAgent. launchd is macOS's native job
> scheduler (the Windows equivalent is Task Scheduler).

## Goal

Run the daily Oracle → `.hyper` → Tableau Cloud refresh once a day on the author's Mac.
For every dataset in `src/pipeline/config.py` that is **not** `skip_refresh: True`, the
run queries Oracle, writes a local `.hyper` extract, and publishes it to Tableau Cloud.
~28 datasets, **normally 143–197 minutes end to end.**

This machine requires the **district VPN** to be connected for the Oracle DSNs to
resolve — which is the reason the refresh is being moved to an always-on Windows box
(see `docs/windows-scheduling.md`). Keep this doc current as the fallback / historical
record even after the cutover.

## Prerequisites this repo does NOT contain

Same four runtime dependencies as Windows; none are in the git clone.

1. **Python 3.13** (`.python-version` pins `3.13`) and a populated venv at `.venv/`
   (macOS layout: `.venv/bin/python`):
   ```bash
   python3.13 -m venv .venv
   .venv/bin/python -m pip install -r requirements.txt
   ```

2. **`src/pipeline/libs/config.ini`** — Oracle DB credentials (gitignored). Two sections
   matching `config.ini.template`, with `dsn = DWHDB_DB` and `dsn = REPT_DB` (TNS
   aliases resolved from `tnsnames.ora`).

3. **`.streamlit/secrets.toml`** — Tableau Cloud credentials (gitignored): `SERVER`,
   `SITE_NAME`, `PAT_NAME`, `PAT_VALUE`. Needed only for the publish step.

4. **Oracle Instant Client** (thick mode), at `/Users/hoonywise/Oracle/instantclient`:
   - **SIP symlink workaround** — macOS System Integrity Protection strips `DYLD_*`
     environment variables from child processes, so `DYLD_LIBRARY_PATH` cannot be used
     to point at the client libs. The fix in place is a self-symlink inside the client
     dir so `$ORACLE_HOME/lib/libclntsh.dylib` resolves on its own:
     ```bash
     ln -s . /Users/hoonywise/Oracle/instantclient/lib
     ```
     Without this, thick-mode init fails with `DPI-1047 (cannot locate Oracle Client)`.
   - `tnsnames.ora` with `REPT_DB` and `DWHDB_DB` entries lives at
     `$ORACLE_HOME/network/admin/tnsnames.ora`. The plist does **not** set `TNS_ADMIN`;
     the thick client finds it at that default location automatically.
   - The connector (`src/pipeline/libs/oracle_db_connector.py`) resolves the client from
     the `ORACLE_HOME` env var, which the plist sets (below).

## Step 1 — prove connectivity manually

With the VPN connected:
```bash
export ORACLE_HOME=/Users/hoonywise/Oracle/instantclient
cd /Users/hoonywise/GitHub/nocccd-data/nocccd-streamlit

# Smallest real check: one tiny dataset, no Tableau upload.
.venv/bin/python -m src.pipeline.run kpi_dual_enrollment --extract-only
```
Expected tail:
```
[preflight] dwhdb: reachable
[kpi_dual_enrollment] Extracting from Oracle...
  Wrote .../kpi_dual_enrollment.hyper (6 rows)
Done. 1 succeeded, 0 failed, 0 skipped of 1.
```
`echo $?` → `0`.

Common failures:
- `DPY-4027: no configuration directory specified` → `ORACLE_HOME` not exported in this
  shell (an interactive shell does not inherit what the plist sets).
- `DPI-1047 ... cannot locate ... Oracle Client` → Instant Client missing, or the SIP
  self-symlink (prereq #4) is absent.
- `ORA-12154 / ORA-12545` → VPN not connected, or `tnsnames.ora` not found.

### Exit codes `run.py` returns
| Code | Meaning |
|------|---------|
| 0 | all datasets succeeded |
| 1 | some datasets failed or were skipped (run still completed) |
| 2 | unknown dataset name on the command line |
| 3 | no database section was reachable (e.g. VPN down) — nothing ran |
| 75 | watchdog abort: the run exceeded its `--timeout` and was force-killed |

`run.py` already isolates per-dataset failures, preflights each DB section once, and has
an in-process watchdog (`--timeout`, default 5h) that hard-kills a wedged run.
**On macOS the watchdog is the *only* run-duration guard** — launchd has no built-in
"stop if it runs longer than N" (unlike Task Scheduler's `ExecutionTimeLimit`). That
watchdog exists because of a real incident: on 2026-07-18 a mid-run VPN drop left this
job blocked inside the Oracle client for 93 hours, and because launchd will not start a
second instance of a running label, the next four daily runs never fired. See
`docs/pipeline.md` → "Scheduled refresh & failure isolation."

## Step 2 — the LaunchAgent

Unlike Windows Task Scheduler, launchd sets env vars, the working directory, and log
redirection natively, so **no wrapper script is needed** — it is all in the plist.

File: `~/Library/LaunchAgents/com.nocccd.pipeline.refresh.plist`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.nocccd.pipeline.refresh</string>

    <key>ProgramArguments</key>
    <array>
        <string>/Users/hoonywise/GitHub/nocccd-data/nocccd-streamlit/.venv/bin/python</string>
        <string>-m</string>
        <string>src.pipeline.run</string>
    </array>

    <key>WorkingDirectory</key>
    <string>/Users/hoonywise/GitHub/nocccd-data/nocccd-streamlit</string>

    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>12</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>

    <key>StandardOutPath</key>
    <string>/Users/hoonywise/Library/Logs/nocccd-pipeline.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/hoonywise/Library/Logs/nocccd-pipeline.log</string>

    <key>EnvironmentVariables</key>
    <dict>
        <key>ORACLE_HOME</key>
        <string>/Users/hoonywise/Oracle/instantclient</string>
        <key>PATH</key>
        <string>/Users/hoonywise/Oracle/instantclient:/usr/local/bin:/usr/bin:/bin</string>
    </dict>
</dict>
</plist>
```

Notes on the fields:
- **`StartCalendarInterval` Hour 12 / Minute 0** — fires at **noon local time**. If the
  Mac is asleep at noon, launchd runs the job on next wake (missed calendar intervals
  are coalesced). If no one is logged into the GUI session, a LaunchAgent does **not**
  run at all — this is inherently less reliable than the always-on Windows box.
- **`StandardOutPath` == `StandardErrorPath`** — both streams merge into one log. This
  is why `run.py`/`extract.py` flush their prints: block-buffered stdout would otherwise
  interleave out of order with the unbuffered `logging` lines.
- **No `TNS_ADMIN`** — the thick client finds `tnsnames.ora` under
  `$ORACLE_HOME/network/admin/` by default.

## Step 3 — install / load

Modern launchd (`bootstrap` into the per-user GUI domain):
```bash
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.nocccd.pipeline.refresh.plist
launchctl enable gui/$(id -u)/com.nocccd.pipeline.refresh
```
(Legacy equivalent, still works: `launchctl load ~/Library/LaunchAgents/com.nocccd.pipeline.refresh.plist`.)

After editing the plist, reload by booting it out (Step 5) and bootstrapping again.

## Step 4 — verify / operate

```bash
# Is it registered? (shows PID if currently running, else '-', and last exit code)
launchctl list | grep nocccd

# Force a run right now (does not wait for noon):
launchctl kickstart -k gui/$(id -u)/com.nocccd.pipeline.refresh

# Watch the log:
tail -f ~/Library/Logs/nocccd-pipeline.log
```
A healthy run ends with `Done. 28 succeeded, 0 failed, 0 skipped of 28.`

If a run appears wedged (no log growth for a long time and a PID still shown by
`launchctl list`), kill it so it stops blocking the schedule:
```bash
launchctl kill TERM gui/$(id -u)/com.nocccd.pipeline.refresh
```

## Step 5 — disable (e.g. after cutover to Windows)

Turn this off once the Windows Task Scheduler job is confirmed, or **both machines will
publish to the same Tableau site every day**:
```bash
launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.nocccd.pipeline.refresh.plist
```
(Legacy: `launchctl unload ...`.) This stops it without deleting the plist, so it can be
bootstrapped back later.

## Notes / out of scope
- The daily refresh does **not** run the bulk PDF/Excel export scripts
  (`bot_excel_export.py`, `seat_count_export.py`, `bot_export.py`).
- `enrollment_dashboard` is intentionally `skip_refresh: True` (source MV dropped); the
  no-arg run already excludes it.
