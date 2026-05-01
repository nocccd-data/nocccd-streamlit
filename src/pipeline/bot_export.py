"""On-demand bulk PDF export for the BOT (Board of Trustees) tabs.

Reads each BOT tab's local Hyper file under ``src/pipeline/hyper/`` and
produces a single combined multi-page PDF containing every BOT tab's
report, written to a date-stamped subfolder under ``EXPORT_ROOT`` so
each run leaves a daily snapshot. Same-day re-runs overwrite the
existing day's PDF.

Usage:
    python -m src.pipeline.bot_export
"""

import io
import logging
import sys
from datetime import date
from pathlib import Path

# Silence Streamlit's "no runtime found" warnings BEFORE importing tab
# modules — their @st.cache_data decorators emit a warning per definition
# when evaluated outside a Streamlit session. See seat_count_export.py for
# the same pattern and rationale.
logging.getLogger("streamlit.runtime.caching.cache_data_api").addFilter(
    lambda record: "No runtime found" not in record.getMessage()
)

import pandas as pd  # noqa: E402
import pantab  # noqa: E402
from pypdf import PdfReader, PdfWriter  # noqa: E402

from src.pipeline.config import DATASETS, HYPER_DIR  # noqa: E402
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


# Destination root on OneDrive. Each run creates a date-stamped subfolder
# (YYYYMMDD); same-day re-runs overwrite the existing day's PDF.
EXPORT_ROOT = Path(
    "/Users/hoonywise/Library/CloudStorage/"
    "OneDrive-NorthOrangeCountyCommunityCollegeDistrict/"
    "Documents - EST Data/BOT Reports/PDF Export"
)


def _read_hyper(name: str) -> pd.DataFrame:
    path = HYPER_DIR / f"{name}.hyper"
    if not path.exists():
        raise FileNotFoundError(
            f"Hyper file not found at {path}.\n"
            f"Run: python -m src.pipeline.run {name}"
        )
    return pantab.frame_from_hyper(path, table="Extract")


# ---------------------------------------------------------------------------
# Per-tab PDF builders. Each returns the PDF bytes for that tab, mimicking
# the data-prep logic in the corresponding tab module's render() Query block.
# ---------------------------------------------------------------------------

def _pdf_goal1_students() -> bytes:
    df = _read_hyper("bot_goal1_students")
    return generate_bot_pdf(df, bot_goal1_students._TITLES)


def _pdf_goal2_adt() -> bytes:
    df = _read_hyper("bot_goal2_adt")
    base = _read_hyper("bot_goal1_students")
    base = base[base["site"] == "Credit"]
    return generate_bot_pdf(df, bot_goal2_adt._TITLES, base_df=base)


def _pdf_goal2_assoc() -> bytes:
    df = _read_hyper("bot_goal2_assoc")
    base = _read_hyper("bot_goal1_students")
    base = base[base["site"] == "Credit"]
    return generate_bot_pdf(df, bot_goal2_assoc._TITLES, base_df=base)


def _pdf_goal2_bac() -> bytes:
    df = _read_hyper("bot_goal2_bac")
    return generate_bot_pdf(df, bot_goal2_bac._TITLES)


def _pdf_goal2_cert() -> bytes:
    df = _read_hyper("bot_goal2_cert")
    base = _read_hyper("bot_goal1_students")
    base = base[base["site"] == "Credit"]
    return generate_bot_pdf(df, bot_goal2_cert._TITLES, base_df=base)


def _pdf_goal2_cert_nc() -> bytes:
    df = _read_hyper("bot_goal2_cert_nc")
    base = _read_hyper("bot_goal2_cert_nc_denom")
    return generate_bot_pdf(df, bot_goal2_cert_nc._TITLES, base_df=base)


def _pdf_goal2_wage() -> bytes:
    df = _read_hyper("bot_goal2_wage")
    base = _read_hyper("bot_goal2_wage_denom")
    # Living-wage outcomes are reported 1 year in arrears; shift display
    # labels forward so they align with how other BOT tabs label the same
    # cohort. Both sides must shift together to preserve the rate-metric
    # join in aggregate_*().
    df = bot_goal2_wage._shift_df(df)
    base = bot_goal2_wage._shift_df(base)
    return generate_bot_pdf(df, bot_goal2_wage._TITLES, base_df=base)


def _pdf_goal2_xfer() -> bytes:
    df = _read_hyper("bot_goal2_xfer")
    base = _read_hyper("bot_goal1_students")
    base = base[base["site"] == "Credit"]
    df = bot_goal2_xfer._normalize(df, base_df=base)
    return generate_bot_pdf(df, bot_goal2_xfer._TITLES, base_df=base)


def _pdf_goal3_finaid() -> bytes:
    df = _read_hyper("bot_goal3_finaid")
    base = _read_hyper("bot_goal1_students")
    base = base[base["site"] == "Credit"]
    return generate_bot_pdf(df, bot_goal3_finaid._TITLES, base_df=base)


def _pdf_goal3_units() -> bytes:
    df = _read_hyper("bot_goal3_units")
    return bot_goal3_units._generate_pdf(df)


# Order mirrors the tab list (Goal 1 → Goal 2 alphabetical → Goal 3).
_TAB_BUILDERS: list[tuple[str, callable]] = [
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


def _acyr_range_label() -> str:
    """`<min>_to_<max>` from bot_goal1_students config.

    Other BOT datasets sometimes cover a different 5-year window (e.g.
    living-wage is shifted by 1), so we anchor the filename on the
    canonical Goal 1 students range to keep it stable.
    """
    cfg = DATASETS["bot_goal1_students"]
    acyrs = sorted(cfg[cfg["param_name"]])
    return f"{acyrs[0]}_to_{acyrs[-1]}"


def main() -> int:
    if not EXPORT_ROOT.exists():
        print(
            f"Export root not found: {EXPORT_ROOT}\n"
            "Make sure OneDrive is mounted and the folder exists.",
            file=sys.stderr,
        )
        return 1

    today = date.today().strftime("%Y%m%d")
    snapshot_dir = EXPORT_ROOT / today
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    out_path = snapshot_dir / f"bot_export_{_acyr_range_label()}.pdf"
    print(f"Writing combined BOT PDF to {out_path}")

    writer = PdfWriter()
    failed = 0

    for name, build in _TAB_BUILDERS:
        print(f"  rendering {name} ...")
        try:
            pdf_bytes = build()
        except Exception as e:  # noqa: BLE001 — keep going on per-tab failures
            print(f"  ! {name} failed: {e}", file=sys.stderr)
            failed += 1
            continue

        reader = PdfReader(io.BytesIO(pdf_bytes))
        for page in reader.pages:
            writer.add_page(page)

    if not writer.pages:
        print("No pages were generated; nothing to write.", file=sys.stderr)
        return 1

    with open(out_path, "wb") as f:
        writer.write(f)

    print(f"\nDone. Wrote {len(writer.pages)} pages to {out_path}")
    if failed:
        print(f"Skipped {failed} tab(s) due to errors (see above).",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
