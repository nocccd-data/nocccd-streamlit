"""Vision 2030 equity tables (spec docs/superpowers/specs/2026-09-28-bot-equity-tables-design.md).

2025-26 is k=3 years after the 2022-23 baseline: growth factor 1 + 0.3*3/7.
"""

import math

import pandas as pd
import pytest

from src.scripts.tabs.bot_equity import (
    FIRSTGEN_CATEGORY,
    GENDER_CATEGORY,
    ON_TRACK,
    PROGRESSING,
    RACE_CATEGORY,
    EquitySource,
    _cell_texts,
    build_equity_table,
    equity_note,
    equity_year,
    format_value,
    format_variance,
)
from src.scripts.tabs.bot_targets import Targets

GROWTH = {"growth": 0.30}
UNITS = {"growth": 0.20, "reduce_over": 60, "value_col": "sum_hours_earned"}
PLAN = ["2022-2023", "2023-2024", "2024-2025", "2025-2026"]
F3 = 1 + 0.3 * 3 / 7


def _targets(years=PLAN, rule=GROWTH):
    # equity_year() only reads the frame's academic_year column.
    return Targets(frame=pd.DataFrame({"academic_year": list(years)}), rule=rule)


def _counts(values, *, order=None, labels=None, category=RACE_CATEGORY):
    """values: {group: {year: students}} -> a count-tab source."""
    agg = pd.DataFrame([
        {"academic_year": y, "grp": g, "count": n}
        for g, by_year in values.items() for y, n in by_year.items()
    ])
    return EquitySource(category=category, agg=agg, key_col="grp", value_col="count",
                        order=order or list(values), labels=labels or {})


def _averages(values, *, category=RACE_CATEGORY):
    """values: {group: {year: (students, average)}} -> a Units-style source."""
    agg = pd.DataFrame([
        {"academic_year": y, "grp": g, "count": n, "avg_units": v}
        for g, by_year in values.items() for y, (n, v) in by_year.items()
    ])
    return EquitySource(category=category, agg=agg, key_col="grp", value_col="avg_units",
                        order=list(values), labels={})


def test_equity_year_is_the_latest_plan_year():
    assert equity_year(_targets()) == "2025-2026"


def test_equity_year_caps_at_the_plan_end():
    assert equity_year(_targets(["2022-2023", "2029-2030", "2030-2031"])) == "2029-2030"


def test_no_equity_year_or_table_with_only_the_baseline():
    only_base = _targets(["2022-2023"])
    assert equity_year(only_base) is None
    src = _counts({"g": {"2022-2023": 50}})
    assert build_equity_table(only_base, [src], min_count=10) is None


def test_values_and_status_per_group():
    src = _counts({"hisp": {"2022-2023": 100, "2025-2026": 120},
                   "asian": {"2022-2023": 50, "2025-2026": 50}},
                  labels={"hisp": "Latino/Hispanic", "asian": "Asian"})
    t = build_equity_table(_targets(), [src], min_count=10)
    assert t is not None
    assert (t.year, t.decimals) == ("2025-2026", False)
    assert list(t.rows["group"]) == ["Latino/Hispanic", "Asian"]
    assert list(t.rows["category"]) == [RACE_CATEGORY, RACE_CATEGORY]
    rows = t.rows.set_index("group")
    assert rows.loc["Latino/Hispanic", "baseline"] == 100
    assert rows.loc["Latino/Hispanic", "benchmark"] == pytest.approx(100 * F3)
    assert rows.loc["Latino/Hispanic", "actual"] == 120
    assert rows.loc["Latino/Hispanic", "variance"] == pytest.approx(120 - 100 * F3)
    assert rows.loc["Latino/Hispanic", "status"] == ON_TRACK
    assert rows.loc["Asian", "status"] == PROGRESSING


def test_ten_student_floor_in_both_years():
    src = _counts({
        "kept": {"2022-2023": 10, "2025-2026": 10},
        "small_base": {"2022-2023": 9, "2025-2026": 40},   # Noncredit Filipino shape
        "small_now": {"2022-2023": 40, "2025-2026": 9},
        "gone_now": {"2022-2023": 40},                      # no row at all in 2025-26
    })
    t = build_equity_table(_targets(), [src], min_count=10)
    assert t is not None
    assert list(t.rows["group"]) == ["kept"]


def test_rows_follow_the_given_order_and_skip_absent_groups():
    src = _counts({"b": {"2022-2023": 20, "2025-2026": 20},
                   "a": {"2022-2023": 20, "2025-2026": 20}},
                  order=["a", "not_in_data", "b"])
    t = build_equity_table(_targets(), [src], min_count=10)
    assert t is not None
    assert list(t.rows["group"]) == ["a", "b"]


def test_categories_stay_in_source_order():
    race = _counts({"r": {"2022-2023": 20, "2025-2026": 20}}, category=RACE_CATEGORY)
    gender = _counts({"g": {"2022-2023": 20, "2025-2026": 20}}, category=GENDER_CATEGORY)
    fg = _counts({"f": {"2022-2023": 20, "2025-2026": 20}}, category=FIRSTGEN_CATEGORY)
    t = build_equity_table(_targets(), [race, gender, fg], min_count=10)
    assert t is not None
    assert list(t.rows["category"]) == [RACE_CATEGORY, GENDER_CATEGORY, FIRSTGEN_CATEGORY]


def test_exact_hit_is_on_track_despite_float_noise():
    # Baseline 210 in 2023-24 (k=1): 210 * (1 + 0.3/7) == 219.00000000000003.
    src = _counts({"g": {"2022-2023": 210, "2023-2024": 219}})
    t = build_equity_table(_targets(["2022-2023", "2023-2024"]), [src], min_count=10)
    assert t is not None
    row = t.rows.iloc[0]
    assert row["variance"] == 0
    assert row["status"] == ON_TRACK


def test_lower_is_better_flips_status():
    src = _averages({"down": {"2022-2023": (40, 90.0), "2025-2026": (40, 80.0)},
                     "flat": {"2022-2023": (40, 80.0), "2025-2026": (40, 80.0)}})
    t = build_equity_table(_targets(rule=UNITS), [src], min_count=10)
    assert t is not None and t.decimals
    rows = t.rows.set_index("group")
    # 90 - (90 - 60) * 0.2 * 3/7 = 87.43; 80 is below it -> On Track.
    assert rows.loc["down", "benchmark"] == pytest.approx(90 - 30 * 0.2 * 3 / 7)
    assert rows.loc["down", "status"] == ON_TRACK
    assert rows.loc["flat", "status"] == PROGRESSING


def test_floor_counts_students_not_the_average():
    src = _averages({"few": {"2022-2023": (5, 90.0), "2025-2026": (5, 80.0)},
                     "many": {"2022-2023": (40, 90.0), "2025-2026": (40, 80.0)}})
    t = build_equity_table(_targets(rule=UNITS), [src], min_count=10)
    assert t is not None
    assert list(t.rows["group"]) == ["many"]


def test_group_with_a_missing_average_is_skipped():
    src = _averages({"no_hours": {"2022-2023": (40, math.nan), "2025-2026": (40, 80.0)},
                     "ok": {"2022-2023": (40, 90.0), "2025-2026": (40, 80.0)}})
    t = build_equity_table(_targets(rule=UNITS), [src], min_count=10)
    assert t is not None
    assert list(t.rows["group"]) == ["ok"]


def test_no_rows_means_no_table():
    src = _counts({"tiny": {"2022-2023": 3, "2025-2026": 4}})
    assert build_equity_table(_targets(), [src], min_count=10) is None


def test_heading_and_headers():
    src = _counts({"g": {"2022-2023": 20, "2025-2026": 20}})
    t = build_equity_table(_targets(), [src], min_count=10)
    assert t is not None
    assert t.heading == "Equity Results, 2025-26"
    assert t.headers() == {
        "category": "Category",
        "group": "Student Population",
        "baseline": "2022-23 Baseline",
        "benchmark": "2025-26 Benchmark",
        "actual": "2025-26 Actual",
        "variance": "Variance",
        "status": "Status",
    }


def test_note_is_generated_from_the_rule():
    assert equity_note(GROWTH) == (
        "Benchmark: 30% increase over the 2022-23 baseline by 2029-30, in equal "
        "annual steps. Variance = Actual − Benchmark."
    )
    assert equity_note(UNITS).endswith(
        "Lower is better. Variance = Actual − Benchmark. "
        "On Track = at or below the benchmark."
    )


def test_display_formats():
    assert format_value(1047.31, decimals=False) == "1,047"
    assert format_value(82.846, decimals=True) == "82.8"
    assert format_variance(69.69, decimals=False) == "+70"
    assert format_variance(-49.37, decimals=False) == "-49"
    assert format_variance(-0.39, decimals=False) == "0"
    assert format_variance(-0.14, decimals=True) == "-0.1"
    assert format_variance(0.04, decimals=True) == "0"


def test_half_benchmark_variance_matches_printed_actual_minus_printed_benchmark():
    # baseline 35, F3 -> benchmark exactly 39.5 -> prints "40" (round-half-up,
    # like Excel's #,##0). Live case: ADT Black or African American, 35 -> 39.5.
    def row_for(actual):
        src = _counts({"g": {"2022-2023": 35, "2025-2026": actual}})
        t = build_equity_table(_targets(), [src], min_count=10)
        assert t is not None
        return t.rows.to_dict("records")[0]

    row41 = row_for(41)
    assert row41["benchmark"] == pytest.approx(39.5)
    texts41 = _cell_texts(row41, decimals=False)
    assert texts41[2] == "40"      # benchmark
    assert texts41[4] == "+1"      # variance: printed actual - printed benchmark
    assert row41["status"] == ON_TRACK

    row39 = row_for(39)
    texts39 = _cell_texts(row39, decimals=False)
    assert texts39[4] == "-1"
    assert row39["status"] == PROGRESSING

    row40 = row_for(40)
    texts40 = _cell_texts(row40, decimals=False)
    assert texts40[4] == "0"
    assert row40["variance"] == pytest.approx(0.5)   # true variance, unrounded
    assert row40["status"] == ON_TRACK               # Status uses the true variance


def test_half_benchmark_tie_with_an_even_whole_part():
    # baseline 25 in 2029-30 (k=7): 25 * 1.3 = 32.5 -> prints "33"; half-even
    # would have printed "32" here, disagreeing with the half-up case above.
    src = _counts({"g": {"2022-2023": 25, "2029-2030": 33}})
    t = build_equity_table(_targets(["2022-2023", "2029-2030"]), [src], min_count=10)
    assert t is not None
    row = t.rows.to_dict("records")[0]
    assert row["benchmark"] == pytest.approx(32.5)
    texts = _cell_texts(row, decimals=False)
    assert texts[2] == "33"
    assert texts[4] == "0"
    assert row["status"] == ON_TRACK


def test_half_benchmark_spec_example_still_holds_below_the_floor():
    # spec's AA American Indian example: baseline 3, actual 3, benchmark
    # 3 * F3 = 3.39 -> Variance "0", Progressing. Below CATEGORY_MIN_COUNT,
    # so assert with min_count=1.
    src = _counts({"g": {"2022-2023": 3, "2025-2026": 3}})
    t = build_equity_table(_targets(), [src], min_count=1)
    assert t is not None
    row = t.rows.to_dict("records")[0]
    assert row["benchmark"] == pytest.approx(3 * F3)
    texts = _cell_texts(row, decimals=False)
    assert texts[4] == "0"
    assert row["status"] == PROGRESSING


def test_tallest_table_fits_above_the_footer():
    import typing

    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.patches import Rectangle

    from src.scripts.tabs.bot_equity import mpl_equity_table

    def every_group(keys, category):
        # UNITS rule so the note wraps to two lines (the tallest note, as well
        # as the tallest table), and _averages is Units-shaped.
        return _averages(
            {k: {"2022-2023": (40, 90.0), "2025-2026": (40, 80.0)} for k in keys},
            category=category,
        )

    t = build_equity_table(_targets(rule=UNITS), [
        every_group([f"race{i}" for i in range(9)], RACE_CATEGORY),
        every_group([f"gender{i}" for i in range(4)], GENDER_CATEGORY),
        every_group([f"fg{i}" for i in range(3)], FIRSTGEN_CATEGORY),
    ], min_count=10)
    assert t is not None and len(t.rows) == 16
    fig = plt.figure(figsize=(8.5, 11.0))
    try:
        mpl_equity_table(fig, t, top=0.505, bottom=0.045)
        ax = fig.axes[0]
        rects = [p for p in ax.patches if isinstance(p, Rectangle)]
        # Every cell sits inside the axes, and the axes sit above *bottom*.
        assert min(r.get_y() for r in rects) >= -1e-9
        assert ax.get_position().y0 >= 0.045
        bands = [r for r in rects if r.get_width() == pytest.approx(1.0)]
        assert len(bands) == 3
        heading, note = fig.texts[0], fig.texts[-1]
        assert heading.get_text() == "Equity Results, 2025-26"
        assert note.get_text().count("\n") == 1      # the two-line Units note
        # The note's anchor is its TOP edge (va="top"); check the rendered
        # extent's bottom edge, not the anchor, so a note running into the
        # footer would actually fail this.
        fig.canvas.draw()
        canvas = typing.cast(FigureCanvasAgg, fig.canvas)
        renderer = canvas.get_renderer()
        assert note.get_window_extent(renderer).y0 / fig.bbox.height > 0.045
    finally:
        plt.close(fig)


# ---------------------------------------------------------------------------
# One display rule everywhere (review of PR #30): the printed Variance is the
# printed Actual minus the printed Benchmark on Units too, and printed numbers
# round half up like Excel.
# ---------------------------------------------------------------------------

def test_units_printed_variance_is_printed_actual_minus_printed_benchmark():
    # Live 2025-26 Units shapes. Before, White printed 84.8 - 80.8 as "+3.9"
    # and Latino printed 80.3 - 80.5 as "-0.1".
    white = {"group": "White", "baseline": 82.8, "benchmark": 80.846, "actual": 84.79,
             "variance": 84.79 - 80.846, "status": PROGRESSING}
    latino = {"group": "Latino/Hispanic", "baseline": 82.39, "benchmark": 80.468,
              "actual": 80.323, "variance": -0.145, "status": ON_TRACK}
    assert _cell_texts(white, decimals=True)[2:5] == ["80.8", "84.8", "+4.0"]
    # Still On Track: Status comes from the true variance (-0.145).
    assert _cell_texts(latino, decimals=True)[2:6] == ["80.5", "80.3", "-0.2", ON_TRACK]


def test_one_decimal_ties_round_half_up_like_excel():
    # 82.25 is exact in binary; Python's round-half-even prints "82.2".
    assert format_value(82.25, decimals=True) == "82.3"
