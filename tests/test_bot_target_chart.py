"""The Actual vs Benchmark chart and its PDF page (spec §7, §8)."""

import io
import math

import pandas as pd
from pypdf import PdfReader

from src.scripts.tabs import bot_goal3_units
from src.scripts.tabs.bot_helpers import generate_bot_pdf
from src.scripts.tabs.bot_targets import (
    Targets,
    build_target_chart,
    district_actual_vs_target,
    mpl_target_chart,
    plan_years,
)

GROWTH = {"growth": 0.30}
YEARS = ["2018-2019", "2021-2022", "2022-2023", "2023-2024", "2024-2025", "2025-2026"]


def _df():
    rows, pidm = [], 0
    for year in YEARS:
        for camp, race, gender, fg, n in (
            ("Cypress", "Hispanic or Latino", "F", "Y", 70),
            ("Fullerton", "Asian", "M", "N", 30),
        ):
            for _ in range(n):
                rows.append({
                    "pidm": pidm, "academic_year": year, "acyr_code": year[:4],
                    "camp_desc": camp, "site": "Credit",
                    "race_description": race, "gender": gender,
                    "first_gen_ind": fg, "sum_hours_earned": 85.0,
                })
                pidm += 1
    return pd.DataFrame(rows)


def _targets(df, rule=None):
    return Targets(frame=df[df["academic_year"] >= "2022-2023"],
                   rule=rule or {"growth": 0.30})


TITLES = {
    "tab_title": "BOT Goal 2 - Associate Degrees",
    "target_title": "Associate Degrees: Progress Toward 2029-30 Benchmark",
    "org": "NOCCCD Credit Colleges",
    "headcount_title": "HC", "headcount_caption": "c",
    "race_title": "R", "race_caption": "c",
    "gender_title": "G", "gender_caption": "c",
    "firstgen_title": "F", "firstgen_caption": "c",
}


def _pages(pdf_bytes: bytes) -> int:
    return len(PdfReader(io.BytesIO(pdf_bytes)).pages)


def test_plotly_chart_has_actual_and_target_over_the_plan():
    df = _df()
    fig = build_target_chart(district_actual_vs_target(_targets(df)), {"growth": 0.30})
    # Plain dicts: plotly's trace attributes are untyped for pyright.
    actual, target = fig.to_dict()["data"]
    assert (actual["name"], target["name"]) == ("Actual", "Benchmark")
    xs = list(target["x"])
    assert xs[0] == "2022-23 (Baseline)"
    assert xs[-1] == "2029-30"
    assert len(xs) == 8
    # Future years are gaps, never zeros.
    assert all(v is None or math.isnan(v) for v in list(actual["y"])[4:])
    assert target["line"]["dash"] == "dash"


def test_pdf_gains_a_first_page_only_with_targets():
    df = _df()
    assert _pages(generate_bot_pdf(df, TITLES, base_df=df)) == 2
    assert _pages(generate_bot_pdf(df, TITLES, base_df=df, targets=_targets(df))) == 3


def test_headcount_only_pdf_gets_two_pages_with_targets():
    df = _df()
    titles = dict(TITLES, headcount_only=True, include_nocccd=False)
    assert _pages(generate_bot_pdf(df, titles)) == 1
    assert _pages(generate_bot_pdf(df, titles, targets=_targets(df))) == 2


def test_units_pdf_gains_a_first_page():
    df = _df()
    rule = {"growth": 0.20, "reduce_over": 60, "value_col": "sum_hours_earned"}
    assert _pages(bot_goal3_units.generate_pdf(df)) == 2
    assert _pages(bot_goal3_units.generate_pdf(df, targets=_targets(df, rule))) == 3


def test_target_page_title_text_is_on_page_one():
    df = _df()
    pdf = generate_bot_pdf(df, TITLES, base_df=df, targets=_targets(df))
    text = PdfReader(io.BytesIO(pdf)).pages[0].extract_text()
    assert "Progress Toward 2029-30 Benchmark" in text
    assert "2022-23 to 2029-30" in text


# ---------------------------------------------------------------------------
# Manager revision (2026-09-28): dark-blue Actual line, every Benchmark point
# labelled, each label on the outside of the pair so the two never collide.
#
# Real Noncredit Certificates numbers through 2024-25 — baseline tie, 2023-24
# met by a wide margin, 2024-25 met by a hair (1,094 vs 1,090, the near-tie
# this layout exists for) — then a 2025-26 miss (1,120 vs 1,133; the real year
# was met) so both directions are pinned, and four benchmark-only years.
# ---------------------------------------------------------------------------

BENCH = [1004.0, 1047.0, 1090.0, 1133.0, 1176.0, 1219.0, 1262.0, 1305.0]
ACTUAL = [1004.0, 1182.0, 1094.0, 1120.0] + [math.nan] * 4


def _avt():
    return pd.DataFrame({"academic_year": plan_years(),
                         "actual": ACTUAL, "target": BENCH})


def test_actual_line_is_dark_blue():
    actual, _ = build_target_chart(_avt(), GROWTH).to_dict()["data"]
    assert actual["line"]["color"] == "#004062"
    assert actual["marker"]["color"] == "#004062"


def test_every_benchmark_point_is_labelled():
    _, bench = build_target_chart(_avt(), GROWTH).to_dict()["data"]
    assert list(bench["text"]) == [
        "1,004", "1,047", "1,090", "1,133", "1,176", "1,219", "1,262", "1,305",
    ]


def test_labels_sit_outside_the_pair():
    actual, bench = build_target_chart(_avt(), GROWTH).to_dict()["data"]
    a_pos, b_pos = list(actual["textposition"]), list(bench["textposition"])
    # Baseline tie: Actual below, Benchmark above (unchanged).
    assert (a_pos[0], b_pos[0]) == ("bottom center", "top center")
    # Met (Actual higher), by a lot or by 4: Actual on top, Benchmark under.
    assert (a_pos[1], b_pos[1]) == ("top center", "bottom center")
    assert (a_pos[2], b_pos[2]) == ("top center", "bottom center")
    # Missed (Benchmark higher): Benchmark on top, Actual underneath.
    assert (a_pos[3], b_pos[3]) == ("bottom center", "top center")
    # Benchmark-only years: above the line.
    assert b_pos[4:] == ["top center"] * 4


def test_pdf_chart_matches_the_screen():
    import matplotlib.pyplot as plt
    from matplotlib.text import Annotation

    fig = plt.figure()
    mpl_target_chart(fig, (0.1, 0.2, 0.8, 0.7), _avt(), GROWTH)
    ax = fig.axes[0]
    assert ax.lines[0].get_color() == "#004062"
    legend = ax.get_legend()
    assert legend is not None
    assert [t.get_text() for t in legend.get_texts()] == ["Actual", "Benchmark"]
    # (x, y, text, drawn above its point?) for every label on the chart.
    labels = [(a.xy[0], a.xy[1], a.get_text(), a.xyann[1] > 0)
              for a in ax.texts if isinstance(a, Annotation)]
    assert len(labels) == 12                               # 4 actual + 8 benchmark
    # Baseline tie: the same number once below (Actual), once above (Benchmark).
    assert sorted((text, up) for x, _, text, up in labels if x == 0) == [
        ("1,004", False), ("1,004", True),
    ]
    up = {(x, y): above for x, y, _, above in labels if x != 0}
    assert up[(1, 1182.0)] and not up[(1, 1047.0)]         # met
    assert up[(2, 1094.0)] and not up[(2, 1090.0)]         # met by a hair
    assert up[(3, 1133.0)] and not up[(3, 1120.0)]         # missed
    assert all(up[(x, BENCH[x])] for x in range(4, 8))     # benchmark only
    plt.close(fig)


def test_no_reader_facing_target_wording_in_the_figures():
    # Readers see "Benchmark"; the old word must not come back in a legend,
    # hover or label. (Lowercase "target" legendgroup ids are internal.)
    df = _df()
    fig = build_target_chart(district_actual_vs_target(_targets(df)), GROWTH)
    text = fig.to_json()
    assert text is not None
    assert "Target" not in text
