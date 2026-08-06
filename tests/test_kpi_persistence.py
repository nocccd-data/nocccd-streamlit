"""Tests for src.scripts.tabs.kpi_persistence completeness logic.

`_attach_completeness` decides whether a persistence point still carries a
"provisional" caveat. Getting it wrong is silent in both directions: a missing
caveat presents a partial count as final, and a spurious one discredits a
number that is settled. The design doc
(docs/superpowers/specs/2026-08-05-persistence-term-completeness-design.md)
names these cases explicitly, which is why they are pinned here.
"""

import pandas as pd
import pytest

from src.scripts.tabs.kpi_persistence import (
    _attach_completeness,
    _build_overall,
    _calendar_gaps,
    _compute_projections,
    _fmt_r_squared,
    _last_completed,
    _project_rate,
    _provisional_by_campus,
    _today_pacific,
)

TODAY = pd.Timestamp("2026-08-05")

# Real NOCCCD dates. The credit and NOCE springs of the same academic year end
# nine days apart, which is what makes the per-track split observable.
CALENDAR = pd.DataFrame({
    "stvterm_code": ["202520", "202535", "202610", "202615", "202699"],
    "stvterm_end_date": pd.to_datetime([
        "2026-05-30",   # credit spring 2026
        "2026-05-21",   # NOCE spring 2026
        "2026-12-12",   # credit fall 2026
        "2026-12-17",   # NOCE fall 2026
        "2026-08-05",   # ends exactly on TODAY
    ]),
})


def _rows(pairs):
    return pd.DataFrame(
        [{"campus": c, "term_short": t, "term_sort": s, "next_fall_term_code": k}
         for c, t, s, k in pairs]
    )


def test_term_that_has_ended_is_complete():
    out = _attach_completeness(
        _rows([("Cypress", "Fall 2025", 257, "202520")]),
        CALENDAR, "next_fall_term_code", TODAY,
    )
    assert not out.iloc[0].is_provisional


def test_term_ending_exactly_today_is_still_provisional():
    """Provisional through the end date *inclusive*.

    The boundary matters: `end_date <= today` instead of `<` would drop the
    caveat while the term is still running its final day.
    """
    out = _attach_completeness(
        _rows([("Cypress", "Fall 2025", 257, "202699")]),
        CALENDAR, "next_fall_term_code", TODAY,
    )
    assert out.iloc[0].is_provisional


def test_term_ending_in_the_future_is_provisional():
    out = _attach_completeness(
        _rows([("Cypress", "Fall 2026", 267, "202610")]),
        CALENDAR, "next_fall_term_code", TODAY,
    )
    assert out.iloc[0].is_provisional


def test_missing_calendar_row_falls_back_to_provisional():
    """Unmatched term codes must fail safe, and be reported.

    Banner can define a credit term before its NOCE counterpart, so this is a
    live path. Claiming such a point is final is the costlier error.
    """
    out = _attach_completeness(
        _rows([("NOCE", "Fall 2026", 267, "202799")]),
        CALENDAR, "next_fall_term_code", TODAY,
    )
    assert out.iloc[0].is_provisional
    assert not out.iloc[0].has_calendar
    assert _calendar_gaps(out, "next_fall_term_code") == ["202799"]


def test_null_term_code_is_reported_as_missing_not_nan():
    out = _attach_completeness(
        _rows([("NOCE", "Fall 2026", 267, None)]),
        CALENDAR, "next_fall_term_code", TODAY,
    )
    assert out.iloc[0].is_provisional
    assert _calendar_gaps(out, "next_fall_term_code") == ["(missing)"]


def test_credit_and_noce_diverge_within_the_same_mis_term():
    """One mis_term_id, two tracks, two end dates.

    2026-05-25 falls between NOCE's spring ending (5/21) and credit's (5/30),
    so a single global flag would be wrong for one track or the other.
    """
    out = _attach_completeness(
        _rows([
            ("Cypress",   "Fall 2025", 257, "202520"),
            ("Fullerton", "Fall 2025", 257, "202520"),
            ("NOCE",      "Fall 2025", 257, "202535"),
        ]),
        CALENDAR, "next_fall_term_code", pd.Timestamp("2026-05-25"),
    )
    assert list(out.is_provisional) == [True, True, False]
    assert _provisional_by_campus(out) == {
        "Cypress": ["Fall 2025"], "Fullerton": ["Fall 2025"],
    }


def test_duplicate_term_codes_raise_rather_than_pick_one():
    """A duplicated key would make the lookup silently arbitrary."""
    dupes = pd.DataFrame({
        "stvterm_code": ["202520", "202520"],
        "stvterm_end_date": pd.to_datetime(["2026-05-30", "2026-06-30"]),
    })
    with pytest.raises(ValueError, match="202520"):
        _attach_completeness(
            _rows([("Cypress", "Fall 2025", 257, "202520")]),
            dupes, "next_fall_term_code", TODAY,
        )


def test_out_of_range_end_date_does_not_break_the_lookup():
    """stvterm carries a 999999 sentinel term dated 2999.

    That is outside pandas' nanosecond datetime64 range; parsing it without
    `errors="coerce"` raises OutOfBoundsDatetime and takes down the whole
    lookup, not just that row.
    """
    cal = pd.DataFrame({
        "stvterm_code": ["202520", "999999"],
        "stvterm_end_date": [
            pd.Timestamp("2026-05-30").to_pydatetime(),
            __import__("datetime").datetime(2999, 5, 15),
        ],
    })
    out = _attach_completeness(
        _rows([
            ("Cypress", "Fall 2025", 257, "202520"),
            ("Cypress", "Sentinel",  999, "999999"),
        ]),
        cal, "next_fall_term_code", TODAY,
    )
    assert not out.iloc[0].is_provisional     # real term still resolves
    assert out.iloc[1].is_provisional         # unrepresentable -> not past


def test_build_overall_keeps_rows_with_a_null_term_code():
    """groupby drops NaN keys by default, deleting a whole campus/term.

    The term-code columns are grouping keys, so without `dropna=False` a null
    code silently removes that campus/term from the Overall line — counts and
    all, in both persistence modes at once.
    """
    df = pd.DataFrame({
        "campus": ["NOCE", "Cypress"],
        "term_short": ["Fall 2024", "Fall 2024"],
        "term_sort": [247, 247],
        "spring_term_code": [None, "202420"],
        "next_fall_term_code": ["202515", "202510"],
        "curr_fall_p_count": [10_398, 15_336],
        "next_fall_p_denominator": [10_045, 14_127],
        "spring_total_headcount": [6_724, 10_683],
        "next_fall_total_headcount": [4_739, 7_409],
    })
    out = _build_overall(df)
    assert set(out["campus"]) == {"NOCE", "Cypress"}
    assert out.loc[out.campus == "NOCE", "next_fall_total_headcount"].iloc[0] == 4_739


def test_today_is_pacific_not_ambient():
    """The app runs on UTC containers; Banner terms are Pacific dates.

    Reading the ambient clock rolls the date over ~17:00 Pacific and drops the
    caveat hours before the term's own end date is over locally.
    """
    today = _today_pacific()
    assert today.tzinfo is None, "must be naive to compare against stvterm DATEs"
    assert today == pd.Timestamp.now(tz="America/Los_Angeles").normalize().tz_localize(None)


# ---------------------------------------------------------------------------
# Projections exclude provisional cohorts (docs/deferred.md cluster 1)
# ---------------------------------------------------------------------------

def _series(rates, provisional_flags):
    return pd.DataFrame({
        "campus": ["Cypress"] * len(rates),
        "term_short": [f"Fall {2020 + i}" for i in range(len(rates))],
        "term_sort": [207 + 10 * i for i in range(len(rates))],
        "rate": rates,
        "is_provisional": provisional_flags,
    })


def test_projection_ignores_the_provisional_point():
    """A partial rate must not drag the fit.

    Measured on the real 2020-2025 history: including the provisional point
    moved Fullerton's forecast from 53.9% to 47.1%.
    """
    # Flat ~52% history, then a partial 45% that would drag a fit downward.
    df = _series([0.51, 0.51, 0.53, 0.53, 0.52, 0.45],
                 [False] * 5 + [True])
    out = _compute_projections(df, "rate", ["campus"], "Linear Regression")
    assert len(out) == 1
    # Fit on the flat completed history projects near it, not below it.
    assert out.iloc[0]["rate"] > 0.52
    # And the same series WITH the partial point included drags it down.
    dragged, _ = _project_rate([0.51, 0.51, 0.53, 0.53, 0.52, 0.45],
                               "Linear Regression")
    assert dragged is not None and dragged < out.iloc[0]["rate"]


def test_projected_term_is_past_the_last_plotted_term():
    """Masking, not dropping — the horizon must not shift back a year.

    Dropping the provisional row would shorten the series and aim the
    forecast at that cohort's own slot, drawing it on a point already there.
    """
    df = _series([0.51, 0.51, 0.53, 0.53, 0.52, 0.45], [False] * 5 + [True])
    out = _compute_projections(df, "rate", ["campus"], "Linear Regression")
    assert out.iloc[0]["term_sort"] == 267        # one past the plotted 257
    assert out.iloc[0]["term_short"] == "Fall 2026"


def test_weighted_moving_average_uses_the_last_3_completed():
    df = _series([0.10, 0.20, 0.51, 0.51, 0.53, 0.45], [False] * 5 + [True])
    out = _compute_projections(df, "rate", ["campus"],
                               "Weighted Moving Average")
    expected = (0.51 * 1 + 0.51 * 2 + 0.53 * 3) / 6
    assert out.iloc[0]["rate"] == pytest.approx(expected)


def test_r_squared_is_suppressed_below_three_completed_terms():
    """A line fits 2 points perfectly, so R2=1.0 there is an artifact."""
    two, r2_two = _project_rate([0.50, 0.52], "Linear Regression")
    assert two is not None
    assert r2_two is None
    three, r2_three = _project_rate([0.50, 0.52, 0.54], "Linear Regression")
    assert three is not None and r2_three is not None


def test_r_squared_formats_none_as_not_available():
    assert _fmt_r_squared(None) == "n/a (<3 terms)"
    assert _fmt_r_squared(0.8912) == "0.891"


def test_projection_anchors_on_the_last_completed_point():
    df = _series([0.51, 0.52, 0.45], [False, False, True])
    assert _last_completed(df)["term_sort"] == 217
    # All-provisional degrades to the last row rather than raising.
    allprov = _series([0.45], [True])
    assert _last_completed(allprov)["term_sort"] == 207


def test_no_projection_when_completeness_is_unknown():
    """A calendar outage must suppress projections, not silently refit.

    Without `is_provisional` the old code fit every point including the
    partial one, while the methodology text on screen and in the PDF still
    claimed completed cohorts only. Measured before the fix: Fullerton
    projected 47.1% instead of 53.9% whenever term_calendar was unavailable.
    """
    df = _series([0.51, 0.51, 0.53, 0.53, 0.52, 0.45], [False] * 5 + [True])
    assert not _compute_projections(
        df, "rate", ["campus"], "Linear Regression").empty
    no_flag = df.drop(columns=["is_provisional"])
    assert _compute_projections(
        no_flag, "rate", ["campus"], "Linear Regression").empty
    assert _compute_projections(
        no_flag, "rate", ["campus"], "Weighted Moving Average").empty
