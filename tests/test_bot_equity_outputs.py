"""The equity table as the tabs build, draw and export it
(spec docs/superpowers/specs/2026-09-28-bot-equity-tables-design.md).

2025-26 is k=3 years after the 2022-23 baseline: growth factor 1 + 0.3*3/7.
"""

import io

import pandas as pd
import pytest
from pypdf import PdfReader

from src.scripts.tabs import bot_goal3_units
from src.scripts.tabs.bot_equity import (
    COLUMNS,
    FIRSTGEN_CATEGORY,
    GENDER_CATEGORY,
    ON_TRACK,
    PROGRESSING,
    RACE_CATEGORY,
    EquityTable,
    equity_html,
)
from src.scripts.tabs.bot_excel_helpers import (
    equity_excel_section,
    standard_bot_excel_sections,
)
from src.scripts.tabs.bot_helpers import equity_table, generate_bot_pdf
from src.scripts.tabs.bot_targets import Targets

GROWTH = {"growth": 0.30}
UNITS = {"growth": 0.20, "reduce_over": 60, "value_col": "sum_hours_earned"}
F3 = 1 + 0.3 * 3 / 7

TITLES = {
    "tab_title": "BOT Goal 2 - Associate Degrees",
    "target_title": "Associate Degrees: Progress Toward 2029-30 Benchmark",
    "org": "NOCCCD Credit Colleges",
    "headcount_title": "HC", "headcount_caption": "c",
    "race_title": "Race", "race_caption": "c",
    "gender_title": "Gender", "gender_caption": "c",
    "firstgen_title": "FG", "firstgen_caption": "c",
}


def _frame(groups):
    """groups: {(race, gender, first_gen_ind, site): {year: students}} -> student rows."""
    rows, pidm = [], 0
    for (race, gender, fg, site), by_year in groups.items():
        for year, n in by_year.items():
            for _ in range(n):
                rows.append({
                    "pidm": pidm, "academic_year": year, "acyr_code": year[:4],
                    "camp_desc": "NOCE" if site == "Noncredit" else "Cypress",
                    "site": site, "race_description": race, "gender": gender,
                    "first_gen_ind": fg, "sum_hours_earned": 80.0,
                })
                pidm += 1
    return pd.DataFrame(rows)


# Female = Hispanic + Black (110 -> 130); Male = Asian + Filipino + White (85 -> 79);
# first-gen Y = Hispanic + Filipino (105 -> 140); N = Asian + Black + White (90 -> 69).
DISTRICT = {
    ("Hispanic or Latino", "F", "Y", "Credit"): {"2022-2023": 100, "2025-2026": 120},
    ("Asian", "M", "N", "Credit"): {"2022-2023": 50, "2025-2026": 50},
    ("Black or African American", "F", "N", "Credit"): {"2022-2023": 10, "2025-2026": 10},
    ("Filipino", "M", "Y", "Credit"): {"2022-2023": 5, "2025-2026": 20},
    ("White Non-Hispanic", "M", "N", "Credit"): {"2022-2023": 30, "2025-2026": 9},
}


def _district_targets():
    df = _frame(DISTRICT)
    return df, Targets(frame=df, rule=GROWTH)


def test_count_tab_rows_in_tab_order_and_labels():
    _, targets = _district_targets()
    t = equity_table(targets, TITLES)
    assert t is not None
    assert list(zip(t.rows["category"], t.rows["group"])) == [
        (RACE_CATEGORY, "Latino/Hispanic"),
        (RACE_CATEGORY, "Asian"),
        (RACE_CATEGORY, "Black or African American"),   # exactly 10 in both years
        (GENDER_CATEGORY, "Female"),
        (GENDER_CATEGORY, "Male"),
        (FIRSTGEN_CATEGORY, "First Generation Student"),
        (FIRSTGEN_CATEGORY, "Not First Generation Student"),
    ]
    rows = t.rows.set_index("group")
    assert rows.loc["Female", "baseline"] == 110
    assert rows.loc["Male", "actual"] == 79
    assert rows.loc["Male", "status"] == PROGRESSING    # 79 vs 85 * F3 = 95.9


def test_no_table_without_targets_or_on_headcount_only_tabs():
    _, targets = _district_targets()
    assert equity_table(None, TITLES) is None
    assert equity_table(targets, dict(TITLES, headcount_only=True)) is None


def test_first_gen_follows_the_tabs_credit_only_setting():
    df = _frame({
        ("Asian", "F", "Y", "Noncredit"): {"2022-2023": 20, "2025-2026": 30},
        ("Asian", "F", "N", "Credit"): {"2022-2023": 20, "2025-2026": 30},
    })
    targets = Targets(frame=df, rule=GROWTH)

    def first_gen(t):
        return list(t.rows.loc[t.rows["category"] == FIRSTGEN_CATEGORY, "group"])

    assert first_gen(equity_table(targets, TITLES)) == ["Not First Generation Student"]
    assert first_gen(equity_table(targets, dict(TITLES, credit_only_firstgen=False))) == [
        "First Generation Student", "Not First Generation Student",
    ]


def test_benchmark_matches_the_summary_counts_column():
    df, targets = _district_targets()
    sections = standard_bot_excel_sections(df, TITLES, base_df=df, targets=targets)
    summary = next(s for s in sections if s.title == "Race - Summary Counts").df
    expected = dict(zip(summary["Race/Ethnicity"], summary["2025-2026 Benchmark"]))
    t = equity_table(targets, TITLES)
    assert t is not None
    rows = t.rows.set_index("group")
    for group in ("Latino/Hispanic", "Asian"):
        assert rows.loc[group, "benchmark"] == pytest.approx(expected[group])


def test_excel_equity_section_follows_the_actual_vs_benchmark_table():
    df, targets = _district_targets()
    sections = standard_bot_excel_sections(df, TITLES, base_df=df, targets=targets)
    assert sections[0].title == TITLES["target_title"]
    eq = sections[1]
    assert eq.title == "Equity Results, 2025-26"
    assert list(eq.df.columns) == [
        "Category", "Student Population", "2022-23 Baseline", "2025-26 Benchmark",
        "2025-26 Actual", "Variance", "Status",
    ]
    assert eq.integer_cols == (
        "2022-23 Baseline", "2025-26 Benchmark", "2025-26 Actual", "Variance",
    )
    by_pop = eq.df.set_index("Student Population")
    assert by_pop.loc["Asian", "2025-26 Benchmark"] == pytest.approx(50 * F3)   # unrounded; Excel formats it
    assert by_pop.loc["Asian", "Status"] == PROGRESSING


def test_no_equity_section_on_headcount_only_tabs_or_without_targets():
    df, targets = _district_targets()
    titles = dict(TITLES, headcount_only=True, include_nocccd=False)
    for sections in (standard_bot_excel_sections(df, titles, targets=targets),
                     standard_bot_excel_sections(df, TITLES, base_df=df)):
        assert not any(s.title.startswith("Equity Results") for s in sections)


# ---------------------------------------------------------------------------
# PDF page 1
# ---------------------------------------------------------------------------


def _pdf_pages(pdf: bytes):
    return PdfReader(io.BytesIO(pdf)).pages


def test_pdf_page_one_carries_the_equity_table():
    df, targets = _district_targets()
    pages = _pdf_pages(generate_bot_pdf(df, TITLES, base_df=df, targets=targets))
    assert len(pages) == 3                      # unchanged: the table uses page 1's free half
    text = pages[0].extract_text()
    assert "Equity Results, 2025-26" in text
    assert "On Track" in text and "Progressing" in text
    assert "Variance = Actual" in text
    assert "Target" not in text


def test_headcount_only_pdf_has_no_equity_table():
    df, targets = _district_targets()
    titles = dict(TITLES, headcount_only=True, include_nocccd=False)
    pages = _pdf_pages(generate_bot_pdf(df, titles, targets=targets))
    assert len(pages) == 2
    assert "Equity Results" not in pages[0].extract_text()


def test_equity_ignores_the_sidebar_year_selection():
    df, targets = _district_targets()
    shown = df[df["academic_year"] == "2022-2023"]          # sidebar narrowed to one year
    pages = _pdf_pages(generate_bot_pdf(shown, TITLES, base_df=shown, targets=targets))
    assert "Equity Results, 2025-26" in pages[0].extract_text()


# ---------------------------------------------------------------------------
# Streamlit tab
# ---------------------------------------------------------------------------


def test_html_has_bands_status_cells_and_both_themes():
    _, targets = _district_targets()
    t = equity_table(targets, TITLES)
    assert t is not None
    html = equity_html(t)
    for band in (RACE_CATEGORY, GENDER_CATEGORY, FIRSTGEN_CATEGORY):
        assert f">{band}</td>" in html
    # On Track: Latino/Hispanic, Female, First Gen. Progressing: Asian, Black, Male, Not First Gen.
    assert html.count(">On Track</td>") == 3
    assert html.count(">Progressing</td>") == 4
    assert "2025-26<br>Benchmark" in html
    assert ">-6</td>" in html                     # Asian: 50 - 56.43
    assert "light-dark(#d6eaf8, #1d4f6e)" in html
    assert "Target" not in html


def test_tab_renders_heading_table_and_note(monkeypatch):
    from src.scripts.tabs import bot_helpers

    calls = []
    monkeypatch.setattr(bot_helpers.st, "markdown",
                        lambda body, **kwargs: calls.append(("markdown", body)))
    monkeypatch.setattr(bot_helpers.st, "caption",
                        lambda body, **kwargs: calls.append(("caption", body)))
    _, targets = _district_targets()
    t = equity_table(targets, TITLES)
    assert t is not None
    bot_helpers.render_equity_table(t)
    assert calls[0] == ("markdown", "**Equity Results, 2025-26**")
    assert calls[1][0] == "markdown" and calls[1][1].startswith("<table")
    assert calls[2] == ("caption", t.note)


# ---------------------------------------------------------------------------
# Average Units (lower is better)
# ---------------------------------------------------------------------------


def _units_frame(groups):
    """groups: {(race, gender, first_gen_ind): {year: (students, hours)}}."""
    rows, pidm = [], 0
    for (race, gender, fg), by_year in groups.items():
        for year, (n, hours) in by_year.items():
            for _ in range(n):
                rows.append({
                    "pidm": pidm, "academic_year": year, "acyr_code": year[:4],
                    "camp_desc": "Cypress", "site": "Credit",
                    "race_description": race, "gender": gender,
                    "first_gen_ind": fg, "sum_hours_earned": hours,
                })
                pidm += 1
    return pd.DataFrame(rows)


# Hispanic falls 90 -> 80 (below its 87.4 benchmark: On Track); Asian stays at 80
# (above 78.3: Progressing).
UNITS_DISTRICT = {
    ("Hispanic or Latino", "F", "Y"): {"2022-2023": (40, 90.0), "2025-2026": (40, 80.0)},
    ("Asian", "M", "N"): {"2022-2023": (40, 80.0), "2025-2026": (40, 80.0)},
}


def test_units_equity_uses_averages_and_lower_is_better():
    df = _units_frame(UNITS_DISTRICT)
    t = bot_goal3_units._equity_table(Targets(frame=df, rule=UNITS))
    assert t is not None and t.decimals
    rows = t.rows[t.rows["category"] == RACE_CATEGORY].set_index("group")
    assert rows.loc["Latino/Hispanic", "baseline"] == pytest.approx(90.0)
    assert rows.loc["Latino/Hispanic", "benchmark"] == pytest.approx(90 - 30 * 0.2 * 3 / 7)
    assert rows.loc["Latino/Hispanic", "status"] == ON_TRACK
    assert rows.loc["Asian", "status"] == PROGRESSING
    assert "On Track = at or below the benchmark." in t.note


def test_units_first_gen_aggregate_counts_students():
    agg = bot_goal3_units._aggregate_firstgen(_units_frame(UNITS_DISTRICT))
    by = agg.set_index(["academic_year", "fg"])["count"]
    assert by[("2022-2023", "Y")] == 40


def test_units_excel_and_pdf_carry_the_equity_table():
    df = _units_frame(UNITS_DISTRICT)
    targets = Targets(frame=df, rule=UNITS)
    sections = bot_goal3_units.units_excel_sections(df, targets=targets)
    assert sections[0].title == bot_goal3_units._TITLES["target_title"]
    assert sections[1].title == "Equity Results, 2025-26"
    assert sections[1].decimal_cols == (
        "2022-23 Baseline", "2025-26 Benchmark", "2025-26 Actual", "Variance",
    )
    pages = _pdf_pages(bot_goal3_units.generate_pdf(df, targets=targets))
    assert len(pages) == 3
    assert "Equity Results, 2025-26" in pages[0].extract_text()


def test_units_without_targets_has_no_equity_table():
    df = _units_frame(UNITS_DISTRICT)
    assert bot_goal3_units._equity_table(None) is None
    sections = bot_goal3_units.units_excel_sections(df)
    assert not any(s.title.startswith("Equity Results") for s in sections)


def test_excel_variance_matches_the_printed_row():
    # ADT Black or African American: baseline 35 -> benchmark exactly 39.5.
    # With an actual of 41 the PDF and tab print 40 | 41 | +1; Excel used to
    # store 1.5, which its #,##0 format shows as "2".
    counts_rows = pd.DataFrame([{
        "category": RACE_CATEGORY, "group": "Black or African American",
        "baseline": 35.0, "benchmark": 39.5, "actual": 41.0, "variance": 1.5,
        "status": ON_TRACK,
    }], columns=COLUMNS)
    counts = equity_excel_section(
        EquityTable(year="2025-2026", rows=counts_rows, decimals=False, note="n"))
    assert counts.df["Variance"].tolist() == [1]
    assert counts.df["2025-26 Benchmark"].tolist() == [39.5]   # still unrounded

    units_rows = pd.DataFrame([{
        "category": RACE_CATEGORY, "group": "Latino/Hispanic",
        "baseline": 82.39, "benchmark": 80.468, "actual": 80.323, "variance": -0.145,
        "status": ON_TRACK,
    }], columns=COLUMNS)
    units = equity_excel_section(
        EquityTable(year="2025-2026", rows=units_rows, decimals=True, note="n"))
    assert units.df["Variance"].tolist() == [pytest.approx(-0.2)]
