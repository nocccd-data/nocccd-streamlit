"""Tests for the pure DataFrame helpers in src.pipeline.bot_excel_export.

These helpers (_count_summary, _value_summary, _matrix_table, _rate_detail)
do all the numeric aggregation behind the BOT Excel export. They are pure:
they take DataFrames in and return DataFrames out. Streamlit, Hyper, and
Oracle are not involved, so they are unit-testable with synthetic frames.
"""

import logging

import pandas as pd
import pytest

# Silence streamlit's "No runtime found" warning that fires at tab-module
# import time; the exporter's main() does this via _setup_env(), but pytest
# imports the module without calling main().
logging.getLogger("streamlit.runtime.caching.cache_data_api").addFilter(
    lambda record: "No runtime found" not in record.getMessage()
)

from src.pipeline.bot_excel_export import (  # noqa: E402
    _count_summary,
    _matrix_table,
    _rate_detail,
    _value_summary,
)


# ---------------------------------------------------------------------------
# _count_summary
# ---------------------------------------------------------------------------

def test_count_summary_happy_path():
    df = pd.DataFrame({
        "academic_year": ["2020-21", "2020-21", "2024-25", "2024-25"],
        "race_description": ["A", "B", "A", "B"],
        "count": [100, 50, 150, 60],
    })
    out = _count_summary(
        df,
        key_col="race_description",
        label_col="Race",
        order=["A", "B"],
        label_map={"A": "Apple", "B": "Banana"},
        years=["2020-21", "2024-25"],
    )
    assert list(out["Race"]) == ["Apple", "Banana"]
    assert out.loc[0, "2020-21 Count"] == 100
    assert out.loc[0, "2024-25 Count"] == 150
    assert out.loc[0, "5-Yr Percent Change"] == pytest.approx((150 - 100) / 100)
    assert out.loc[1, "5-Yr Percent Change"] == pytest.approx((60 - 50) / 50)


def test_count_summary_zero_first_year_returns_nan():
    """fc=0 must yield NaN, not divide-by-zero."""
    df = pd.DataFrame({
        "academic_year": ["2020-21", "2024-25"],
        "race_description": ["A", "A"],
        "count": [0, 100],
    })
    out = _count_summary(
        df,
        key_col="race_description",
        label_col="Race",
        order=["A"],
        label_map={"A": "A"},
        years=["2020-21", "2024-25"],
    )
    assert pd.isna(out.loc[0, "5-Yr Percent Change"])


def test_count_summary_single_year_returns_empty():
    df = pd.DataFrame({
        "academic_year": ["2024-25"],
        "race_description": ["A"],
        "count": [50],
    })
    out = _count_summary(
        df,
        key_col="race_description",
        label_col="Race",
        order=["A"],
        label_map={"A": "A"},
        years=["2024-25"],
    )
    assert out.empty


def test_count_summary_missing_key_yields_zero_counts():
    """A key in `order` that has no rows in `df` shows 0/0 counts and NaN
    change rather than KeyError."""
    df = pd.DataFrame({
        "academic_year": ["2020-21", "2024-25"],
        "race_description": ["A", "A"],
        "count": [10, 20],
    })
    out = _count_summary(
        df,
        key_col="race_description",
        label_col="Race",
        order=["A", "Z"],
        label_map={"A": "A", "Z": "Z"},
        years=["2020-21", "2024-25"],
    )
    z_row = out[out["Race"] == "Z"].iloc[0]
    assert z_row["2020-21 Count"] == 0
    assert z_row["2024-25 Count"] == 0
    assert pd.isna(z_row["5-Yr Percent Change"])


# ---------------------------------------------------------------------------
# _value_summary  — covers the first_val truthiness fix
# ---------------------------------------------------------------------------

def test_value_summary_happy_path():
    df = pd.DataFrame({
        "academic_year": ["2020-21", "2020-21", "2024-25", "2024-25"],
        "race_description": ["A", "B", "A", "B"],
        "avg_units": [12.0, 10.0, 13.5, 9.0],
    })
    out = _value_summary(
        df,
        key_col="race_description",
        label_col="Race",
        order=["A", "B"],
        label_map={"A": "A", "B": "B"},
        years=["2020-21", "2024-25"],
        value_col="avg_units",
        value_name="Avg Units",
    )
    assert out.loc[0, "5-Yr Percent Change"] == pytest.approx((13.5 - 12.0) / 12.0)
    assert out.loc[1, "5-Yr Percent Change"] == pytest.approx((9.0 - 10.0) / 10.0)


def test_value_summary_first_val_zero_returns_nan_not_falsy_skip():
    """The bug we fixed: `if first_val and last_val is not None` treated
    first_val=0.0 as falsy, returning NaN — but the new explicit-None guard
    must still return NaN for legitimate zero (avoids divide-by-zero), while
    NOT returning NaN for a small non-zero first_val.
    """
    df = pd.DataFrame({
        "academic_year": ["2020-21", "2024-25"],
        "race_description": ["A", "A"],
        "avg_units": [0.0, 5.0],
    })
    out = _value_summary(
        df,
        key_col="race_description",
        label_col="Race",
        order=["A"],
        label_map={"A": "A"},
        years=["2020-21", "2024-25"],
        value_col="avg_units",
        value_name="Avg Units",
    )
    # Zero first_val -> NaN (avoid division by zero).
    assert pd.isna(out.loc[0, "5-Yr Percent Change"])


def test_value_summary_small_nonzero_first_val_still_computes():
    """Regression guard for the truthiness fix: 0.001 used to be allowed by
    `if first_val and ...`, but only because Python treats 0.001 as truthy.
    The explicit `!= 0` check must keep this case working."""
    df = pd.DataFrame({
        "academic_year": ["2020-21", "2024-25"],
        "race_description": ["A", "A"],
        "avg_units": [0.001, 0.002],
    })
    out = _value_summary(
        df,
        key_col="race_description",
        label_col="Race",
        order=["A"],
        label_map={"A": "A"},
        years=["2020-21", "2024-25"],
        value_col="avg_units",
        value_name="Avg Units",
    )
    assert out.loc[0, "5-Yr Percent Change"] == pytest.approx(1.0)


def test_value_summary_missing_first_year_value_returns_nan():
    df = pd.DataFrame({
        "academic_year": ["2024-25"],
        "race_description": ["A"],
        "avg_units": [13.0],
    })
    out = _value_summary(
        df,
        key_col="race_description",
        label_col="Race",
        order=["A"],
        label_map={"A": "A"},
        years=["2020-21", "2024-25"],
        value_col="avg_units",
        value_name="Avg Units",
    )
    assert pd.isna(out.loc[0, "5-Yr Percent Change"])
    assert pd.isna(out.loc[0, "2020-21 Avg Units"])


# ---------------------------------------------------------------------------
# _matrix_table
# ---------------------------------------------------------------------------

def test_matrix_table_pivots_to_year_columns():
    df = pd.DataFrame({
        "academic_year": ["2020-21", "2020-21", "2024-25"],
        "race_description": ["A", "B", "A"],
        "pct": [0.5, 0.3, 0.6],
    })
    out = _matrix_table(
        df,
        key_col="race_description",
        label_col="Race",
        order=["A", "B"],
        label_map={"A": "Apple", "B": "Banana"},
        years=["2020-21", "2024-25"],
        value_col="pct",
    )
    assert list(out.columns) == ["Race", "2020-21", "2024-25"]
    assert list(out["Race"]) == ["Apple", "Banana"]
    assert out.loc[0, "2024-25"] == 0.6
    # Banana has no row for 2024-25 → NaN, not KeyError.
    assert pd.isna(out.loc[1, "2024-25"])


def test_matrix_table_missing_key_in_data_yields_nan_row():
    df = pd.DataFrame({
        "academic_year": ["2024-25"],
        "race_description": ["A"],
        "pct": [0.4],
    })
    out = _matrix_table(
        df,
        key_col="race_description",
        label_col="Race",
        order=["A", "Z"],
        label_map={"A": "A", "Z": "Z"},
        years=["2024-25"],
        value_col="pct",
    )
    z_row = out[out["Race"] == "Z"].iloc[0]
    assert pd.isna(z_row["2024-25"])


# ---------------------------------------------------------------------------
# _rate_detail  — covers the reindex KeyError fix
# ---------------------------------------------------------------------------

def test_rate_detail_happy_path():
    df = pd.DataFrame({
        "academic_year": ["2024-25", "2024-25"],
        "race_description": ["A", "B"],
        "count": [10, 20],
        "total": [100, 200],
        "pct": [0.10, 0.10],
    })
    out = _rate_detail(
        df,
        key_col="race_description",
        label_col="Race",
        order=["A", "B"],
        label_map={"A": "Apple", "B": "Banana"},
    )
    assert list(out.columns) == [
        "Academic Year", "Race", "Numerator Count", "Denominator Count", "Percent",
    ]
    assert sorted(out["Race"].tolist()) == ["Apple", "Banana"]


def test_rate_detail_missing_source_column_uses_nan_not_keyerror():
    """Regression guard: with the [[...]] selector this raised KeyError.
    With reindex(columns=...) the missing column becomes NaN.
    """
    # No 'pct' column upstream — reindex must fill it as NaN.
    df = pd.DataFrame({
        "academic_year": ["2024-25"],
        "race_description": ["A"],
        "count": [10],
        "total": [100],
    })
    out = _rate_detail(
        df,
        key_col="race_description",
        label_col="Race",
        order=["A"],
        label_map={"A": "A"},
    )
    assert "Percent" in out.columns
    assert pd.isna(out.iloc[0]["Percent"])


def test_rate_detail_filters_to_keys_in_order():
    df = pd.DataFrame({
        "academic_year": ["2024-25", "2024-25", "2024-25"],
        "race_description": ["A", "B", "Z"],
        "count": [1, 2, 3],
        "total": [10, 20, 30],
        "pct": [0.1, 0.1, 0.1],
    })
    out = _rate_detail(
        df,
        key_col="race_description",
        label_col="Race",
        order=["A", "B"],
        label_map={"A": "A", "B": "B"},
    )
    assert "Z" not in out["Race"].tolist()
    assert sorted(out["Race"].tolist()) == ["A", "B"]
