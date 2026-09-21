"""x-axis range for the horizontal "5-Yr % Change" bar charts.

The same range formula was copy-pasted into four chart builders (Plotly and
matplotlib, in bot_helpers and bot_goal3_units). It padded each side
multiplicatively, which collapses for near-zero values — Goal 4's +0.2% bar
got 0.16 units of room and its "outside" label was clipped off the right
edge — and it did not anchor the axis at zero, so a chart where every bar
was large and positive would start the axis past zero and cut the bars off
at the left. One shared helper now does it.
"""

import math

import pytest

from src.scripts.tabs.bot_helpers import pct_change_axis_range


def test_near_zero_single_bar_gets_room_for_its_label():
    # Goal 4 transfer-ready: 5,761 -> 5,774 = +0.2%. Old range was
    # [-4.8, 0.36]; the label needs real room past the bar's tip.
    bar = 0.2
    lo, hi = pct_change_axis_range([bar])
    assert lo < 0 < bar < hi
    room_past_bar = hi - bar
    assert room_past_bar / (hi - lo) >= 0.35


def test_axis_always_spans_zero():
    # All large and positive: old formula gave [15, 36], cutting the bars
    # off at the left because they grow from zero.
    lo, hi = pct_change_axis_range([20, 22, 18, 21])
    assert lo < 0
    assert hi > 22


def test_typical_mixed_values_barely_change():
    lo, hi = pct_change_axis_range([-3, 8, 5, 6])
    assert math.isclose(hi, 14.4, abs_tol=0.01)   # 8 * 1.8, as before
    assert -6.5 < lo < -5                          # was -5.4; a touch wider


def test_all_negative_matches_previous_behaviour():
    lo, hi = pct_change_axis_range([-8, -3])
    assert math.isclose(lo, -14.4, abs_tol=0.01)  # -8 * 1.8
    assert math.isclose(hi, 2.0, abs_tol=0.01)    # small positive margin


def test_exact_zero_does_not_produce_a_degenerate_axis():
    lo, hi = pct_change_axis_range([0.0])
    assert lo < 0 < hi
    assert hi - lo >= 1.0


@pytest.mark.parametrize("values", [[], [float("nan")], [None]])
def test_no_usable_values_falls_back_to_a_sane_default(values):
    lo, hi = pct_change_axis_range(values)
    assert lo < 0 < hi
