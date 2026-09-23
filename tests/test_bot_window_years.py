"""The BOT reference-year contract.

Executives asked for 2018-19 as a *reference* column on every BOT chart. It is
context only: the rolling 5-year window (2021-22 .. 2025-26) still drives every
metric the Board already reads — the summary table's first/last columns, the
"5-Yr % Change", and the small-n suppression rule. These tests pin that down
with a six-year frame so any regression that lets the reference year leak into
a metric fails loudly.
"""

import pandas as pd

from src.pipeline.config import BOT_WINDOW_YEARS, DATASETS
from src.scripts.tabs.bot_excel_helpers import _count_summary
from src.scripts.tabs.bot_goal3_units import _pct_change as units_pct_change
from src.scripts.tabs.bot_helpers import (
    CATEGORY_MIN_COUNT,
    RACE_ORDER,
    _visible_categories,
    build_race_summary_html,
    compute_pct_change,
    window_bounds,
    window_years,
)

REF = "2018-2019"
WINDOW = ["2021-2022", "2022-2023", "2023-2024", "2024-2025", "2025-2026"]
SIX = [REF] + WINDOW


# ---------------------------------------------------------------------------
# config invariant: the explicit ref_acyr_code key and the tabs' positional
# "last BOT_WINDOW_YEARS years" rule can never disagree
# ---------------------------------------------------------------------------

BOT = {k: v for k, v in DATASETS.items() if k.startswith("bot_")}


def test_every_bot_dataset_window_is_exactly_bot_window_years():
    for name, cfg in BOT.items():
        assert len(cfg["acyr_code"]) == BOT_WINDOW_YEARS, name


def test_every_bot_reference_year_sorts_before_its_window():
    # If a ref year ever landed inside or after the window, the tabs would
    # silently treat it as part of the 5-year metrics. Catch that here.
    for name, cfg in BOT.items():
        refs = cfg.get("ref_acyr_code", [])
        assert refs, f"{name}: executives asked for a reference year"
        assert max(refs) < min(cfg["acyr_code"]), name
        assert not set(refs) & set(cfg["acyr_code"]), name


def test_reference_year_is_2018_19_on_every_bot_chart():
    # The wage pair lags a year in acyr terms but displays +1, so its ref is
    # 2017 and renders as 2018-2019 — same column the other 11 show.
    for name, cfg in BOT.items():
        expected = ["2017"] if name.startswith("bot_goal2_wage") else ["2018"]
        assert cfg["ref_acyr_code"] == expected, name


# ---------------------------------------------------------------------------
# window_years / window_bounds
# ---------------------------------------------------------------------------

def test_window_years_drops_reference_year_keeps_last_five():
    assert window_years(SIX) == WINDOW


def test_window_years_is_identity_for_exactly_five():
    assert window_years(WINDOW) == WINDOW


def test_window_years_is_identity_for_fewer_than_five():
    assert window_years(WINDOW[:3]) == WINDOW[:3]


def test_window_years_sorts_unsorted_input():
    assert window_years(list(reversed(SIX))) == WINDOW


def test_window_years_empty():
    assert window_years([]) == []


def test_window_bounds_are_window_edges_not_reference():
    assert window_bounds(SIX) == ("2021-2022", "2025-2026")


def test_window_bounds_empty():
    assert window_bounds([]) == (None, None)


# --- the reference year must never slide into the window to fill a gap ---

def test_window_excludes_reference_when_a_middle_window_year_is_missing():
    # 2023-24 has no rows (e.g. user deselected it). Only 5 labels present —
    # a naive "last 5" would return all of them, ref included.
    present = [REF, "2021-2022", "2022-2023", "2024-2025", "2025-2026"]
    assert window_years(present) == ["2021-2022", "2022-2023", "2024-2025", "2025-2026"]
    assert window_bounds(present) == ("2021-2022", "2025-2026")


def test_window_excludes_reference_when_last_window_year_not_yet_landed():
    # Wage tab shape after +1 shift: window 2020-21..2024-25 but the 2024-25
    # SCFF file hasn't arrived, so the frame stops at 2023-24. Five labels
    # present again; the window must still be the four real ones.
    present = ["2018-19", "2020-21", "2021-22", "2022-23", "2023-24"]
    assert window_years(present) == ["2020-21", "2021-22", "2022-23", "2023-24"]


def test_window_handles_wage_tab_two_digit_labels():
    present = ["2018-19", "2020-21", "2021-22", "2022-23", "2023-24", "2024-25"]
    assert window_years(present) == ["2020-21", "2021-22", "2022-23", "2023-24", "2024-25"]
    assert window_bounds(present) == ("2020-21", "2024-25")


# --- narrowed sidebar selection: the reference year must never join the window ---

def test_window_excludes_reference_when_only_earliest_window_year_selected():
    # User unchecks everything but 2021-22; the fetch still carries 2018-19.
    # Anchoring on the latest present year (2021 - 4 = 2017 <= 2018) would
    # pull the reference in. It must not.
    assert window_years([REF, "2021-2022"]) == ["2021-2022"]
    assert window_bounds([REF, "2021-2022"]) == ("2021-2022", "2021-2022")


def test_window_excludes_reference_with_two_early_window_years():
    assert window_years([REF, "2021-2022", "2022-2023"]) == ["2021-2022", "2022-2023"]


def test_window_is_empty_when_only_reference_present():
    assert window_years([REF]) == []
    assert window_bounds([REF]) == (None, None)


def test_wage_reference_2017_is_also_excluded():
    # The wage pair's ref is acyr 2017; before the +1 display shift its raw
    # label would be 2017-2018. Both raw and shifted forms must be excluded.
    assert window_years(["2017-2018", "2020-2021"]) == ["2020-2021"]
    assert window_years(["2018-19", "2020-21"]) == ["2020-21"]


def test_window_ignores_non_year_labels():
    assert window_years([None, "n/a", *SIX]) == WINDOW


# ---------------------------------------------------------------------------
# small-n suppression keys on the window, not the reference year
# ---------------------------------------------------------------------------

def _race_frame(counts_by_year: dict[str, int], race="Filipino") -> pd.DataFrame:
    return pd.DataFrame({
        "academic_year": list(counts_by_year),
        "race_description": [race] * len(counts_by_year),
        "count": list(counts_by_year.values()),
    })


def test_suppression_ignores_tiny_reference_year():
    # 2018-19 is below threshold but both window edges are healthy: must show.
    df = _race_frame({REF: 3, **{y: 50 for y in WINDOW}})
    assert "Filipino" in _visible_categories(df, "race_description", RACE_ORDER)


def test_single_selected_year_suppression_ignores_reference_count():
    # Only 2025-26 selected. Filipino: 50 in the reference year, 3 on screen.
    # The <2-window-years fallback must judge the 3, not the 50.
    df = _race_frame({REF: 50, WINDOW[-1]: 3})
    assert "Filipino" not in _visible_categories(df, "race_description", RACE_ORDER)
    df_ok = _race_frame({REF: 3, WINDOW[-1]: 50})
    assert "Filipino" in _visible_categories(df_ok, "race_description", RACE_ORDER)


def test_suppression_still_hides_when_window_last_year_is_small():
    # Reference year is large; last window year is below threshold: must hide.
    df = _race_frame({REF: 500, **{y: 50 for y in WINDOW[:-1]}, WINDOW[-1]: CATEGORY_MIN_COUNT - 1})
    assert "Filipino" not in _visible_categories(df, "race_description", RACE_ORDER)


# ---------------------------------------------------------------------------
# campus / group "5-Yr % Change" bars come from the window
# ---------------------------------------------------------------------------

def test_campus_pct_change_ignores_reference_year():
    # Cypress: 2018-19 = 1000, window 100 -> 150. Must report +50%, not -85%.
    df = pd.DataFrame({
        "academic_year": SIX,
        "camp_desc": ["Cypress"] * 6,
        "headcount": [1000, 100, 110, 120, 130, 150],
    })
    out = compute_pct_change(df)
    assert out.loc[out["camp_desc"] == "Cypress", "pct_change"].iloc[0] == 50.0


def test_units_pct_change_ignores_reference_year():
    df = pd.DataFrame({
        "academic_year": SIX,
        "camp_desc": ["Cypress"] * 6,
        "avg_units": [30.0, 10.0, 11.0, 12.0, 13.0, 15.0],
    })
    out = units_pct_change(df)
    assert out.loc[out["camp_desc"] == "Cypress", "pct_change"].iloc[0] == 50.0


# ---------------------------------------------------------------------------
# summary table first/last columns come from the window
# ---------------------------------------------------------------------------

def test_race_summary_html_headers_use_window_edges():
    df = _race_frame({REF: 10, **{y: 50 for y in WINDOW}}, race="Asian")
    html = build_race_summary_html(df, SIX)
    assert "2021-2022<br>Student Count" in html
    assert "2025-2026<br>Student Count" in html
    assert REF not in html


def test_race_summary_html_is_blank_for_single_window_year_plus_reference():
    df = _race_frame({REF: 600, WINDOW[-1]: 500}, race="Asian")
    assert build_race_summary_html(df, [REF, WINDOW[-1]]) == ""


def test_excel_count_summary_is_empty_for_single_window_year_plus_reference():
    df = pd.DataFrame({
        "academic_year": [REF, WINDOW[-1]],
        "race_description": ["A", "A"],
        "count": [1000, 150],
    })
    out = _count_summary(
        df, key_col="race_description", label_col="Race",
        order=["A"], label_map={"A": "Apple"}, years=[REF, WINDOW[-1]],
    )
    assert out.empty


def test_excel_count_summary_first_year_is_window_start():
    df = pd.DataFrame({
        "academic_year": SIX * 1,
        "race_description": ["A"] * 6,
        "count": [1000, 100, 110, 120, 130, 150],
    })
    out = _count_summary(
        df, key_col="race_description", label_col="Race",
        order=["A"], label_map={"A": "Apple"}, years=SIX,
    )
    row = out.iloc[0]
    assert row["2021-2022 Count"] == 100
    assert row["2025-2026 Count"] == 150
    # (150-100)/100 = +50%, NOT (150-1000)/1000 = -85%
    assert abs(row["5-Yr Percent Change"] - 0.5) < 1e-9
    assert f"{REF} Count" not in out.columns
