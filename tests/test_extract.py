"""Tests for src.pipeline.extract."""

import re

import pandas as pd

from src.pipeline.extract import _concat_query_frames


def test_in_clause_regex_handles_multiline_template():
    """The DOTALL fix: regex must replace IN (:t1, ...) even across newlines.

    Without re.DOTALL, `.*?` stops at the first newline and the substitution
    silently fails; Oracle then executes with only :t1 bound and returns a
    partial result with no error.
    """
    template = (
        "SELECT *\n"
        "FROM students\n"
        "WHERE acyr_code IN (\n"
        "    :t1,\n"
        "    :t2,\n"
        "    :t3\n"
        ")\n"
    )
    placeholders = ":t1, :t2, :t3"
    out = re.sub(
        r"IN\s*\(:t1.*?\)",
        f"IN ({placeholders})",
        template,
        flags=re.IGNORECASE | re.DOTALL,
    )
    assert ":t2" in out and ":t3" in out
    assert out.count(":t1") == 1


def test_in_clause_regex_single_line_unchanged():
    template = "SELECT * FROM x WHERE y IN (:t1)"
    out = re.sub(
        r"IN\s*\(:t1.*?\)",
        "IN (:t1, :t2)",
        template,
        flags=re.IGNORECASE | re.DOTALL,
    )
    assert out == "SELECT * FROM x WHERE y IN (:t1, :t2)"


def test_concat_query_frames_empty_list():
    assert _concat_query_frames([]).empty


def test_concat_query_frames_all_empty_frames():
    """When all frames are empty, returns an empty frame matching the first
    frame's schema (so downstream pantab.frame_to_hyper sees stable columns).
    """
    schema = pd.DataFrame({"acyr_code": pd.Series(dtype="object"),
                           "count": pd.Series(dtype="int64")})
    out = _concat_query_frames([schema, schema])
    assert out.empty
    assert list(out.columns) == ["acyr_code", "count"]


def test_concat_query_frames_concatenates_and_unions_columns():
    """Per-acyr frames may have different all-NaN columns dropped; the union
    of seen columns must be reinstated as NaN columns.
    """
    a = pd.DataFrame({"acyr_code": ["2023"], "count": [10]})
    b = pd.DataFrame({"acyr_code": ["2024"], "count": [20], "extra": [1.5]})
    out = _concat_query_frames([a, b])
    assert len(out) == 2
    assert set(out.columns) == {"acyr_code", "count", "extra"}
    # Row from frame `a` has NaN in "extra".
    assert pd.isna(out.loc[out["acyr_code"] == "2023", "extra"].iloc[0])
    assert out.loc[out["acyr_code"] == "2024", "extra"].iloc[0] == 1.5


def test_concat_query_frames_skips_empty_then_concatenates_rest():
    empty = pd.DataFrame({"acyr_code": pd.Series(dtype="object"),
                          "count": pd.Series(dtype="int64")})
    populated = pd.DataFrame({"acyr_code": ["2024"], "count": [5]})
    out = _concat_query_frames([empty, populated])
    assert len(out) == 1
    assert out.iloc[0]["count"] == 5
