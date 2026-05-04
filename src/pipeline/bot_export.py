"""On-demand bulk PDF export for the BOT (Board of Trustees) tabs.

Reads each BOT tab's local Hyper file under ``src/pipeline/hyper/`` and
produces a single combined multi-page PDF containing every BOT tab's
report, written under a max-academic-year subfolder of ``EXPORT_ROOT``.
Each run uses a date-stamped filename, so same-day re-runs overwrite the
existing day's PDF and later run dates create new files in that folder.

Usage:
    python -m src.pipeline.bot_export
"""

import io
import logging
import os
import sys
from datetime import date
from pathlib import Path
from typing import Callable

# Silence Streamlit's "no runtime found" warnings BEFORE importing tab
# modules — their @st.cache_data decorators emit a warning per definition
# when evaluated outside a Streamlit session. See seat_count_export.py for
# the same pattern and rationale.
logging.getLogger("streamlit.runtime.caching.cache_data_api").addFilter(
    lambda record: "No runtime found" not in record.getMessage()
)

import pandas as pd  # noqa: E402
from pypdf import PdfReader, PdfWriter  # noqa: E402

from src.pipeline.config import max_acyr_label  # noqa: E402
from src.pipeline.hyper_cache import HyperCache  # noqa: E402
from src.scripts.tabs import (  # noqa: E402
    bot_goal1_students,
    bot_goal2_adt,
    bot_goal2_assoc,
    bot_goal2_bac,
    bot_goal2_cert,
    bot_goal2_cert_nc,
    bot_goal2_wage,
    bot_goal2_xfer,
    bot_goal3_finaid,
    bot_goal3_units,
)
from src.scripts.tabs.bot_helpers import generate_bot_pdf  # noqa: E402


# Destination root on OneDrive. Each run creates/uses a max-academic-year
# subfolder (e.g. 2024-25) and writes a date-stamped PDF inside it.
# Override with BOT_EXPORT_ROOT_PDF env var on machines/CI without OneDrive.
_DEFAULT_EXPORT_ROOT = (
    "/Users/hoonywise/Library/CloudStorage/"
    "OneDrive-NorthOrangeCountyCommunityCollegeDistrict/"
    "Documents - EST Data/BOT Reports/PDF Export"
)
EXPORT_ROOT = Path(os.environ.get("BOT_EXPORT_ROOT_PDF", _DEFAULT_EXPORT_ROOT))


# ---------------------------------------------------------------------------
# Per-tab PDF builders. Each returns the PDF bytes for that tab, mimicking
# the data-prep logic in the corresponding tab module's render() Query block.
# ---------------------------------------------------------------------------

def _credit_goal1_base(cache: HyperCache) -> pd.DataFrame:
    base = cache.get("bot_goal1_students")
    return base[base["site"] == "Credit"]


def _pdf_goal1_students(cache: HyperCache) -> bytes:
    df = cache.get("bot_goal1_students")
    return generate_bot_pdf(df, bot_goal1_students._TITLES)


def _pdf_goal2_adt(cache: HyperCache) -> bytes:
    df = cache.get("bot_goal2_adt")
    return generate_bot_pdf(df, bot_goal2_adt._TITLES, base_df=_credit_goal1_base(cache))


def _pdf_goal2_assoc(cache: HyperCache) -> bytes:
    df = cache.get("bot_goal2_assoc")
    return generate_bot_pdf(df, bot_goal2_assoc._TITLES, base_df=_credit_goal1_base(cache))


def _pdf_goal2_bac(cache: HyperCache) -> bytes:
    df = cache.get("bot_goal2_bac")
    return generate_bot_pdf(df, bot_goal2_bac._TITLES)


def _pdf_goal2_cert(cache: HyperCache) -> bytes:
    df = cache.get("bot_goal2_cert")
    return generate_bot_pdf(df, bot_goal2_cert._TITLES, base_df=_credit_goal1_base(cache))


def _pdf_goal2_cert_nc(cache: HyperCache) -> bytes:
    df = cache.get("bot_goal2_cert_nc")
    base = cache.get("bot_goal2_cert_nc_denom")
    return generate_bot_pdf(df, bot_goal2_cert_nc._TITLES, base_df=base)


def _pdf_goal2_wage(cache: HyperCache) -> bytes:
    # Living-wage outcomes are reported 1 year in arrears; shift display
    # labels forward so they align with how other BOT tabs label the same
    # cohort. Both sides must shift together to preserve the rate-metric
    # join in aggregate_*().
    df = bot_goal2_wage.shift_df(cache.get("bot_goal2_wage"))
    base = bot_goal2_wage.shift_df(cache.get("bot_goal2_wage_denom"))
    return generate_bot_pdf(df, bot_goal2_wage._TITLES, base_df=base)


def _pdf_goal2_xfer(cache: HyperCache) -> bytes:
    base = _credit_goal1_base(cache)
    df = bot_goal2_xfer.normalize(cache.get("bot_goal2_xfer"), base_df=base)
    return generate_bot_pdf(df, bot_goal2_xfer._TITLES, base_df=base)


def _pdf_goal3_finaid(cache: HyperCache) -> bytes:
    df = cache.get("bot_goal3_finaid")
    return generate_bot_pdf(df, bot_goal3_finaid._TITLES, base_df=_credit_goal1_base(cache))


def _pdf_goal3_units(cache: HyperCache) -> bytes:
    df = cache.get("bot_goal3_units")
    return bot_goal3_units.generate_pdf(df)


# Order mirrors the tab list (Goal 1 → Goal 2 alphabetical → Goal 3).
_TAB_BUILDERS: list[tuple[str, Callable[[HyperCache], bytes]]] = [
    ("bot_goal1_students", _pdf_goal1_students),
    ("bot_goal2_adt",      _pdf_goal2_adt),
    ("bot_goal2_assoc",    _pdf_goal2_assoc),
    ("bot_goal2_bac",      _pdf_goal2_bac),
    ("bot_goal2_cert",     _pdf_goal2_cert),
    ("bot_goal2_cert_nc",  _pdf_goal2_cert_nc),
    ("bot_goal2_wage",     _pdf_goal2_wage),
    ("bot_goal2_xfer",     _pdf_goal2_xfer),
    ("bot_goal3_finaid",   _pdf_goal3_finaid),
    ("bot_goal3_units",    _pdf_goal3_units),
]


def main() -> int:
    if not EXPORT_ROOT.parent.exists():
        print(
            f"Export parent not found: {EXPORT_ROOT.parent}\n"
            "Make sure OneDrive is mounted and the BOT Reports folder exists "
            "(or set BOT_EXPORT_ROOT_PDF to an existing parent path).",
            file=sys.stderr,
        )
        return 1
    EXPORT_ROOT.mkdir(parents=True, exist_ok=True)

    today = date.today().strftime("%Y%m%d")
    snapshot_dir = EXPORT_ROOT / max_acyr_label()
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    out_path = snapshot_dir / f"bot_{today}.pdf"
    # Write to a sibling tmp first, then atomic-rename only on full success.
    # Without this, a partial failure on one tab silently overwrites yesterday's
    # complete same-day PDF with one missing pages. Keep the .pdf suffix on the
    # tmp so any downstream tooling that inspects by extension still recognises
    # it during the brief moment before os.replace().
    tmp_path = out_path.with_name(f"{out_path.stem}.tmp{out_path.suffix}")
    print(f"Writing combined BOT PDF to {out_path}")

    cache = HyperCache()
    writer = PdfWriter()
    failed = 0

    for name, build in _TAB_BUILDERS:
        print(f"  rendering {name} ...")
        try:
            pdf_bytes = build(cache)
        except Exception as e:  # noqa: BLE001 — keep going on per-tab failures
            print(f"  ! {name} failed: {e}", file=sys.stderr)
            failed += 1
            continue

        reader = PdfReader(io.BytesIO(pdf_bytes))
        for page in reader.pages:
            writer.add_page(page)

    if failed or not writer.pages:
        if not writer.pages:
            print("No pages were generated; nothing to write.", file=sys.stderr)
        else:
            print(
                f"Skipped {failed} tab(s) due to errors — refusing to overwrite "
                f"{out_path} with a partial PDF.",
                file=sys.stderr,
            )
        return 1

    # Match bot_excel_export.py's symmetric try/finally: a write failure
    # (disk full, permission, PdfWriter corruption) or a failed os.replace
    # (e.g. cross-device rename on a CI mount) must not orphan a half-written
    # tmp file next to the user's good same-day PDF.
    try:
        with open(tmp_path, "wb") as f:
            writer.write(f)
        os.replace(tmp_path, out_path)
    except Exception as exc:  # noqa: BLE001 — surface a concise CLI failure
        tmp_path.unlink(missing_ok=True)
        print(f"PDF write failed: {exc}", file=sys.stderr)
        return 1

    print(f"\nDone. Wrote {len(writer.pages)} pages to {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
