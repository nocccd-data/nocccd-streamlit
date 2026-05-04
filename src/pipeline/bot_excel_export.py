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
import re
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


import numpy as np  # noqa: E402
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
)
from src.scripts.tabs.bot_helpers import (  # noqa: E402
    CAMPUS_ORDER,
    FIRSTGEN_LABELS,
    FIRSTGEN_ORDER,
    GENDER_LABELS,
    GENDER_ORDER,
    RACE_SHORT,
    aggregate_firstgen,
    aggregate_gender,
    aggregate_headcount,
    aggregate_race,
    compute_pct_change,
    visible_genders,
    visible_races,
)


# Destination root on OneDrive. Each run creates/uses a max-academic-year
# subfolder (e.g. 2024-25) and writes a date-stamped workbook inside it.
# Override with BOT_EXPORT_ROOT_EXCEL env var on machines/CI without OneDrive.
_DEFAULT_EXPORT_ROOT = (
    "/Users/hoonywise/Library/CloudStorage/"
    "OneDrive-NorthOrangeCountyCommunityCollegeDistrict/"
    "Documents - EST Data/BOT Reports/Streamlit Data Export"
)
EXPORT_ROOT = Path(os.environ.get("BOT_EXPORT_ROOT_EXCEL", _DEFAULT_EXPORT_ROOT))

EXCEL_MAX_ROWS = 1_048_576
EXCEL_MAX_COLS = 16_384


@dataclass(frozen=True)
class ExcelSection:
    title: str
    df: pd.DataFrame
    percent_cols: tuple[str, ...] = ()
    integer_cols: tuple[str, ...] = ()
    decimal_cols: tuple[str, ...] = ()


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
]


def _safe_sheet_name(name: str) -> str:
    cleaned = re.sub(r"[][*/?:\\]", "_", name)
    return cleaned[:31]


def _safe_table_name(sheet_name: str, section_idx: int) -> str:
    base = re.sub(r"\W+", "_", sheet_name).strip("_")
    if not base or base[0].isdigit():
        base = f"t_{base}"
    return f"{base}_{section_idx}"[:255]


def _academic_years(df: pd.DataFrame) -> list[str]:
    if "academic_year" not in df.columns:
        return []
    return sorted(df["academic_year"].dropna().astype(str).unique())


def _ordered_present(values: pd.Series, order: list[str]) -> list[str]:
    present = set(values.dropna().astype(str))
    return [item for item in order if item in present]


def _get_numeric(piv: pd.DataFrame, key: str, col: str) -> float | None:
    if key not in piv.index or col not in piv.columns:
        return None
    value = piv.loc[key, col]
    if pd.isna(value):
        return None
    return float(value)


def _count_summary(
    df: pd.DataFrame,
    *,
    key_col: str,
    label_col: str,
    order: list[str],
    label_map: dict[str, str],
    years: list[str],
) -> pd.DataFrame:
    if len(years) < 2:
        return pd.DataFrame()
    first_yr, last_yr = years[0], years[-1]
    piv = df.pivot_table(
        index=key_col,
        columns="academic_year",
        values="count",
        aggfunc="first",
        observed=True,
    )
    rows: list[dict] = []
    for key in order:
        fc = _get_numeric(piv, key, first_yr) or 0
        lc = _get_numeric(piv, key, last_yr) or 0
        rows.append({
            label_col: label_map.get(key, key),
            f"{first_yr} Count": int(fc),
            f"{last_yr} Count": int(lc),
            "5-Yr Percent Change": ((lc - fc) / fc) if fc > 0 else np.nan,
        })
    return pd.DataFrame(rows)


def _value_summary(
    df: pd.DataFrame,
    *,
    key_col: str,
    label_col: str,
    order: list[str],
    label_map: dict[str, str],
    years: list[str],
    value_col: str,
    value_name: str,
) -> pd.DataFrame:
    if len(years) < 2:
        return pd.DataFrame()
    first_yr, last_yr = years[0], years[-1]
    piv = df.pivot_table(
        index=key_col,
        columns="academic_year",
        values=value_col,
        aggfunc="first",
        observed=True,
    )
    rows: list[dict] = []
    for key in order:
        first_val = _get_numeric(piv, key, first_yr)
        last_val = _get_numeric(piv, key, last_yr)
        change = (
            (last_val - first_val) / first_val
            if first_val is not None and first_val != 0 and last_val is not None
            else np.nan
        )
        rows.append({
            label_col: label_map.get(key, key),
            f"{first_yr} {value_name}": first_val,
            f"{last_yr} {value_name}": last_val,
            "5-Yr Percent Change": change,
        })
    return pd.DataFrame(rows)


def _matrix_table(
    df: pd.DataFrame,
    *,
    key_col: str,
    label_col: str,
    order: list[str],
    label_map: dict[str, str],
    years: list[str],
    value_col: str,
) -> pd.DataFrame:
    piv = df.pivot_table(
        index=key_col,
        columns="academic_year",
        values=value_col,
        aggfunc="first",
        observed=True,
    )
    piv = piv.reindex(order)
    out = piv.reindex(columns=years).reset_index()
    out.insert(0, label_col, [label_map.get(key, key) for key in out[key_col]])
    return out.drop(columns=[key_col])


def _rate_detail(
    df: pd.DataFrame,
    *,
    key_col: str,
    label_col: str,
    order: list[str],
    label_map: dict[str, str],
) -> pd.DataFrame:
    detail = df[df[key_col].astype(str).isin(order)].copy()
    detail[label_col] = detail[key_col].map(label_map).fillna(detail[key_col])
    detail = detail.rename(columns={
        "academic_year": "Academic Year",
        "count": "Numerator Count",
        "total": "Denominator Count",
        "pct": "Percent",
    })
    # Fail loudly if an upstream Hyper drops a required metric (count/total/
    # pct → Numerator/Denominator/Percent). Per project policy, the export
    # must surface schema regressions, not silently ship blank columns to
    # the workbook (CLAUDE.md: "Do not return unfiltered data when required
    # schema/filter columns are missing — fail loudly").
    required_cols = ["Academic Year", label_col,
                     "Numerator Count", "Denominator Count", "Percent"]
    missing = [c for c in required_cols if c not in detail.columns]
    if missing:
        raise KeyError(
            f"_rate_detail: missing required column(s) {missing} in upstream "
            f"frame (have: {sorted(detail.columns.tolist())}). Check the "
            f"source Hyper's count/total/pct schema."
        )
    return detail[required_cols].sort_values(["Academic Year", label_col])


def _headcount_table(df: pd.DataFrame, titles: dict) -> pd.DataFrame:
    df_agg = aggregate_headcount(
        df,
        include_nocccd=titles.get("include_nocccd", True),
    )
    years = _academic_years(df_agg)
    campuses = _ordered_present(df_agg["camp_desc"], CAMPUS_ORDER)
    piv = df_agg.pivot_table(
        index="camp_desc",
        columns="academic_year",
        values="headcount",
        aggfunc="first",
        observed=True,
    )
    out = piv.reindex(campuses).reindex(columns=years).reset_index()
    out = out.rename(columns={"camp_desc": "Campus"})

    df_pct = compute_pct_change(df_agg)
    if not df_pct.empty:
        df_pct = df_pct.copy()
        df_pct["5-Yr Percent Change"] = df_pct["pct_change"] / 100
        out = out.merge(
            df_pct[["camp_desc", "5-Yr Percent Change"]],
            left_on="Campus",
            right_on="camp_desc",
            how="left",
        ).drop(columns=["camp_desc"])
    return out


def _standard_chart_sections(
    df: pd.DataFrame,
    titles: dict,
    base_df: pd.DataFrame | None = None,
) -> list[ExcelSection]:
    years = _academic_years(df)
    sections = [
        ExcelSection(
            titles["headcount_title"],
            _headcount_table(df, titles),
            percent_cols=("5-Yr Percent Change",),
            integer_cols=tuple(years),
        ),
    ]

    if titles.get("headcount_only"):
        return sections

    df_race = aggregate_race(df, base_df=base_df)
    race_keys = visible_races(df_race)
    sections.extend([
        ExcelSection(
            titles["race_title"],
            _matrix_table(
                df_race,
                key_col="race_description",
                label_col="Race/Ethnicity",
                order=race_keys,
                label_map=RACE_SHORT,
                years=years,
                value_col="pct",
            ),
            percent_cols=tuple(years),
        ),
        ExcelSection(
            f"{titles['race_title']} - Summary Counts",
            _count_summary(
                df_race,
                key_col="race_description",
                label_col="Race/Ethnicity",
                order=race_keys,
                label_map=RACE_SHORT,
                years=years,
            ),
            percent_cols=("5-Yr Percent Change",),
        ),
        ExcelSection(
            f"{titles['race_title']} - Rate Detail",
            _rate_detail(
                df_race,
                key_col="race_description",
                label_col="Race/Ethnicity",
                order=race_keys,
                label_map=RACE_SHORT,
            ),
            percent_cols=("Percent",),
            integer_cols=("Numerator Count", "Denominator Count"),
        ),
    ])

    df_gender = aggregate_gender(df, base_df=base_df)
    gender_keys = visible_genders(df_gender)
    gender_label_map = {key: GENDER_LABELS[key] for key in GENDER_ORDER}
    sections.extend([
        ExcelSection(
            titles["gender_title"],
            _matrix_table(
                df_gender,
                key_col="gender",
                label_col="Gender",
                order=gender_keys,
                label_map=gender_label_map,
                years=years,
                value_col="pct",
            ),
            percent_cols=tuple(years),
        ),
        ExcelSection(
            f"{titles['gender_title']} - Summary Counts",
            _count_summary(
                df_gender,
                key_col="gender",
                label_col="Gender",
                order=gender_keys,
                label_map=gender_label_map,
                years=years,
            ),
            percent_cols=("5-Yr Percent Change",),
        ),
        ExcelSection(
            f"{titles['gender_title']} - Rate Detail",
            _rate_detail(
                df_gender,
                key_col="gender",
                label_col="Gender",
                order=gender_keys,
                label_map=gender_label_map,
            ),
            percent_cols=("Percent",),
            integer_cols=("Numerator Count", "Denominator Count"),
        ),
    ])

    df_fg = aggregate_firstgen(
        df,
        credit_only=titles.get("credit_only_firstgen", True),
        base_df=base_df,
    )
    fg_label_map = {key: FIRSTGEN_LABELS[key] for key in FIRSTGEN_ORDER}
    sections.extend([
        ExcelSection(
            titles["firstgen_title"],
            _matrix_table(
                df_fg,
                key_col="fg",
                label_col="First-Generation Status",
                order=FIRSTGEN_ORDER,
                label_map=fg_label_map,
                years=years,
                value_col="pct",
            ),
            percent_cols=tuple(years),
        ),
        ExcelSection(
            f"{titles['firstgen_title']} - Summary Counts",
            _count_summary(
                df_fg,
                key_col="fg",
                label_col="First-Generation Status",
                order=FIRSTGEN_ORDER,
                label_map=fg_label_map,
                years=years,
            ),
            percent_cols=("5-Yr Percent Change",),
        ),
        ExcelSection(
            f"{titles['firstgen_title']} - Rate Detail",
            _rate_detail(
                df_fg,
                key_col="fg",
                label_col="First-Generation Status",
                order=FIRSTGEN_ORDER,
                label_map=fg_label_map,
            ),
            percent_cols=("Percent",),
            integer_cols=("Numerator Count", "Denominator Count"),
        ),
    ])

    return sections


def _units_campus_table(df: pd.DataFrame) -> pd.DataFrame:
    df_agg = bot_goal3_units.aggregate_campus(df)
    years = _academic_years(df_agg)
    campuses = _ordered_present(df_agg["camp_desc"], CAMPUS_ORDER)
    piv = df_agg.pivot_table(
        index="camp_desc",
        columns="academic_year",
        values="avg_units",
        aggfunc="first",
        observed=True,
    )
    out = piv.reindex(campuses).reindex(columns=years).reset_index()
    out = out.rename(columns={"camp_desc": "Campus"})

    df_pct = bot_goal3_units.pct_change(df_agg, "camp_desc", CAMPUS_ORDER)
    if not df_pct.empty:
        df_pct = df_pct.copy()
        df_pct["5-Yr Percent Change"] = df_pct["pct_change"] / 100
        out = out.merge(
            df_pct[["camp_desc", "5-Yr Percent Change"]],
            left_on="Campus",
            right_on="camp_desc",
            how="left",
        ).drop(columns=["camp_desc"])
    return out


def _units_chart_sections(df: pd.DataFrame, titles: dict) -> list[ExcelSection]:
    years = _academic_years(df)
    sections = [
        ExcelSection(
            titles["headcount_title"],
            _units_campus_table(df),
            percent_cols=("5-Yr Percent Change",),
            decimal_cols=tuple(years),
        ),
    ]

    df_race = bot_goal3_units.aggregate_race(df)
    race_keys = bot_goal3_units.visible_races(df_race)
    race_summary = _value_summary(
        df_race,
        key_col="race_description",
        label_col="Race/Ethnicity",
        order=race_keys,
        label_map=RACE_SHORT,
        years=years,
        value_col="avg_units",
        value_name="Avg Units",
    )
    sections.extend([
        ExcelSection(
            titles["race_title"],
            _matrix_table(
                df_race,
                key_col="race_description",
                label_col="Race/Ethnicity",
                order=race_keys,
                label_map=RACE_SHORT,
                years=years,
                value_col="avg_units",
            ),
            decimal_cols=tuple(years),
        ),
        ExcelSection(
            f"{titles['race_title']} - Summary",
            race_summary,
            percent_cols=("5-Yr Percent Change",),
            decimal_cols=_avg_unit_cols(race_summary),
        ),
        ExcelSection(
            f"{titles['race_title']} - Detail",
            df_race.rename(columns={
                "academic_year": "Academic Year",
                "race_description": "Race/Ethnicity",
                "avg_units": "Avg Units",
                "count": "Student Count",
            })[["Academic Year", "Race/Ethnicity", "Avg Units", "Student Count"]],
            integer_cols=("Student Count",),
            decimal_cols=("Avg Units",),
        ),
    ])

    df_gender = bot_goal3_units.aggregate_gender(df)
    gender_keys = bot_goal3_units.visible_genders(df_gender)
    gender_label_map = {key: GENDER_LABELS[key] for key in GENDER_ORDER}
    gender_summary = _value_summary(
        df_gender,
        key_col="gender",
        label_col="Gender",
        order=gender_keys,
        label_map=gender_label_map,
        years=years,
        value_col="avg_units",
        value_name="Avg Units",
    )
    sections.extend([
        ExcelSection(
            titles["gender_title"],
            _matrix_table(
                df_gender,
                key_col="gender",
                label_col="Gender",
                order=gender_keys,
                label_map=gender_label_map,
                years=years,
                value_col="avg_units",
            ),
            decimal_cols=tuple(years),
        ),
        ExcelSection(
            f"{titles['gender_title']} - Summary",
            gender_summary,
            percent_cols=("5-Yr Percent Change",),
            decimal_cols=_avg_unit_cols(gender_summary),
        ),
        ExcelSection(
            f"{titles['gender_title']} - Detail",
            df_gender.rename(columns={
                "academic_year": "Academic Year",
                "gender_label": "Gender",
                "avg_units": "Avg Units",
                "count": "Student Count",
            })[["Academic Year", "Gender", "Avg Units", "Student Count"]],
            integer_cols=("Student Count",),
            decimal_cols=("Avg Units",),
        ),
    ])

    df_fg = bot_goal3_units.aggregate_firstgen(df)
    fg_label_map = {key: FIRSTGEN_LABELS[key] for key in FIRSTGEN_ORDER}
    fg_summary = _value_summary(
        df_fg,
        key_col="fg",
        label_col="First-Generation Status",
        order=FIRSTGEN_ORDER,
        label_map=fg_label_map,
        years=years,
        value_col="avg_units",
        value_name="Avg Units",
    )
    sections.extend([
        ExcelSection(
            titles["firstgen_title"],
            _matrix_table(
                df_fg,
                key_col="fg",
                label_col="First-Generation Status",
                order=FIRSTGEN_ORDER,
                label_map=fg_label_map,
                years=years,
                value_col="avg_units",
            ),
            decimal_cols=tuple(years),
        ),
        ExcelSection(
            f"{titles['firstgen_title']} - Summary",
            fg_summary,
            percent_cols=("5-Yr Percent Change",),
            decimal_cols=_avg_unit_cols(fg_summary),
        ),
        ExcelSection(
            f"{titles['firstgen_title']} - Detail",
            df_fg.rename(columns={
                "academic_year": "Academic Year",
                "fg_label": "First-Generation Status",
                "avg_units": "Avg Units",
            })[["Academic Year", "First-Generation Status", "Avg Units"]],
            decimal_cols=("Avg Units",),
        ),
    ])

    return sections


def _avg_unit_cols(df: pd.DataFrame) -> tuple[str, ...]:
    return tuple(col for col in df.columns if str(col).endswith("Avg Units"))


def _validate_sheet_shape(df: pd.DataFrame, sheet_name: str) -> None:
    # One Excel row is consumed by the header.
    if len(df) + 1 > EXCEL_MAX_ROWS:
        raise ValueError(
            f"{sheet_name} has {len(df):,} rows, exceeding Excel's "
            f"{EXCEL_MAX_ROWS - 1:,} data-row limit."
        )
    if len(df.columns) > EXCEL_MAX_COLS:
        raise ValueError(
            f"{sheet_name} has {len(df.columns):,} columns, exceeding "
            f"Excel's {EXCEL_MAX_COLS:,} column limit."
        )


def _string_width(value: object) -> int:
    if pd.isna(value):
        return 0
    return len(str(value))


def _format_columns(
    workbook,
    worksheet,
    df: pd.DataFrame,
    *,
    header_row: int,
    start_col: int,
    percent_cols: tuple[str, ...] = (),
    integer_cols: tuple[str, ...] = (),
    decimal_cols: tuple[str, ...] = (),
) -> None:
    # Formats are applied per-cell within this section's data range, NOT via
    # set_column. Multiple sections on a single sheet share the same Excel
    # columns (A, B, C, …); a column-level format from set_column would be
    # overwritten by the next section's set_column call, leaving e.g. the
    # Summary Counts "5-Yr Percent Change" column rendered with the trailing
    # Rate Detail section's integer format. set_column is used here for width
    # only.
    percent_fmt = workbook.add_format({"num_format": "0.0%"})
    integer_fmt = workbook.add_format({"num_format": "#,##0"})
    decimal_fmt = workbook.add_format({"num_format": "#,##0.0"})
    percent_set = set(percent_cols)
    integer_set = set(integer_cols)
    decimal_set = set(decimal_cols)
    sample = df.head(500)

    col_formats: list = []
    for col in df.columns:
        if col in percent_set:
            col_formats.append(percent_fmt)
        elif col in integer_set:
            col_formats.append(integer_fmt)
        elif col in decimal_set:
            col_formats.append(decimal_fmt)
        elif pd.api.types.is_integer_dtype(df[col]):
            col_formats.append(integer_fmt)
        elif pd.api.types.is_float_dtype(df[col]):
            col_formats.append(decimal_fmt)
        else:
            col_formats.append(None)

    for idx, col in enumerate(df.columns):
        values = sample[col] if col in sample.columns else []
        width = max([len(str(col)), *[_string_width(v) for v in values]])
        width = min(max(width + 2, 10), 42)
        worksheet.set_column(start_col + idx, start_col + idx, width)

    for r, row_tuple in enumerate(df.itertuples(index=False)):
        target_row = header_row + 1 + r
        for c, value in enumerate(row_tuple):
            fmt = col_formats[c]
            if fmt is None:
                continue
            target_col = start_col + c
            if pd.isna(value):
                worksheet.write_blank(target_row, target_col, None, fmt)
            elif isinstance(value, (int, np.integer, float, np.floating)):
                worksheet.write_number(target_row, target_col, float(value), fmt)


def _format_dataframe(
    workbook,
    worksheet,
    df: pd.DataFrame,
    *,
    sheet_name: str,
    section_idx: int,
    header_row: int,
    start_col: int = 0,
    percent_cols: tuple[str, ...] = (),
    integer_cols: tuple[str, ...] = (),
    decimal_cols: tuple[str, ...] = (),
) -> None:
    header_fmt = workbook.add_format({
        "bold": True,
        "bg_color": "#D9EAF7",
        "border": 1,
        "text_wrap": True,
        "valign": "top",
    })
    for idx, col in enumerate(df.columns):
        worksheet.write(header_row, start_col + idx, col, header_fmt)

    _format_columns(
        workbook,
        worksheet,
        df,
        header_row=header_row,
        start_col=start_col,
        percent_cols=percent_cols,
        integer_cols=integer_cols,
        decimal_cols=decimal_cols,
    )

    if df.empty or df.columns.empty:
        return

    last_row = header_row + len(df)
    last_col = start_col + len(df.columns) - 1
    worksheet.add_table(
        header_row,
        start_col,
        last_row,
        last_col,
        {
            "name": _safe_table_name(sheet_name, section_idx),
            "columns": [{"header": str(col)} for col in df.columns],
            "style": "Table Style Light 9",
        },
    )


def _write_chart_sheet(
    writer: pd.ExcelWriter,
    sheet_name: str,
    title: str,
    sections: list[ExcelSection],
) -> None:
    sheet_name = _safe_sheet_name(sheet_name)
    workbook = writer.book
    worksheet = workbook.add_worksheet(sheet_name)
    writer.sheets[sheet_name] = worksheet

    title_fmt = workbook.add_format({
        "bold": True,
        "font_size": 14,
        "font_color": "#FFFFFF",
        "bg_color": "#004062",
    })
    section_fmt = workbook.add_format({
        "bold": True,
        "font_size": 11,
        "bg_color": "#E2F0D9",
    })

    worksheet.write(0, 0, title, title_fmt)
    row = 2
    for idx, section in enumerate(sections, start=1):
        df = section.df.copy()
        df.columns = [str(col) for col in df.columns]
        _validate_sheet_shape(df, sheet_name)

        worksheet.write(row, 0, section.title, section_fmt)
        row += 1
        if df.empty:
            worksheet.write(row, 0, "No data")
            row += 3
            continue

        df.to_excel(writer, sheet_name=sheet_name, startrow=row, index=False)
        _format_dataframe(
            workbook,
            worksheet,
            df,
            sheet_name=sheet_name,
            section_idx=idx,
            header_row=row,
            percent_cols=section.percent_cols,
            integer_cols=section.integer_cols,
            decimal_cols=section.decimal_cols,
        )
        row += len(df) + 3

    worksheet.freeze_panes(1, 0)


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
                sections = (
                    _units_chart_sections(df, titles)
                    if spec.units_metric
                    else _standard_chart_sections(df, titles, base_df)
                )
                title = f"{titles['tab_title']} - Chart Table Data"
                _write_chart_sheet(writer, spec.sheet_name, title, sections)
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
