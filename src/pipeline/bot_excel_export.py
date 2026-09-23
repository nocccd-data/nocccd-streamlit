"""On-demand Excel export for BOT chart-table data.

Reads the local BOT Hyper files under ``src/pipeline/hyper/`` and writes one
chart-data sheet per Streamlit BOT tab, using the same aggregation helpers and
denominator logic as the Streamlit/PDF views.

Usage:
    python -m src.pipeline.bot_excel_export
"""

from __future__ import annotations

import logging
import os
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from tempfile import gettempdir
from typing import Callable


# Matplotlib is imported transitively by the BOT tab modules below, even
# though this exporter writes tables only. Matplotlib reads MPLCONFIGDIR
# during its own import, so this MUST run before the tab-module imports —
# deferring it into main() makes the override a no-op. The setdefault and
# mkdir calls are idempotent, so importing this module from a test or REPL
# is safe.
_MPLCONFIGDIR = Path(gettempdir()) / "nocccd-streamlit-matplotlib"
_MPLCONFIGDIR.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(_MPLCONFIGDIR))

# Silence Streamlit's "no runtime found" warnings emitted by tab modules'
# @st.cache_data decorators when evaluated outside a Streamlit session.
# Same constraint: must run before the tab imports below or the warnings
# escape during decorator evaluation.
logging.getLogger("streamlit.runtime.caching.cache_data_api").addFilter(
    lambda record: "No runtime found" not in record.getMessage()
)


import pandas as pd  # noqa: E402

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
    bot_goal4_xfer_ready,
)
from src.scripts.tabs.bot_excel_helpers import (  # noqa: E402
    standard_bot_excel_sections,
    write_sections_sheet,
)
from src.scripts.tabs.bot_targets import targets_from_cache


# Destination root on OneDrive. Each run creates/uses a max-academic-year
# subfolder (e.g. 2024-25) and writes a date-stamped workbook inside it.
# Override with BOT_EXPORT_ROOT_EXCEL env var on machines/CI without OneDrive.
_DEFAULT_EXPORT_ROOT = (
    "/Users/hoonywise/Library/CloudStorage/"
    "OneDrive-NorthOrangeCountyCommunityCollegeDistrict/"
    "Documents - EST Data/BOT Reports/Streamlit Data Export"
)
EXPORT_ROOT = Path(os.environ.get("BOT_EXPORT_ROOT_EXCEL", _DEFAULT_EXPORT_ROOT))


@dataclass(frozen=True)
class BotChartSpec:
    dataset_name: str
    sheet_name: str
    build: Callable[[HyperCache], tuple[pd.DataFrame, dict, pd.DataFrame | None]]
    units_metric: bool = False


def _credit_goal1_base(cache: HyperCache) -> pd.DataFrame:
    base = cache.get("bot_goal1_students")
    return base[base["site"] == "Credit"].copy()


def _build_goal1_students(
    cache: HyperCache,
) -> tuple[pd.DataFrame, dict, pd.DataFrame | None]:
    return cache.get("bot_goal1_students"), bot_goal1_students._TITLES, None


def _build_goal2_adt(
    cache: HyperCache,
) -> tuple[pd.DataFrame, dict, pd.DataFrame | None]:
    return cache.get("bot_goal2_adt"), bot_goal2_adt._TITLES, _credit_goal1_base(cache)


def _build_goal2_assoc(
    cache: HyperCache,
) -> tuple[pd.DataFrame, dict, pd.DataFrame | None]:
    return (
        cache.get("bot_goal2_assoc"),
        bot_goal2_assoc._TITLES,
        _credit_goal1_base(cache),
    )


def _build_goal2_bac(
    cache: HyperCache,
) -> tuple[pd.DataFrame, dict, pd.DataFrame | None]:
    return cache.get("bot_goal2_bac"), bot_goal2_bac._TITLES, None


def _build_goal2_cert(
    cache: HyperCache,
) -> tuple[pd.DataFrame, dict, pd.DataFrame | None]:
    return (
        cache.get("bot_goal2_cert"),
        bot_goal2_cert._TITLES,
        _credit_goal1_base(cache),
    )


def _build_goal2_cert_nc(
    cache: HyperCache,
) -> tuple[pd.DataFrame, dict, pd.DataFrame | None]:
    return (
        cache.get("bot_goal2_cert_nc"),
        bot_goal2_cert_nc._TITLES,
        cache.get("bot_goal2_cert_nc_denom"),
    )


def _build_goal2_wage(
    cache: HyperCache,
) -> tuple[pd.DataFrame, dict, pd.DataFrame | None]:
    df = bot_goal2_wage.shift_df(cache.get("bot_goal2_wage"))
    base = bot_goal2_wage.shift_df(cache.get("bot_goal2_wage_denom"))
    return df, bot_goal2_wage._TITLES, base


def _build_goal2_xfer(
    cache: HyperCache,
) -> tuple[pd.DataFrame, dict, pd.DataFrame | None]:
    base = _credit_goal1_base(cache)
    df = bot_goal2_xfer.normalize(cache.get("bot_goal2_xfer"), base_df=base)
    return df, bot_goal2_xfer._TITLES, base


def _build_goal3_finaid(
    cache: HyperCache,
) -> tuple[pd.DataFrame, dict, pd.DataFrame | None]:
    return (
        cache.get("bot_goal3_finaid"),
        bot_goal3_finaid._TITLES,
        _credit_goal1_base(cache),
    )


def _build_goal3_units(
    cache: HyperCache,
) -> tuple[pd.DataFrame, dict, pd.DataFrame | None]:
    return cache.get("bot_goal3_units"), bot_goal3_units._TITLES, None


def _build_goal4_xfer_ready(
    cache: HyperCache,
) -> tuple[pd.DataFrame, dict, pd.DataFrame | None]:
    return (
        cache.get("bot_goal4_xfer_ready"),
        bot_goal4_xfer_ready._TITLES,
        _credit_goal1_base(cache),
    )


_CHART_SPECS: list[BotChartSpec] = [
    BotChartSpec("bot_goal1_students", "chart_goal1_students", _build_goal1_students),
    BotChartSpec("bot_goal2_adt", "chart_goal2_adt", _build_goal2_adt),
    BotChartSpec("bot_goal2_assoc", "chart_goal2_assoc", _build_goal2_assoc),
    BotChartSpec("bot_goal2_bac", "chart_goal2_bac", _build_goal2_bac),
    BotChartSpec("bot_goal2_cert", "chart_goal2_cert", _build_goal2_cert),
    BotChartSpec("bot_goal2_cert_nc", "chart_goal2_cert_nc", _build_goal2_cert_nc),
    BotChartSpec("bot_goal2_wage", "chart_goal2_wage", _build_goal2_wage),
    BotChartSpec("bot_goal2_xfer", "chart_goal2_xfer", _build_goal2_xfer),
    BotChartSpec("bot_goal3_finaid", "chart_goal3_finaid", _build_goal3_finaid),
    BotChartSpec(
        "bot_goal3_units",
        "chart_goal3_units",
        _build_goal3_units,
        units_metric=True,
    ),
    BotChartSpec(
        "bot_goal4_xfer_ready",
        "chart_goal4_xfer_ready",
        _build_goal4_xfer_ready,
    ),
]


def main() -> int:
    if not EXPORT_ROOT.parent.exists():
        print(
            f"Export parent not found: {EXPORT_ROOT.parent}\n"
            "Make sure OneDrive is mounted and the BOT Reports folder exists "
            "(or set BOT_EXPORT_ROOT_EXCEL to an existing parent path).",
            file=sys.stderr,
        )
        return 1

    EXPORT_ROOT.mkdir(parents=True, exist_ok=True)
    today = date.today().strftime("%Y%m%d")
    snapshot_dir = EXPORT_ROOT / max_acyr_label()
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    out_path = snapshot_dir / f"bot_{today}.xlsx"
    # Write to a sibling tmp file, then atomic-rename only on full success.
    # Without this, a partial failure (e.g. one sheet raises) leaves a
    # truncated workbook at the date-stamped final path, overwriting a valid
    # same-day export. The tmp file MUST keep the .xlsx suffix because
    # xlsxwriter validates the extension and rejects anything else (e.g.
    # bot_YYYYMMDD.xlsx.tmp would raise ValueError before any data is written).
    tmp_path = out_path.with_name(f"{out_path.stem}.tmp{out_path.suffix}")
    print(f"Writing BOT Excel export to {out_path}")

    cache = HyperCache()
    try:
        with pd.ExcelWriter(tmp_path, engine="xlsxwriter") as writer:
            for spec in _CHART_SPECS:
                print(f"  writing chart-data sheet {spec.sheet_name} ...")
                df, titles, base_df = spec.build(cache)
                targets = targets_from_cache(cache, spec.dataset_name)
                sections = (
                    bot_goal3_units.units_excel_sections(df, targets=targets)
                    if spec.units_metric
                    else standard_bot_excel_sections(df, titles, base_df, targets=targets)
                )
                title = f"{titles['tab_title']} - Chart Table Data"
                write_sections_sheet(
                    writer, sections, title=title, sheet_name=spec.sheet_name,
                )
    except ImportError as exc:
        tmp_path.unlink(missing_ok=True)
        print(
            "Missing Excel writer dependency. Run: pip install -r requirements.txt",
            file=sys.stderr,
        )
        print(str(exc), file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001 - surface a concise CLI failure
        tmp_path.unlink(missing_ok=True)
        print(f"Export failed: {exc}", file=sys.stderr)
        return 1

    os.replace(tmp_path, out_path)
    print(f"\nDone. Wrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
