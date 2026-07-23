"""CLI entry point: extract Oracle data to Hyper and publish to Tableau Cloud.

Usage:
    python -m src.pipeline.run                    # all datasets
    python -m src.pipeline.run coi_nhrdist_val    # single dataset
    python -m src.pipeline.run --extract-only     # skip upload
    python -m src.pipeline.run --no-preflight     # skip the reachability probe
"""

import argparse
import os
import sys
import threading
import time
import tomllib
from pathlib import Path

from sqlalchemy import text

from .config import DATASETS
from .extract import extract_dataset
from .libs.sql import get_engine
from .publish import publish_hyper

EXIT_OK = 0
EXIT_INCOMPLETE = 1
EXIT_BAD_ARGS = 2
EXIT_UNREACHABLE = 3
EXIT_TIMEOUT = 75

# Observed daily runs take 143-197 min, so 5h is ~1.5x the worst case: long
# enough never to cut off a legitimately slow run, short enough that a wedged
# one clears well before the next noon fire.
DEFAULT_TIMEOUT_SECONDS = 5 * 60 * 60


def _brief(exc: BaseException) -> str:
    """One-line summary of an exception, for compact failure reporting.

    Oracle puts the actionable part (ORA-12545, ORA-12528, ...) on the first
    line, which is the only part of a 100+ line SQLAlchemy traceback worth
    keeping when 28 datasets can each fail the same way.
    """
    message = str(exc).strip()
    return message.splitlines()[0][:200] if message else exc.__class__.__name__


def _start_watchdog(seconds: int) -> None:
    """Hard-abort the process if the run outlives ``seconds``.

    On 2026-07-18 a mid-run VPN drop left this process blocked inside the
    Oracle client for 93 hours. launchd will not start a second instance of a
    label that is still running, so the next four scheduled refreshes never
    fired -- a silent four-day outage from a single stuck socket.

    This has to be ``os._exit`` from a separate thread: a thread blocked in the
    Oracle client's C code never returns to the interpreter, so exceptions,
    signals, and KeyboardInterrupt are not delivered to it. Only an immediate
    process exit is guaranteed to land.
    """

    limit = f"{seconds / 3600:.1f}h" if seconds >= 3600 else f"{seconds}s"

    def abort() -> None:
        time.sleep(seconds)
        print(
            f"WATCHDOG: run exceeded {limit} and is presumed wedged; "
            f"aborting so the next scheduled run is not blocked.",
            file=sys.stderr,
            flush=True,
        )
        sys.stderr.flush()
        sys.stdout.flush()
        os._exit(EXIT_TIMEOUT)

    threading.Thread(target=abort, daemon=True, name="pipeline-watchdog").start()


def _preflight(sections: set[str]) -> set[str]:
    """Return the subset of ``sections`` that answers a trivial query.

    Off VPN the DSN does not resolve and every dataset on that section fails
    identically (ORA-12545). Probing each section once turns 28 duplicate
    stack traces into one line per section, and lets the run still proceed on
    whichever section is reachable.
    """
    reachable = set()
    for section in sorted(sections):
        try:
            engine = get_engine(section)
            with engine.connect() as conn:
                conn.execute(text("SELECT 1 FROM dual"))
        except Exception as exc:
            print(f"[preflight] {section}: UNREACHABLE -- {_brief(exc)}", flush=True)
        else:
            reachable.add(section)
            print(f"[preflight] {section}: reachable", flush=True)
    return reachable


def _load_secrets() -> dict:
    secrets_path = Path(__file__).resolve().parents[2] / ".streamlit" / "secrets.toml"
    with open(secrets_path, "rb") as f:
        return tomllib.load(f)


def _section_of(name: str) -> str:
    return DATASETS[name].get("db_section", "dwhdb")


def main() -> int:
    parser = argparse.ArgumentParser(description="Oracle → Hyper → Tableau Cloud pipeline")
    parser.add_argument("datasets", nargs="*", help="Dataset names (default: all)")
    parser.add_argument("--extract-only", action="store_true", help="Only create .hyper files, skip upload")
    parser.add_argument("--no-preflight", action="store_true", help="Skip the per-section reachability probe")
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT_SECONDS,
        help=f"Abort the whole run after N seconds (default {DEFAULT_TIMEOUT_SECONDS}; 0 disables)",
    )
    args = parser.parse_args()

    names = args.datasets if args.datasets else [
        n for n, c in DATASETS.items() if not c.get("skip_refresh")
    ]
    for name in names:
        if name not in DATASETS:
            print(f"Unknown dataset: {name}")
            print(f"Available: {', '.join(DATASETS.keys())}")
            return EXIT_BAD_ARGS

    if args.timeout > 0:
        _start_watchdog(args.timeout)

    secrets = None if args.extract_only else _load_secrets()

    sections = {_section_of(n) for n in names}
    if args.no_preflight:
        reachable = sections
    else:
        reachable = _preflight(sections)
        if not reachable:
            print(
                "No database section is reachable (VPN down?); nothing to do.",
                flush=True,
            )
            return EXIT_UNREACHABLE

    succeeded: list[str] = []
    failed: list[tuple[str, str]] = []
    skipped: list[str] = []

    for name in names:
        section = _section_of(name)
        if section not in reachable:
            skipped.append(name)
            continue

        # One dataset's failure must not abort the other 27 -- before this,
        # a single unreachable DSN on the first dataset meant a run that
        # published nothing at all.
        try:
            print(f"[{name}] Extracting from Oracle...", flush=True)
            hyper_path = extract_dataset(name)

            if not args.extract_only:
                assert secrets is not None
                print(f"[{name}] Publishing to Tableau Cloud...", flush=True)
                publish_hyper(
                    name,
                    hyper_path,
                    server_url=secrets["SERVER"],
                    site_name=secrets["SITE_NAME"],
                    pat_name=secrets["PAT_NAME"],
                    pat_value=secrets["PAT_VALUE"],
                )
        except Exception as exc:
            reason = _brief(exc)
            print(f"[{name}] FAILED: {reason}", file=sys.stderr, flush=True)
            failed.append((name, reason))
        else:
            succeeded.append(name)

    print(
        f"\nDone. {len(succeeded)} succeeded, {len(failed)} failed, "
        f"{len(skipped)} skipped of {len(names)}.",
        flush=True,
    )
    if skipped:
        unreachable = sorted(sections - reachable)
        print(f"  skipped (section unreachable: {', '.join(unreachable)}): {', '.join(skipped)}")
    for name, reason in failed:
        print(f"  FAILED {name}: {reason}")

    return EXIT_OK if not failed and not skipped else EXIT_INCOMPLETE


if __name__ == "__main__":
    sys.exit(main())
