"""BOT Goal 3 Average Units: a student who completed at both colleges counts at both.

`_mean_by` deduped to one row per student and year before grouping by campus,
so a student awarded at Cypress and Fullerton in the same year was averaged
into only one campus, whichever row came first. On the 2026-10 data that left
Fullerton 0.1 off in three years (e.g. 2025-26 shown 83.0, 83.1 with every
completer counted). The district line's rule for such a student is an open
definition question (docs/deferred.md #9) and is not pinned here.
"""

import pandas as pd

from src.scripts.tabs.bot_goal3_units import _aggregate_campus

_YEAR = "2025-2026"


def _df():
    return pd.DataFrame([
        {"pidm": 1, "academic_year": _YEAR, "camp_desc": "Cypress", "sum_hours_earned": 160.0},
        {"pidm": 1, "academic_year": _YEAR, "camp_desc": "Fullerton", "sum_hours_earned": 180.0},
        {"pidm": 2, "academic_year": _YEAR, "camp_desc": "Fullerton", "sum_hours_earned": 60.0},
    ])


def _campus_avgs(df):
    out = _aggregate_campus(df)
    return out[out["camp_desc"] != "NOCCCD (Unduplicated)"].set_index("camp_desc")["avg_units"].to_dict()


def test_two_college_completer_counts_at_both_campuses():
    assert _campus_avgs(_df()) == {"Cypress": 160.0, "Fullerton": 120.0}


def test_campus_averages_do_not_depend_on_row_order():
    assert _campus_avgs(_df().iloc[::-1]) == _campus_avgs(_df())


def test_district_line_counts_a_two_college_completer_once():
    # Which college's units the student contributes is deferred #9, so either is
    # allowed; counting them twice ((160 + 180 + 60) / 3 = 133.3) is not.
    for df in (_df(), _df().iloc[::-1]):
        out = _aggregate_campus(df)
        district = out.loc[out["camp_desc"] == "NOCCCD (Unduplicated)", "avg_units"].tolist()
        assert district in ([110.0], [120.0])
