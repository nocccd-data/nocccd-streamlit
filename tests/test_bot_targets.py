"""Vision 2030 target math, pinned to the manager's workbook formulas.

AA sheet:    C3 = $G$2*(1+$G$3*(ROW()-ROW($C$2))/$G$4), G3=0.3, G4=7
Units sheet: C3 = $G$2-(($G$2-60)*$G$3*(ROW()-ROW($C$2))/$G$4), G3=0.2
Bach sheet:  benchmarks manually rounded up (1 -> 2).
"""

import math

import pandas as pd
import pytest

from src.scripts.tabs.bot_targets import (
    PLAN_LENGTH,
    Targets,
    district_actual_vs_target,
    group_baselines,
    group_target,
    plan_range_label,
    plan_years,
    short_year,
    target_caption,
    target_value,
    years_from_baseline,
)

GROWTH = {"growth": 0.30}
UNITS = {"growth": 0.20, "reduce_over": 60, "value_col": "sum_hours_earned"}
BACH = {"growth": 0.30, "round_up": True}


def test_plan_years_and_labels():
    assert PLAN_LENGTH == 7
    assert plan_years()[0] == "2022-2023"
    assert plan_years()[-1] == "2029-2030"
    assert len(plan_years()) == 8
    assert short_year("2022-2023") == "2022-23"
    assert plan_range_label() == "2022-23 to 2029-30"
    assert years_from_baseline("2025-2026") == 3
    assert years_from_baseline("2018-2019") == -4


def test_growth_matches_workbook_aa():
    assert target_value(1669, 0, GROWTH) == 1669
    assert target_value(1669, 1, GROWTH) == pytest.approx(1740.53, abs=0.01)
    assert target_value(1669, 7, GROWTH) == pytest.approx(2169.7)


def test_units_reduction_matches_workbook():
    b = 82.64480931263859
    assert target_value(b, 7, UNITS) == pytest.approx(78.1158, abs=1e-4)
    assert target_value(b, 0, UNITS) == pytest.approx(b)


def test_units_baseline_at_or_below_floor_is_held():
    assert target_value(58.0, 7, UNITS) == 58.0


def test_bach_rounds_up_after_baseline_only():
    assert target_value(1, 0, BACH) == 1
    assert [target_value(1, k, BACH) for k in range(1, 8)] == [2.0] * 7


def test_undefined_targets_are_nan_not_zero():
    assert math.isnan(target_value(None, 3, GROWTH))
    assert math.isnan(target_value(float("nan"), 3, GROWTH))
    assert math.isnan(target_value(0, 3, GROWTH))      # no baseline to grow
    assert math.isnan(target_value(100, -1, GROWTH))   # before the plan
    assert math.isnan(target_value(100, 8, GROWTH))    # after the plan
    assert math.isnan(target_value(100, None, GROWTH))


def _frame(counts: dict[str, int]) -> pd.DataFrame:
    rows, pidm = [], 0
    for year, n in counts.items():
        for _ in range(n):
            rows.append({"pidm": pidm, "academic_year": year})
            pidm += 1
    return pd.DataFrame(rows)


def test_district_series_counts_unduplicated_students():
    frame = _frame({"2022-2023": 100, "2023-2024": 110, "2025-2026": 120})
    # A student appearing twice in a year (two campuses) counts once.
    frame = pd.concat([frame, frame.iloc[[0]]], ignore_index=True)
    avt = district_actual_vs_target(Targets(frame=frame, rule=GROWTH))
    assert list(avt.columns) == ["academic_year", "actual", "target"]
    assert list(avt["academic_year"]) == plan_years()
    assert avt["actual"].iloc[0] == 100
    assert math.isnan(avt["actual"].iloc[2])          # 2024-25 absent
    assert math.isnan(avt["actual"].iloc[-1])         # future year
    assert avt["target"].iloc[-1] == pytest.approx(130.0)


def test_district_series_for_units_is_student_mean():
    frame = pd.DataFrame({
        "pidm": [1, 1, 2],
        "academic_year": ["2022-2023"] * 3,
        "sum_hours_earned": [80.0, 80.0, 90.0],
    })
    avt = district_actual_vs_target(Targets(frame=frame, rule=UNITS))
    assert avt["actual"].iloc[0] == pytest.approx(85.0)
    assert avt["target"].iloc[-1] == pytest.approx(85.0 - 25.0 * 0.20)


def test_missing_baseline_year_gives_blank_targets():
    frame = _frame({"2023-2024": 50})
    avt = district_actual_vs_target(Targets(frame=frame, rule=GROWTH))
    assert avt["target"].isna().all()


def test_group_targets_use_each_groups_own_baseline():
    agg = pd.DataFrame({
        "academic_year": ["2022-2023", "2022-2023", "2025-2026"],
        "race_description": ["Hispanic or Latino", "Asian", "Filipino"],
        "count": [928, 244, 15],
    })
    base = group_baselines(agg, key_col="race_description", value_col="count")
    assert base == {"Hispanic or Latino": 928.0, "Asian": 244.0}
    assert group_target(base, "Hispanic or Latino", "2025-2026", GROWTH) == (
        pytest.approx(1047.31, abs=0.01)
    )
    # Filipino has no 2022-23 row -> blank, not 0.
    assert math.isnan(group_target(base, "Filipino", "2025-2026", GROWTH))
    # Years before the baseline have no target.
    assert math.isnan(group_target(base, "Asian", "2021-2022", GROWTH))


def test_group_baselines_accept_categorical_keys():
    agg = pd.DataFrame({
        "academic_year": ["2022-2023"],
        "camp_desc": pd.Categorical(["NOCCCD (Unduplicated)"]),
        "headcount": [1669],
    })
    base = group_baselines(agg, key_col="camp_desc", value_col="headcount")
    assert base == {"NOCCCD (Unduplicated)": 1669.0}


def test_for_dataset_reads_config_rule():
    t = Targets.for_dataset("bot_goal3_units", pd.DataFrame())
    assert t.rule["reduce_over"] == 60 and t.is_average
    assert not Targets.for_dataset("bot_goal2_assoc", pd.DataFrame()).is_average
    with pytest.raises(KeyError):
        Targets.for_dataset("bot_goal1_students", pd.DataFrame())


def test_caption_is_derived_from_the_rule():
    assert target_caption(GROWTH) == (
        "Target: 30% increase over the 2022-23 baseline by 2029-30, "
        "in equal annual steps."
    )
    assert "rounded up" in target_caption(BACH)
    assert target_caption(UNITS) == (
        "Target: reduce the average units above 60 by 20% from the 2022-23 "
        "baseline by 2029-30, in equal annual steps. Lower is better."
    )
