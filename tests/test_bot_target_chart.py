"""The Actual vs Target chart and its PDF page (spec §7, §8)."""

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
)

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
    "target_title": "Associate Degrees: Progress Toward 2029-30 Target",
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
    assert (actual["name"], target["name"]) == ("Actual", "Target")
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
    assert "Progress Toward 2029-30 Target" in text
    assert "2022-23 to 2029-30" in text
