"""Shared chart builders and aggregation helpers for BOT (Board of Trustees) tabs.

Each BOT goal tab imports from this module and calls render_bot_charts()
with its own titles dict. This avoids duplicating ~600 lines per tab.
"""

import io
import textwrap

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from matplotlib import patheffects
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.patches import Rectangle

from src.pipeline.config import BOT_WINDOW_YEARS, DATASETS
from src.scripts.tabs.bot_targets import (
    Targets,
    build_target_chart,
    district_actual_vs_target,
    group_baselines,
    group_target,
    mpl_target_chart,
    plan_range_label,
    plan_years,
    target_caption,
)

# ---------------------------------------------------------------------------
# Constants — NOCCCD brand colors & category orders
# ---------------------------------------------------------------------------

COLOR_MAP = {
    "Cypress": "#50b913",
    "Fullerton": "#f99d40",
    "NOCE": "#004062",
    "NOCCCD (Unduplicated)": "#50b9c3",
}
CAMPUS_ORDER = ["Cypress", "Fullerton", "NOCE", "NOCCCD (Unduplicated)"]

RACE_ORDER = [
    "Hispanic or Latino",
    "Asian",
    "White Non-Hispanic",
    "Multiethnicity",
    "Black or African American",
    "Filipino",
    "American Indian or Alaska Native",
    "Pacific Islander or Native Hawaiian",
    "Unreported",
]
RACE_SHORT = {
    "Hispanic or Latino": "Latino/Hispanic",
    "Asian": "Asian",
    "White Non-Hispanic": "White",
    "Multiethnicity": "Multiethnic",
    "Black or African American": "Black or African American",
    "Filipino": "Filipino",
    "American Indian or Alaska Native": "Amer Indian/AK Native",
    "Pacific Islander or Native Hawaiian": "Pacific Islander/HI Native",
    "Unreported": "Unknown/Non-Respondent",
}
RACE_COLORS = {
    "Hispanic or Latino": "#50b9c3",
    "Asian": "#007a94",
    "White Non-Hispanic": "#0081b7",
    "Multiethnicity": "#5faed3",
    "Black or African American": "#f99d40",
    "Filipino": "#00b3a0",
    "American Indian or Alaska Native": "#007a94",
    "Pacific Islander or Native Hawaiian": "#575a5d",
    "Unreported": "#50b913",
}

GENDER_ORDER = ["F", "M", "NB", "N"]
GENDER_LABELS = {"F": "Female", "M": "Male", "NB": "Non-Binary", "N": "Unknown"}
GENDER_COLORS = {
    "Female": "#007a94",
    "Male": "#0081b7",
    "Non-Binary": "#50b9c3",
    "Unknown": "#f99d40",
}

FIRSTGEN_ORDER = ["Y", "N", "Unknown"]
FIRSTGEN_LABELS = {
    "Y": "First Generation Student",
    "N": "Not First Generation Student",
    "Unknown": "Unknown",
}
FIRSTGEN_COLORS = {
    "First Generation Student": "#007a94",
    "Not First Generation Student": "#50b9c3",
    "Unknown": "#f99d40",
}


# ---------------------------------------------------------------------------
# Aggregation helpers
# ---------------------------------------------------------------------------

def aggregate_headcount(
    df: pd.DataFrame, *, include_nocccd: bool = True,
) -> pd.DataFrame:
    """Distinct PIDM count per campus per academic year + NOCCCD unduplicated."""
    by_campus = (
        df.groupby(["academic_year", "camp_desc"])["pidm"]
        .nunique()
        .reset_index(name="headcount")
    )
    if include_nocccd:
        nocccd = (
            df.groupby("academic_year")["pidm"]
            .nunique()
            .reset_index(name="headcount")
        )
        nocccd["camp_desc"] = "NOCCCD (Unduplicated)"
        out = pd.concat([by_campus, nocccd], ignore_index=True)
    else:
        out = by_campus
    out["camp_desc"] = pd.Categorical(
        out["camp_desc"], categories=CAMPUS_ORDER, ordered=True,
    )
    return out.sort_values(["academic_year", "camp_desc"])


def compute_pct_change(df_agg: pd.DataFrame) -> pd.DataFrame:
    """5-year % change: (last - first) / first * 100 per campus."""
    rows: list[dict] = []
    window = window_years(df_agg["academic_year"].dropna().unique())
    for camp in CAMPUS_ORDER:
        grp = df_agg[df_agg["camp_desc"] == camp].sort_values("academic_year")
        grp = grp[grp["academic_year"].isin(window) & (grp["headcount"] > 0)]
        if len(grp) < 2:
            continue
        first = grp.iloc[0]["headcount"]
        last = grp.iloc[-1]["headcount"]
        if first == 0:
            continue
        rows.append({
            "camp_desc": camp,
            "pct_change": round((last - first) / first * 100, 1),
        })
    return pd.DataFrame(rows) if rows else pd.DataFrame()


def pct_change_axis_range(values) -> tuple[float, float]:
    """x-axis ``(lo, hi)`` for a horizontal "5-Yr % Change" bar chart.

    Two rules, shared by the Plotly and matplotlib builders:

    * The axis always spans zero — the bars grow from it, so an axis that
      starts at ``min - 5`` cuts every bar off at the left once all values
      exceed 5.
    * Each side is padded for the "outside" text label: proportional to the
      largest bar on that side, with an absolute floor. Multiplicative
      padding alone collapses for near-zero values — Goal 4's +0.2% bar got
      ``0.2 * 1.8 - 0.2 = 0.16`` units of room and its label was clipped.
    """
    vals = [float(v) for v in values if v is not None and pd.notna(v)]
    if not vals:
        return (-5.0, 5.0)
    lo_v, hi_v = min(vals), max(vals)
    lo, hi = min(lo_v, 0.0), max(hi_v, 0.0)
    extent = max(hi - lo, 2.0)
    floor = extent * 0.25
    left = max(abs(lo_v) * 0.8, floor) if lo_v < 0 else floor
    right = max(hi_v * 0.8, floor) if hi_v > 0 else floor
    return (lo - left, hi + right)


def year_header_fontsize(years) -> int:
    """Font size for the year headers of the PDF proportion tables.

    The data columns split a fixed strip, so they narrow as years are added.
    Five 9-character labels fit at 7pt bold; the reference year makes six,
    and at 7pt the last digit of each disappears under the next label.
    6pt matches the cell values beneath them.
    """
    return 7 if len(years) <= 5 else 6


def _label_start_year(label) -> int | None:
    """``"2021-2022"`` and the wage tab's shifted ``"2021-22"`` both -> 2021."""
    try:
        return int(str(label)[:4])
    except (TypeError, ValueError):
        return None


def _reference_start_years() -> frozenset[int]:
    """Start years that are reference-only on some BOT chart, from config.

    Every BOT dataset's ``ref_acyr_code`` is included as-is. The wage pair's
    ref is acyr 2017 and its tab shifts display labels +1 (so it renders as
    2018-19); including both the raw and shifted forms is harmless because a
    reference year is always strictly older than every window year, so
    over-excluding 2017 on a tab whose window starts at 2021 removes nothing.
    """
    starts: set[int] = set()
    for name, cfg in DATASETS.items():
        if not name.startswith("bot_"):
            continue
        for ref in cfg.get("ref_acyr_code", []):
            starts.add(int(ref))
            starts.add(int(ref) + 1)
    return frozenset(starts)


def window_years(years) -> list:
    """The rolling metrics window: the non-reference years in *years*, at
    most the latest ``BOT_WINDOW_YEARS`` of them.

    BOT extracts may carry an older reference year (2018-19) ahead of the
    rolling window. Charts render every year, but the summary table's
    first/last columns, the "5-Yr % Change", and small-n suppression must
    only ever see the window — otherwise a 5-year label silently reports a
    7-year change. Every first/last derivation goes through here.

    Reference years are excluded EXPLICITLY, from ``ref_acyr_code`` in
    config — never inferred from position. Inferring "the last N present"
    or "N consecutive years ending at the latest" both let the reference
    year slide into the window whenever a window year is absent: a late
    SCFF wage file, or a user narrowing the sidebar to 2021-22 alone.
    """
    refs = _reference_start_years()
    labelled = sorted(
        (start, str(y)) for y in set(years)
        if (start := _label_start_year(y)) is not None and start not in refs
    )
    return [label for _, label in labelled[-BOT_WINDOW_YEARS:]]


def window_bounds(years) -> tuple:
    """``(first, last)`` of the metrics window, or ``(None, None)``."""
    w = window_years(years)
    return (w[0], w[-1]) if w else (None, None)


# Categories whose window first-year OR last-year count falls below this
# threshold are suppressed from proportion charts and summary tables
# (both boundary years must be >= threshold for the category to show).
CATEGORY_MIN_COUNT = 10
# Legacy alias kept for backward compatibility
RACE_MIN_COUNT = CATEGORY_MIN_COUNT


def _visible_categories(df, key_col, order,
                        threshold: int = CATEGORY_MIN_COUNT) -> list:
    """Return *order* filtered to categories where BOTH boundary years'
    counts are >= threshold.

    A category is hidden when EITHER the first or the last year's count
    is below the threshold (because the 5-yr % change in the summary
    table is computed from those two values and would be unreliable if
    either side is a small sample). Middle years are ignored by this
    rule.
    """
    if df is None or df.empty or "count" not in df.columns:
        return list(order)
    years = window_years(df["academic_year"].dropna().unique())
    if len(years) < 2:
        # Judge only the window year(s) actually on screen — the frame
        # may still carry the reference year, whose larger historical
        # count must not lift a sub-threshold group past suppression.
        in_window = df[df["academic_year"].isin(years)]
        max_by_cat = in_window.groupby(key_col)["count"].max()
        return [c for c in order if max_by_cat.get(c, 0) >= threshold]
    first_yr, last_yr = years[0], years[-1]
    first_counts = (
        df[df["academic_year"] == first_yr]
        .set_index(key_col)["count"]
    )
    last_counts = (
        df[df["academic_year"] == last_yr]
        .set_index(key_col)["count"]
    )

    def _keep(c):
        fc = first_counts.get(c, 0) or 0
        lc = last_counts.get(c, 0) or 0
        return fc >= threshold and lc >= threshold

    return [c for c in order if _keep(c)]


def _visible_races(df_race: pd.DataFrame,
                   threshold: int = CATEGORY_MIN_COUNT) -> list[str]:
    return _visible_categories(df_race, "race_description", RACE_ORDER,
                               threshold)


def _visible_genders(df_gender: pd.DataFrame,
                     threshold: int = CATEGORY_MIN_COUNT) -> list[str]:
    return _visible_categories(df_gender, "gender", GENDER_ORDER, threshold)


# Retained public aliases — no current in-repo caller (bot_excel_helpers.py
# imports the underscore-prefixed _visible_races/_visible_genders directly).
# Kept in case an external/future consumer wants the non-underscore name.
visible_races = _visible_races
visible_genders = _visible_genders


def aggregate_race(
    df: pd.DataFrame, base_df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Unduplicated PIDM count by race/ethnicity by academic year.

    When *base_df* is provided the percentage is computed as
    count(df) / count(base_df) per race per year (rate metric).
    """
    stu = df.drop_duplicates(subset=["pidm", "academic_year"])
    by_race = (
        stu.groupby(["academic_year", "race_description"])
        .size()
        .reset_index(name="count")
    )
    if base_df is not None:
        base_stu = base_df.drop_duplicates(subset=["pidm", "academic_year"])
        totals = (
            base_stu.groupby(["academic_year", "race_description"])
            .size()
            .reset_index(name="total")
        )
        out = by_race.merge(totals, on=["academic_year", "race_description"], how="left")
    else:
        totals = stu.groupby("academic_year").size().reset_index(name="total")
        out = by_race.merge(totals, on="academic_year")
    out["total"] = out["total"].fillna(0)
    out["pct"] = out["count"] / out["total"].replace(0, float("nan"))
    return out


def aggregate_gender(
    df: pd.DataFrame, base_df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Unduplicated PIDM count by gender by academic year.

    When *base_df* is provided the percentage is computed as
    count(df) / count(base_df) per gender per year (rate metric).
    """
    stu = df.drop_duplicates(subset=["pidm", "academic_year"])
    by_gender = (
        stu.groupby(["academic_year", "gender"])
        .size()
        .reset_index(name="count")
    )
    if base_df is not None:
        base_stu = base_df.drop_duplicates(subset=["pidm", "academic_year"])
        totals = (
            base_stu.groupby(["academic_year", "gender"])
            .size()
            .reset_index(name="total")
        )
        out = by_gender.merge(totals, on=["academic_year", "gender"], how="left")
    else:
        totals = stu.groupby("academic_year").size().reset_index(name="total")
        out = by_gender.merge(totals, on="academic_year")
    out["total"] = out["total"].fillna(0)
    out["pct"] = out["count"] / out["total"].replace(0, float("nan"))
    out["gender_label"] = out["gender"].map(GENDER_LABELS)
    return out


def aggregate_firstgen(
    df: pd.DataFrame, *, credit_only: bool = True,
    base_df: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Unduplicated PIDM count by first-gen status (credit-only by default).

    When *base_df* is provided the percentage is computed as
    count(df) / count(base_df) per first-gen status per year.
    """
    subset = df[df["site"] == "Credit"].copy() if credit_only else df.copy()
    stu = subset.drop_duplicates(subset=["pidm", "academic_year"]).copy()
    stu["fg"] = stu["first_gen_ind"].where(
        stu["first_gen_ind"].isin(["Y", "N"]), "Unknown",
    )
    by_fg = (
        stu.groupby(["academic_year", "fg"])
        .size()
        .reset_index(name="count")
    )
    if base_df is not None:
        base_subset = base_df[base_df["site"] == "Credit"].copy() if credit_only else base_df.copy()
        base_stu = base_subset.drop_duplicates(
            subset=["pidm", "academic_year"],
        ).copy()
        base_stu["fg"] = base_stu["first_gen_ind"].where(
            base_stu["first_gen_ind"].isin(["Y", "N"]), "Unknown",
        )
        totals = (
            base_stu.groupby(["academic_year", "fg"])
            .size()
            .reset_index(name="total")
        )
        out = by_fg.merge(totals, on=["academic_year", "fg"], how="left")
    else:
        totals = stu.groupby("academic_year").size().reset_index(name="total")
        out = by_fg.merge(totals, on="academic_year")
    out["total"] = out["total"].fillna(0)
    out["pct"] = out["count"] / out["total"].replace(0, float("nan"))
    out["fg_label"] = out["fg"].map(FIRSTGEN_LABELS)
    return out


# ---------------------------------------------------------------------------
# Chart builders
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Campus target ticks (optional overlay on the campus bar chart)
# ---------------------------------------------------------------------------
# A thin dark bar exactly as wide as its campus bar, drawn at that campus's
# target for each plan year after the baseline (the baseline tick would just
# repeat the actual). The target number sits centred under the tick with a
# white halo so it reads on any bar colour (NOCE navy included) or on the page.
# When the target is above the bar, the actual's label is lifted above the
# tick so the two never overlap. Counts only — never drawn on the rate charts.

TICK_COLOR = "#111111"
_TICK_HALO = "0px 0px 2px white, 0px 0px 3px white, 0px 0px 4px white"


def campus_target_rows(agg_plan: pd.DataFrame, *, value_col: str,
                       rule: dict) -> pd.DataFrame:
    """Per-campus targets for the chart ticks: ``camp_desc, academic_year,
    target`` for every plan year after the baseline.

    *agg_plan* is the campus aggregate of the plan-year frame (the same
    aggregation the chart uses, e.g. ``aggregate_headcount(targets.frame)``),
    so each campus's baseline is its own 2022-23 value.
    """
    baselines = group_baselines(agg_plan, key_col="camp_desc", value_col=value_col)
    rows = [
        {"camp_desc": camp, "academic_year": year,
         "target": group_target(baselines, camp, year, rule)}
        for camp in baselines
        for year in plan_years()[1:]
    ]
    out = pd.DataFrame(rows, columns=["camp_desc", "academic_year", "target"])
    return out.dropna(subset=["target"])


def campus_tick_geometry(df_agg: pd.DataFrame, df_tgt: pd.DataFrame, value_col: str):
    """Shared by the Plotly and matplotlib builders: lookups plus the scale
    numbers (tick thickness, label lift) derived from the tallest element."""
    actual = {
        (str(c), y): float(v)
        for c, y, v in zip(df_agg["camp_desc"].astype(str),
                           df_agg["academic_year"], df_agg[value_col])
        if pd.notna(v)
    }
    # A tick only where its campus has a bar that year: a target with no bar
    # behind it would read as data for a campus that reported nothing.
    target = {
        (str(c), y): float(t)
        for c, y, t in zip(df_tgt["camp_desc"].astype(str),
                           df_tgt["academic_year"], df_tgt["target"])
        if (str(c), y) in actual and pd.notna(t)
    }
    peak = max([*actual.values(), *target.values()], default=0.0)
    return actual, target, peak


def _label_y(actual: float, target: float | None, lift: float) -> float:
    """Where the actual's label sits: on the bar, or above a higher tick."""
    if target is None or target <= actual:
        return actual
    return target + lift


def add_campus_target_ticks(fig, df_agg: pd.DataFrame, df_tgt: pd.DataFrame,
                            *, value_col: str, fmt: str):
    """Overlay target ticks on a ``px.bar`` campus chart built with
    ``color="camp_desc", barmode="group"`` (px sets each trace's
    ``offsetgroup`` to the campus, which the overlay reuses to align)."""
    actual, target, peak = campus_tick_geometry(df_agg, df_tgt, value_col)
    if not target:
        return fig
    years = sorted(df_agg["academic_year"].unique())
    thick = peak * 0.008
    lift = peak * 0.035
    campuses = [c for c in CAMPUS_ORDER if any(k[0] == c for k in actual)]

    # The bars' own labels are replaced by text traces positioned per bar.
    fig.update_traces(textposition="none", selector={"type": "bar"})
    for i, camp in enumerate(campuses):
        acts = [actual.get((camp, y)) for y in years]
        tgts = [target.get((camp, y)) for y in years]
        fig.add_trace(go.Bar(
            x=years,
            y=[thick if t is not None else None for t in tgts],
            base=[t - thick / 2 if t is not None else None for t in tgts],
            offsetgroup=camp, name="Target", legendgroup="target",
            showlegend=i == 0,
            marker={"color": TICK_COLOR, "line": {"color": "white", "width": 1}},
            customdata=tgts,
            hovertemplate=f"{camp} %{{x}}<br>Target: %{{customdata:{fmt}}}<extra></extra>",
        ))
        fig.add_trace(go.Scatter(
            x=years,
            y=[None if a is None else _label_y(a, t, lift) for a, t in zip(acts, tgts)],
            # Same legendgroup as px's bar for this campus, so clicking the
            # campus in the legend hides its labels along with its bars.
            mode="text", offsetgroup=camp, legendgroup=camp,
            showlegend=False, hoverinfo="skip",
            text=["" if a is None else format(a, fmt) for a in acts],
            textposition="top center", textfont={"size": 12},
        ))
        fig.add_trace(go.Scatter(
            x=years,
            y=[t - thick / 2 if t is not None else None for t in tgts],
            # Hides with the Target ticks when "Target" is clicked.
            mode="text", offsetgroup=camp, legendgroup="target",
            showlegend=False, hoverinfo="skip",
            text=["" if t is None else format(t, fmt) for t in tgts],
            textposition="bottom center",
            textfont={"size": 10, "color": TICK_COLOR, "shadow": _TICK_HALO},
        ))
    fig.update_layout(scattermode="group")
    fig.update_yaxes(range=[0, peak * 1.15])
    return fig


def mpl_campus_bar_labels(ax, xs, vals, tgts, *, bar_w: float, peak: float,
                          fmt: str) -> None:
    """matplotlib twin of the Plotly overlay for one campus's bars: draws the
    actual labels (lifted above a higher tick) and, where *tgts* has a value,
    the tick and its haloed number. With no targets it draws exactly the
    labels the PDF drew before ticks existed."""
    thick = peak * 0.006
    lift = peak * 0.035
    halo = [patheffects.withStroke(linewidth=2, foreground="white")]
    for x, v, t in zip(xs, vals, tgts):
        # None = no data for this campus/year (no label); a real 0 is
        # labelled, exactly as the on-screen Plotly chart does.
        if v is not None:
            ax.text(x, _label_y(v, t, lift), format(v, fmt), ha="center",
                    va="bottom", fontsize=6)
        if t is None:
            continue
        ax.add_patch(Rectangle(
            (x - bar_w / 2, t - thick / 2), bar_w, thick,
            facecolor=TICK_COLOR, edgecolor="white", linewidth=0.4, zorder=3,
        ))
        ax.text(x, t - thick, format(t, fmt), ha="center", va="top",
                fontsize=5, color=TICK_COLOR, zorder=4, path_effects=halo)


def build_headcount_chart(df_agg: pd.DataFrame,
                          df_tgt: pd.DataFrame | None = None):
    years = sorted(df_agg["academic_year"].unique())
    fig = px.bar(
        df_agg,
        x="academic_year",
        y="headcount",
        color="camp_desc",
        barmode="group",
        text="headcount",
        color_discrete_map=COLOR_MAP,
        category_orders={"camp_desc": CAMPUS_ORDER, "academic_year": years},
    )
    fig.update_traces(
        texttemplate="%{text:,}",
        textposition="outside",
        textfont=dict(size=12),
    )
    fig.update_layout(
        height=420,
        xaxis_title=None,
        yaxis_title=None,
        yaxis=dict(showticklabels=False),
        legend_title=None,
        legend=dict(
            orientation="h", yanchor="top", y=-0.18,
            xanchor="center", x=0.5,
        ),
        uniformtext_minsize=8,
        uniformtext_mode="hide",
        margin=dict(l=10, t=30),
    )
    if df_tgt is not None and not df_tgt.empty:
        add_campus_target_ticks(fig, df_agg, df_tgt,
                                value_col="headcount", fmt=",.0f")
    return fig


def build_pct_change_chart(df_pct: pd.DataFrame):
    fig = px.bar(
        df_pct,
        x="pct_change",
        y="camp_desc",
        orientation="h",
        text="pct_change",
        color="camp_desc",
        color_discrete_map=COLOR_MAP,
        category_orders={
            "camp_desc": [c for c in reversed(CAMPUS_ORDER)
                          if c in df_pct["camp_desc"].values],
        },
    )
    fig.update_traces(
        texttemplate="%{text:.1f}%",
        textposition="outside",
        textfont=dict(size=12),
    )
    fig.update_layout(
        height=420,
        showlegend=False,
        title="5-Yr % Change",
        xaxis_title="% Change",
        xaxis_range=list(pct_change_axis_range(df_pct["pct_change"])),
        yaxis_title=None,
        margin=dict(l=10, t=50),
    )
    return fig


# ---------------------------------------------------------------------------
# HTML table builders
# ---------------------------------------------------------------------------

_CELL_STYLE = (
    "padding:4px 8px; color:light-dark(#000000, #FFFFFF); background:{bg}; "
    "text-align:right; border-bottom:1px solid #444;"
)
_CHG_STYLE = (
    "text-align:right; padding:4px 8px; font-weight:bold; "
    "color:light-dark(#000000, #FFFFFF); background:{bg}; "
    "border-bottom:1px solid #444;"
)


def build_race_proportion_html(df_race: pd.DataFrame, years: list[str]) -> str:
    """Table with inline data bars: race rows x year columns."""
    piv = df_race.pivot_table(
        index="race_description", columns="academic_year",
        values="pct", aggfunc="first",
    )
    max_pct = piv.max().max() if not piv.empty else 1.0

    rows: list[str] = []
    rows.append('<table style="border-collapse:collapse; font-size:13px;">')
    rows.append("<thead><tr>")
    rows.append(
        "<th style='padding:4px 8px; border-bottom:2px solid #555;'></th>"
    )
    for yr in years:
        rows.append(
            f"<th style='text-align:center; padding:4px 10px; "
            f"border-bottom:2px solid #555;'>{yr}</th>"
        )
    rows.append("</tr></thead><tbody>")
    for race in _visible_races(df_race):
        label = RACE_SHORT.get(race, race)
        rows.append("<tr>")
        rows.append(
            f"<td style='text-align:right; padding:4px 8px; "
            f"white-space:nowrap; font-weight:bold;'>{label}</td>"
        )
        bar_color = RACE_COLORS.get(race, "#555555")
        for yr in years:
            pct = (
                piv.loc[race, yr]
                if race in piv.index and yr in piv.columns
                else None
            )
            if pct is not None and pd.notna(pct):
                bar_w = pct / max_pct * 100 if max_pct > 0 else 0
                rows.append(
                    f"<td style='padding:3.6px 4px; min-width:80px;'>"
                    f"<div style='background:{bar_color}; width:{bar_w:.0f}%; "
                    f"padding:2.6px 6px; color:light-dark(#000000, #FFFFFF); "
                    f"font-size:12px; white-space:nowrap; border-radius:2px;'>"
                    f"{pct:.1%}</div></td>"
                )
            else:
                rows.append("<td style='padding:4px 4px;'></td>")
        rows.append("</tr>")
    rows.append("</tbody></table>")
    return "\n".join(rows)


def _build_summary_table(
    order: list, label_map: dict, color_map: dict,
    piv: pd.DataFrame, first_yr: str, last_yr: str,
) -> str:
    """Generic colored summary table: first count, last count, 5-yr % change."""
    rows: list[str] = []
    rows.append(
        '<table style="border-collapse:collapse; font-size:13px; '
        'table-layout:fixed;">'
    )
    rows.append("<colgroup>")
    rows.append("<col style='width:33.3%'>")
    rows.append("<col style='width:33.3%'>")
    rows.append("<col style='width:33.3%'>")
    rows.append("</colgroup>")
    rows.append("<thead><tr>")
    rows.append(
        f"<th style='text-align:center; padding:6px 8px; "
        f"border-bottom:2px solid #555;'>{first_yr}<br>Student Count</th>"
    )
    rows.append(
        f"<th style='text-align:center; padding:6px 8px; "
        f"border-bottom:2px solid #555;'>{last_yr}<br>Student Count</th>"
    )
    rows.append(
        "<th style='text-align:center; padding:6px 8px; "
        "border-bottom:2px solid #555;'>5-Yr %<br>Change</th>"
    )
    rows.append("</tr></thead><tbody>")

    for key in order:
        label = label_map.get(key, key) if label_map else key
        color = color_map.get(label, color_map.get(key, "#555555"))
        fc = (
            int(piv.loc[key, first_yr])
            if key in piv.index and first_yr in piv.columns
            and pd.notna(piv.loc[key, first_yr])
            else 0
        )
        lc = (
            int(piv.loc[key, last_yr])
            if key in piv.index and last_yr in piv.columns
            and pd.notna(piv.loc[key, last_yr])
            else 0
        )
        chg_str = f"{(lc - fc) / fc * 100:+.0f}%" if fc > 0 else ""

        rows.append("<tr>")
        rows.append(f"<td style='{_CELL_STYLE.format(bg=color)}'>{fc:,}</td>")
        rows.append(f"<td style='{_CELL_STYLE.format(bg=color)}'>{lc:,}</td>")
        rows.append(f"<td style='{_CHG_STYLE.format(bg=color)}'>{chg_str}</td>")
        rows.append("</tr>")

    rows.append("</tbody></table>")
    return "\n".join(rows)


def build_race_summary_html(df_race: pd.DataFrame, years: list[str]) -> str:
    if len(window_years(years)) < 2:
        return ""
    piv = df_race.pivot_table(
        index="race_description", columns="academic_year",
        values="count", aggfunc="first",
    )
    return _build_summary_table(
        _visible_races(df_race), RACE_SHORT, RACE_COLORS,
        piv, *window_bounds(years),
    )


def build_gender_bar_chart(df_gender: pd.DataFrame, years: list[str]):
    visible = _visible_genders(df_gender)
    df_plot = df_gender[df_gender["gender"].isin(visible)].copy()
    labels = [GENDER_LABELS[g] for g in visible]
    df_plot["gender_label"] = pd.Categorical(
        df_plot["gender_label"], categories=labels, ordered=True,
    )
    fig = px.bar(
        df_plot.sort_values(["academic_year", "gender_label"]),
        x="pct",
        y="academic_year",
        color="gender_label",
        orientation="h",
        barmode="group",
        text="pct",
        color_discrete_map=GENDER_COLORS,
        category_orders={
            "academic_year": list(reversed(years)),
            "gender_label": list(reversed(labels)),
        },
    )
    fig.update_traces(
        texttemplate="%{text:.1%}",
        textposition="outside",
        textfont=dict(size=12),
    )
    fig.update_layout(
        height=420,
        xaxis_title=None,
        xaxis=dict(tickformat=".0%", range=[0, df_plot["pct"].max() * 1.2]),
        yaxis_title=None,
        legend_title=None,
        legend=dict(
            orientation="h", yanchor="top", y=-0.1,
            xanchor="center", x=0.5,
        ),
        margin=dict(t=10),
    )
    return fig


def build_gender_summary_html(df_gender: pd.DataFrame, years: list[str]) -> str:
    if len(window_years(years)) < 2:
        return ""
    piv = df_gender.pivot_table(
        index="gender", columns="academic_year",
        values="count", aggfunc="first",
    )
    return _build_summary_table(
        _visible_genders(df_gender), GENDER_LABELS, GENDER_COLORS,
        piv, *window_bounds(years),
    )


def build_firstgen_line_chart(df_fg: pd.DataFrame, years: list[str]):
    labels = [FIRSTGEN_LABELS[g] for g in FIRSTGEN_ORDER]
    fig = px.line(
        df_fg,
        x="academic_year",
        y="pct",
        color="fg_label",
        text="pct",
        markers=True,
        color_discrete_map=FIRSTGEN_COLORS,
        category_orders={"academic_year": years, "fg_label": labels},
    )
    fig.update_traces(
        texttemplate="%{y:.1%}",
        textposition="top center",
        mode="lines+markers+text",
        textfont=dict(size=12),
    )
    # Zoom y-axis tight around actual data range so lines are visually
    # separated. Smaller pad = more vertical spread between lines.
    min_v = df_fg["pct"].min() if not df_fg.empty else 0
    max_v = df_fg["pct"].max() if not df_fg.empty else 1.0
    pad = max((max_v - min_v) * 0.25, 0.015)
    fig.update_layout(
        height=420,
        xaxis_title=None,
        yaxis_title=None,
        yaxis=dict(
            tickformat=".0%",
            range=[max(0, min_v - pad), max_v + pad]
                  if pd.notna(min_v) else [0, 1.0],
            showticklabels=False,
        ),
        legend_title=None,
        legend=dict(
            orientation="h", yanchor="top", y=-0.15,
            xanchor="center", x=0.5,
        ),
        margin=dict(t=10),
    )
    return fig


def build_firstgen_summary_html(df_fg: pd.DataFrame, years: list[str]) -> str:
    if len(window_years(years)) < 2:
        return ""
    piv = df_fg.pivot_table(
        index="fg", columns="academic_year",
        values="count", aggfunc="first",
    )
    return _build_summary_table(
        FIRSTGEN_ORDER, FIRSTGEN_LABELS, FIRSTGEN_COLORS,
        piv, *window_bounds(years),
    )


# ---------------------------------------------------------------------------
# Shared render layout
# ---------------------------------------------------------------------------

_SOURCE_FOOTER = (
    "<div style='text-align:left'><small>Source: Banner</small></div>"
)


def _source_html(titles: dict) -> str:
    """Render the Source footer line, honoring an optional ``source`` override.

    The ``source`` value is the suffix after ``Source: `` (default ``Banner``).
    """
    src = titles.get("source", "Banner")
    return f"<div style='text-align:left'><small>Source: {src}</small></div>"


def render_target_section(titles: dict, targets: Targets) -> None:
    """Chart 0: district Actual vs Target, 2022-23 -> 2029-30.

    Always the full plan — it does not follow the Academic Years selection.
    """
    st.subheader(titles["org"])
    st.markdown(f"**{titles['target_title']}**  \n{plan_range_label()}")
    st.caption(
        f"{target_caption(targets.rule)} This chart always shows the full "
        "plan and does not follow the Academic Years selection."
    )
    st.plotly_chart(
        build_target_chart(district_actual_vs_target(targets), targets.rule),
        width="stretch",
    )
    st.markdown(_source_html(titles), unsafe_allow_html=True)
    st.divider()


def headcount_campus_targets(targets: Targets | None, titles: dict,
                             show: bool) -> pd.DataFrame | None:
    """Tick rows for the headcount chart, or None when ticks are off or there
    is no plan frame (e.g. a stale session)."""
    if not show or targets is None:
        return None
    agg_plan = aggregate_headcount(
        targets.frame, include_nocccd=titles.get("include_nocccd", True),
    )
    return campus_target_rows(agg_plan, value_col="headcount", rule=targets.rule)


def _campus_toggle_key(prefix: str) -> str:
    return f"{prefix}_campus_targets"


def campus_targets_on(prefix: str) -> bool:
    """Current state of a tab's "Show campus targets" switch.

    The switch is drawn right above the campus chart, but the tab builds its
    Download PDF earlier in the script; Streamlit keeps the widget's state in
    session_state across reruns, so the PDF reads it from there.
    """
    return bool(st.session_state.get(_campus_toggle_key(prefix), False))


def render_campus_target_toggle(prefix: str) -> bool:
    """The "Show campus targets" switch, placed right above the campus chart
    it controls. Off by default so the chart looks exactly as it always has."""
    return st.toggle("Show campus targets", value=False,
                     key=_campus_toggle_key(prefix))


def render_bot_charts(
    df: pd.DataFrame, titles: dict,
    base_df: pd.DataFrame | None = None,
    targets: Targets | None = None,
    campus_toggle_prefix: str | None = None,
):
    """Render the standard 4-chart BOT layout.

    When *base_df* is provided (Goal 1 Students data), the proportion
    charts (race, gender, first-gen) compute rates relative to the base
    population rather than within the current dataset.

    titles keys:
        org, headcount_title, headcount_caption,
        race_title, race_caption,
        gender_title, gender_caption,
        firstgen_org (optional, defaults to org),
        firstgen_title, firstgen_caption,
        headcount_note, race_note, gender_note, firstgen_note
            (optional per-section footer notes; None to skip)
        source (optional, default "Banner") — text after "Source: " in section footers
        include_nocccd (optional, default True) — show NOCCCD unduplicated bar
        credit_only_firstgen (optional, default True) — filter first-gen to credit
        headcount_only (optional, default False) — show only chart 1, skip race/gender/first-gen
    targets (optional) — Vision 2030 plan rows + rule; renders the Actual vs Target chart first
    campus_toggle_prefix (optional) — the tab's widget prefix; with *targets*, draws the
        "Show campus targets" switch right above the campus chart and, when on, per-campus
        target ticks on it
    """
    years = sorted(df["academic_year"].dropna().unique())
    window = window_years(years)
    year_range = (
        f"{window[0]} to {window[-1]}" if len(window) >= 2
        else window[0] if window else ""
    )
    org = titles["org"]
    if targets is not None:
        render_target_section(titles, targets)

    # --- Chart 1: Headcount by Campus ---
    show_campus_targets = (
        targets is not None and campus_toggle_prefix is not None
        and render_campus_target_toggle(campus_toggle_prefix)
    )
    st.subheader(org)
    st.markdown(f"**{titles['headcount_title']}**  \n{year_range}")
    st.caption(titles["headcount_caption"])
    df_agg = aggregate_headcount(
        df, include_nocccd=titles.get("include_nocccd", True),
    )
    df_pct = compute_pct_change(df_agg)
    df_tgt = headcount_campus_targets(targets, titles, show_campus_targets)

    col_main, col_pct = st.columns([3, 1])
    with col_main:
        st.plotly_chart(build_headcount_chart(df_agg, df_tgt=df_tgt),
                        width="stretch")
    with col_pct:
        if not df_pct.empty:
            st.plotly_chart(
                build_pct_change_chart(df_pct), width="stretch",
            )
        else:
            st.info("Need at least 2 years for % change.")
    st.markdown(_source_html(titles), unsafe_allow_html=True)
    if titles.get("headcount_note"):
        st.caption(titles["headcount_note"])

    if titles.get("headcount_only"):
        return

    # --- Chart 2: Proportion by Race/Ethnicity ---
    st.divider()
    st.subheader(org)
    st.markdown(f"**{titles['race_title']}**  \n{year_range}")
    st.caption(titles["race_caption"])
    df_race = aggregate_race(df, base_df=base_df)

    col_prop, col_summary = st.columns([3, 2])
    with col_prop:
        st.markdown(
            build_race_proportion_html(df_race, years),
            unsafe_allow_html=True,
        )
    with col_summary:
        html = build_race_summary_html(df_race, years)
        if html:
            st.markdown(html, unsafe_allow_html=True)
    st.markdown(_source_html(titles), unsafe_allow_html=True)
    if titles.get("race_note"):
        st.caption(titles["race_note"])

    # --- Chart 3: Proportion by Gender ---
    st.divider()
    st.subheader(org)
    st.markdown(f"**{titles['gender_title']}**  \n{year_range}")
    st.caption(titles["gender_caption"])
    df_gender = aggregate_gender(df, base_df=base_df)

    col_gc, col_gs = st.columns([3, 2])
    with col_gc:
        st.plotly_chart(
            build_gender_bar_chart(df_gender, years),
            width="stretch",
        )
    with col_gs:
        html = build_gender_summary_html(df_gender, years)
        if html:
            st.markdown(html, unsafe_allow_html=True)
    st.markdown(_source_html(titles), unsafe_allow_html=True)
    if titles.get("gender_note"):
        st.caption(titles["gender_note"])

    # --- Chart 4: Proportion by First-Generation Status ---
    st.divider()
    fg_org = titles.get("firstgen_org", org)
    st.subheader(fg_org)
    st.markdown(f"**{titles['firstgen_title']}**  \n{year_range}")
    st.caption(titles["firstgen_caption"])
    df_fg = aggregate_firstgen(
        df, credit_only=titles.get("credit_only_firstgen", True),
        base_df=base_df,
    )

    col_fc, col_fs = st.columns([3, 2])
    with col_fc:
        st.plotly_chart(
            build_firstgen_line_chart(df_fg, years),
            width="stretch",
        )
    with col_fs:
        html = build_firstgen_summary_html(df_fg, years)
        if html:
            st.markdown(html, unsafe_allow_html=True)
    st.markdown(_source_html(titles), unsafe_allow_html=True)
    if titles.get("firstgen_note"):
        st.caption(titles["firstgen_note"])


# ---------------------------------------------------------------------------
# PDF export (matplotlib)
# ---------------------------------------------------------------------------

_PDF_FOOTER_LEFT = "https://nocccd.streamlit.app/"
_PDF_FOOTER_RIGHT = "Author: Jihoon Ahn  jahn@nocccd.edu"


def _add_pdf_footer(fig):
    fig.text(0.06, 0.015, _PDF_FOOTER_LEFT,
             fontsize=7, color="grey", ha="left")
    fig.text(0.94, 0.015, _PDF_FOOTER_RIGHT,
             fontsize=7, color="grey", ha="right")


def _draw_section_header(fig, section_top, org, title, year_range, caption,
                         pad: float = 0.025):
    """Draw section header (org, title, year range, caption) at paper coords.

    Returns the y-coordinate of the content area (chart) top. *pad* is
    the gap below the caption to prevent matplotlib axis titles from
    overlapping it. Pass a smaller value (e.g. 0.005) for sections
    where the chart has no axis title above the axes box (e.g. the
    race data-bar table drawn on an ``axis("off")`` axes).
    """
    y = section_top
    fig.text(0.06, y, org, fontsize=12, fontweight="bold", va="top")
    y -= 0.022
    fig.text(0.06, y, title, fontsize=10, fontweight="bold", va="top")
    y -= 0.018
    fig.text(0.06, y, year_range, fontsize=8, color="#555555", va="top")
    y -= 0.020
    wrapped = textwrap.fill(caption, width=140)
    fig.text(0.06, y, wrapped, fontsize=7, color="#555555",
             va="top", style="italic")
    y_after_caption = y - 0.022 * (wrapped.count("\n") + 1)
    return y_after_caption - pad


def _draw_section_source(fig, y, source: str = "Banner"):
    fig.text(0.06, y, f"Source: {source}", fontsize=7, color="grey", va="top")


def _draw_section_note(fig, y, note):
    """Render a grey footnote under a section's Source line."""
    note_wrapped = textwrap.fill(note, width=140)
    fig.text(0.06, y, note_wrapped,
             fontsize=6, color="grey", va="top")


def add_target_page(pdf, titles: dict, targets: Targets) -> None:
    """PDF page 1 for target tabs. The existing pages follow unchanged.

    The caller has already forced the light-theme rcParams.
    """
    fig = plt.figure(figsize=(8.5, 11.0))
    fig.text(0.5, 0.97, titles.get("tab_title", "BOT Goal"), fontsize=14,
             fontweight="bold", ha="center", va="top")
    y_after_header = _draw_section_header(
        fig, 0.935, titles["org"], titles["target_title"],
        plan_range_label(), target_caption(targets.rule),
    )
    bottom = 0.58
    mpl_target_chart(
        fig, (0.08, bottom, 0.86, y_after_header - bottom),
        district_actual_vs_target(targets), targets.rule,
    )
    _draw_section_source(fig, 0.54, titles.get("source", "Banner"))
    _add_pdf_footer(fig)
    pdf.savefig(fig)
    plt.close(fig)


def _mpl_headcount(fig, bbox, df_agg, df_pct, df_tgt=None):
    """Draw grouped bar (counts) + horizontal bar (5-yr % change) side by side.

    bbox = (left, bottom, width, height) in paper coords. *df_tgt* (from
    ``campus_target_rows``) adds per-campus target ticks.
    """
    left, bottom, width, height = bbox
    # Left: grouped bar, Right: horizontal bar; keep ~63:30 ratio but
    # widen the gap so 5-yr y-axis labels don't overlap the bar chart.
    ax_bar = fig.add_axes([left, bottom, width * 0.55, height])
    ax_pct = fig.add_axes([left + width * 0.72, bottom, width * 0.26, height])

    years = sorted(df_agg["academic_year"].unique())
    campuses = [c for c in CAMPUS_ORDER
                if c in df_agg["camp_desc"].values]
    n_groups = len(years)
    n_bars = len(campuses)
    bar_w = 0.8 / max(n_bars, 1)
    tgt_rows = df_tgt if df_tgt is not None else pd.DataFrame(
        columns=["camp_desc", "academic_year", "target"])
    _, target, peak = campus_tick_geometry(df_agg, tgt_rows, "headcount")

    for i, camp in enumerate(campuses):
        vals = []
        for yr in years:
            row = df_agg[(df_agg["camp_desc"] == camp)
                         & (df_agg["academic_year"] == yr)]
            vals.append(row["headcount"].iloc[0] if not row.empty else None)
        xs = np.arange(n_groups) + (i - (n_bars - 1) / 2) * bar_w
        ax_bar.bar(xs, [0 if v is None else v for v in vals], width=bar_w,
                   color=COLOR_MAP.get(camp, "#888"), label=camp)
        mpl_campus_bar_labels(
            ax_bar, xs, vals, [target.get((camp, yr)) for yr in years],
            bar_w=bar_w, peak=peak, fmt=",.0f",
        )
    if target:
        ax_bar.plot([], [], color=TICK_COLOR, linewidth=2, label="Target")

    ax_bar.set_xticks(range(n_groups))
    ax_bar.set_xticklabels(years, fontsize=7)
    ax_bar.tick_params(axis="y", labelsize=7)
    ax_bar.spines["top"].set_visible(False)
    ax_bar.spines["right"].set_visible(False)
    # Target (a line handle) sorts ahead of the bars by default; keep it last.
    handles, labels = ax_bar.get_legend_handles_labels()
    order = sorted(range(len(labels)), key=lambda i: labels[i] == "Target")
    ax_bar.legend([handles[i] for i in order], [labels[i] for i in order],
                  fontsize=6, loc="upper center", bbox_to_anchor=(0.5, -0.08),
                  ncol=n_bars + (1 if target else 0), frameon=False)
    # peak covers both bars and ticks, so a tick above every bar still fits.
    ax_bar.set_ylim(0, peak * 1.15 if peak else 1)

    # 5-yr % change chart
    if not df_pct.empty:
        pct_campuses = [c for c in reversed(campuses)
                        if c in df_pct["camp_desc"].values]
        vals = [
            df_pct[df_pct["camp_desc"] == c]["pct_change"].iloc[0]
            for c in pct_campuses
        ]
        colors = [COLOR_MAP.get(c, "#888") for c in pct_campuses]
        ys = np.arange(len(pct_campuses))
        ax_pct.barh(ys, vals, color=colors)
        lo, hi = pct_change_axis_range(vals)
        # Label gap scales with the axis so it neither vanishes on a wide
        # axis nor pushes the label off the edge of a tight one.
        gap = (hi - lo) * 0.02
        for y_, v in zip(ys, vals):
            ha = "left" if v >= 0 else "right"
            offset = gap if v >= 0 else -gap
            ax_pct.text(v + offset, y_, f"{v:.1f}%", va="center",
                        ha=ha, fontsize=6)
        ax_pct.set_yticks(ys)
        ax_pct.set_yticklabels(pct_campuses, fontsize=6)
        ax_pct.tick_params(axis="x", labelsize=6)
        ax_pct.set_title("5-Yr % Change", fontsize=8, fontweight="bold")
        ax_pct.spines["top"].set_visible(False)
        ax_pct.spines["right"].set_visible(False)
        ax_pct.axvline(0, color="#888", linewidth=0.5)
        ax_pct.set_xlim(lo, hi)
    else:
        ax_pct.axis("off")


def _mpl_race_proportion_table(fig, bbox, df_race, years):
    """Draw race proportion table with colored data bars using Rectangles."""
    left, bottom, width, height = bbox
    ax = fig.add_axes([left, bottom, width, height])
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")

    piv = df_race.pivot_table(
        index="race_description", columns="academic_year",
        values="pct", aggfunc="first",
    )
    max_pct = piv.max().max() if not piv.empty else 1.0

    visible = _visible_races(df_race)
    n_rows = len(visible) + 1  # +1 header
    row_h = 1.0 / n_rows
    label_col_w = 0.30
    data_col_w = (1.0 - label_col_w) / len(years)

    # Header row: year labels
    y_top = 1.0 - row_h
    for i, yr in enumerate(years):
        x = label_col_w + i * data_col_w
        ax.text(x + data_col_w / 2, y_top + row_h / 2, yr,
                ha="center", va="center",
                fontsize=year_header_fontsize(years), fontweight="bold")

    # Data rows
    for r, race in enumerate(visible):
        y = 1.0 - (r + 2) * row_h
        label = RACE_SHORT.get(race, race)
        ax.text(label_col_w - 0.01, y + row_h / 2, label,
                ha="right", va="center", fontsize=7, fontweight="bold")
        bar_color = RACE_COLORS.get(race, "#888")
        for i, yr in enumerate(years):
            pct = piv.loc[race, yr] if race in piv.index and yr in piv.columns else None
            if pct is None or pd.isna(pct):
                continue
            cell_x = label_col_w + i * data_col_w
            bar_w = (pct / max_pct) * data_col_w if max_pct > 0 else 0
            ax.add_patch(Rectangle(
                (cell_x + 0.002, y + row_h * 0.15),
                bar_w - 0.004, row_h * 0.7,
                facecolor=bar_color, edgecolor="none",
            ))
            ax.text(cell_x + 0.006, y + row_h / 2, f"{pct:.1%}",
                    ha="left", va="center", fontsize=6, color="black",
                    fontweight="bold")


def _mpl_summary_table(fig, bbox, order, label_map, color_map, piv,
                      first_yr, last_yr):
    """Draw a colored summary table: first count, last count, 5-yr % change."""
    left, bottom, width, height = bbox
    ax = fig.add_axes([left, bottom, width, height])
    ax.axis("off")

    headers = [
        f"{first_yr}\nStudent Count",
        f"{last_yr}\nStudent Count",
        "5-Yr %\nChange",
    ]
    rows = []
    cell_colors = []
    for key in order:
        label = label_map.get(key, key) if label_map else key
        color = color_map.get(label, color_map.get(key, "#888"))
        fc = int(piv.loc[key, first_yr]) if (
            key in piv.index and first_yr in piv.columns
            and pd.notna(piv.loc[key, first_yr])
        ) else 0
        lc = int(piv.loc[key, last_yr]) if (
            key in piv.index and last_yr in piv.columns
            and pd.notna(piv.loc[key, last_yr])
        ) else 0
        chg_str = f"{(lc - fc) / fc * 100:+.0f}%" if fc > 0 else ""
        rows.append([f"{fc:,}", f"{lc:,}", chg_str])
        cell_colors.append([color, color, color])

    tbl = ax.table(
        cellText=rows, colLabels=headers, cellColours=cell_colors,
        cellLoc="right", colLoc="center", loc="center",
    )
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(7)
    tbl.scale(1, 1.6)
    # Style header cells
    for col_idx in range(len(headers)):
        cell = tbl[(0, col_idx)]
        cell.set_fontsize(7)
        cell.set_text_props(fontweight="bold")
        cell.set_facecolor("#FFFFFF")
    # Style data cells: black text on colored bg
    for row_idx in range(1, len(rows) + 1):
        for col_idx in range(len(headers)):
            cell = tbl[(row_idx, col_idx)]
            cell.set_text_props(color="black", fontweight="bold")


def _mpl_race_summary(fig, bbox, df_race, years):
    if len(window_years(years)) < 2:
        return
    piv = df_race.pivot_table(
        index="race_description", columns="academic_year",
        values="count", aggfunc="first",
    )
    _mpl_summary_table(fig, bbox, _visible_races(df_race),
                       RACE_SHORT, RACE_COLORS,
                       piv, *window_bounds(years))


def _mpl_gender_chart(fig, bbox, df_gender, years):
    """Horizontal grouped bar chart: academic years × gender."""
    left, bottom, width, height = bbox
    ax = fig.add_axes([left, bottom, width, height])

    visible = _visible_genders(df_gender)
    labels = [GENDER_LABELS[g] for g in visible]
    n_years = len(years)
    n_genders = len(labels)
    bar_h = 0.8 / max(n_genders, 1)

    for i, (g_code, g_label) in enumerate(zip(visible, labels)):
        vals = []
        for yr in years:
            row = df_gender[(df_gender["gender"] == g_code)
                            & (df_gender["academic_year"] == yr)]
            vals.append(row["pct"].iloc[0] if not row.empty else 0)
        ys = np.arange(n_years) + (i - (n_genders - 1) / 2) * bar_h
        color = GENDER_COLORS.get(g_label, "#888")
        ax.barh(ys, vals, height=bar_h, color=color, label=g_label)
        for y_, v in zip(ys, vals):
            if pd.notna(v) and v > 0:
                ax.text(v, y_, f"{v:.1%}", va="center",
                        ha="left", fontsize=6)

    ax.set_yticks(range(n_years))
    ax.set_yticklabels(years, fontsize=7)
    ax.tick_params(axis="x", labelsize=6)
    ax.xaxis.set_major_formatter(
        plt.FuncFormatter(lambda v, _: f"{v:.0%}")
    )
    max_pct = df_gender["pct"].max() if not df_gender.empty else 0.5
    ax.set_xlim(0, max_pct * 1.2 if pd.notna(max_pct) else 0.5)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.legend(fontsize=6, loc="upper center",
              bbox_to_anchor=(0.5, -0.08), ncol=n_genders, frameon=False)


def _mpl_gender_summary(fig, bbox, df_gender, years):
    if len(window_years(years)) < 2:
        return
    piv = df_gender.pivot_table(
        index="gender", columns="academic_year",
        values="count", aggfunc="first",
    )
    _mpl_summary_table(fig, bbox, _visible_genders(df_gender),
                       GENDER_LABELS, GENDER_COLORS,
                       piv, *window_bounds(years))


def _mpl_firstgen_chart(fig, bbox, df_fg, years):
    """Line chart for first-gen proportion over years."""
    left, bottom, width, height = bbox
    ax = fig.add_axes([left, bottom, width, height])

    for fg in FIRSTGEN_ORDER:
        label = FIRSTGEN_LABELS[fg]
        color = FIRSTGEN_COLORS.get(label, "#888")
        vals = []
        for yr in years:
            row = df_fg[(df_fg["fg"] == fg)
                        & (df_fg["academic_year"] == yr)]
            vals.append(row["pct"].iloc[0] if not row.empty else None)
        xs = list(range(len(years)))
        ax.plot(xs, vals, marker="o", color=color, label=label, linewidth=1.5)
        for x, v in zip(xs, vals):
            if v is not None and pd.notna(v):
                ax.annotate(f"{v:.1%}", (x, v), textcoords="offset points",
                            xytext=(0, 6), ha="center", fontsize=6)

    ax.set_xticks(range(len(years)))
    ax.set_xticklabels(years, fontsize=7)
    ax.tick_params(axis="y", labelsize=6)
    ax.yaxis.set_major_formatter(
        plt.FuncFormatter(lambda v, _: f"{v:.0%}")
    )
    # Zoom y-axis tight to data so line points are visually separated
    min_pct = df_fg["pct"].min() if not df_fg.empty else 0
    max_pct = df_fg["pct"].max() if not df_fg.empty else 0.5
    pad = max((max_pct - min_pct) * 0.25, 0.015)
    if pd.notna(min_pct):
        ax.set_ylim(max(0, min_pct - pad), max_pct + pad)
    else:
        ax.set_ylim(0, 0.5)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(axis="y", alpha=0.3)
    ax.legend(fontsize=6, loc="upper center",
              bbox_to_anchor=(0.5, -0.08), ncol=3, frameon=False)


def _mpl_firstgen_summary(fig, bbox, df_fg, years):
    if len(window_years(years)) < 2:
        return
    piv = df_fg.pivot_table(
        index="fg", columns="academic_year",
        values="count", aggfunc="first",
    )
    _mpl_summary_table(fig, bbox, FIRSTGEN_ORDER, FIRSTGEN_LABELS,
                       FIRSTGEN_COLORS, piv, *window_bounds(years))


def generate_bot_pdf(df, titles, base_df=None,
                     targets: Targets | None = None,
                     show_campus_targets: bool = False) -> bytes:
    """Generate a portrait PDF with 2 BOT sections per page.

    Page 0 (only with targets): Actual vs Target
    Page 1: Headcount + Race
    Page 2: Gender + First-Gen
    If titles['headcount_only'] is True, only page 1 with just Headcount.
    *show_campus_targets* adds per-campus target ticks to the headcount chart
    (needs *targets*); the bulk exporter never sets it.
    """
    # Force light theme for PDF output regardless of user's Streamlit theme
    matplotlib.rcParams.update({
        "figure.facecolor": "white",
        "figure.edgecolor": "white",
        "axes.facecolor": "white",
        "axes.edgecolor": "#333333",
        "axes.labelcolor": "black",
        "axes.titlecolor": "black",
        "xtick.color": "black",
        "ytick.color": "black",
        "text.color": "black",
        "savefig.facecolor": "white",
        "savefig.edgecolor": "white",
    })

    PAGE_W, PAGE_H = 8.5, 11.0
    years = sorted(df["academic_year"].dropna().unique())
    window = window_years(years)
    year_range = (
        f"{window[0]} to {window[-1]}" if len(window) >= 2
        else window[0] if window else ""
    )
    headcount_only = titles.get("headcount_only", False)

    # Precompute aggregates
    df_agg = aggregate_headcount(
        df, include_nocccd=titles.get("include_nocccd", True))
    df_pct = compute_pct_change(df_agg)
    df_tgt = headcount_campus_targets(targets, titles, show_campus_targets)
    if not headcount_only:
        df_race = aggregate_race(df, base_df=base_df)
        df_gender = aggregate_gender(df, base_df=base_df)
        df_fg = aggregate_firstgen(
            df, credit_only=titles.get("credit_only_firstgen", True),
            base_df=base_df)

    # Per-section note presence shifts that section's chart and Source
    # line up by NOTE_OFFSET so the note fits beneath the Source line.
    # NOTE_OFFSET equals the y-coord gap between the Source line and
    # the note. 0.01 matches the firstgen_note spacing on Goal 1 (the
    # canonical reference) and is uniform across every BOT section.
    NOTE_OFFSET = 0.01
    headcount_note = titles.get("headcount_note")
    race_note = titles.get("race_note")
    gender_note = titles.get("gender_note")
    firstgen_note = titles.get("firstgen_note")
    hc_off = NOTE_OFFSET if headcount_note else 0
    rc_off = NOTE_OFFSET if race_note else 0
    gn_off = NOTE_OFFSET if gender_note else 0

    source = titles.get("source", "Banner")

    buf = io.BytesIO()
    with PdfPages(buf) as pdf:
        if targets is not None:
            add_target_page(pdf, titles, targets)

        # --- Page 1 ---
        fig = plt.figure(figsize=(PAGE_W, PAGE_H))
        tab_title = titles.get("tab_title", "BOT Goal")
        fig.text(0.5, 0.97, tab_title, fontsize=14, fontweight="bold",
                 ha="center", va="top")

        # Section 1: Headcount (top half) — chart bottom raised to 0.58
        # so legend sits above the Source line with a clear gap.
        y_after_header = _draw_section_header(
            fig, 0.935, titles["org"], titles["headcount_title"],
            year_range, titles["headcount_caption"],
        )
        hc_bottom = 0.58 + hc_off
        _mpl_headcount(
            fig,
            (0.06, hc_bottom, 0.88, y_after_header - hc_bottom),
            df_agg, df_pct, df_tgt,
        )
        _draw_section_source(fig, 0.54 + hc_off, source)
        if headcount_note:
            _draw_section_note(fig, 0.54, headcount_note)

        if not headcount_only:
            # Section 2: Race (bottom half) — top raised to 0.50 to use
            # the vertical space freed above; header uses reduced pad
            # to tighten the gap between caption and the race table.
            y_after_header = _draw_section_header(
                fig, 0.50, titles["org"], titles["race_title"],
                year_range, titles["race_caption"],
                pad=0.005,
            )
            rc_bottom = 0.06 + rc_off
            chart_bbox = (0.06, rc_bottom, 0.54, y_after_header - rc_bottom)
            _mpl_race_proportion_table(fig, chart_bbox, df_race, years)
            table_bbox = (0.62, rc_bottom, 0.32, y_after_header - rc_bottom)
            _mpl_race_summary(fig, table_bbox, df_race, years)
            _draw_section_source(fig, 0.04 + rc_off, source)
            if race_note:
                _draw_section_note(fig, 0.04, race_note)

        _add_pdf_footer(fig)
        pdf.savefig(fig)
        plt.close(fig)

        if not headcount_only:
            # --- Page 2: Gender + First-Gen ---
            fig = plt.figure(figsize=(PAGE_W, PAGE_H))
            fig.text(0.5, 0.97, tab_title, fontsize=14, fontweight="bold",
                     ha="center", va="top")

            # Section 3: Gender (top half) — shift chart right so long
            # y-axis year labels aren't clipped at the page edge.
            y_after_header = _draw_section_header(
                fig, 0.935, titles["org"], titles["gender_title"],
                year_range, titles["gender_caption"],
            )
            gn_bottom = 0.56 + gn_off
            chart_bbox = (0.12, gn_bottom, 0.48, y_after_header - gn_bottom)
            _mpl_gender_chart(fig, chart_bbox, df_gender, years)
            table_bbox = (0.62, gn_bottom, 0.32, y_after_header - gn_bottom)
            _mpl_gender_summary(fig, table_bbox, df_gender, years)
            _draw_section_source(fig, 0.52 + gn_off, source)
            if gender_note:
                _draw_section_note(fig, 0.52, gender_note)

            # Section 4: First-Gen (bottom half) — raise chart bottom to
            # 0.13 so the legend has room below before "Source: Banner".
            fg_org = titles.get("firstgen_org", titles["org"])
            y_after_header = _draw_section_header(
                fig, 0.48, fg_org, titles["firstgen_title"],
                year_range, titles["firstgen_caption"],
            )
            chart_bbox = (0.06, 0.13, 0.54, y_after_header - 0.13)
            _mpl_firstgen_chart(fig, chart_bbox, df_fg, years)
            table_bbox = (0.62, 0.13, 0.32, y_after_header - 0.13)
            _mpl_firstgen_summary(fig, table_bbox, df_fg, years)

            # Source sits between the legend and the page footer with
            # balanced gaps. Same layout across all tabs.
            _draw_section_source(fig, 0.085, source)
            if firstgen_note:
                _draw_section_note(fig, 0.075, firstgen_note)

            _add_pdf_footer(fig)
            pdf.savefig(fig)
            plt.close(fig)

    return buf.getvalue()
