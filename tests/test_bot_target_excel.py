"""Target columns in the BOT Excel export (spec §8).

Synthetic district: every year 70 Cypress (Hispanic, F, first-gen) and 30
Fullerton (Asian, M, not first-gen) students -> 2022-23 baseline 100.
2025-26 is k=3: growth factor 1 + 0.3*3/7.
"""

import math

import pandas as pd
import pytest

from src.scripts.tabs import bot_goal3_units
from src.scripts.tabs.bot_excel_helpers import standard_bot_excel_sections
from src.scripts.tabs.bot_targets import Targets

YEARS = ["2018-2019", "2021-2022", "2022-2023", "2023-2024", "2024-2025", "2025-2026"]
F3 = 1 + 0.3 * 3 / 7
TITLES = {
    "tab_title": "T",
    "target_title": "AA: Progress Toward 2029-30 Target",
    "headcount_title": "HC",
    "race_title": "Race",
    "gender_title": "Gender",
    "firstgen_title": "FG",
}


def _df(years=YEARS, *, fullerton_in_baseline=True, units=False):
    rows, pidm = [], 0
    for year in years:
        groups = [("Cypress", "Hispanic or Latino", "F", "Y", 70, 80.0)]
        if fullerton_in_baseline or year != "2022-2023":
            groups.append(("Fullerton", "Asian", "M", "N", 30, 90.0))
        for camp, race, gender, fg, n, hours in groups:
            for _ in range(n):
                rows.append({
                    "pidm": pidm, "academic_year": year, "acyr_code": year[:4],
                    "camp_desc": camp, "site": "Credit",
                    "race_description": race, "gender": gender,
                    "first_gen_ind": fg, "sum_hours_earned": hours,
                })
                pidm += 1
    return pd.DataFrame(rows)


def _targets(df, rule=None):
    plan = df[df["academic_year"] >= "2022-2023"]
    return Targets(frame=plan, rule=rule or {"growth": 0.30})


def _section(sections, title):
    return next(s for s in sections if s.title == title).df


def test_first_section_is_actual_vs_target():
    df = _df()
    sections = standard_bot_excel_sections(df, TITLES, base_df=df, targets=_targets(df))
    first = sections[0]
    assert first.title == TITLES["target_title"]
    assert list(first.df.columns) == ["Academic Year", "Actual", "Target"]
    assert len(first.df) == 8
    assert first.df["Actual"].iloc[0] == 100
    assert first.df["Target"].iloc[-1] == pytest.approx(130.0)
    assert math.isnan(first.df["Actual"].iloc[-1])
    assert first.integer_cols == ("Actual", "Target")


def test_headcount_table_gets_latest_year_target_per_campus():
    df = _df()
    hc = _section(standard_bot_excel_sections(df, TITLES, base_df=df, targets=_targets(df)), "HC")
    cols = list(hc.columns)
    assert cols[cols.index("2025-2026") + 1] == "2025-2026 Target"
    by = dict(zip(hc["Campus"], hc["2025-2026 Target"]))
    assert by["Cypress"] == pytest.approx(70 * F3)
    # Categorical camp_desc must still match (Review Focus 4).
    assert by["NOCCCD (Unduplicated)"] == pytest.approx(100 * F3)


def test_campus_absent_in_baseline_gets_blank_target():
    df = _df(fullerton_in_baseline=False)
    hc = _section(standard_bot_excel_sections(df, TITLES, base_df=df, targets=_targets(df)), "HC")
    by = dict(zip(hc["Campus"], hc["2025-2026 Target"]))
    assert math.isnan(by["Fullerton"])
    assert by["Cypress"] == pytest.approx(70 * F3)


def test_summary_counts_target_follows_last_count():
    df = _df()
    sections = standard_bot_excel_sections(df, TITLES, base_df=df, targets=_targets(df))
    summary = _section(sections, "Race - Summary Counts")
    cols = list(summary.columns)
    assert cols[cols.index("2025-2026 Count") + 1] == "2025-2026 Target"
    by = dict(zip(summary["Race/Ethnicity"], summary["2025-2026 Target"]))
    assert by["Latino/Hispanic"] == pytest.approx(70 * F3)
    assert by["Asian"] == pytest.approx(30 * F3)


def test_rate_detail_target_count_per_year():
    df = _df()
    detail = _section(
        standard_bot_excel_sections(df, TITLES, base_df=df, targets=_targets(df)),
        "Gender - Rate Detail",
    )
    cols = list(detail.columns)
    assert cols[cols.index("Numerator Count") + 1] == "Target Count"
    female = detail[detail["Gender"] == "Female"].set_index("Academic Year")
    assert pd.isna(female.loc["2021-2022", "Target Count"])
    assert female.loc["2022-2023", "Target Count"] == 70
    assert female.loc["2025-2026", "Target Count"] == pytest.approx(70 * F3)


def test_percent_matrices_have_no_target_columns():
    df = _df()
    sections = standard_bot_excel_sections(df, TITLES, base_df=df, targets=_targets(df))
    for title in ("Race", "Gender", "FG"):
        assert not any("Target" in str(c) for c in _section(sections, title).columns)


def test_without_targets_nothing_changes():
    df = _df()
    sections = standard_bot_excel_sections(df, TITLES, base_df=df)
    assert sections[0].title == "HC"
    for s in sections:
        assert not any("Target" in str(c) for c in s.df.columns), s.title


def test_narrowed_to_pre_baseline_year_has_no_campus_target_column():
    # Campus targets are per plan year; a year before the 2022-23 baseline
    # has no target, so it gets no Target column at all.
    df = _df()
    shown = df[df["academic_year"] == "2021-2022"]
    hc = _section(
        standard_bot_excel_sections(shown, TITLES, base_df=shown, targets=_targets(df)), "HC",
    )
    assert not any("Target" in str(c) for c in hc.columns)


def test_units_sections_carry_targets():
    df = _df(units=True)
    rule = {"growth": 0.20, "reduce_over": 60, "value_col": "sum_hours_earned"}
    sections = bot_goal3_units.units_excel_sections(df, targets=_targets(df, rule))
    t = bot_goal3_units._TITLES
    assert sections[0].title == t["target_title"]
    assert sections[0].decimal_cols == ("Actual", "Target")
    campus = _section(sections, t["headcount_title"])
    by = dict(zip(campus["Campus"], campus["2025-2026 Target"]))
    baseline = (70 * 80 + 30 * 90) / 100          # 83.0
    assert by["NOCCCD (Unduplicated)"] == pytest.approx(
        baseline - (baseline - 60) * 0.2 * 3 / 7,
    )
    race = _section(sections, f"{t['race_title']} - Summary")
    assert "2025-2026 Target" in race.columns


def test_every_target_tab_has_a_target_title():
    from src.scripts.tabs import (
        bot_goal2_adt,
        bot_goal2_assoc,
        bot_goal2_bac,
        bot_goal2_cert,
        bot_goal2_cert_nc,
        bot_goal4_xfer_ready,
    )
    for mod in (bot_goal2_adt, bot_goal2_assoc, bot_goal2_bac, bot_goal2_cert,
                bot_goal2_cert_nc, bot_goal3_units, bot_goal4_xfer_ready):
        assert mod._TITLES["target_title"].endswith(
            "Progress Toward 2029-30 Target"), mod.__name__
