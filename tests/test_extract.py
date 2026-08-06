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


# ---------------------------------------------------------------------------
# Unparameterized datasets — pulling a whole table must be an explicit opt-in
# ---------------------------------------------------------------------------

def _stray_bind(sql: str):
    """Mirror of the placeholder scan in `extract_dataset`.

    Kept in lockstep with the implementation; asserts on the regex rather than
    on Oracle, so it runs without a database.
    """
    body = re.sub(r"--[^\n]*", "", sql)
    body = re.sub(r"/\*.*?\*/", "", body, flags=re.DOTALL)
    body = re.sub(r"'[^']*'", "", body)
    m = re.search(r"(?<![\w:]):(\w+)", body)
    return m.group(1) if m else None


def test_stray_bind_detects_a_real_placeholder():
    """A SQL file that should have been parameterized must not run unfiltered."""
    assert _stray_bind("SELECT 1 FROM t WHERE x = :acyr_code") == "acyr_code"
    assert _stray_bind("SELECT 1 FROM t WHERE x IN (:t1)") == "t1"


def test_stray_bind_ignores_prose_in_comments():
    """`1:many` in a SQL header is not a bind placeholder."""
    assert _stray_bind("-- one MIS term is 1:many against stvterm\nSELECT 1") is None


def test_stray_bind_ignores_oracle_format_masks():
    """'HH24:MI:SS' inside a string literal would otherwise false-positive."""
    sql = "SELECT TO_CHAR(d, 'YYYY-MM-DD HH24:MI:SS') FROM t"
    assert _stray_bind(sql) is None


def test_stray_bind_ignores_block_comments():
    assert _stray_bind("/* ratio is 1:many */ SELECT 1 FROM t") is None


def test_missing_param_name_is_a_config_error_not_a_whole_table_pull():
    """Absence of `param_name` must fail, never imply "pull everything".

    A config entry copy-pasted from another dataset that loses its
    `param_name` line would otherwise ship every row of every term to the app
    with no error, which is exactly the unfiltered-data case the repo forbids.
    """
    from src.pipeline.config import DATASETS

    for name, cfg in DATASETS.items():
        has_param = "param_name" in cfg
        opted_in = cfg.get("unparameterized", False)
        assert has_param or opted_in, (
            f"dataset {name!r} has neither 'param_name' nor "
            "'unparameterized': True"
        )
        assert not (has_param and opted_in), (
            f"dataset {name!r} sets both 'param_name' and 'unparameterized'"
        )
