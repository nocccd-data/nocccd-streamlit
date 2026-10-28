"""Tests for src.scripts.tabs.kpi_styp_headcount.

The extract is already one distinct headcount per Fall x college group x type,
so the tab's own logic is small but easy to get silently wrong: which Fall is
the baseline, which cards are highlighted, and that a type the SQL emits but
no card shows fails instead of vanishing from the screen.
"""

import io
import math
import re
from pathlib import Path

import pandas as pd
import pytest

from src.pipeline.config import DATASETS
from src.scripts.tabs.kpi_styp_headcount import (
    ALL_CARDS,
    CREDIT_CARDS,
    NOCE_CARD,
    _build_excel_sections,
    _build_table,
    _card_series,
    _change_text,
    _fall_range,
    _fall_year,
    _generate_excel,
    _generate_pdf,
    _highlighted,
    _is_flat,
    _pct_change,
    _prepare_data,
)

SQL = Path(__file__).resolve().parent.parent / "src/pipeline/sql/kpi_styp_headcount.sql"

# Real counts from the 2026-10-28 REPT extract, Fall 2022 and Fall 2026 only.
_COUNTS = {
    ("credit", "adult"): (1830, 2138),
    ("credit", "continuing"): (15943, 18025),
    ("credit", "first_time"): (5750, 6528),
    ("credit", "first_time_trans"): (1414, 1590),
    ("credit", "returning"): (3277, 2549),
    ("credit", "special_admit_dual"): (1987, 3723),
    ("noce", "adult"): (9410, 10680),
}


def _raw(terms=("227", "267"), counts=_COUNTS) -> pd.DataFrame:
    rows = [
        {"mis_term_id": term, "college_group": group, "styp_code": styp, "pidm_count": n}
        for (group, styp), values in counts.items()
        for term, n in zip(terms, values)
    ]
    return pd.DataFrame(rows)


def test_fall_year_from_mis_term_id():
    assert _fall_year("227") == 2022
    assert _fall_year(267) == 2026


def test_prepare_data_rejects_a_type_no_card_shows():
    df = pd.concat([_raw(), pd.DataFrame([{
        "mis_term_id": "267", "college_group": "credit",
        "styp_code": "concurrent", "pidm_count": 5,
    }])])
    with pytest.raises(ValueError, match="concurrent"):
        _prepare_data(df)


def test_prepare_data_rejects_missing_columns():
    with pytest.raises(KeyError, match="pidm_count"):
        _prepare_data(_raw().drop(columns="pidm_count"))


def test_change_runs_from_earliest_to_latest_selected_fall():
    df = _prepare_data(_raw())
    series = _card_series(df, CREDIT_CARDS[0])
    assert series.index.tolist() == [2022, 2026]
    assert _pct_change(series) == pytest.approx((2138 - 1830) / 1830)


def test_change_is_undefined_for_one_fall_or_a_zero_baseline():
    assert math.isnan(_pct_change(pd.Series([100.0], index=[2026])))
    assert math.isnan(_pct_change(pd.Series([0.0, 50.0], index=[2022, 2026])))
    assert math.isnan(_pct_change(pd.Series([float("nan"), 50.0], index=[2022, 2026])))


def test_a_type_with_no_row_in_a_fall_had_zero_students():
    """GROUP BY emits no zero counts, so a missing row is 0 -- and the credit
    total must still equal the sum of the cards, not skip the gap."""
    df = _raw()
    df = _prepare_data(df[~((df["styp_code"] == "returning") & (df["mis_term_id"] == "227"))])
    series = _card_series(df, CREDIT_CARDS[4])
    assert series.loc[2022] == 0
    assert math.isnan(_pct_change(series))
    table = _build_table(df, CREDIT_CARDS, total_label="Total")
    assert table.iloc[-1]["Fall 2022"] == table.iloc[:-1]["Fall 2022"].sum()


def test_highlight_picks_the_two_largest_gains():
    df = _prepare_data(_raw())
    changes = {spec: _pct_change(_card_series(df, spec)) for spec in CREDIT_CARDS}
    picked = {spec.styp for spec in _highlighted(changes)}
    assert picked == {"special_admit_dual", "adult"}


def test_highlight_never_picks_a_decline():
    a, b, c = CREDIT_CARDS[:3]
    assert _highlighted({a: -0.1, b: -0.3, c: float("nan")}) == set()
    assert _highlighted({a: 0.05, b: -0.3, c: 0.0}) == {a}


def test_a_gain_that_shows_as_zero_is_not_highlighted():
    a, b = CREDIT_CARDS[:2]
    assert _highlighted({a: 0.0002, b: 0.3}) == {b}


def test_highlight_tie_goes_to_the_earlier_card():
    a, b, c = CREDIT_CARDS[:3]
    assert _highlighted({a: 0.2, b: 0.1, c: 0.1}) == {a, b}


def test_change_text():
    assert _change_text(0.157) == "▲ 15.7%"
    assert _change_text(-0.212) == "▼ 21.2%"
    assert _change_text(0.0) == "0.0%"
    assert _change_text(float("nan")) == "—"


def test_a_change_that_shows_as_zero_is_flat_not_up_or_down():
    assert _is_flat(-0.0004) and _is_flat(0.0004)
    assert _change_text(-0.0004) == "0.0%"
    assert not _is_flat(0.0006)


def test_fall_range_names_one_fall_once():
    assert _fall_range([2022, 2023, 2026]) == "Fall 2022 to Fall 2026"
    assert _fall_range([2026]) == "Fall 2026"


def test_credit_total_is_the_sum_of_the_six_types():
    table = _build_table(_prepare_data(_raw()), CREDIT_CARDS, total_label="Total")
    total = table.iloc[-1]
    assert total["Student Type"] == "Total"
    assert total["Fall 2022"] == sum(v[0] for k, v in _COUNTS.items() if k[0] == "credit")
    assert total["Fall 2026"] == sum(v[1] for k, v in _COUNTS.items() if k[0] == "credit")
    assert "% Change vs Fall 2022" in table.columns


def test_one_fall_has_no_change_column():
    table = _build_table(_prepare_data(_raw(terms=("267",), counts={
        k: (v[1],) for k, v in _COUNTS.items()
    })), CREDIT_CARDS)
    assert not any(col.startswith("% Change") for col in table.columns)


def test_excel_has_a_credit_and_a_noce_section():
    sections = _build_excel_sections(_prepare_data(_raw()))
    assert [len(s.df) for s in sections] == [len(CREDIT_CARDS) + 1, 1]
    assert sections[1].df.iloc[0]["Student Type"] == NOCE_CARD.title
    assert sections[0].percent_cols == ("% Change vs Fall 2022",)
    sheet = pd.read_excel(io.BytesIO(_generate_excel(_prepare_data(_raw()))), header=None)
    assert "Special Admit / Dual Enrollment" in sheet[0].tolist()


def test_pdf_is_one_page():
    fitz = pytest.importorskip("fitz")
    doc = fitz.open(stream=_generate_pdf(_prepare_data(_raw())), filetype="pdf")
    assert len(doc) == 1
    text = doc[0].get_text()
    assert "Special Admit / Dual" in text and "NOCE (Noncredit)" in text


def test_every_card_is_a_distinct_group_and_type():
    keys = [(c.group, c.styp) for c in ALL_CARDS]
    assert len(keys) == len(set(keys))


def test_sql_expands_the_configured_term_list():
    """extract.py runs the IN (:t1) form once for all Falls; a single
    `:mis_term_id` bind would instead rerun the whole SGBSTDN scan per Fall."""
    cfg = DATASETS["kpi_styp_headcount"]
    assert cfg["param_name"] == "mis_term_id"
    sql = SQL.read_text()
    assert re.search(r"IN\s*\(\s*:t1", sql, re.IGNORECASE)
    assert ":mis_term_id" not in sql
