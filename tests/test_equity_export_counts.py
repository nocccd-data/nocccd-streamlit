"""Equity PPG-1 First-Gen counts must not depend on row order.

A student enrolled in both Credit and Noncredit in a year has a row of each.
The workbook deduped to one row per student *before* filtering to Credit, so
whenever the Noncredit row came first the student dropped out of the credit
First-Gen count. Hyper returns rows in a different order on each read, so the
2025-26 count moved between downloads (16,850 / 16,855 / 16,860 / 16,861 on four
reads of one file) instead of matching the BOT Goal 1 tab's 16,903.
"""

import pandas as pd

from src.pipeline.equity_export import _composition_counts, _rate_counts, _units_counts
from src.scripts.tabs.bot_helpers import aggregate_firstgen

_YEAR = "2025-2026"


def _row(pidm, site, fg, units=10.0):
    return {"pidm": pidm, "academic_year": _YEAR, "site": site, "first_gen_ind": fg,
            "race_description": "Asian", "gender": "F", "sum_hours_earned": units}


def _fg(counts):
    return {k[1]: v for k, v in counts.items() if k[0] == "First-Generation Status"}


def test_composition_counts_a_student_whose_noncredit_row_comes_first():
    df = pd.DataFrame([_row(1, "Noncredit", "Y"), _row(1, "Credit", "Y"), _row(2, "Credit", "N")])
    fg = _fg(_composition_counts(df, _YEAR))
    assert fg["First-Generation College Student"] == (1, 2)
    assert fg["Not First-Generation College Student"] == (1, 2)


def test_composition_first_gen_matches_bot_tab_for_any_row_order():
    rows = []
    for pidm in range(60):
        fg = "Y" if pidm % 3 == 0 else "N"
        rows.append(_row(pidm, "Credit" if pidm % 4 else "Noncredit", fg))
        if pidm % 5 == 0:  # every fifth student is in both tracks
            rows.append(_row(pidm, "Credit" if pidm % 4 == 0 else "Noncredit", fg))
    df = pd.DataFrame(rows)
    bot = aggregate_firstgen(df)
    expected = tuple(bot[bot["fg"] == "Y"][["count", "total"]].astype(int).iloc[0].tolist())
    for seed in range(5):
        got = _fg(_composition_counts(df.sample(frac=1, random_state=seed), _YEAR))
        assert got["First-Generation College Student"] == expected, seed


def test_rate_fallback_denominator_keeps_a_student_whose_noncredit_row_comes_first():
    # No first-gen student completed, so the Y denominator comes from the base fallback.
    outcomes = pd.DataFrame([_row(2, "Credit", "N")])
    base = pd.DataFrame([_row(1, "Noncredit", "Y"), _row(1, "Credit", "Y"), _row(2, "Credit", "N")])
    fg = _fg(_rate_counts(outcomes, base, _YEAR))
    assert fg["First-Generation College Student"] == (0, 1)


def test_units_first_gen_keeps_a_student_whose_noncredit_row_comes_first():
    df = pd.DataFrame([_row(1, "Noncredit", "Y", 99.0), _row(1, "Credit", "Y", 12.0), _row(2, "Credit", "N", 6.0)])
    fg = _fg(_units_counts(df, _YEAR))
    assert fg["First-Generation College Student"] == (12.0, 1)
