"""Vision 2030 equity tables for the BOT tabs (spec 2026-09-28).

For the latest plan year, each student population's actual against its own
benchmark — the group's 2022-23 value run through the tab's Vision 2030 rule
(the same ``group_baselines`` / ``group_target`` path as the Excel Summary
Counts ``{year} Benchmark`` column) — with Variance = Actual − Benchmark and
a Status.

Callers supply each category's aggregate of the plan frame (``bot_helpers``
for the count tabs, ``bot_goal3_units`` for average units). No Streamlit /
``bot_helpers`` imports, so every BOT module can use this one without a cycle.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from src.scripts.tabs.bot_targets import (
    BENCHMARK,
    PLAN_LENGTH,
    Targets,
    group_baselines,
    group_target,
    plan_years,
    short_year,
    target_caption,
    years_from_baseline,
)

ON_TRACK = "On Track"
PROGRESSING = "Progressing"

RACE_CATEGORY = "Race/Ethnicity"
GENDER_CATEGORY = "Gender"
FIRSTGEN_CATEGORY = "First Generation College Student Status"

COLUMNS = ["category", "group", "baseline", "benchmark", "actual", "variance", "status"]


@dataclass(frozen=True, eq=False)
class EquitySource:
    """One category's plan-frame aggregate: ``academic_year``, *key_col*,
    *value_col* and ``count`` (students, for the 10-student floor)."""

    category: str
    agg: pd.DataFrame
    key_col: str
    value_col: str
    order: list[str]
    labels: dict[str, str]


@dataclass(frozen=True, eq=False)
class EquityTable:
    year: str            # the equity year, e.g. "2025-2026"
    rows: pd.DataFrame   # COLUMNS, one row per shown group, in display order
    decimals: bool       # Units: 1 decimal; counts: whole numbers
    note: str

    @property
    def heading(self) -> str:
        return f"Equity Results, {short_year(self.year)}"

    def headers(self) -> dict[str, str]:
        year = short_year(self.year)
        return {
            "category": "Category",
            "group": "Student Population",
            "baseline": f"{short_year(plan_years()[0])} Baseline",
            "benchmark": f"{year} {BENCHMARK}",
            "actual": f"{year} Actual",
            "variance": "Variance",
            "status": "Status",
        }


def equity_year(targets: Targets) -> str | None:
    """Latest year after the baseline in the plan frame, capped at the plan end."""
    years = [
        y for y in targets.frame["academic_year"].dropna().astype(str).unique()
        if (k := years_from_baseline(y)) is not None and 1 <= k <= PLAN_LENGTH
    ]
    return max(years) if years else None


def _by_group(agg: pd.DataFrame, key_col: str, col: str, year: str) -> dict[str, float]:
    sel = agg[agg["academic_year"] == year]
    return {
        str(k): float(v)
        for k, v in zip(sel[key_col].astype(str), sel[col])
        if pd.notna(v)
    }


def build_equity_table(
    targets: Targets, sources: list[EquitySource], *, min_count: int,
) -> EquityTable | None:
    """The equity table, or None when there is no equity year or no group
    has *min_count* students in both the baseline and the equity year."""
    year = equity_year(targets)
    if year is None:
        return None
    base_year = plan_years()[0]
    lower_is_better = targets.rule.get("reduce_over") is not None
    rows = []
    for src in sources:
        base_n = _by_group(src.agg, src.key_col, "count", base_year)
        year_n = _by_group(src.agg, src.key_col, "count", year)
        actuals = _by_group(src.agg, src.key_col, src.value_col, year)
        baselines = group_baselines(src.agg, key_col=src.key_col, value_col=src.value_col)
        for key in src.order:
            if base_n.get(key, 0) < min_count or year_n.get(key, 0) < min_count:
                continue
            if key not in baselines or key not in actuals:
                continue
            benchmark = group_target(baselines, key, year, targets.rule)
            if pd.isna(benchmark):
                continue
            # round() so float noise (219.00000000000003) cannot turn an exact
            # hit into a miss.
            variance = round(actuals[key] - benchmark, 9)
            met = variance <= 0 if lower_is_better else variance >= 0
            rows.append({
                "category": src.category,
                "group": src.labels.get(key, key),
                "baseline": baselines[key],
                "benchmark": benchmark,
                "actual": actuals[key],
                "variance": variance,
                "status": ON_TRACK if met else PROGRESSING,
            })
    if not rows:
        return None
    return EquityTable(
        year=year, rows=pd.DataFrame(rows, columns=COLUMNS),
        decimals=targets.is_average, note=equity_note(targets.rule),
    )


def equity_note(rule: dict) -> str:
    """The note under the table — derived from the rule, like the chart caption."""
    text = f"{target_caption(rule)} Variance = Actual − {BENCHMARK}."
    if rule.get("reduce_over") is not None:
        text += f" {ON_TRACK} = at or below the {BENCHMARK.lower()}."
    return text


def format_value(value: float, *, decimals: bool) -> str:
    return f"{value:,.1f}" if decimals else f"{value:,.0f}"


def format_variance(value: float, *, decimals: bool) -> str:
    """Signed (``+70``, ``-49``, ``-0.1``); a value that rounds to zero is ``0``."""
    shown = round(value, 1) if decimals else round(value)
    if shown == 0:
        return "0"
    return f"{shown:+,.1f}" if decimals else f"{shown:+,.0f}"
