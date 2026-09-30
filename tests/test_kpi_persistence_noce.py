"""Tests for the NOCE-excluding-credit series on the Persistence tab.

`dwh.mv_noce_persistence_excl_credit` reports each NOCE fall cohort twice: its
unchanged columns reproduce the NOCE row of `mv_persistence_by_styp`, and its
`*_excl_credit` columns drop students who enroll at Cypress or Fullerton in
the follow-up term. The tab plots the second set as its own chart below NOCE.

The move is small — -0.1 to +0.3 points on every live cohort — so both NOCE
charts print one decimal; at whole percents the two charts read identically.

The numbers are the live MV rows (DWHDB, 2026-09-30).
"""

import io

import openpyxl
import pandas as pd
import plotly.graph_objects as go
import pytest
from openpyxl.cell.cell import Cell
from openpyxl.worksheet.worksheet import Worksheet
from pypdf import PdfReader

from src.pipeline.config import DATASETS, SQL_DIR
from src.scripts.tabs import kpi_persistence as kp
from src.scripts.tabs.kpi_persistence import (
    CAMPUSES,
    NOCE_EXCL_CREDIT,
    OVERALL_LABEL,
    _build_campus_fig,
    _build_excel_sections,
    _build_overall,
    _credit_exclusion_terms,
    _generate_excel,
    _generate_pdf,
    _load_noce_extract,
    _noce_diff_for_mode,
    _noce_diff_html,
    _noce_diff_table,
    _noce_excl_credit_note,
    _prepare_data,
    _prepare_noce_excl_credit,
    _prepare_noce_pair,
    _rate_label,
    _views_for_mode,
)

TODAY = pd.Timestamp("2026-09-30")
SPRING = "Fall → Spring"
NEXT_FALL = "Fall → Next Fall"

# Fall 2024 and Fall 2025, plus Fall 2026, whose follow-up terms have not
# started (the MV reports 0 for it).
MV_ROWS = pd.DataFrame({
    "mis_term_id": ["247", "257", "267"],
    "academic_term": ["2024-25 Fall", "2025-26 Fall", "2026-27 Fall"],
    "camp_code": ["3", "3", "3"],
    "styp_code": ["adult", "adult", "adult"],
    "spring_term_code": ["202435", "202535", "202635"],
    "next_fall_term_code": ["202515", "202615", "202715"],
    "curr_fall_p_count": [10399, 10443, 10413],
    "spring_total_headcount": [6724, 7011, 0],
    "next_fall_p_denominator": [10045, 10048, 10413],
    "next_fall_total_headcount": [4739, 4941, 0],
    "spring_p_count_excl_credit": [10185, 10235, 10413],
    "spring_headcount_excl_credit": [6610, 6888, 0],
    "next_fall_p_denominator_excl_credit": [9758, 9796, 10413],
    "next_fall_headcount_excl_credit": [4624, 4841, 0],
})

# The main extract's NOCE rows are the MV's unchanged columns.
MAIN_ROWS = MV_ROWS[[
    "mis_term_id", "camp_code", "styp_code", "spring_term_code",
    "next_fall_term_code", "curr_fall_p_count", "spring_total_headcount",
    "next_fall_p_denominator", "next_fall_total_headcount",
]]


# Fall 2022 → Spring 2023 prints 65.80% and 65.91%: a printed change of +0.11
# where the true difference is +0.104.
MV_2022 = pd.DataFrame({
    "mis_term_id": ["227"],
    "academic_term": ["2022-23 Fall"],
    "camp_code": ["3"],
    "styp_code": ["adult"],
    "spring_term_code": ["202235"],
    "next_fall_term_code": ["202315"],
    "curr_fall_p_count": [8881],
    "spring_total_headcount": [5844],
    "next_fall_p_denominator": [8621],
    "next_fall_total_headcount": [4109],
    "spring_p_count_excl_credit": [8732],
    "spring_headcount_excl_credit": [5755],
    "next_fall_p_denominator_excl_credit": [8424],
    "next_fall_headcount_excl_credit": [4031],
})

# Banner's end dates (stvterm, 2026-09-30). NOCE and credit terms of the same
# season end on different days; the credit ones are what the exclusion reads.
# The Fall 2025 cohort's next fall (202615 / 202610) is still running on TODAY.
CALENDAR = pd.DataFrame({
    "stvterm_code": ["202435", "202420", "202515", "202510",
                     "202535", "202520", "202615", "202610"],
    "stvterm_end_date": pd.to_datetime([
        "2025-05-23",   # NOCE Spring 2025
        "2025-05-31",   # credit Spring 2025
        "2025-12-19",   # NOCE Fall 2025
        "2025-12-13",   # credit Fall 2025
        "2026-05-21",   # NOCE Spring 2026
        "2026-05-30",   # credit Spring 2026
        "2026-12-17",   # NOCE Fall 2026
        "2026-12-12",   # credit Fall 2026
    ]),
})


def _combined(mv: pd.DataFrame = MV_ROWS) -> tuple[pd.DataFrame, pd.DataFrame]:
    main = mv[MAIN_ROWS.columns]
    types = pd.concat(
        [_prepare_data(main), _prepare_noce_excl_credit(mv)],
        ignore_index=True,
    )
    return types, _build_overall(types)


def _diff(mode: str, mv: pd.DataFrame = MV_ROWS, calendar=None) -> pd.DataFrame:
    table = _noce_diff_for_mode(_prepare_noce_pair(mv), mode, calendar, TODAY)
    assert table is not None
    return table


# The main extract a day behind the NOCE extract: one student more in the
# Fall 2024 cohort, and one more persisting (live, 2026-09-30).
DRIFTED_MAIN = MAIN_ROWS.assign(
    curr_fall_p_count=[10400, 10443, 10413],
    spring_total_headcount=[6725, 7011, 0],
)


def _overall_rate(overall, campus, term_short, rate_col):
    row = overall[(overall["campus"] == campus)
                  & (overall["term_short"] == term_short)]
    assert len(row) == 1, row
    return row.iloc[0][rate_col]


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def test_noce_extract_is_registered_on_the_persistence_terms():
    main = DATASETS["kpi_persistence"]
    cfg = DATASETS["kpi_persistence_noce"]
    assert (SQL_DIR / cfg["sql_file"]).is_file()
    assert cfg["param_name"] == "mis_term_id"
    assert cfg["db_section"] == "dwhdb"
    # One Query sends the same term selection to both extracts.
    assert cfg["mis_term_id"] == main["mis_term_id"]
    assert not cfg.get("skip_refresh")


# ---------------------------------------------------------------------------
# Data
# ---------------------------------------------------------------------------

def test_excl_credit_counts_stand_in_for_the_standard_columns():
    out = _prepare_noce_excl_credit(MV_ROWS)
    fall_2024 = out[out["term_short"] == "Fall 2024"].iloc[0]
    assert fall_2024["campus"] == NOCE_EXCL_CREDIT
    assert fall_2024["styp_label"] == "Adult"
    assert fall_2024["curr_fall_p_count"] == 10185
    assert fall_2024["spring_total_headcount"] == 6610
    assert fall_2024["next_fall_p_denominator"] == 9758
    assert fall_2024["next_fall_total_headcount"] == 4624
    assert fall_2024["spring_persistence_rate"] == pytest.approx(6610 / 10185)
    assert fall_2024["next_fall_persistence_rate"] == pytest.approx(4624 / 9758)
    # The NOCE follow-up terms ride along for the provisional check.
    assert fall_2024["spring_term_code"] == "202435"


def test_noce_and_excl_series_stay_apart_in_the_overall_line():
    _, overall = _combined()
    rate = "spring_persistence_rate"
    assert _overall_rate(overall, "NOCE", "Fall 2024", rate) == pytest.approx(
        6724 / 10399)
    assert _overall_rate(
        overall, NOCE_EXCL_CREDIT, "Fall 2024", rate,
    ) == pytest.approx(6610 / 10185)


def test_unstarted_cohort_is_dropped_from_both_noce_series():
    types, overall = _combined()
    _, view = _views_for_mode(types, overall, SPRING, None, TODAY)
    for campus in ("NOCE", NOCE_EXCL_CREDIT):
        terms = view.loc[view["campus"] == campus, "term_short"].tolist()
        assert terms == ["Fall 2024", "Fall 2025"], campus


# ---------------------------------------------------------------------------
# Loading: the new extract must never take the rest of the tab down
# ---------------------------------------------------------------------------

def test_loader_returns_the_prepared_series(monkeypatch):
    monkeypatch.setattr(kp, "fetch_kpi_persistence_noce", lambda _terms: MV_ROWS)
    df, error = _load_noce_extract(("247", "257", "267"))
    assert error is None
    assert df is not None
    assert set(df["campus"]) == {"NOCE", NOCE_EXCL_CREDIT}


def test_loader_reports_a_failed_download_instead_of_raising(monkeypatch):
    def unpublished(_terms):
        raise FileNotFoundError("kpi_persistence_noce not found on Tableau Cloud")

    monkeypatch.setattr(kp, "fetch_kpi_persistence_noce", unpublished)
    df, error = _load_noce_extract(("247",))
    assert df is None
    assert error is not None
    assert "FileNotFoundError" in error
    assert "python -m src.pipeline.run kpi_persistence_noce" in error


def test_loader_names_missing_columns(monkeypatch):
    stale = MV_ROWS.drop(columns=["next_fall_headcount_excl_credit"])
    monkeypatch.setattr(kp, "fetch_kpi_persistence_noce", lambda _terms: stale)
    df, error = _load_noce_extract(("247",))
    assert df is None
    assert error is not None
    assert "next_fall_headcount_excl_credit" in error


def test_loader_reports_an_empty_extract(monkeypatch):
    monkeypatch.setattr(
        kp, "fetch_kpi_persistence_noce", lambda _terms: MV_ROWS.iloc[0:0],
    )
    df, error = _load_noce_extract(("277",))
    assert df is None
    assert error is not None


# ---------------------------------------------------------------------------
# Display
# ---------------------------------------------------------------------------

def test_campus_order_puts_the_excl_chart_right_after_noce():
    assert CAMPUSES == ("Cypress", "Fullerton", "NOCE", NOCE_EXCL_CREDIT)


def test_both_noce_charts_print_one_decimal_and_the_colleges_whole():
    # Fall 2024 → Spring 2025: 64.66% for NOCE, 64.90% without credit students.
    # At whole percents both read "65%".
    assert _rate_label(6724 / 10399, "NOCE") == "64.7%"
    assert _rate_label(6610 / 10185, NOCE_EXCL_CREDIT) == "64.9%"
    assert _rate_label(6724 / 10399, "Cypress") == "65%"
    assert _rate_label(6724 / 10399, "Fullerton") == "65%"


@pytest.mark.parametrize("campus, label", [
    ("NOCE", "64.7%"),
    (NOCE_EXCL_CREDIT, "64.9%"),
])
def test_plotly_overall_labels_follow_the_campus_rule(campus, label):
    types, overall = _combined()
    types, overall = _views_for_mode(types, overall, SPRING, None, TODAY)
    fig = _build_campus_fig(types, overall, campus, SPRING)
    overall_trace = next(
        t for t in fig.data
        if isinstance(t, go.Scatter) and t.name == OVERALL_LABEL
    )
    assert overall_trace.text is not None
    assert label in list(overall_trace.text)


def test_note_names_the_follow_up_terms_each_rate_excludes():
    spring = _noce_excl_credit_note(SPRING)
    next_fall = _noce_excl_credit_note(NEXT_FALL)
    assert "Cypress or Fullerton" in spring
    assert "the following spring" in spring
    assert "next fall" not in spring
    assert "the following spring or the next fall" in next_fall


# ---------------------------------------------------------------------------
# Exports
# ---------------------------------------------------------------------------

def test_pdf_gives_the_excl_series_its_own_page_with_its_rule():
    types, overall = _combined()
    types, overall = _views_for_mode(types, overall, SPRING, None, TODAY)
    pdf = _generate_pdf(types, overall, SPRING, noce_diff=_diff(SPRING))
    pages = PdfReader(io.BytesIO(pdf)).pages
    assert len(pages) == 3   # NOCE, NOCE excl. credit, the difference table
    noce, excl = (page.extract_text() for page in pages[:2])
    assert "64.7%" in noce
    assert NOCE_EXCL_CREDIT in excl
    assert "64.9%" in excl
    assert "Cypress or Fullerton" in excl


def test_excel_lists_the_excl_series_after_noce():
    types, overall = _combined()
    sections = _build_excel_sections(types, overall)
    for section in sections[:2]:
        campuses = section.df["Campus"].drop_duplicates().tolist()
        assert campuses == ["NOCE", NOCE_EXCL_CREDIT], section.title
    first = sections[0].df
    row = first[(first["Campus"] == NOCE_EXCL_CREDIT)
                & (first["Term"] == "Fall 2024")].iloc[0]
    assert row["Fall P-Count (→Spring)"] == 10185
    assert row["Spring Headcount"] == 6610


# ---------------------------------------------------------------------------
# NOCE vs NOCE excl. credit: the difference table
# ---------------------------------------------------------------------------

def _row(table: pd.DataFrame, term_short: str) -> pd.Series:
    rows = table[table["term_short"] == term_short]
    assert len(rows) == 1, rows
    return rows.iloc[0]


def test_diff_table_compares_counts_and_rates_per_cohort():
    table = _diff(SPRING)
    # Same cohorts as the charts: Fall 2026 has no spring yet and is dropped.
    assert table["term_short"].tolist() == ["Fall 2024", "Fall 2025"]
    fall_2024 = _row(table, "Fall 2024")
    assert (fall_2024["p_noce"], fall_2024["p_excl"], fall_2024["p_change"]) == (
        10399, 10185, -214)
    assert (fall_2024["hc_noce"], fall_2024["hc_excl"], fall_2024["hc_change"]) == (
        6724, 6610, -114)
    assert fall_2024["rate_noce"] == pytest.approx(6724 / 10399)
    assert fall_2024["rate_excl"] == pytest.approx(6610 / 10185)
    assert fall_2024["rate_change"] == pytest.approx(0.24)


def test_diff_table_follows_the_persistence_type():
    fall_2024 = _row(_diff(NEXT_FALL), "Fall 2024")
    assert (fall_2024["p_noce"], fall_2024["p_excl"], fall_2024["p_change"]) == (
        10045, 9758, -287)
    assert (fall_2024["hc_noce"], fall_2024["hc_excl"], fall_2024["hc_change"]) == (
        4739, 4624, -115)
    assert fall_2024["rate_change"] == pytest.approx(0.21)


def test_rate_change_is_the_printed_difference():
    # 65.80% and 65.91% print a +0.11 change; the true difference, +0.104,
    # would print +0.10 and the row would not add up.
    fall_2022 = _row(_diff(SPRING, MV_2022), "Fall 2022")
    assert fall_2022["rate_change"] == pytest.approx(0.11)
    assert (fall_2022["rate_excl"] - fall_2022["rate_noce"]) * 100 == pytest.approx(
        0.104, abs=5e-4)


def test_diff_table_marks_a_provisional_cohort():
    table = _diff(NEXT_FALL, calendar=CALENDAR)
    assert _row(table, "Fall 2025")["is_provisional"]
    assert not _row(table, "Fall 2024")["is_provisional"]
    html = _noce_diff_html(table, NEXT_FALL)
    assert "Fall 2025 →Fall 2026 (provisional)" in html
    assert "Fall 2024 →Fall 2025 (provisional)" not in html


def test_diff_table_needs_both_noce_series():
    types = _prepare_data(MAIN_ROWS)
    _, view = _views_for_mode(types, _build_overall(types), SPRING, None, TODAY)
    assert _noce_diff_table(view, SPRING) is None


def test_diff_html_prints_the_row_that_adds_up():
    html = _noce_diff_html(_diff(SPRING), SPRING)
    for text in ("Fall 2024 →Spr 2025", "10,399", "10,185", "-214", "6,724",
                 "6,610", "-114", "64.66%", "64.90%", "+0.24", "Fall P-Count",
                 "Persisted", "Change (pts)"):
        assert text in html, text


def test_diff_html_uses_the_next_fall_count_label():
    html = _noce_diff_html(_diff(NEXT_FALL), NEXT_FALL)
    assert "Fall P-Count (less spring completers)" in html
    assert "-287" in html


def test_pdf_ends_with_the_difference_table_page():
    types, overall = _combined()
    types, overall = _views_for_mode(types, overall, SPRING, None, TODAY)
    pdf = _generate_pdf(types, overall, SPRING, noce_diff=_diff(SPRING))
    last = PdfReader(io.BytesIO(pdf)).pages[-1]
    text = last.extract_text()
    assert f"NOCE vs {NOCE_EXCL_CREDIT}" in text
    for value in ("10,399", "10,185", "-214", "64.66%", "64.90%", "+0.24"):
        assert value in text, value


def test_pdf_has_no_difference_page_without_the_excl_series():
    types = _prepare_data(MAIN_ROWS)
    types, overall = _views_for_mode(
        types, _build_overall(types), SPRING, None, TODAY)
    assert len(PdfReader(io.BytesIO(_generate_pdf(types, overall, SPRING))).pages) == 1


def test_excel_has_a_difference_section_per_persistence_type():
    types, overall = _combined()
    sections = _build_excel_sections(
        types, overall, noce_pair=_prepare_noce_pair(MV_ROWS))
    assert [s.title for s in sections[2:]] == [
        f"NOCE vs {NOCE_EXCL_CREDIT}: {SPRING}",
        f"NOCE vs {NOCE_EXCL_CREDIT}: {NEXT_FALL}",
    ]
    spring = sections[2].df
    assert list(spring.columns) == [
        "Fall Cohort",
        "Fall P-Count (→Spring): NOCE",
        "Fall P-Count (→Spring): Excl. Credit",
        "Fall P-Count (→Spring): Change",
        "Spring Headcount: NOCE",
        "Spring Headcount: Excl. Credit",
        "Spring Headcount: Change",
        "Fall → Spring Rate: NOCE",
        "Fall → Spring Rate: Excl. Credit",
        "Fall → Spring Rate: Change (pts)",
    ]
    fall_2024 = spring[spring["Fall Cohort"] == "Fall 2024"].iloc[0]
    assert fall_2024["Fall P-Count (→Spring): Change"] == -214
    assert fall_2024["Fall → Spring Rate: Change (pts)"] == pytest.approx(0.24)
    # Like the other sections, a cohort with no follow-up yet keeps its
    # counts and leaves its rates blank.
    fall_2026 = spring[spring["Fall Cohort"] == "Fall 2026"].iloc[0]
    assert fall_2026["Fall P-Count (→Spring): NOCE"] == 10413
    assert pd.isna(fall_2026["Fall → Spring Rate: NOCE"])
    assert pd.isna(fall_2026["Fall → Spring Rate: Change (pts)"])


def test_excel_has_no_difference_section_without_the_excl_series():
    types = _prepare_data(MAIN_ROWS)
    assert len(_build_excel_sections(types, _build_overall(types))) == 2


def test_excel_prints_difference_rates_to_two_decimals():
    types, overall = _combined()
    xlsx = _generate_excel(types, overall, noce_pair=_prepare_noce_pair(MV_ROWS))
    book = openpyxl.load_workbook(io.BytesIO(xlsx))
    sheet = book["chart_data"]
    assert isinstance(sheet, Worksheet)
    formats = {}
    for row in sheet.iter_rows():
        for cell in row:
            if isinstance(cell, Cell) and cell.value in (
                "Fall → Spring Rate: NOCE",
                "Fall → Spring Rate: Change (pts)",
                "Fall P-Count (→Spring): Change",
            ):
                formats[cell.value] = cell.offset(row=1).number_format
    assert formats == {
        "Fall → Spring Rate: NOCE": "0.00%",
        "Fall → Spring Rate: Change (pts)": "+0.00;-0.00;0",
        "Fall P-Count (→Spring): Change": "+#,##0;-#,##0;0",
    }


def test_pair_holds_both_noce_series_from_the_noce_extract():
    pair = _prepare_noce_pair(MV_ROWS)
    fall_2024 = pair[pair["term_short"] == "Fall 2024"].set_index("campus")
    assert fall_2024.loc["NOCE", "curr_fall_p_count"] == 10399
    assert fall_2024.loc[NOCE_EXCL_CREDIT, "curr_fall_p_count"] == 10185


def test_difference_ignores_a_main_extract_from_another_refresh():
    """The change must be the credit exclusion alone.

    On 2026-09-30 the main extract was a day behind the NOCE extract, one
    student off in Fall 2024. Taking NOCE from it printed -215 / -115; the
    exclusion itself is -214 / -114.
    """
    types = pd.concat(
        [_prepare_data(DRIFTED_MAIN), _prepare_noce_excl_credit(MV_ROWS)],
        ignore_index=True,
    )
    overall = _build_overall(types)
    sections = _build_excel_sections(
        types, overall, noce_pair=_prepare_noce_pair(MV_ROWS))
    chart = sections[0].df
    assert chart.loc[(chart["Campus"] == "NOCE") & (chart["Term"] == "Fall 2024"),
                     "Fall P-Count (→Spring)"].item() == 10400
    spring = sections[2].df
    diff = spring[spring["Fall Cohort"] == "Fall 2024"].iloc[0]
    assert diff["Fall P-Count (→Spring): NOCE"] == 10399
    assert diff["Fall P-Count (→Spring): Change"] == -214
    assert diff["Spring Headcount: Change"] == -114


def test_difference_note_says_where_noce_comes_from():
    assert "same extract" in kp._NOCE_DIFF_NOTE


# ---------------------------------------------------------------------------
# Provisional: the excluded series also waits on the credit terms it reads
# ---------------------------------------------------------------------------

# Between NOCE Spring 2026's end (May 21) and credit Spring 2026's (May 30).
MAY_25 = pd.Timestamp("2026-05-25")


def _flag(view: pd.DataFrame, campus: str, term_short: str) -> bool:
    rows = view[(view["campus"] == campus) & (view["term_short"] == term_short)]
    assert len(rows) == 1, rows
    return bool(rows.iloc[0]["is_provisional"])


def test_credit_exclusion_terms_follow_the_mv():
    # The MV: credit spring = credit fall + 10, credit next fall = + 100.
    # Fall 2025 (mis 257, credit fall 202510) -> 202520, 202610.
    assert _credit_exclusion_terms(257, SPRING) == ["202520"]
    assert _credit_exclusion_terms(257, NEXT_FALL) == ["202520", "202610"]


def test_excl_point_stays_provisional_until_the_credit_spring_ends():
    """On May 25 NOCE's spring is over but the credit spring is not.

    A late credit registration could still move a student out of the Fall
    2025 cohort, so the excluded point is still partial; plain NOCE is final.
    """
    types, overall = _combined()
    _, view = _views_for_mode(types, overall, SPRING, CALENDAR, MAY_25)
    assert not _flag(view, "NOCE", "Fall 2025")
    assert _flag(view, NOCE_EXCL_CREDIT, "Fall 2025")
    assert not _flag(view, NOCE_EXCL_CREDIT, "Fall 2024")

    _, view = _views_for_mode(
        types, overall, SPRING, CALENDAR, pd.Timestamp("2026-05-31"))
    assert not _flag(view, NOCE_EXCL_CREDIT, "Fall 2025")


def test_next_fall_excl_point_waits_for_every_term_it_reads():
    types, overall = _combined()
    # Credit Fall 2026 ends Dec 12, NOCE Fall 2026 Dec 17: NOCE decides.
    _, view = _views_for_mode(
        types, overall, NEXT_FALL, CALENDAR, pd.Timestamp("2026-12-15"))
    assert _flag(view, NOCE_EXCL_CREDIT, "Fall 2025")
    _, view = _views_for_mode(
        types, overall, NEXT_FALL, CALENDAR, pd.Timestamp("2026-12-18"))
    assert not _flag(view, NOCE_EXCL_CREDIT, "Fall 2025")


def test_missing_credit_term_keeps_the_excl_point_provisional():
    no_credit_spring = CALENDAR[CALENDAR["stvterm_code"] != "202520"]
    types, overall = _combined()
    _, view = _views_for_mode(
        types, overall, SPRING, no_credit_spring, pd.Timestamp("2026-09-30"))
    assert _flag(view, NOCE_EXCL_CREDIT, "Fall 2025")
    assert not _flag(view, "NOCE", "Fall 2025")


def test_difference_row_is_provisional_while_the_credit_spring_runs():
    table = _noce_diff_for_mode(_prepare_noce_pair(MV_ROWS), SPRING, CALENDAR, MAY_25)
    assert table is not None
    assert _row(table, "Fall 2025")["is_provisional"]
    assert not _row(table, "Fall 2024")["is_provisional"]
