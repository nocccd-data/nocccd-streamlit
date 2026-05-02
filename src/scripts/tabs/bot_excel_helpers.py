"""Excel export helpers for BOT chart-table data."""

from __future__ import annotations

import io
import re
from dataclasses import dataclass

import pandas as pd

from src.scripts.tabs.bot_helpers import (
    CAMPUS_ORDER,
    FIRSTGEN_LABELS,
    FIRSTGEN_ORDER,
    GENDER_LABELS,
    GENDER_ORDER,
    RACE_SHORT,
    _visible_genders,
    _visible_races,
    aggregate_firstgen,
    aggregate_gender,
    aggregate_headcount,
    aggregate_race,
    compute_pct_change,
)

EXCEL_MAX_ROWS = 1_048_576
EXCEL_MAX_COLS = 16_384

EXCEL_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@dataclass(frozen=True)
class ExcelSection:
    title: str
    df: pd.DataFrame
    percent_cols: tuple[str, ...] = ()
    integer_cols: tuple[str, ...] = ()
    decimal_cols: tuple[str, ...] = ()


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
            "5-Yr Percent Change": ((lc - fc) / fc) if fc > 0 else float("nan"),
        })
    return pd.DataFrame(rows)


def value_summary(
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
            if first_val and last_val is not None
            else float("nan")
        )
        rows.append({
            label_col: label_map.get(key, key),
            f"{first_yr} {value_name}": first_val,
            f"{last_yr} {value_name}": last_val,
            "5-Yr Percent Change": change,
        })
    return pd.DataFrame(rows)


def matrix_table(
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
    return detail[[
        "Academic Year",
        label_col,
        "Numerator Count",
        "Denominator Count",
        "Percent",
    ]].sort_values(["Academic Year", label_col])


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


def standard_bot_excel_sections(
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
    visible_races = _visible_races(df_race)
    sections.extend([
        ExcelSection(
            titles["race_title"],
            matrix_table(
                df_race,
                key_col="race_description",
                label_col="Race/Ethnicity",
                order=visible_races,
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
                order=visible_races,
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
                order=visible_races,
                label_map=RACE_SHORT,
            ),
            percent_cols=("Percent",),
            integer_cols=("Numerator Count", "Denominator Count"),
        ),
    ])

    df_gender = aggregate_gender(df, base_df=base_df)
    visible_genders = _visible_genders(df_gender)
    gender_label_map = {key: GENDER_LABELS[key] for key in GENDER_ORDER}
    sections.extend([
        ExcelSection(
            titles["gender_title"],
            matrix_table(
                df_gender,
                key_col="gender",
                label_col="Gender",
                order=visible_genders,
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
                order=visible_genders,
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
                order=visible_genders,
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
            matrix_table(
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


def avg_unit_cols(df: pd.DataFrame) -> tuple[str, ...]:
    return tuple(col for col in df.columns if str(col).endswith("Avg Units"))


def _validate_sheet_shape(df: pd.DataFrame, sheet_name: str) -> None:
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
    start_col: int,
    percent_cols: tuple[str, ...] = (),
    integer_cols: tuple[str, ...] = (),
    decimal_cols: tuple[str, ...] = (),
) -> None:
    percent_fmt = workbook.add_format({"num_format": "0.0%"})
    integer_fmt = workbook.add_format({"num_format": "#,##0"})
    decimal_fmt = workbook.add_format({"num_format": "#,##0.0"})
    percent_set = set(percent_cols)
    integer_set = set(integer_cols)
    decimal_set = set(decimal_cols)
    sample = df.head(500)

    for idx, col in enumerate(df.columns):
        fmt = None
        if col in percent_set:
            fmt = percent_fmt
        elif col in integer_set:
            fmt = integer_fmt
        elif col in decimal_set:
            fmt = decimal_fmt
        elif pd.api.types.is_integer_dtype(df[col]):
            fmt = integer_fmt
        elif pd.api.types.is_float_dtype(df[col]):
            fmt = decimal_fmt

        values = sample[col] if col in sample.columns else []
        width = max([len(str(col)), *[_string_width(v) for v in values]])
        width = min(max(width + 2, 10), 42)
        worksheet.set_column(start_col + idx, start_col + idx, width, fmt)


def _format_dataframe(
    workbook,
    worksheet,
    df: pd.DataFrame,
    *,
    sheet_name: str,
    section_idx: int,
    header_row: int,
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
        worksheet.write(header_row, idx, col, header_fmt)

    _format_columns(
        workbook,
        worksheet,
        df,
        start_col=0,
        percent_cols=percent_cols,
        integer_cols=integer_cols,
        decimal_cols=decimal_cols,
    )

    if df.empty or df.columns.empty:
        return

    last_row = header_row + len(df)
    last_col = len(df.columns) - 1
    worksheet.add_table(
        header_row,
        0,
        last_row,
        last_col,
        {
            "name": _safe_table_name(sheet_name, section_idx),
            "columns": [{"header": str(col)} for col in df.columns],
            "style": "Table Style Light 9",
        },
    )


def sections_to_excel_bytes(
    sections: list[ExcelSection],
    *,
    title: str,
    sheet_name: str = "chart_data",
) -> bytes:
    sheet_name = _safe_sheet_name(sheet_name)
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter") as writer:
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
    return buf.getvalue()


def generate_bot_excel(
    df: pd.DataFrame,
    titles: dict,
    base_df: pd.DataFrame | None = None,
) -> bytes:
    return sections_to_excel_bytes(
        standard_bot_excel_sections(df, titles, base_df=base_df),
        title=f"{titles['tab_title']} - Chart Table Data",
    )
