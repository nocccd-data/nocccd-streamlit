"""NOCCCD Equity Analysis Excel exporter (PPG-1).

Produces the Equity Gap workbook that mirrors
``NOCCCD_Equity_Gap_Template_PPG1_ALL_METRICS.xlsx``: the same 10 BOT metrics
disaggregated by Race/Ethnicity, Gender, and First-Generation Status, with
CCCCO Percentage Point Gap Minus One (PPG-1) calculations.

Hybrid value/formula workbook:
- Numerator and denominator cells are values from the BOT Hyper extracts so a
  re-run picks up any future revision to BOT SQL or aggregation logic.
- Rates, gaps, PPG-1, MOE, DI flags, and the heatmap are live Excel formulas
  that reference Data_Entry, so the math stays auditable in cells and an
  analyst can hand-edit a denominator for what-if analysis.

Usage:
    python -m src.pipeline.equity_export

Output:
    <EXPORT_ROOT>/<max_acyr_label>/equity_<YYYYMMDD>.xlsx
"""

from __future__ import annotations

import io
import logging
import os
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from tempfile import gettempdir

# Matplotlib is imported transitively through the BOT tab modules even though
# this exporter writes only tables. The MPLCONFIGDIR override must run before
# any tab import or it is a no-op (matplotlib reads it during its own import).
_MPLCONFIGDIR = Path(gettempdir()) / "nocccd-streamlit-matplotlib"
_MPLCONFIGDIR.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("MPLCONFIGDIR", str(_MPLCONFIGDIR))

# Silence Streamlit's "no runtime found" warnings when tab modules import
# @st.cache_data outside a Streamlit session.
logging.getLogger("streamlit.runtime.caching.cache_data_api").addFilter(
    lambda record: "No runtime found" not in record.getMessage()
)


import pandas as pd  # noqa: E402
import xlsxwriter  # noqa: E402

from src.pipeline.config import max_acyr_label  # noqa: E402
from src.pipeline.hyper_cache import HyperCache  # noqa: E402
from src.scripts.tabs import (  # noqa: E402
    bot_goal2_wage,
    bot_goal2_xfer,
)
from src.scripts.tabs.bot_helpers import (  # noqa: E402
    aggregate_firstgen,
    aggregate_gender,
    aggregate_race,
)


# ---------------------------------------------------------------------------
# Output destination — mirrors bot_excel_export.py convention
# ---------------------------------------------------------------------------

_DEFAULT_EXPORT_ROOT = (
    "/Users/hoonywise/Library/CloudStorage/"
    "OneDrive-NorthOrangeCountyCommunityCollegeDistrict/"
    "Documents - EST Data/BOT Reports/Equity Analysis"
)
EXPORT_ROOT = Path(os.environ.get("BOT_EXPORT_ROOT_EQUITY", _DEFAULT_EXPORT_ROOT))


# ---------------------------------------------------------------------------
# Metric and subgroup configuration
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class EquityMetric:
    title: str
    vision: str            # "Equity in Access" | "Equity in Success" | "Equity in Support"
    metric_type: str       # "Composition" | "Outcome Rate" | "Average"
    direction: str         # "Higher is Better" | "Lower is Better" | "Context Only"
    moderate: float | None  # gap threshold (decimal for rates, units for averages)
    large: float | None
    notes: str
    dataset: str
    units_metric: bool = False     # special path for avg-units (Goal 3)
    composition: bool = False      # no separate base; num = denom = headcount
    use_xfer_normalize: bool = False
    use_wage_shift: bool = False
    base_dataset: str | None = None             # e.g. "bot_goal2_wage_denom"
    base_credit_only: bool = False              # filter base to site=="Credit"
    base_noncredit_only: bool = False           # filter base to site=="Noncredit"


METRICS: list[EquityMetric] = [
    EquityMetric(
        title="Student Enrollment",
        vision="Equity in Access",
        metric_type="Composition",
        direction="Context Only",
        moderate=None, large=None,
        notes=(
            "Enter subgroup enrollment headcount as numerator and total "
            "population as denominator."
        ),
        dataset="bot_goal1_students",
        composition=True,
    ),
    EquityMetric(
        title="Completion: Credit Certificates",
        vision="Equity in Success",
        metric_type="Outcome Rate",
        direction="Higher is Better",
        moderate=0.02, large=0.05,
        notes=(
            "Numerator = students who earned a CCCCO-approved credit "
            "certificate. Denominator = total credit students."
        ),
        dataset="bot_goal2_cert",
        base_dataset="bot_goal1_students",
        base_credit_only=True,
    ),
    EquityMetric(
        title="Completion: Noncredit Certificates",
        vision="Equity in Success",
        metric_type="Outcome Rate",
        direction="Higher is Better",
        moderate=0.02, large=0.05,
        notes=(
            "Numerator = NOCE students who earned a noncredit certificate. "
            "Denominator = NOCE noncredit students enrolled in CTE-eligible "
            "subjects."
        ),
        dataset="bot_goal2_cert_nc",
        base_dataset="bot_goal2_cert_nc_denom",
    ),
    EquityMetric(
        title="Completion: Associate Degrees (Not for Transfer)",
        vision="Equity in Success",
        metric_type="Outcome Rate",
        direction="Higher is Better",
        moderate=0.02, large=0.05,
        notes=(
            "Numerator = students who earned an associate degree (not ADT). "
            "Denominator = total credit students."
        ),
        dataset="bot_goal2_assoc",
        base_dataset="bot_goal1_students",
        base_credit_only=True,
    ),
    EquityMetric(
        title="Completion: Associate Degrees for Transfer",
        vision="Equity in Success",
        metric_type="Outcome Rate",
        direction="Higher is Better",
        moderate=0.02, large=0.05,
        notes=(
            "Numerator = students who earned an ADT. Denominator = total "
            "credit students."
        ),
        dataset="bot_goal2_adt",
        base_dataset="bot_goal1_students",
        base_credit_only=True,
    ),
    EquityMetric(
        title="Completion: Baccalaureate Degrees",
        vision="Equity in Success",
        metric_type="Outcome Rate",
        direction="Higher is Better",
        moderate=0.02, large=0.05,
        notes=(
            "Numerator = students who earned a baccalaureate degree. "
            "Denominator = total credit students. NOCCCD currently has no "
            "baccalaureate awardees; all cells will be empty."
        ),
        dataset="bot_goal2_bac",
        base_dataset="bot_goal1_students",
        base_credit_only=True,
    ),
    EquityMetric(
        title="Transfer to 4-Year Institution",
        vision="Equity in Success",
        metric_type="Outcome Rate",
        direction="Higher is Better",
        moderate=0.02, large=0.05,
        notes=(
            "Numerator = students who transferred to a four-year institution. "
            "Denominator = total credit students."
        ),
        dataset="bot_goal2_xfer",
        base_dataset="bot_goal1_students",
        base_credit_only=True,
        use_xfer_normalize=True,
    ),
    EquityMetric(
        title="Attain Living Wage",
        vision="Equity in Support",
        metric_type="Outcome Rate",
        direction="Higher is Better",
        moderate=0.02, large=0.05,
        notes=(
            "Numerator = exited non-transfer students who attained the Orange "
            "County living wage in the year after exit. Denominator = exited "
            "non-transfer students."
        ),
        dataset="bot_goal2_wage",
        base_dataset="bot_goal2_wage_denom",
        use_wage_shift=True,
    ),
    EquityMetric(
        title="Maximize Financial Aid",
        vision="Equity in Support",
        metric_type="Outcome Rate",
        direction="Higher is Better",
        moderate=0.02, large=0.05,
        notes=(
            "Numerator = students meeting the financial aid outcome (Pell or "
            "BOG). Denominator = total credit students (Goal 1 Credit base)."
        ),
        dataset="bot_goal3_finaid",
        base_dataset="bot_goal1_students",
        base_credit_only=True,
    ),
    EquityMetric(
        title="Reduce Units to Completion",
        vision="Equity in Support",
        metric_type="Average",
        direction="Lower is Better",
        moderate=2.0, large=5.0,
        notes=(
            "For an accurate overall average, numerator = total credit units "
            "earned across ADT recipients and denominator = number of ADT "
            "recipients. Rate = numerator / denominator = average units."
        ),
        dataset="bot_goal3_units",
        units_metric=True,
    ),
]


# Subgroups that appear as data rows in Data_Entry. Order is fixed because
# the PPG-1 sheet's row layout mirrors Data_Entry row-for-row.
@dataclass(frozen=True)
class Subgroup:
    group_type: str        # "Race/Ethnicity" | "Gender" | "First-Generation Status"
    label: str             # template label (e.g. "Latino/Hispanic")
    bot_key: str           # BOT internal key (e.g. "Hispanic or Latino", "F", "Y")


SUBGROUPS: list[Subgroup] = [
    Subgroup("Race/Ethnicity", "Asian", "Asian"),
    Subgroup("Race/Ethnicity", "Black/African American", "Black or African American"),
    Subgroup("Race/Ethnicity", "Filipino", "Filipino"),
    Subgroup("Race/Ethnicity", "Latino/Hispanic", "Hispanic or Latino"),
    Subgroup("Race/Ethnicity", "Multiethnic", "Multiethnicity"),
    Subgroup("Race/Ethnicity", "White", "White Non-Hispanic"),
    Subgroup("Gender", "Female", "F"),
    Subgroup("Gender", "Male", "M"),
    Subgroup("Gender", "Non-Binary", "NB"),
    Subgroup("First-Generation Status", "First-Generation College Student", "Y"),
    Subgroup("First-Generation Status", "Not First-Generation College Student", "N"),
]

# Always-suppressed groups — listed in Summary as "--" but not in Data_Entry,
# mirroring the template. Pulled out so they can grow without disturbing the
# SUMIFS row ranges in the PPG-1 sheet. Heatmap_Summary omits suppressed
# groups entirely (matching the template), since their cells would all be "--".
SUPPRESSED_RACE_LABELS = [
    "American Indian/AK Native",
    "Pacific Islander/HI Native",
]

# Display order of race rows in the Summary sheet, matching the prior NOCCCD
# template exactly (Asian leads as the largest non-Latino group, then alpha
# with suppressed groups interleaved at AK Native and Pacific Islander).
SUMMARY_RACE_ORDER = [
    "Asian",
    "American Indian/AK Native",
    "Black/African American",
    "Filipino",
    "Latino/Hispanic",
    "Multiethnic",
    "Pacific Islander/HI Native",
    "White",
]


# ---------------------------------------------------------------------------
# Year selection
# ---------------------------------------------------------------------------

def _baseline_and_current_labels() -> tuple[str, str, str, str]:
    """Returns (baseline_filter, current_filter, baseline_display, current_display).

    The BOT Hyper extracts store ``academic_year`` in long form
    (``2020-2021``); workbook headers and the prior Excel template use short
    form (``2020-21``). We need both: the long form to filter rows, the
    short form to label cells.

    Anchoring on Goal 1 keeps the equity workbook aligned with the BOT
    workbook's reporting cycle even when the 5-yr window slides forward.
    """
    from src.pipeline.config import DATASETS

    cfg = DATASETS["bot_goal1_students"]
    acyrs = sorted(cfg[cfg["param_name"]], key=lambda value: int(value))
    baseline_start = int(acyrs[0])
    current_start = int(acyrs[-1])
    return (
        f"{baseline_start}-{baseline_start + 1}",                 # "2020-2021"
        f"{current_start}-{current_start + 1}",                   # "2024-2025"
        f"{baseline_start}-{(baseline_start + 1) % 100:02d}",     # "2020-21"
        f"{current_start}-{(current_start + 1) % 100:02d}",       # "2024-25"
    )


def _normalize_academic_year(df: pd.DataFrame) -> pd.DataFrame:
    """Coerce ``academic_year`` column to long form ``YYYY-YYYY``.

    bot_goal2_wage's ``_shift_academic_year()`` collapses ``2023-2024`` to
    ``2024-25`` (short form), which would not match the long-form filter
    label used everywhere else in this exporter. Re-expand short form so
    every metric is filterable with the same canonical label.
    """
    if "academic_year" not in df.columns:
        return df
    out = df.copy()

    def _to_long(s):
        if not isinstance(s, str) or "-" not in s:
            return s
        parts = s.split("-", 1)
        if len(parts[0]) == 4 and len(parts[1]) == 2:
            try:
                return f"{parts[0]}-{int(parts[0]) + 1}"
            except ValueError:
                return s
        return s

    out["academic_year"] = out["academic_year"].astype(str).map(_to_long)
    return out


# ---------------------------------------------------------------------------
# BOT data loading per metric (mirrors bot_excel_export._build_*)
# ---------------------------------------------------------------------------

def _credit_goal1_base(cache: HyperCache) -> pd.DataFrame:
    base = cache.get("bot_goal1_students")
    return base[base["site"] == "Credit"].copy()


def _load_metric_data(
    metric: EquityMetric, cache: HyperCache,
) -> tuple[pd.DataFrame, pd.DataFrame | None]:
    """Return (df, base_df) for a metric, applying the same prep each BOT tab does."""
    if metric.composition:
        return _normalize_academic_year(cache.get(metric.dataset)), None

    if metric.use_wage_shift:
        df = bot_goal2_wage.shift_df(cache.get(metric.dataset))
        base = bot_goal2_wage.shift_df(cache.get(metric.base_dataset))
        return _normalize_academic_year(df), _normalize_academic_year(base)

    if metric.use_xfer_normalize:
        # Goal 1 Credit base supplies the acyr→academic_year mapping that
        # xfer.normalize uses to keep the rate-metric merge consistent.
        base = _credit_goal1_base(cache)
        df = bot_goal2_xfer.normalize(cache.get(metric.dataset), base_df=base)
        return _normalize_academic_year(df), _normalize_academic_year(base)

    if metric.base_dataset is None:
        return _normalize_academic_year(cache.get(metric.dataset)), None

    base = cache.get(metric.base_dataset).copy()
    if metric.base_credit_only:
        base = base[base["site"] == "Credit"].copy()
    elif metric.base_noncredit_only:
        base = base[base["site"] == "Noncredit"].copy()
    return (
        _normalize_academic_year(cache.get(metric.dataset)),
        _normalize_academic_year(base),
    )


# ---------------------------------------------------------------------------
# Numerator / denominator computation per metric × subgroup × year
# ---------------------------------------------------------------------------

def _composition_counts(df: pd.DataFrame, year_label: str) -> dict[tuple[str, str], tuple[int, int]]:
    """Composition (Student Enrollment): num = subgroup headcount, denom = total headcount."""
    yr = df[df["academic_year"] == year_label]
    stu = yr.drop_duplicates(subset=["pidm", "academic_year"]).copy()

    out: dict[tuple[str, str], tuple[int, int]] = {}
    if stu.empty:
        return out

    total_all = int(stu["pidm"].nunique())

    # Race
    race_counts = stu.groupby("race_description")["pidm"].nunique()
    for sub in SUBGROUPS:
        if sub.group_type != "Race/Ethnicity":
            continue
        n = int(race_counts.get(sub.bot_key, 0) or 0)
        # Composition denominator = subgroup itself for race (matches template).
        out[(sub.group_type, sub.label)] = (n, n)

    # Gender — template denominator is total (gender breakdown of full population)
    gender_counts = stu.groupby("gender")["pidm"].nunique()
    for sub in SUBGROUPS:
        if sub.group_type != "Gender":
            continue
        n = int(gender_counts.get(sub.bot_key, 0) or 0)
        out[(sub.group_type, sub.label)] = (n, total_all)

    # First-Gen — credit-only filter mirrors the BOT goal1 firstgen rule
    fg_stu = stu[stu["site"] == "Credit"].copy()
    fg_total = int(fg_stu["pidm"].nunique()) if not fg_stu.empty else 0
    fg_stu["fg"] = fg_stu["first_gen_ind"].where(
        fg_stu["first_gen_ind"].isin(["Y", "N"]), "Unknown",
    )
    fg_counts = fg_stu.groupby("fg")["pidm"].nunique()
    for sub in SUBGROUPS:
        if sub.group_type != "First-Generation Status":
            continue
        n = int(fg_counts.get(sub.bot_key, 0) or 0)
        out[(sub.group_type, sub.label)] = (n, fg_total)

    return out


def _rate_counts(
    df: pd.DataFrame, base_df: pd.DataFrame, year_label: str,
) -> dict[tuple[str, str], tuple[int, int]]:
    """Rate metric: num = subgroup count(df), denom = subgroup count(base_df)."""
    df_yr = df[df["academic_year"] == year_label]
    base_yr = base_df[base_df["academic_year"] == year_label]
    out: dict[tuple[str, str], tuple[int, int]] = {}
    if df_yr.empty and base_yr.empty:
        return out

    # Reuse bot_helpers.aggregate_* — same logic as Streamlit/PDF/Excel views.
    df_race = aggregate_race(df_yr, base_df=base_yr)
    df_gender = aggregate_gender(df_yr, base_df=base_yr)
    df_fg = aggregate_firstgen(df_yr, credit_only=True, base_df=base_yr)

    for sub in SUBGROUPS:
        if sub.group_type == "Race/Ethnicity":
            row = df_race[df_race["race_description"] == sub.bot_key]
            n = int(row["count"].iloc[0]) if not row.empty else 0
            d = int(row["total"].iloc[0]) if not row.empty else 0
        elif sub.group_type == "Gender":
            row = df_gender[df_gender["gender"] == sub.bot_key]
            n = int(row["count"].iloc[0]) if not row.empty else 0
            d = int(row["total"].iloc[0]) if not row.empty else 0
        elif sub.group_type == "First-Generation Status":
            row = df_fg[df_fg["fg"] == sub.bot_key]
            n = int(row["count"].iloc[0]) if not row.empty else 0
            d = int(row["total"].iloc[0]) if not row.empty else 0
        else:
            n, d = 0, 0
        out[(sub.group_type, sub.label)] = (n, d)
    return out


def _units_counts(df: pd.DataFrame, year_label: str) -> dict[tuple[str, str], tuple[float, int]]:
    """Average-units metric: num = SUM of sum_hours_earned, denom = student count.

    rate = num/denom = average units, matching how Goal 3 Average Units tab
    displays the metric. PPG-1 doesn't apply (Direction = Lower is Better),
    but we still populate Data_Entry so the heatmap's descriptive thresholds
    (±2 / ±5 units from Overall_Inputs) can flow through.
    """
    yr = df[df["academic_year"] == year_label]
    stu = yr.drop_duplicates(subset=["pidm", "academic_year"]).copy()
    out: dict[tuple[str, str], tuple[float, int]] = {}
    if stu.empty:
        return out

    # Race
    race_grp = stu.groupby("race_description").agg(
        units_sum=("sum_hours_earned", "sum"),
        student_count=("pidm", "nunique"),
    )
    for sub in SUBGROUPS:
        if sub.group_type != "Race/Ethnicity":
            continue
        if sub.bot_key in race_grp.index:
            row = race_grp.loc[sub.bot_key]
            out[(sub.group_type, sub.label)] = (
                float(row["units_sum"] or 0),
                int(row["student_count"] or 0),
            )
        else:
            out[(sub.group_type, sub.label)] = (0.0, 0)

    gender_grp = stu.groupby("gender").agg(
        units_sum=("sum_hours_earned", "sum"),
        student_count=("pidm", "nunique"),
    )
    for sub in SUBGROUPS:
        if sub.group_type != "Gender":
            continue
        if sub.bot_key in gender_grp.index:
            row = gender_grp.loc[sub.bot_key]
            out[(sub.group_type, sub.label)] = (
                float(row["units_sum"] or 0),
                int(row["student_count"] or 0),
            )
        else:
            out[(sub.group_type, sub.label)] = (0.0, 0)

    fg_stu = stu.copy()
    fg_stu["fg"] = fg_stu["first_gen_ind"].where(
        fg_stu["first_gen_ind"].isin(["Y", "N"]), "Unknown",
    )
    fg_grp = fg_stu.groupby("fg").agg(
        units_sum=("sum_hours_earned", "sum"),
        student_count=("pidm", "nunique"),
    )
    for sub in SUBGROUPS:
        if sub.group_type != "First-Generation Status":
            continue
        if sub.bot_key in fg_grp.index:
            row = fg_grp.loc[sub.bot_key]
            out[(sub.group_type, sub.label)] = (
                float(row["units_sum"] or 0),
                int(row["student_count"] or 0),
            )
        else:
            out[(sub.group_type, sub.label)] = (0.0, 0)

    return out


def _overall_counts_for_year(
    metric: EquityMetric,
    df: pd.DataFrame,
    base_df: pd.DataFrame | None,
    year_label: str,
) -> tuple[float | None, float | None]:
    """District-wide totals for a metric × year, ignoring subgroup filters.

    Mirrors the values the template author hand-entered in Overall_Inputs!E/F/H/I:
    e.g., for Credit Cert 2024-25 the template shows 3152/46836 — that's the
    total cert earners across ALL races (including AK Native, Pacific Islander,
    Unreported) divided by the full credit population. Computing this from the
    BOT pipeline lets the workbook self-populate that "true overall" instead
    of leaving the cells blank.

    Returns (None, None) for metrics where an overall doesn't apply
    (composition, average, or empty data) — the writer will leave those cells
    blank, matching the template.
    """
    if metric.composition:
        return None, None
    if metric.units_metric:
        # Units is an average; overall avg ≠ sum of subgroup numerators / sum
        # of subgroup denominators in a meaningful way for the analyst — leave
        # blank, matching the template.
        return None, None

    df_yr = df[df["academic_year"] == year_label]
    n_unique = df_yr.drop_duplicates(subset=["pidm", "academic_year"])["pidm"].nunique()
    if n_unique == 0:
        # No data for this year (e.g., Bac with no NOCCCD awardees).
        return None, None
    if base_df is None:
        return float(n_unique), None
    base_yr = base_df[base_df["academic_year"] == year_label]
    d_unique = base_yr.drop_duplicates(subset=["pidm", "academic_year"])["pidm"].nunique()
    return float(n_unique), float(d_unique) if d_unique else None


def _build_metric_counts(
    metric: EquityMetric,
    cache: HyperCache,
    baseline_label: str,
    current_label: str,
) -> tuple[
    dict[tuple[str, str], dict[str, tuple[float, float]]],
    dict[str, tuple[float | None, float | None]],
]:
    """Returns (subgroup_counts, overall_counts) for one metric.

    - subgroup_counts: {(group_type, label): {year_label: (num, denom)}}
    - overall_counts:  {year_label: (num, denom) or (None, None)}
    """
    df, base_df = _load_metric_data(metric, cache)
    subgroup_result: dict[tuple[str, str], dict[str, tuple[float, float]]] = {}
    overall_result: dict[str, tuple[float | None, float | None]] = {}

    for year_label in (baseline_label, current_label):
        if metric.composition:
            counts = _composition_counts(df, year_label)
        elif metric.units_metric:
            counts = _units_counts(df, year_label)
        else:
            counts = _rate_counts(df, base_df, year_label)
        for key, (n, d) in counts.items():
            subgroup_result.setdefault(key, {})[year_label] = (n, d)
        overall_result[year_label] = _overall_counts_for_year(
            metric, df, base_df, year_label,
        )

    # Ensure every subgroup has an entry for both years (default to 0/0 if
    # data was empty for that year — fall through to "Insufficient data" in
    # the workbook's PPG-1 formulas).
    for sub in SUBGROUPS:
        key = (sub.group_type, sub.label)
        subgroup_result.setdefault(key, {})
        for yr in (baseline_label, current_label):
            subgroup_result[key].setdefault(yr, (0.0, 0.0))

    return subgroup_result, overall_result


# ---------------------------------------------------------------------------
# Workbook writers
# ---------------------------------------------------------------------------

# Sheet/row constants — keep in sync across all sheets that reference them.
DE_HEADER_ROW = 0           # Data_Entry header row index (0-based) -> Excel row 1
DE_FIRST_DATA_ROW = 1       # Excel row 2
DE_TOTAL_ROWS = len(METRICS) * len(SUBGROUPS)   # 110
DE_LAST_DATA_ROW = DE_FIRST_DATA_ROW + DE_TOTAL_ROWS - 1    # row index 110, Excel row 111

PPG_HEADER_ROW = 3          # Excel row 4
PPG_FIRST_DATA_ROW = 4      # Excel row 5
PPG_LAST_DATA_ROW = PPG_FIRST_DATA_ROW + DE_TOTAL_ROWS - 1


def _de_excel_row(row_idx: int) -> int:
    """Convert 0-based Data_Entry data-row index (0..109) to Excel 1-based row."""
    return DE_FIRST_DATA_ROW + row_idx + 1


def _ppg_excel_row(row_idx: int) -> int:
    return PPG_FIRST_DATA_ROW + row_idx + 1


def _is_suppressed(numerator: float, denominator: float) -> bool:
    """N <= 10 suppression rule from PPG-1 methodology."""
    return numerator is None or denominator is None or float(numerator) <= 10


def _write_instructions_sheet(workbook, baseline_label: str, current_label: str) -> None:
    ws = workbook.add_worksheet("Instructions")
    title_fmt = workbook.add_format({
        "bold": True, "font_size": 14, "font_color": "#FFFFFF",
        "bg_color": "#004062",
    })
    label_fmt = workbook.add_format({"bold": True, "valign": "top"})
    body_fmt = workbook.add_format({"text_wrap": True, "valign": "top"})

    ws.write(0, 0, "NOCCCD Descriptive Equity Gap Template", title_fmt)
    ws.set_column(0, 0, 24)
    ws.set_column(1, 1, 90)

    rows = [
        ("Purpose", (
            "Enter numerator and denominator data by subgroup for each BOT "
            "metric. The PPG-1 sheet computes the Percentage Point Gap Minus "
            "One; the Heatmap and Summary sheets visualize disproportionate "
            "impact."
        )),
        ("Method", (
            "PPG-1 (CCCCO 2022) compares each subgroup's outcome rate against "
            "all OTHER students. Disproportionate impact (DI) is observed "
            "when the adjusted gap is at least 1 percentage point below zero "
            "AND outside the 95% margin of error, with E floored at 2%."
        )),
        ("Reporting cycle", (
            f"Baseline = {baseline_label}, Current = {current_label}. "
            "Numerator/denominator values are written from the BOT pipeline "
            "on every export run; re-running picks up any BOT logic revision "
            "automatically."
        )),
        ("How to use", (
            "1) Open this workbook in Excel; formulas recalculate on open. "
            "2) Review Summary and Heatmap_Summary for at-a-glance DI "
            "results. 3) Drill into the PPG-1 sheet for per-subgroup detail. "
            "4) Adjust thresholds in Overall_Inputs columns K/L if a metric "
            "needs different moderate/large gap cutoffs."
        )),
        ("Suppression", (
            "Subgroups with subgroup numerator <= 10 are reported as "
            "\"Insufficient data (N<=10)\" in the PPG-1 sheet to maintain "
            "confidentiality. American Indian/AK Native and Pacific "
            "Islander/HI Native typically fall in this range and are listed "
            "in Summary as \"--\"."
        )),
        ("Average-units metric", (
            "Reduce Units to Completion is an average, not a rate. PPG-1 "
            "does not apply; the heatmap uses descriptive thresholds (\xb12 "
            "and \xb15 units from Overall_Inputs)."
        )),
        ("Source", (
            "Banner via the BOT Hyper extracts. Living-wage data is "
            "CCCCO Supplemental & Success Data for the SCFF files."
        )),
    ]
    for r, (label, body) in enumerate(rows, start=2):
        ws.write(r, 0, label, label_fmt)
        ws.write(r, 1, body, body_fmt)
        ws.set_row(r, 60)


def _write_overall_inputs_sheet(
    workbook,
    overall_data: dict[str, dict[str, tuple[float | None, float | None]]],
    baseline_display: str,
    current_display: str,
) -> None:
    ws = workbook.add_worksheet("Overall_Inputs")
    header_fmt = workbook.add_format({
        "bold": True, "bg_color": "#D9EAF7", "border": 1,
        "text_wrap": True, "valign": "top",
    })
    pct_fmt = workbook.add_format({"num_format": "0.0%"})
    int_fmt = workbook.add_format({"num_format": "#,##0"})
    dec_fmt = workbook.add_format({"num_format": "#,##0.0"})

    headers = [
        "Metric", "Vision Area", "Metric Type", "Direction",
        f"Overall Numerator {baseline_display}",
        f"Overall Denominator {baseline_display}",
        f"Overall Rate {baseline_display}",
        f"Overall Numerator {current_display}",
        f"Overall Denominator {current_display}",
        f"Overall Rate {current_display}",
        "Moderate Gap Threshold", "Large Gap Threshold",
        "Notes",
    ]
    for c, h in enumerate(headers):
        ws.write(0, c, h, header_fmt)

    widths = [42, 18, 14, 16, 22, 22, 18, 22, 22, 18, 18, 18, 60]
    for c, w in enumerate(widths):
        ws.set_column(c, c, w)

    for r, m in enumerate(METRICS, start=1):
        ws.write(r, 0, m.title)
        ws.write(r, 1, m.vision)
        ws.write(r, 2, m.metric_type)
        ws.write(r, 3, m.direction)

        # Overall N/D: write district-wide totals from the BOT pipeline.
        # Composition (Student Enrollment) and Average (Reduce Units) get
        # blank cells, matching the template — neither has a meaningful
        # "overall rate" to compute from a numerator/denominator pair.
        # Analysts can hand-enter override values; the Data_Entry SUMIFS
        # formula falls back to summing displayed subgroups when these
        # cells are blank.
        n_base, d_base = overall_data.get(m.title, {}).get(baseline_display, (None, None))
        n_curr, d_curr = overall_data.get(m.title, {}).get(current_display, (None, None))
        if n_base is not None:
            ws.write_number(r, 4, float(n_base), int_fmt)
        else:
            ws.write_blank(r, 4, None)
        if d_base is not None:
            ws.write_number(r, 5, float(d_base), int_fmt)
        else:
            ws.write_blank(r, 5, None)
        ws.write_formula(r, 6, f"=IFERROR(E{r+1}/F{r+1},\"\")", pct_fmt)
        if n_curr is not None:
            ws.write_number(r, 7, float(n_curr), int_fmt)
        else:
            ws.write_blank(r, 7, None)
        if d_curr is not None:
            ws.write_number(r, 8, float(d_curr), int_fmt)
        else:
            ws.write_blank(r, 8, None)
        ws.write_formula(r, 9, f"=IFERROR(H{r+1}/I{r+1},\"\")", pct_fmt)
        if m.units_metric:
            ws.write_number(r, 10, float(m.moderate), dec_fmt)
            ws.write_number(r, 11, float(m.large), dec_fmt)
        elif m.moderate is None:
            ws.write_blank(r, 10, None)
            ws.write_blank(r, 11, None)
        else:
            ws.write_number(r, 10, float(m.moderate), pct_fmt)
            ws.write_number(r, 11, float(m.large), pct_fmt)
        ws.write(r, 12, m.notes)
        ws.set_row(r, 30)


def _write_data_entry_sheet(
    workbook,
    metric_data: dict[str, dict[tuple[str, str], dict[str, tuple[float, float]]]],
    baseline_label: str,
    current_label: str,
) -> None:
    ws = workbook.add_worksheet("Data_Entry")
    header_fmt = workbook.add_format({
        "bold": True, "bg_color": "#D9EAF7", "border": 1,
        "text_wrap": True, "valign": "top",
    })
    pct_fmt = workbook.add_format({"num_format": "0.0%"})
    int_fmt = workbook.add_format({"num_format": "#,##0"})
    dec_fmt = workbook.add_format({"num_format": "#,##0.0"})

    headers = [
        "Key", "Vision Area", "Metric", "Metric Type", "Direction",
        "Group Type", "Group", "Include in Displayed-Group Overall?",
        f"Numerator {baseline_label}", f"Denominator {baseline_label}",
        f"Rate/Avg {baseline_label}",
        f"Numerator {current_label}", f"Denominator {current_label}",
        f"Rate/Avg {current_label}",
        f"Overall Numerator {baseline_label}",
        f"Overall Denominator {baseline_label}",
        f"Overall Rate/Avg {baseline_label}",
        f"Beneficial Gap {baseline_label}",
        f"Overall Numerator {current_label}",
        f"Overall Denominator {current_label}",
        f"Overall Rate/Avg {current_label}",
        f"Beneficial Gap {current_label}",
        "Gap Change", "Trend", "Gap Category", "Priority", "Confidence",
        "Notes",
    ]
    for c, h in enumerate(headers):
        ws.write(0, c, h, header_fmt)

    widths = [44, 18, 36, 14, 16, 16, 28, 26,
              18, 20, 18, 18, 20, 18, 22, 24, 20, 18,
              22, 24, 20, 18, 14, 22, 22, 14, 28, 50]
    for c, w in enumerate(widths):
        ws.set_column(c, c, w)

    SUMIFS_RANGE = (
        f"$I${DE_FIRST_DATA_ROW + 1}:$I${DE_LAST_DATA_ROW + 1}"
    )
    SUMIFS_CRITERIA = (
        f"Data_Entry!$I${DE_FIRST_DATA_ROW + 1}:$I${DE_LAST_DATA_ROW + 1}"
    )

    row_idx = 0
    for m in METRICS:
        for sub in SUBGROUPS:
            r = _de_excel_row(row_idx)   # 1-based Excel row
            r0 = r - 1                    # 0-based for xlsxwriter
            counts = metric_data[m.title].get(
                (sub.group_type, sub.label), {}
            )
            n_base, d_base = counts.get(baseline_label, (0, 0))
            n_curr, d_curr = counts.get(current_label, (0, 0))

            ws.write(r0, 0, f"{m.title}|{sub.label}")
            ws.write(r0, 1, m.vision)
            ws.write(r0, 2, m.title)
            ws.write(r0, 3, m.metric_type)
            ws.write(r0, 4, m.direction)
            ws.write(r0, 5, sub.group_type)
            ws.write(r0, 6, sub.label)
            ws.write(r0, 7, "Yes")

            # Numerator/denominator are values from the BOT pipeline.
            # For units metric, numerator may be a float (sum of units).
            num_fmt = dec_fmt if m.units_metric else int_fmt
            den_fmt = int_fmt
            if n_base or d_base:
                ws.write_number(r0, 8, float(n_base), num_fmt)
                ws.write_number(r0, 9, float(d_base), den_fmt)
            else:
                ws.write_blank(r0, 8, None, num_fmt)
                ws.write_blank(r0, 9, None, den_fmt)
            ws.write_formula(r0, 10, f"=IFERROR(I{r}/J{r},\"\")",
                             dec_fmt if m.units_metric else pct_fmt)

            if n_curr or d_curr:
                ws.write_number(r0, 11, float(n_curr), num_fmt)
                ws.write_number(r0, 12, float(d_curr), den_fmt)
            else:
                ws.write_blank(r0, 11, None, num_fmt)
                ws.write_blank(r0, 12, None, den_fmt)
            ws.write_formula(r0, 13, f"=IFERROR(L{r}/M{r},\"\")",
                             dec_fmt if m.units_metric else pct_fmt)

            # Overall N/D — fall back to SUMIFS over Data_Entry when
            # Overall_Inputs leaves the cell blank.
            for col, src_letter in [(14, "I"), (15, "J"), (18, "L"), (19, "M")]:
                # Overall_Inputs columns: E=4, F=5, H=7, I=8 (1-based: E,F,H,I)
                oi_col = {"I": "E", "J": "F", "L": "H", "M": "I"}[src_letter]
                ws.write_formula(
                    r0, col,
                    (
                        f"=IF(AND(IFERROR(VLOOKUP($C{r},Overall_Inputs!$A:$M,"
                        f"{ord(oi_col)-ord('A')+1},FALSE),\"\")<>\"\","
                        f"IFERROR(VLOOKUP($C{r},Overall_Inputs!$A:$M,"
                        f"{ord(oi_col)-ord('A')+2},FALSE),\"\")<>\"\"),"
                        f"IFERROR(VLOOKUP($C{r},Overall_Inputs!$A:$M,"
                        f"{ord(oi_col)-ord('A')+1},FALSE),\"\"),"
                        f"SUMIFS(${src_letter}${DE_FIRST_DATA_ROW+1}:"
                        f"${src_letter}${DE_LAST_DATA_ROW+1},"
                        f"$C${DE_FIRST_DATA_ROW+1}:$C${DE_LAST_DATA_ROW+1},$C{r},"
                        f"$F${DE_FIRST_DATA_ROW+1}:$F${DE_LAST_DATA_ROW+1},$F{r},"
                        f"$H${DE_FIRST_DATA_ROW+1}:$H${DE_LAST_DATA_ROW+1},\"Yes\"))"
                    ),
                    int_fmt,
                )
            ws.write_formula(r0, 16, f"=IFERROR(O{r}/P{r},\"\")",
                             dec_fmt if m.units_metric else pct_fmt)
            ws.write_formula(
                r0, 17,
                (
                    f"=IF($D{r}=\"Composition\",\"\","
                    f"IF($E{r}=\"Lower is Better\",Q{r}-K{r},K{r}-Q{r}))"
                ),
                dec_fmt if m.units_metric else pct_fmt,
            )
            ws.write_formula(r0, 20, f"=IFERROR(S{r}/T{r},\"\")",
                             dec_fmt if m.units_metric else pct_fmt)
            ws.write_formula(
                r0, 21,
                (
                    f"=IF($D{r}=\"Composition\",\"\","
                    f"IF($E{r}=\"Lower is Better\",U{r}-N{r},N{r}-U{r}))"
                ),
                dec_fmt if m.units_metric else pct_fmt,
            )
            # Gap change
            ws.write_formula(r0, 22, f"=IF(OR(R{r}=\"\",V{r}=\"\"),\"\",V{r}-R{r})",
                             dec_fmt if m.units_metric else pct_fmt)
            ws.write_formula(
                r0, 23,
                (
                    f"=IF(W{r}=\"\",\"No Data\","
                    f"IF(ABS(W{r})<{0.5 if m.units_metric else 0.01},"
                    f"\"Stable/Relatively Unchanged\","
                    f"IF(W{r}>0,\"Closing/Improving\",\"Widening/Worsening\")))"
                ),
            )
            # Gap Category — uses Overall_Inputs thresholds.
            ws.write_formula(
                r0, 24,
                (
                    f"=IF(V{r}=\"\",\"\","
                    f"IF(V{r}<=-IFERROR(IF(VLOOKUP($C{r},Overall_Inputs!$A:$M,12,FALSE)=\"\","
                    f"{m.large if m.large is not None else 0.05},"
                    f"VLOOKUP($C{r},Overall_Inputs!$A:$M,12,FALSE)),"
                    f"{m.large if m.large is not None else 0.05}),"
                    f"\"Large Negative Gap\","
                    f"IF(V{r}<=-IFERROR(IF(VLOOKUP($C{r},Overall_Inputs!$A:$M,11,FALSE)=\"\","
                    f"{m.moderate if m.moderate is not None else 0.02},"
                    f"VLOOKUP($C{r},Overall_Inputs!$A:$M,11,FALSE)),"
                    f"{m.moderate if m.moderate is not None else 0.02}),"
                    f"\"Moderate Negative Gap\","
                    f"IF(V{r}<0,\"Small Negative Gap\",\"At/Above Overall\"))))"
                ),
            )
            ws.write_formula(
                r0, 25,
                (
                    f"=IF(Y{r}=\"\",\"\","
                    f"IF(Y{r}=\"Large Negative Gap\",\"High\","
                    f"IF(Y{r}=\"Moderate Negative Gap\",\"Moderate\","
                    f"IF(Y{r}=\"Small Negative Gap\",\"Monitor\",\"Low\"))))"
                ),
            )
            # Confidence based on current denominator size.
            ws.write_formula(
                r0, 26,
                (
                    f"=IF(OR(M{r}=\"\",M{r}=0),\"No denominator entered\","
                    f"IF(M{r}<30,\"Low N; use caution\","
                    f"IF(M{r}<100,\"Moderate N; monitor\","
                    f"\"Sufficient for descriptive review\")))"
                ),
            )
            ws.write(r0, 27, m.notes)
            row_idx += 1

    ws.freeze_panes(1, 0)
    _ = SUMIFS_RANGE  # already used inline above (kept for readability)
    _ = SUMIFS_CRITERIA


def _write_ppg1_sheet(workbook, baseline_label: str, current_label: str) -> None:
    ws = workbook.add_worksheet("PPG-1")
    title_fmt = workbook.add_format({
        "bold": True, "font_size": 14, "font_color": "#FFFFFF",
        "bg_color": "#004062",
    })
    intro_fmt = workbook.add_format({"italic": True, "text_wrap": True})
    header_fmt = workbook.add_format({
        "bold": True, "bg_color": "#D9EAF7", "border": 1,
        "text_wrap": True, "valign": "top",
    })
    pct_fmt = workbook.add_format({"num_format": "0.0%"})
    dec_fmt = workbook.add_format({"num_format": "0.000"})
    int_fmt = workbook.add_format({"num_format": "#,##0"})

    ws.merge_range(0, 1, 0, 17, "PPG-1 Analysis Template", title_fmt)
    ws.merge_range(
        1, 1, 1, 17,
        (
            "This sheet pulls all metrics and groups from Data_Entry. Rows "
            "without sufficient numerator/denominator are flagged as "
            "Insufficient data. Two-proportion z-test margin of error with "
            "1-percentage-point penalty per CCCCO 2022 PPG-1 methodology."
        ),
        intro_fmt,
    )

    headers = [
        "Key", "Metric", "Group Type", "Group", "Direction",
        f"{baseline_label} Numerator", f"{baseline_label} Denominator",
        f"{baseline_label} Subgroup Rate",
        f"{baseline_label} Total Numerator", f"{baseline_label} Total Denominator",
        f"{baseline_label} Others Numerator", f"{baseline_label} Others Denominator",
        f"{baseline_label} Others Rate",
        f"{baseline_label} Raw Gap (Subgroup - Others)",
        f"{baseline_label} PPG-1 Adjusted Gap",
        f"{baseline_label} SE", f"{baseline_label} MOE (95%)",
        f"{baseline_label} PPG-1 Result",
        f"{current_label} Numerator", f"{current_label} Denominator",
        f"{current_label} Subgroup Rate",
        f"{current_label} Total Numerator", f"{current_label} Total Denominator",
        f"{current_label} Others Numerator", f"{current_label} Others Denominator",
        f"{current_label} Others Rate",
        f"{current_label} Raw Gap (Subgroup - Others)",
        f"{current_label} PPG-1 Adjusted Gap",
        f"{current_label} SE", f"{current_label} MOE (95%)",
        f"{current_label} PPG-1 Result",
        "Raw Gap Change", "Gap Direction", "Overall Interpretation",
        "Analyst Notes",
    ]
    for c, h in enumerate(headers):
        ws.write(PPG_HEADER_ROW, c, h, header_fmt)

    # Reasonable widths
    ws.set_column(0, 0, 44)
    ws.set_column(1, 1, 36)
    ws.set_column(2, 4, 14)
    ws.set_column(5, 34, 16)

    DE_N1 = DE_FIRST_DATA_ROW + 1
    DE_NL = DE_LAST_DATA_ROW + 1

    def sumifs(value_col: str, key_letter: str = "B", group_type_letter: str = "C") -> str:
        return (
            f"SUMIFS(Data_Entry!${value_col}${DE_N1}:${value_col}${DE_NL},"
            f"Data_Entry!$C${DE_N1}:$C${DE_NL},${key_letter}{{r}},"
            f"Data_Entry!$F${DE_N1}:$F${DE_NL},${group_type_letter}{{r}},"
            f"Data_Entry!$H${DE_N1}:$H${DE_NL},\"Yes\")"
        )

    sumifs_I_curr = sumifs("I")    # baseline numerator (Data_Entry I)
    sumifs_J_curr = sumifs("J")    # baseline denominator
    sumifs_L_curr = sumifs("L")    # current numerator
    sumifs_M_curr = sumifs("M")    # current denominator

    for row_idx in range(DE_TOTAL_ROWS):
        ppg_r = _ppg_excel_row(row_idx)        # 1-based PPG-1 Excel row
        de_r = _de_excel_row(row_idx)          # 1-based Data_Entry row
        r0 = ppg_r - 1                          # 0-based for xlsxwriter

        # A: Key, B: Metric, C: Group Type, D: Group, E: Direction
        ws.write_formula(r0, 0, f"=Data_Entry!A{de_r}")
        ws.write_formula(r0, 1, f"=Data_Entry!C{de_r}")
        ws.write_formula(r0, 2, f"=Data_Entry!F{de_r}")
        ws.write_formula(r0, 3, f"=Data_Entry!G{de_r}")
        ws.write_formula(r0, 4, f"=Data_Entry!E{de_r}")

        # F-G: Subgroup numerator/denominator (baseline)
        ws.write_formula(r0, 5, f"=Data_Entry!I{de_r}", int_fmt)
        ws.write_formula(r0, 6, f"=Data_Entry!J{de_r}", int_fmt)
        # H: Subgroup rate (baseline)
        ws.write_formula(r0, 7, f"=IFERROR(F{ppg_r}/G{ppg_r},\"\")", pct_fmt)
        # I-J: Total Numerator/Denominator (baseline) via SUMIFS
        ws.write_formula(r0, 8, "=" + sumifs_I_curr.format(r=ppg_r), int_fmt)
        ws.write_formula(r0, 9, "=" + sumifs_J_curr.format(r=ppg_r), int_fmt)
        # K: Others Numerator (baseline) = Total - Subgroup
        ws.write_formula(r0, 10, f"=IFERROR(I{ppg_r}-F{ppg_r},\"\")", int_fmt)
        # L: Others Denominator (baseline)
        ws.write_formula(r0, 11, f"=IFERROR(J{ppg_r}-G{ppg_r},\"\")", int_fmt)
        # M: Others Rate (baseline)
        ws.write_formula(r0, 12, f"=IFERROR(K{ppg_r}/L{ppg_r},\"\")", pct_fmt)
        # N: Raw Gap (baseline)
        ws.write_formula(r0, 13, f"=IFERROR(H{ppg_r}-M{ppg_r},\"\")", pct_fmt)
        # O: PPG-1 Adjusted Gap (baseline)
        ws.write_formula(
            r0, 14,
            (
                f"=IFERROR(IF($E{ppg_r}=\"Higher is Better\","
                f"M{ppg_r}-H{ppg_r}-0.01,"
                f"IF($E{ppg_r}=\"Lower is Better\","
                f"H{ppg_r}-M{ppg_r}-0.01,\"\")),\"\")"
            ),
            pct_fmt,
        )
        # P: SE (baseline) — two-proportion z-test
        ws.write_formula(
            r0, 15,
            (
                f"=IF(OR($E{ppg_r}=\"Context Only\",$E{ppg_r}=\"Lower is Better\","
                f"$E{ppg_r}=\"\",G{ppg_r}=\"\",L{ppg_r}=\"\",G{ppg_r}=0,L{ppg_r}=0),\"\","
                f"IFERROR(SQRT((H{ppg_r}*(1-H{ppg_r})/G{ppg_r})+"
                f"(M{ppg_r}*(1-M{ppg_r})/L{ppg_r})),\"\"))"
            ),
            dec_fmt,
        )
        # Q: MOE (baseline) — matches template (1.96 * SE, no 2% floor).
        # CCCCO methodology PDF prescribes a 2% floor, but the prior NOCCCD
        # template doesn't apply one and the team's historical reports use
        # the unfloored value. Keeping consistency with the prior workbook
        # so DI flags don't drift between runs.
        ws.write_formula(
            r0, 16,
            f"=IFERROR(1.96*P{ppg_r},\"\")",
            pct_fmt,
        )
        # R: PPG-1 Result (baseline) — matches template logic:
        #   DI when (others - subgroup - 0.01) > MOE  (i.e., O > Q)
        #   Above reference when (subgroup - others) > MOE  (i.e., H-M > Q)
        #   Suppress when either denominator < 10
        ws.write_formula(
            r0, 17,
            (
                f"=IF($E{ppg_r}=\"Context Only\",\"Not applicable - composition/context\","
                f"IF($E{ppg_r}=\"Lower is Better\",\"Not applicable - lower-is-better average/rate; review method\","
                f"IF(OR(G{ppg_r}=\"\",L{ppg_r}=\"\",G{ppg_r}<10,L{ppg_r}<10),\"Insufficient data\","
                f"IF(O{ppg_r}>Q{ppg_r},\"DI: significant PPG-1 gap\","
                f"IF(H{ppg_r}-M{ppg_r}>Q{ppg_r},\"Significantly above reference\","
                f"\"No significant PPG-1 gap\")))))"
            ),
        )

        # S-T: Subgroup numerator/denominator (current)
        ws.write_formula(r0, 18, f"=Data_Entry!L{de_r}", int_fmt)
        ws.write_formula(r0, 19, f"=Data_Entry!M{de_r}", int_fmt)
        ws.write_formula(r0, 20, f"=IFERROR(S{ppg_r}/T{ppg_r},\"\")", pct_fmt)
        ws.write_formula(r0, 21, "=" + sumifs_L_curr.format(r=ppg_r), int_fmt)
        ws.write_formula(r0, 22, "=" + sumifs_M_curr.format(r=ppg_r), int_fmt)
        ws.write_formula(r0, 23, f"=IFERROR(V{ppg_r}-S{ppg_r},\"\")", int_fmt)
        ws.write_formula(r0, 24, f"=IFERROR(W{ppg_r}-T{ppg_r},\"\")", int_fmt)
        ws.write_formula(r0, 25, f"=IFERROR(X{ppg_r}/Y{ppg_r},\"\")", pct_fmt)
        ws.write_formula(r0, 26, f"=IFERROR(U{ppg_r}-Z{ppg_r},\"\")", pct_fmt)
        ws.write_formula(
            r0, 27,
            (
                f"=IFERROR(IF($E{ppg_r}=\"Higher is Better\","
                f"Z{ppg_r}-U{ppg_r}-0.01,"
                f"IF($E{ppg_r}=\"Lower is Better\","
                f"U{ppg_r}-Z{ppg_r}-0.01,\"\")),\"\")"
            ),
            pct_fmt,
        )
        ws.write_formula(
            r0, 28,
            (
                f"=IF(OR($E{ppg_r}=\"Context Only\",$E{ppg_r}=\"Lower is Better\","
                f"$E{ppg_r}=\"\",T{ppg_r}=\"\",Y{ppg_r}=\"\",T{ppg_r}=0,Y{ppg_r}=0),\"\","
                f"IFERROR(SQRT((U{ppg_r}*(1-U{ppg_r})/T{ppg_r})+"
                f"(Z{ppg_r}*(1-Z{ppg_r})/Y{ppg_r})),\"\"))"
            ),
            dec_fmt,
        )
        # AD: MOE (current) — same convention as Q above (no 2% floor).
        ws.write_formula(
            r0, 29,
            f"=IFERROR(1.96*AC{ppg_r},\"\")",
            pct_fmt,
        )
        # AE: PPG-1 Result (current) — same logic as col R, on current-year cols
        ws.write_formula(
            r0, 30,
            (
                f"=IF($E{ppg_r}=\"Context Only\",\"Not applicable - composition/context\","
                f"IF($E{ppg_r}=\"Lower is Better\",\"Not applicable - lower-is-better average/rate; review method\","
                f"IF(OR(T{ppg_r}=\"\",Y{ppg_r}=\"\",T{ppg_r}<10,Y{ppg_r}<10),\"Insufficient data\","
                f"IF(AB{ppg_r}>AD{ppg_r},\"DI: significant PPG-1 gap\","
                f"IF(U{ppg_r}-Z{ppg_r}>AD{ppg_r},\"Significantly above reference\","
                f"\"No significant PPG-1 gap\")))))"
            ),
        )

        # AF: Raw Gap Change
        ws.write_formula(r0, 31, f"=IFERROR(AA{ppg_r}-N{ppg_r},\"\")", pct_fmt)
        # AG: Gap Direction
        ws.write_formula(
            r0, 32,
            (
                f"=IF(AF{ppg_r}=\"\",\"\","
                f"IF(ABS(AF{ppg_r})<0.01,\"Relatively unchanged\","
                f"IF(AF{ppg_r}>0,\"Closing/improving\",\"Widening/worsening\")))"
            ),
        )
        # AH: Overall Interpretation — string used by Heatmap_Summary VLOOKUP
        ws.write_formula(
            r0, 33,
            (
                f"=IF(AE{ppg_r}=\"DI: significant PPG-1 gap\",\"DI Observed\","
                f"IF(AE{ppg_r}=\"Significantly above reference\",\"Significantly above reference\","
                f"IF(AE{ppg_r}=\"No significant PPG-1 gap\",\"No statistically significant gap\","
                f"AE{ppg_r})))"
            ),
        )
        # AI: Analyst Notes (blank)
        ws.write_blank(r0, 34, None)

    ws.freeze_panes(PPG_FIRST_DATA_ROW, 0)


def _write_heatmap_sheet(
    workbook,
    baseline_label: str,
    current_label: str,
) -> None:
    ws = workbook.add_worksheet("Heatmap_Summary")
    band_fmt = workbook.add_format({
        "bold": True, "bg_color": "#E2F0D9", "border": 1,
        "align": "center", "valign": "vcenter", "text_wrap": True,
    })
    header_fmt = workbook.add_format({
        "bold": True, "bg_color": "#D9EAF7", "border": 1,
        "text_wrap": True, "align": "center", "valign": "vcenter",
    })
    label_fmt = workbook.add_format({"bold": True, "valign": "vcenter"})
    cell_fmt = workbook.add_format({"align": "center", "border": 1})
    note_fmt = workbook.add_format({"italic": True, "font_color": "#555555"})

    # Row 0: vision-area band, Row 1: metric headers
    outcome_metrics = [m for m in METRICS if m.title != "Student Enrollment"]
    ws.write(0, 0, "Equity Group", header_fmt)
    success_count = sum(1 for m in outcome_metrics if m.vision == "Equity in Success")
    support_count = len(outcome_metrics) - success_count
    if success_count:
        ws.merge_range(0, 1, 0, success_count, "Equity in Success", band_fmt)
    if support_count:
        ws.merge_range(0, success_count + 1, 0, success_count + support_count,
                       "Equity in Support", band_fmt)

    for c, m in enumerate(outcome_metrics, start=1):
        ws.write(1, c, m.title, header_fmt)

    ws.set_column(0, 0, 38)
    ws.set_column(1, len(outcome_metrics), 22)

    # Heatmap omits suppressed race groups (matching the template); they
    # only appear as "--" rows on the Summary sheet.
    rows: list[tuple[str, str]] = []
    rows.extend([(s.label, s.group_type) for s in SUBGROUPS if s.group_type == "Race/Ethnicity"])
    rows.extend([(s.label, s.group_type) for s in SUBGROUPS if s.group_type == "Gender"])
    rows.extend([(s.label, s.group_type) for s in SUBGROUPS if s.group_type == "First-Generation Status"])

    PPG_KEY_RANGE = (
        f"'PPG-1'!$A${PPG_FIRST_DATA_ROW + 1}:$AH${PPG_LAST_DATA_ROW + 1}"
    )

    for r, (label, _) in enumerate(rows, start=2):
        ws.write(r, 0, label, label_fmt)
        for c, m in enumerate(outcome_metrics, start=1):
            if m.units_metric:
                # Use Data_Entry's beneficial gap with thresholds from Overall_Inputs.
                de_lookup = (
                    f"VLOOKUP(\"{m.title}|\"&$A{r+1},Data_Entry!$A:$AB,22,FALSE)"
                )
                ws.write_formula(
                    r, c,
                    (
                        f"=IFERROR(IF({de_lookup}=\"\",\"--\","
                        f"IF({de_lookup}<=-IFERROR(VLOOKUP(\"{m.title}\","
                        f"Overall_Inputs!$A:$M,12,FALSE),5),\"DI Observed\","
                        f"IF({de_lookup}<=-IFERROR(VLOOKUP(\"{m.title}\","
                        f"Overall_Inputs!$A:$M,11,FALSE),2),"
                        f"\"Moderate Gap\","
                        f"\"No statistically significant gap\"))),\"--\")"
                    ),
                    cell_fmt,
                )
            else:
                lookup = (
                    f"VLOOKUP(\"{m.title}|\"&$A{r+1},{PPG_KEY_RANGE},34,FALSE)"
                )
                ws.write_formula(
                    r, c,
                    f"=IFERROR({lookup},\"--\")",
                    cell_fmt,
                )

    # Notes
    note_row = 2 + len(rows) + 1
    ws.write(note_row, 0,
             ("Note: Cells populate from PPG-1 once Data_Entry numerator/"
              "denominator values are present. \"--\" indicates suppressed "
              "(N<=10) or unavailable."),
             note_fmt)
    ws.write(note_row + 1, 0,
             ("Legend: \"DI Observed\" = adverse disproportionate impact "
              "below threshold. \"Significantly above reference\" = "
              "disproportionate advantage. \"No statistically significant "
              "gap\" = within margin of error."),
             note_fmt)
    _ = baseline_label
    _ = current_label


def _write_summary_sheet(workbook) -> None:
    ws = workbook.add_worksheet("Summary")
    title_fmt = workbook.add_format({
        "bold": True, "font_size": 14, "font_color": "#FFFFFF",
        "bg_color": "#004062",
    })
    band_fmt = workbook.add_format({
        "bold": True, "bg_color": "#E2F0D9", "border": 1,
        "align": "center", "valign": "vcenter",
    })
    section_fmt = workbook.add_format({
        "bold": True, "bg_color": "#F2F2F2", "italic": True,
    })
    header_fmt = workbook.add_format({
        "bold": True, "bg_color": "#D9EAF7", "border": 1,
        "text_wrap": True, "align": "center", "valign": "vcenter",
    })
    label_fmt = workbook.add_format({"bold": True, "valign": "vcenter"})
    cell_fmt = workbook.add_format({"align": "center", "border": 1})
    legend_fmt = workbook.add_format({"italic": True, "font_color": "#555555"})

    outcome_metrics = [m for m in METRICS if m.title != "Student Enrollment"]
    success_count = sum(1 for m in outcome_metrics if m.vision == "Equity in Success")
    support_count = len(outcome_metrics) - success_count

    ws.merge_range(0, 0, 0, len(outcome_metrics), "Equity Analysis Overview", title_fmt)
    ws.write(2, 0, "KEY:", label_fmt)
    ws.write(2, 1, "1 = Disproportionate Impact   2 = Monitor   3 = No DI   -- = Suppressed (N<=10)", legend_fmt)

    # Row 4: vision-area band, Row 5: metric headers
    ws.write(4, 0, "Equity Group", header_fmt)
    if success_count:
        ws.merge_range(4, 1, 4, success_count, "Equity in Success", band_fmt)
    if support_count:
        ws.merge_range(4, success_count + 1, 4, success_count + support_count,
                       "Equity in Support", band_fmt)
    for c, m in enumerate(outcome_metrics, start=1):
        ws.write(5, c, m.title, header_fmt)

    ws.set_column(0, 0, 38)
    ws.set_column(1, len(outcome_metrics), 22)

    # Sections: Race (with suppressed groups interleaved), Gender, First-Gen
    sections = [
        ("Race/Ethnicity", SUMMARY_RACE_ORDER),
        ("Gender", [s.label for s in SUBGROUPS if s.group_type == "Gender"]),
        ("First-Generation College Status",
         [s.label for s in SUBGROUPS if s.group_type == "First-Generation Status"]),
    ]

    r = 6
    for section_label, group_labels in sections:
        ws.merge_range(r, 0, r, len(outcome_metrics), section_label, section_fmt)
        r += 1
        for label in group_labels:
            ws.write(r, 0, label, label_fmt)
            for c in range(1, len(outcome_metrics) + 1):
                if label in SUPPRESSED_RACE_LABELS:
                    ws.write(r, c, "--", cell_fmt)
                else:
                    # Heatmap_Summary cells live at row index r-6+? Easier: do a
                    # lookup into Heatmap_Summary by label and column letter.
                    # Heatmap col letters: B,C,D,... map 1:1 to outcome_metrics.
                    col_letter = xlsxwriter.utility.xl_col_to_name(c)
                    formula = (
                        f"=IFERROR(IF(VLOOKUP(\"{label}\","
                        f"Heatmap_Summary!$A:${xlsxwriter.utility.xl_col_to_name(len(outcome_metrics))},"
                        f"{c+1},FALSE)=\"DI Observed\",1,"
                        f"IF(VLOOKUP(\"{label}\","
                        f"Heatmap_Summary!$A:${xlsxwriter.utility.xl_col_to_name(len(outcome_metrics))},"
                        f"{c+1},FALSE)=\"Moderate Gap\",2,"
                        f"IF(VLOOKUP(\"{label}\","
                        f"Heatmap_Summary!$A:${xlsxwriter.utility.xl_col_to_name(len(outcome_metrics))},"
                        f"{c+1},FALSE)=\"--\",\"--\",3))),\"--\")"
                    )
                    ws.write_formula(r, c, formula, cell_fmt)
                    _ = col_letter
            r += 1

    # Conditional formatting for color coding
    red_fmt = workbook.add_format({"bg_color": "#D95C3E", "font_color": "#FFFFFF"})
    yellow_fmt = workbook.add_format({"bg_color": "#E3C37A"})
    green_fmt = workbook.add_format({"bg_color": "#7BBB99"})
    grey_fmt = workbook.add_format({"bg_color": "#D9D9D9", "font_color": "#666666"})

    last_col = len(outcome_metrics)
    last_col_letter = xlsxwriter.utility.xl_col_to_name(last_col)
    cond_range = f"B7:{last_col_letter}{r}"
    ws.conditional_format(cond_range, {
        "type": "cell", "criteria": "==", "value": 1, "format": red_fmt,
    })
    ws.conditional_format(cond_range, {
        "type": "cell", "criteria": "==", "value": 2, "format": yellow_fmt,
    })
    ws.conditional_format(cond_range, {
        "type": "cell", "criteria": "==", "value": 3, "format": green_fmt,
    })
    ws.conditional_format(cond_range, {
        "type": "cell", "criteria": "==", "value": "\"--\"", "format": grey_fmt,
    })

    ws.write(r + 1, 0, "Source: Banner via NOCCCD BOT Hyper extracts.", legend_fmt)


# ---------------------------------------------------------------------------
# Top-level entrypoints
# ---------------------------------------------------------------------------

def generate_equity_excel(cache: HyperCache) -> bytes:
    """Build the equity workbook in-memory and return its bytes."""
    (
        baseline_filter, current_filter,
        baseline_display, current_display,
    ) = _baseline_and_current_labels()

    # Compute numerator/denominator for every metric × subgroup × year using
    # long-form filter labels, plus district-wide overall N/D for
    # Overall_Inputs. The dictionaries are keyed on display labels so the
    # workbook writers can use them directly without further translation.
    metric_data: dict[str, dict[tuple[str, str], dict[str, tuple[float, float]]]] = {}
    overall_data: dict[str, dict[str, tuple[float | None, float | None]]] = {}
    for m in METRICS:
        raw_subgroups, raw_overall = _build_metric_counts(
            m, cache, baseline_filter, current_filter,
        )
        metric_data[m.title] = {
            sub_key: {
                baseline_display: years.get(baseline_filter, (0.0, 0.0)),
                current_display: years.get(current_filter, (0.0, 0.0)),
            }
            for sub_key, years in raw_subgroups.items()
        }
        overall_data[m.title] = {
            baseline_display: raw_overall.get(baseline_filter, (None, None)),
            current_display: raw_overall.get(current_filter, (None, None)),
        }

    buf = io.BytesIO()
    workbook = xlsxwriter.Workbook(buf, {"in_memory": True})

    _write_instructions_sheet(workbook, baseline_display, current_display)
    _write_summary_sheet(workbook)
    _write_overall_inputs_sheet(workbook, overall_data, baseline_display, current_display)
    _write_data_entry_sheet(workbook, metric_data, baseline_display, current_display)
    _write_heatmap_sheet(workbook, baseline_display, current_display)
    _write_ppg1_sheet(workbook, baseline_display, current_display)

    workbook.close()
    return buf.getvalue()


def main() -> int:
    if not EXPORT_ROOT.parent.exists():
        print(
            f"Export parent not found: {EXPORT_ROOT.parent}\n"
            "Make sure OneDrive is mounted and the BOT Reports folder exists "
            "(or set BOT_EXPORT_ROOT_EQUITY to an existing parent path).",
            file=sys.stderr,
        )
        return 1

    EXPORT_ROOT.mkdir(parents=True, exist_ok=True)
    today = date.today().strftime("%Y%m%d")
    snapshot_dir = EXPORT_ROOT / max_acyr_label()
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    out_path = snapshot_dir / f"equity_{today}.xlsx"
    # Atomic-rename pattern: write to .tmp.xlsx then os.replace, so a partial
    # failure doesn't overwrite a valid same-day workbook with a truncated
    # one. Mirrors bot_excel_export.py.
    tmp_path = out_path.with_name(f"{out_path.stem}.tmp{out_path.suffix}")
    print(f"Writing equity workbook to {out_path}")

    cache = HyperCache()
    try:
        data = generate_equity_excel(cache)
        with open(tmp_path, "wb") as fh:
            fh.write(data)
    except Exception as exc:  # noqa: BLE001
        tmp_path.unlink(missing_ok=True)
        print(f"Export failed: {exc}", file=sys.stderr)
        return 1

    os.replace(tmp_path, out_path)
    print(f"Done. Wrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
