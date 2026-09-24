"""Per-campus Vision 2030 targets: every plan year in the campus Excel table,
and optional target ticks on the campus bar chart (Streamlit + PDF).

Synthetic district: every year 70 Cypress + 30 Fullerton students, except
2025-26 where Cypress drops to 60 (misses its target) -> baseline 70 / 30 / 100.
Growth factor for year k: 1 + 0.3*k/7.
"""

import io
import math

import pandas as pd
import pytest
from pypdf import PdfReader

from src.scripts.tabs import bot_goal3_units
from src.scripts.tabs.bot_excel_helpers import standard_bot_excel_sections
from src.scripts.tabs.bot_helpers import (
    aggregate_headcount,
    build_headcount_chart,
    campus_target_rows,
    generate_bot_pdf,
)
from src.scripts.tabs.bot_targets import Targets

YEARS = ["2018-2019", "2021-2022", "2022-2023", "2023-2024", "2024-2025", "2025-2026"]
GROWTH = {"growth": 0.30}
UNITS = {"growth": 0.20, "reduce_over": 60, "value_col": "sum_hours_earned"}
TITLES = {
    "tab_title": "T", "target_title": "AA: Progress Toward 2029-30 Target",
    "org": "NOCCCD Credit Colleges",
    "headcount_title": "HC", "headcount_caption": "c",
    "race_title": "Race", "race_caption": "c",
    "gender_title": "Gender", "gender_caption": "c",
    "firstgen_title": "FG", "firstgen_caption": "c",
}


def f(k):
    return 1 + 0.3 * k / 7


def _df():
    rows, pidm = [], 0
    for year in YEARS:
        cyp = 60 if year == "2025-2026" else 70
        for camp, race, gender, fg, n, hours in (
            ("Cypress", "Hispanic or Latino", "F", "Y", cyp, 80.0),
            ("Fullerton", "Asian", "M", "N", 30, 90.0),
        ):
            for _ in range(n):
                rows.append({
                    "pidm": pidm, "academic_year": year, "acyr_code": year[:4],
                    "camp_desc": camp, "site": "Credit",
                    "race_description": race, "gender": gender,
                    "first_gen_ind": fg, "sum_hours_earned": hours,
                })
                pidm += 1
    return pd.DataFrame(rows)


def _targets(df, rule=None):
    return Targets(frame=df[df["academic_year"] >= "2022-2023"], rule=rule or GROWTH)


def _hc(sections):
    return next(s for s in sections if s.title == "HC")


# ---------------------------------------------------------------------------
# Excel: campus table carries a Target column after every plan year
# ---------------------------------------------------------------------------

def test_campus_table_interleaves_a_target_after_every_plan_year():
    df = _df()
    sec = _hc(standard_bot_excel_sections(df, TITLES, base_df=df, targets=_targets(df)))
    assert list(sec.df.columns) == [
        "Campus", "2018-2019", "2021-2022",
        "2022-2023", "2022-2023 Target",
        "2023-2024", "2023-2024 Target",
        "2024-2025", "2024-2025 Target",
        "2025-2026", "2025-2026 Target",
        "5-Yr Percent Change",
    ]
    by = sec.df.set_index("Campus")
    assert by.loc["Cypress", "2022-2023 Target"] == 70
    assert by.loc["Cypress", "2023-2024 Target"] == pytest.approx(70 * f(1))
    assert by.loc["NOCCCD (Unduplicated)", "2024-2025 Target"] == pytest.approx(100 * f(2))
    # Every Target column is formatted as a whole number.
    for y in YEARS[2:]:
        assert f"{y} Target" in sec.integer_cols


def test_units_campus_table_interleaves_targets_with_decimals():
    df = _df()
    sections = bot_goal3_units.units_excel_sections(df, targets=_targets(df, UNITS))
    sec = next(s for s in sections if s.title == bot_goal3_units._TITLES["headcount_title"])
    cols = list(sec.df.columns)
    for y in YEARS[2:]:
        assert cols[cols.index(y) + 1] == f"{y} Target"
        assert f"{y} Target" in sec.decimal_cols
    assert "2021-2022 Target" not in cols
    base = (70 * 80 + 30 * 90) / 100
    by = dict(zip(sec.df["Campus"], sec.df["2023-2024 Target"]))
    assert by["NOCCCD (Unduplicated)"] == pytest.approx(base - (base - 60) * 0.2 / 7)


# ---------------------------------------------------------------------------
# Chart: tick rows, and the Plotly figure with / without ticks
# ---------------------------------------------------------------------------

def test_campus_target_rows_skip_the_baseline_year():
    df = _df()
    agg = aggregate_headcount(_targets(df).frame)
    rows = campus_target_rows(agg, value_col="headcount", rule=GROWTH)
    assert set(rows.columns) == {"camp_desc", "academic_year", "target"}
    assert "2022-2023" not in set(rows["academic_year"])
    got = rows.set_index(["camp_desc", "academic_year"])["target"]
    assert got[("Cypress", "2025-2026")] == pytest.approx(70 * f(3))


def _traces(fig) -> list[dict]:
    return fig.to_dict()["data"]


def test_chart_without_ticks_is_unchanged():
    agg = aggregate_headcount(_df())
    traces = _traces(build_headcount_chart(agg))
    assert [t["type"] for t in traces] == ["bar"] * 3
    assert all(t["textposition"] == "outside" for t in traces)


def test_chart_with_ticks_adds_tick_and_label_traces():
    df = _df()
    agg = aggregate_headcount(df)
    tgt = campus_target_rows(aggregate_headcount(_targets(df).frame),
                             value_col="headcount", rule=GROWTH)
    fig = build_headcount_chart(agg, df_tgt=tgt)
    ticks = [t for t in _traces(fig) if t.get("name") == "Target"]
    assert len(ticks) == 3                       # one per campus
    assert sum(bool(t.get("showlegend")) for t in ticks) == 1
    cyp = next(t for t in ticks if t["offsetgroup"] == "Cypress")
    years = list(cyp["x"])
    heights = list(cyp["y"])
    # No tick in the baseline year or before it.
    for y in ("2018-2019", "2021-2022", "2022-2023"):
        h = heights[years.index(y)]
        assert h is None or math.isnan(h)
    # Tick is centred on the target.
    i = years.index("2025-2026")
    assert cyp["base"][i] + heights[i] / 2 == pytest.approx(70 * f(3))
    assert fig.to_dict()["layout"]["scattermode"] == "group"


def test_actual_label_lifts_above_a_missed_target():
    df = _df()
    agg = aggregate_headcount(df)
    tgt = campus_target_rows(aggregate_headcount(_targets(df).frame),
                             value_col="headcount", rule=GROWTH)
    traces = _traces(build_headcount_chart(agg, df_tgt=tgt))
    # Bars no longer draw their own labels; a text trace per campus does.
    assert all(t["textposition"] == "none" for t in traces
               if t["type"] == "bar" and t.get("name") != "Target")
    labels = next(t for t in traces if t["type"] == "scatter"
                  and t["offsetgroup"] == "Cypress" and next(iter(t["text"])) == "70")
    years, ys = list(labels["x"]), list(labels["y"])
    assert ys[years.index("2025-2026")] > 70 * f(3)   # 60 vs 78.6 -> missed
    assert ys[years.index("2023-2024")] > 70 * f(1)   # 70 vs 73 -> missed too
    assert ys[years.index("2021-2022")] == 70          # no target -> on the bar


# ---------------------------------------------------------------------------
# PDF: toggle adds ticks without changing the page structure
# ---------------------------------------------------------------------------

def _pages(pdf_bytes):
    return len(PdfReader(io.BytesIO(pdf_bytes)).pages)


def test_pdf_builds_with_campus_ticks_on_and_off():
    df = _df()
    off = generate_bot_pdf(df, TITLES, base_df=df, targets=_targets(df))
    on = generate_bot_pdf(df, TITLES, base_df=df, targets=_targets(df),
                          show_campus_targets=True)
    assert _pages(off) == _pages(on) == 3
    assert off != on


def test_units_pdf_builds_with_campus_ticks():
    df = _df()
    on = bot_goal3_units.generate_pdf(df, targets=_targets(df, UNITS),
                                      show_campus_targets=True)
    assert _pages(on) == 3


def test_campus_ticks_need_targets():
    # Toggle on but no plan frame (e.g. a stale session) -> plain chart, no error.
    df = _df()
    assert _pages(generate_bot_pdf(df, TITLES, base_df=df,
                                   show_campus_targets=True)) == 2


# ---------------------------------------------------------------------------
# Review fixes: a tick only where its campus has a bar; a real 0 is labelled
# the same way on screen and in the PDF
# ---------------------------------------------------------------------------

def test_no_tick_where_the_campus_has_no_bar():
    df = _df()
    plan = _targets(df)                      # Fullerton has a 2022-23 baseline
    shown = df[~((df["camp_desc"] == "Fullerton")
                 & (df["academic_year"] == "2024-2025"))]
    tgt = campus_target_rows(aggregate_headcount(plan.frame),
                             value_col="headcount", rule=GROWTH)
    ticks = [t for t in _traces(build_headcount_chart(aggregate_headcount(shown),
                                                      df_tgt=tgt))
             if t.get("name") == "Target" and t["offsetgroup"] == "Fullerton"]
    assert len(ticks) == 1
    years, heights = list(ticks[0]["x"]), list(ticks[0]["y"])
    assert heights[years.index("2024-2025")] is None        # no bar -> no tick
    assert heights[years.index("2025-2026")] is not None    # bar -> tick


def test_pdf_labels_a_real_zero_but_not_missing_data():
    import matplotlib.pyplot as plt

    from src.scripts.tabs.bot_helpers import mpl_campus_bar_labels

    fig, ax = plt.subplots()
    mpl_campus_bar_labels(ax, [0, 1], [0.0, None], [None, None],
                          bar_w=0.8, peak=10.0, fmt=".1f")
    assert [t.get_text() for t in ax.texts] == ["0.0"]
    plt.close(fig)


def test_overlay_labels_follow_their_legend_entry():
    # Clicking a legend entry hides every trace in its legendgroup. The actual
    # labels must hide with their campus's bars, and the target numbers with
    # the Target ticks — otherwise hiding a series leaves its numbers floating.
    df = _df()
    tgt = campus_target_rows(aggregate_headcount(_targets(df).frame),
                             value_col="headcount", rule=GROWTH)
    traces = _traces(build_headcount_chart(aggregate_headcount(df), df_tgt=tgt))
    for t in traces:
        if t["type"] != "scatter":
            continue
        is_target_label = t["textfont"].get("color") is not None
        expected = "target" if is_target_label else t["offsetgroup"]
        assert t.get("legendgroup") == expected, t["offsetgroup"]
    bars = {t["name"]: t["legendgroup"] for t in traces
            if t["type"] == "bar" and t["name"] != "Target"}
    assert bars == {"Cypress": "Cypress", "Fullerton": "Fullerton",
                    "NOCCCD (Unduplicated)": "NOCCCD (Unduplicated)"}
