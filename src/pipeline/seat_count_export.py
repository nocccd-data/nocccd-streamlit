"""On-demand bulk PDF export for the Seat Count Report.

Reads ``src/pipeline/hyper/seat_count_report.hyper`` and writes one PDF per
``(term, campus, division)`` combination found in the data, into a
date-stamped subfolder under ``EXPORT_ROOT`` so each run leaves a daily
snapshot. Same-day re-runs overwrite the existing day's PDFs.

Usage:
    python -m src.pipeline.seat_count_export
"""

import logging
import re
import sys
from datetime import date
from pathlib import Path

# Silence Streamlit's "no runtime found" warnings BEFORE we import any module
# that uses @st.cache_data — the decorator emits a warning per definition when
# evaluated outside a Streamlit session, and the tab module we import below
# pulls in data_provider which has ~25 of them. Setting the level on the
# parent "streamlit" logger doesn't work because Streamlit initializes the
# leaf logger "streamlit.runtime.caching.cache_data_api" with its own level,
# so we attach a message-text filter directly to that leaf.
logging.getLogger("streamlit.runtime.caching.cache_data_api").addFilter(
    lambda record: "No runtime found" not in record.getMessage()
)

import pandas as pd  # noqa: E402
import pantab  # noqa: E402

from src.pipeline.config import HYPER_DIR  # noqa: E402
from src.scripts.tabs.seat_count_report import _compute_totals, _generate_pdf  # noqa: E402


# Destination root on OneDrive. Each run creates a date-stamped subfolder
# (YYYYMMDD) underneath, then Campus / Season subfolders within that.
# Same-day re-runs overwrite the existing day's PDFs; new days create new
# snapshots so daily enrollment numbers can be retained.
EXPORT_ROOT = Path(
    "/Users/hoonywise/Library/CloudStorage/"
    "OneDrive-NorthOrangeCountyCommunityCollegeDistrict/"
    "Documents - EST Data/Seat Count Report"
)

# Last 2 digits of the banner term code → season folder name.
_SEASON_BY_SUFFIX = {
    "10": "Fall",   "15": "Fall",
    "20": "Spring", "35": "Spring",
    "30": "Summer", "05": "Summer",
}


def _slug(s: str) -> str:
    """Lowercase + collapse non-alphanumerics to single underscores."""
    return re.sub(r"[^a-z0-9]+", "_", s.lower().strip()).strip("_")


def _term_title(df: pd.DataFrame, term_code: str) -> str:
    if "term_title" in df.columns:
        for v in df["term_title"].dropna().unique():
            return str(v)
    return term_code


def main() -> int:
    hyper_path = HYPER_DIR / "seat_count_report.hyper"
    if not hyper_path.exists():
        print(
            f"Hyper file not found at {hyper_path}.\n"
            f"Run: python -m src.pipeline.run seat_count_report",
            file=sys.stderr,
        )
        return 1
    if not EXPORT_ROOT.exists():
        print(
            f"Export root not found: {EXPORT_ROOT}\n"
            "Make sure OneDrive is mounted and the folder exists.",
            file=sys.stderr,
        )
        return 1

    today = date.today().strftime("%Y%m%d")
    snapshot_root = EXPORT_ROOT / today
    print(f"Reading {hyper_path} ...")
    print(f"Writing snapshot to {snapshot_root}")
    df_all = pantab.frame_from_hyper(hyper_path, table="Extract")
    df_all["term_code"] = df_all["term_code"].astype(str)

    written = 0
    failed = 0

    for term_code in sorted(df_all["term_code"].dropna().unique()):
        suffix = term_code[-2:]
        season = _SEASON_BY_SUFFIX.get(suffix)
        if season is None:
            print(f"  ! unknown term suffix {suffix!r} for {term_code}; skipping",
                  file=sys.stderr)
            failed += 1
            continue

        df_term = df_all[df_all["term_code"] == term_code]
        term_title = _term_title(df_term, term_code)

        for campus in sorted(df_term["campus_desc"].dropna().unique()):
            df_campus = df_term[df_term["campus_desc"] == campus]
            for division in sorted(df_campus["division_desc"].dropna().unique()):
                df_div = df_campus[df_campus["division_desc"] == division]
                if df_div.empty:
                    continue

                filter_scope = f"{term_title} / {campus} / {division}"
                summary = _compute_totals(df_div)
                try:
                    pdf_bytes = _generate_pdf(
                        df_div, term_title,
                        filter_scope=filter_scope, summary=summary,
                    )
                except Exception as e:  # noqa: BLE001 — we want to keep going
                    print(f"  ! generate failed for {term_code}/{campus}/{division}: {e}",
                          file=sys.stderr)
                    failed += 1
                    continue

                out_dir = snapshot_root / campus / season
                out_dir.mkdir(parents=True, exist_ok=True)
                fname = (
                    f"{term_code}_{_slug(campus)}_{season.lower()}_"
                    f"{_slug(division)}.pdf"
                )
                out_path = out_dir / fname
                out_path.write_bytes(pdf_bytes)
                written += 1
                print(f"  wrote {out_path.relative_to(EXPORT_ROOT)}")

    print(f"\nDone. Wrote {written} PDFs to {snapshot_root}")
    if failed:
        print(f"Skipped {failed} due to errors (see above).", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
