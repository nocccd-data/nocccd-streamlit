"""Vision 2030 targets for the BOT tabs.

The district plan is FIXED: a 2022-23 baseline and a 2029-30 end year
(``config.BOT_TARGET_BASELINE_ACYR`` / ``BOT_TARGET_END_ACYR``), independent
of the rolling 5-year metrics window. Targets move in equal annual steps from
each group's own baseline value — the rule in the manager's workbook
(docs/specification_docs_2/2022-23 to 2029-30 Target Charts as of 25-26
Actuals.xlsx). Baselines are computed live from the extract.

Targets are COUNTS (or, for Units, averages). They are never drawn on the
race/gender/first-gen rate charts: a count target converted into a rate target
reverses the Met/Not-Met verdict whenever enrollment moves (spec §9).

No Streamlit / bot_helpers imports here, so bot_helpers and
bot_excel_helpers can both depend on this module without a cycle.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import pandas as pd

from src.pipeline.config import (
    BOT_TARGET_BASELINE_ACYR,
    BOT_TARGET_END_ACYR,
    DATASETS,
)

BASELINE_START = int(BOT_TARGET_BASELINE_ACYR)
END_START = int(BOT_TARGET_END_ACYR)
PLAN_LENGTH = END_START - BASELINE_START


def plan_years() -> list[str]:
    """Plan year labels in the extracts' format, ``"2022-2023"`` … ``"2029-2030"``."""
    return [f"{y}-{y + 1}" for y in range(BASELINE_START, END_START + 1)]


def short_year(label: str) -> str:
    """``"2022-2023"`` -> ``"2022-23"`` (the workbook's chart labels)."""
    start = int(str(label)[:4])
    return f"{start}-{str(start + 1)[-2:]}"


def plan_range_label() -> str:
    years = plan_years()
    return f"{short_year(years[0])} to {short_year(years[-1])}"


def years_from_baseline(label) -> int | None:
    try:
        return int(str(label)[:4]) - BASELINE_START
    except ValueError:
        return None


def target_value(baseline, k: int | None, rule: dict) -> float:
    """Target ``k`` years after the baseline, or NaN where none is defined.

    NaN — never 0 — for a missing baseline, a year outside the plan, or a
    growth metric whose baseline is 0 (nothing to grow).
    """
    if k is None or k < 0 or k > PLAN_LENGTH:
        return math.nan
    if baseline is None or pd.isna(baseline):
        return math.nan
    base = float(baseline)
    growth = float(rule["growth"])
    floor = rule.get("reduce_over")
    if floor is not None:
        # Units: shrink only the part above the floor (workbook "units OVER 60").
        if base <= floor:
            return base
        return base - (base - floor) * growth * k / PLAN_LENGTH
    if base <= 0:
        return math.nan
    value = base * (1 + growth * k / PLAN_LENGTH)
    if rule.get("round_up") and k >= 1:
        # round() first so float noise (2.0000000001) does not ceil to 3.
        value = float(math.ceil(round(value, 9)))
    return value


@dataclass(frozen=True, eq=False)
class Targets:
    """A dataset's plan-year rows (acyr >= baseline) plus its config rule."""

    frame: pd.DataFrame
    rule: dict

    @classmethod
    def for_dataset(cls, name: str, frame: pd.DataFrame) -> Targets:
        rule = DATASETS[name].get("target")
        if rule is None:
            raise KeyError(f"{name!r} has no 'target' rule in config.DATASETS")
        return cls(frame=frame, rule=rule)

    @property
    def is_average(self) -> bool:
        return bool(self.rule.get("value_col"))


def _district_actuals(frame: pd.DataFrame, rule: dict) -> pd.Series:
    """The existing "NOCCCD (Unduplicated)" figure per academic year."""
    stu = frame.drop_duplicates(subset=["pidm", "academic_year"])
    value_col = rule.get("value_col")
    if value_col:
        return stu.groupby("academic_year")[value_col].mean()
    return stu.groupby("academic_year")["pidm"].nunique()


def district_actual_vs_target(targets: Targets) -> pd.DataFrame:
    """One row per plan year: ``academic_year, actual, target``.

    ``actual`` is NaN for years not in the data yet (future years).
    """
    years = plan_years()
    actual = _district_actuals(targets.frame, targets.rule).astype(float)
    baseline = actual.get(years[0])
    return pd.DataFrame({
        "academic_year": years,
        "actual": [float(actual.get(y, math.nan)) for y in years],
        "target": [target_value(baseline, k, targets.rule) for k in range(len(years))],
    })


def group_baselines(
    agg: pd.DataFrame, *, key_col: str, value_col: str,
) -> dict[str, float]:
    """Baseline-year value per group, keyed by the group as a plain string.

    Keys are str()-ed so a Categorical ``camp_desc`` still matches the
    plain-string labels the tables carry.
    """
    base = agg[agg["academic_year"] == plan_years()[0]]
    return {
        str(key): float(value)
        for key, value in zip(base[key_col].astype(str), base[value_col])
        if pd.notna(value)
    }


def group_target(baselines: dict[str, float], key, year_label, rule: dict) -> float:
    return target_value(
        baselines.get(str(key)), years_from_baseline(year_label), rule,
    )


def target_caption(rule: dict) -> str:
    """Plain-English statement of the rule — derived, so it cannot drift."""
    pct = f"{rule['growth']:.0%}"
    years = plan_years()
    start, end = short_year(years[0]), short_year(years[-1])
    if rule.get("reduce_over") is not None:
        text = (
            f"Target: reduce the average units above {rule['reduce_over']} by "
            f"{pct} from the {start} baseline by {end}, in equal annual steps. "
            "Lower is better."
        )
    else:
        text = (
            f"Target: {pct} increase over the {start} baseline by {end}, "
            "in equal annual steps."
        )
    if rule.get("round_up"):
        text += " Targets are rounded up to whole students."
    return text


def targets_from_cache(cache, name: str) -> Targets | None:
    """Bulk exporters: the dataset's Targets, or None when it has no rule."""
    if "target" not in DATASETS[name]:
        return None
    return Targets.for_dataset(name, cache.get_targets_frame(name))
