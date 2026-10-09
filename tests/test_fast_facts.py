"""Tests for the Fast Facts student term filter.

The filter narrows an already-loaded academic year to the terms a user ticks,
so a districtwide Fall snapshot is credit Fall + NOCE Fall together. The two
silent ways it can go wrong are pinned here: a headcount that double-counts a
student enrolled in both tracks, and a credit-only percentage that reads 0.00
when no credit term is selected at all.
"""

import fitz
import pandas as pd
import pytest

from src.scripts.tabs.fast_facts import (
    _generate_pdf,
    _process,
    _student_scope,
    _term_label,
)


# Year rule checked against the Banner term calendar (stvterm start dates):
# 05/10/15 start in the code's own year; 20/25/30/35 start in the next one.
@pytest.mark.parametrize(
    ("code", "want"),
    [
        ("202605", "202605 · Summer 2026 (NOCE)"),
        ("202610", "202610 · Fall 2026 (Credit)"),
        ("202615", "202615 · Fall 2026 (NOCE)"),
        ("202520", "202520 · Spring 2026 (Credit)"),
        ("201825", "201825 · Winter 2019 (NOCE)"),
        ("202430", "202430 · Summer 2025 (Credit)"),
        ("202535", "202535 · Spring 2026 (NOCE)"),
    ],
)
def test_term_label(code, want):
    assert _term_label(code) == want


def test_term_label_unknown_suffix_shows_raw_code():
    """No calendar evidence for '40', so no guessed season or year."""
    assert _term_label("202640") == "202640"


def _stu(rows):
    cols = ["pidm", "term_code", "camp_code", "site"]
    df = pd.DataFrame(rows, columns=cols)
    df["acyr_code"] = "2026"
    df["academic_year"] = "2026-2027"
    df["crn"] = "10001"
    df["econ_disa_ind"] = "Y"
    df["first_gen_ind"] = "N"
    df["gender"] = "F"
    df["race_description"] = "Asian"
    df["age"] = 20.0
    return df


_EMP = pd.DataFrame({
    "pidm": [900],
    "ecls_desc": ["FT Faculty"],
    "gender": ["F"],
    "agegroup": ["35 to 39"],
    "ipeds_ethn": ["A"],
})

# pidm 1 takes a credit class and a NOCE class in Fall 2026; pidm 3 is
# Spring-only and must drop out of a Fall selection.
_FALL_AND_SPRING = _stu([
    (1, "202610", "1", "Credit"),
    (1, "202615", "3", "Noncredit"),
    (2, "202610", "2", "Credit"),
    (3, "202620", "1", "Credit"),
])


def test_scope_subset_keeps_only_selected_terms_and_labels_them():
    df, label = _student_scope(_FALL_AND_SPRING, ["202615", "202610"])
    assert sorted(df["term_code"].unique()) == ["202610", "202615"]
    assert label == "202610 + 202615"


def test_scope_all_terms_keeps_academic_year_label():
    df, label = _student_scope(_FALL_AND_SPRING, ["202610", "202615", "202620"])
    assert len(df) == 4
    assert label == "2026-2027"


def test_combined_fall_headcount_counts_cross_track_student_once():
    df, label = _student_scope(_FALL_AND_SPRING, ["202610", "202615"])
    out = {title: d for d, title in _process(df, _EMP, "2026", label)}

    total = out["202610 + 202615 Districtwide Headcount (Unduplicated)"]
    assert total["headcount"].tolist() == ["2"]
    assert total["enrollments"].tolist() == ["3"]

    campus = out["202610 + 202615 Campus Headcount (Unduplicated)"]
    assert dict(zip(campus["campus"], campus["headcount"])) == {
        "Cypress": "1", "Fullerton": "1", "NOCE": "1",
    }


def test_characteristics_not_applicable_without_a_credit_term():
    """Credit-only metric over a NOCE-only selection has no denominator."""
    df, label = _student_scope(_FALL_AND_SPRING, ["202615"])
    out = {title: d for d, title in _process(df, _EMP, "2026", label)}
    assert out["202615 Student Characteristics"]["pct"].tolist() == ["N/A", "N/A"]


def test_characteristics_percent_with_a_credit_term():
    df, label = _student_scope(_FALL_AND_SPRING, ["202610"])
    out = {title: d for d, title in _process(df, _EMP, "2026", label)}
    # Every fixture student is econ-disadvantaged and none are first-gen.
    assert out["202610 Student Characteristics"]["pct"].tolist() == ["100.00", "0.00"]


@pytest.mark.filterwarnings("error::pandas.errors.SettingWithCopyWarning")
def test_process_does_not_write_through_a_filtered_slice():
    """_process now reruns on every term change; a chained write would warn each time."""
    emp = pd.concat([_EMP, _EMP.assign(pidm=901, ecls_desc="Other")], ignore_index=True)
    df, label = _student_scope(_FALL_AND_SPRING, ["202610"])
    _process(df, emp, "2026", label)


def test_pdf_keeps_a_five_term_title_on_the_page():
    """Five ticked terms made the longest title run past both page edges."""
    label = "202530 + 202605 + 202610 + 202615 + 202620"
    pdf = _generate_pdf(_process(_FALL_AND_SPRING, _EMP, "2026", label))
    page = fitz.open(stream=pdf, filetype="pdf")[0]
    assert f"{label} Districtwide Headcount (Unduplicated)" in page.get_text()


def _title_sizes(pdf: bytes, needle: str) -> set[float]:
    page = fitz.open(stream=pdf, filetype="pdf")[0]
    return {
        round(span["size"], 1)
        for block in page.get_text("dict")["blocks"]
        for line in block.get("lines", [])
        for span in line["spans"]
        if needle in span["text"]
    }


def test_pdf_shrinks_only_titles_too_wide_for_the_page():
    short = _generate_pdf(_process(_FALL_AND_SPRING, _EMP, "2026", "2026-2027"))
    assert _title_sizes(short, "Districtwide Headcount") == {13.0}

    label = "202530 + 202605 + 202610 + 202615 + 202620"
    long = _generate_pdf(_process(_FALL_AND_SPRING, _EMP, "2026", label))
    (size,) = _title_sizes(long, "Districtwide Headcount")
    assert size < 13
