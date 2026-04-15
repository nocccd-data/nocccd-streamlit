"""BOT Goal 3 - Average Number of Units.

Different from other BOT tabs: metric is the MEAN of sum_hours_earned
(not counts/proportions). All 4 sections show averages among ADT
recipients. Credit colleges only (SQL filter). No base_df/denominator.
"""

import io
import textwrap

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.patches import Rectangle

from src.pipeline.config import DATASETS
from src.scripts.data_provider import fetch_bot_goal3_units
from src.scripts.tabs.bot_helpers import (
    CAMPUS_ORDER,
    COLOR_MAP,
    FIRSTGEN_COLORS,
    FIRSTGEN_LABELS,
    FIRSTGEN_ORDER,
    GENDER_COLORS,
    GENDER_LABELS,
    GENDER_ORDER,
    RACE_COLORS,
    RACE_ORDER,
    RACE_SHORT,
)

_CFG = DATASETS["bot_goal3_units"]
_DEFAULT_ACYRS = _CFG[_CFG["param_name"]]

_TITLES = {
    "tab_title": "BOT Goal 3 - Average Units",
    "org": "NOCCCD Credit Colleges",
    "headcount_title": "Average Number of Units Earned by ADT Recipients",
    "headcount_caption": (
        "The average cumulative units earned by students awarded associate "
        "degrees for transfer at Cypress College and Fullerton College in "
        "the reporting year."
    ),
    "race_title": "Average Units Earned by Race/Ethnicity",
    "race_caption": (
        "Among students awarded ADTs at NOCCCD credit colleges in the "
        "reporting year, the average cumulative units earned by race/ethnicity."
    ),
    "gender_title": "Average Units Earned by Gender",
    "gender_caption": (
        "Among students awarded ADTs at NOCCCD credit colleges in the "
        "reporting year, the average cumulative units earned by gender."
    ),
    "firstgen_title": "Average Units Earned by First-Generation College Status",
    "firstgen_caption": (
        "Among students awarded ADTs at Cypress and Fullerton Colleges in "
        "the reporting year, the average cumulative units earned by "
        "first-generation college status."
    ),
}


# ---------------------------------------------------------------------------
# Aggregations — mean of sum_hours_earned within each group
# ---------------------------------------------------------------------------

def _mean_by(df: pd.DataFrame, group_cols: list[str]) -> pd.DataFrame:
    stu = df.drop_duplicates(subset=["pidm", "academic_year"])
    return (
        stu.groupby(group_cols)["sum_hours_earned"]
        .mean()
        .reset_index(name="avg_units")
    )


def _aggregate_campus(df):
    by_campus = _mean_by(df, ["academic_year", "camp_desc"])
    # NOCCCD (Unduplicated): mean across ADT recipients at both credit
    # campuses combined per academic year.
    stu = df.drop_duplicates(subset=["pidm", "academic_year"])
    nocccd = (
        stu.groupby("academic_year")["sum_hours_earned"]
        .mean()
        .reset_index(name="avg_units")
    )
    nocccd["camp_desc"] = "NOCCCD (Unduplicated)"
    out = pd.concat([by_campus, nocccd], ignore_index=True)
    out["camp_desc"] = pd.Categorical(
        out["camp_desc"], categories=CAMPUS_ORDER, ordered=True,
    )
    return out.sort_values(["academic_year", "camp_desc"])


def _aggregate_race(df):
    stu = df.drop_duplicates(subset=["pidm", "academic_year"])
    return (
        stu.groupby(["academic_year", "race_description"])
        .agg(
            avg_units=("sum_hours_earned", "mean"),
            count=("pidm", "nunique"),
        )
        .reset_index()
    )


def _visible_categories(df, key_col, order, threshold=10):
    """Filter *order* by first-year OR last-year count >= threshold.

    A category is hidden only when BOTH the first and last year's counts
    are below the threshold.
    """
    if df.empty or "count" not in df.columns:
        return list(order)
    years = sorted(df["academic_year"].dropna().unique())
    if len(years) < 2:
        max_by_cat = df.groupby(key_col)["count"].max()
        return [c for c in order if max_by_cat.get(c, 0) >= threshold]
    first_yr, last_yr = years[0], years[-1]
    first_counts = (
        df[df["academic_year"] == first_yr].set_index(key_col)["count"]
    )
    last_counts = (
        df[df["academic_year"] == last_yr].set_index(key_col)["count"]
    )

    def _keep(c):
        fc = first_counts.get(c, 0) or 0
        lc = last_counts.get(c, 0) or 0
        return fc >= threshold or lc >= threshold

    return [c for c in order if _keep(c)]


def _visible_races(df_race, threshold=10):
    return _visible_categories(df_race, "race_description", RACE_ORDER,
                               threshold)


def _visible_genders(df_gender, threshold=10):
    return _visible_categories(df_gender, "gender", GENDER_ORDER, threshold)


def _aggregate_gender(df):
    stu = df.drop_duplicates(subset=["pidm", "academic_year"])
    out = (
        stu.groupby(["academic_year", "gender"])
        .agg(
            avg_units=("sum_hours_earned", "mean"),
            count=("pidm", "nunique"),
        )
        .reset_index()
    )
    out["gender_label"] = out["gender"].map(GENDER_LABELS)
    return out


def _aggregate_firstgen(df):
    stu = df.drop_duplicates(subset=["pidm", "academic_year"]).copy()
    stu["fg"] = stu["first_gen_ind"].where(
        stu["first_gen_ind"].isin(["Y", "N"]), "Unknown",
    )
    out = (
        stu.groupby(["academic_year", "fg"])["sum_hours_earned"]
        .mean()
        .reset_index(name="avg_units")
    )
    out["fg_label"] = out["fg"].map(FIRSTGEN_LABELS)
    return out


def _pct_change(df_agg, group_col="camp_desc", order=None):
    """5-yr % change in average units per group."""
    rows = []
    keys = order if order is not None else sorted(df_agg[group_col].unique())
    for key in keys:
        grp = df_agg[df_agg[group_col] == key].sort_values("academic_year")
        grp = grp[grp["avg_units"].notna() & (grp["avg_units"] > 0)]
        if len(grp) < 2:
            continue
        first = grp.iloc[0]["avg_units"]
        last = grp.iloc[-1]["avg_units"]
        rows.append({
            group_col: key,
            "pct_change": round((last - first) / first * 100, 1),
        })
    return pd.DataFrame(rows) if rows else pd.DataFrame()


# ---------------------------------------------------------------------------
# Plotly charts
# ---------------------------------------------------------------------------

def _build_campus_chart(df_avg):
    years = sorted(df_avg["academic_year"].unique())
    fig = px.bar(
        df_avg,
        x="academic_year",
        y="avg_units",
        color="camp_desc",
        barmode="group",
        text="avg_units",
        color_discrete_map=COLOR_MAP,
        category_orders={"camp_desc": CAMPUS_ORDER, "academic_year": years},
    )
    fig.update_traces(texttemplate="%{text:.1f}", textposition="outside")
    fig.update_layout(
        height=420,
        xaxis_title=None,
        yaxis_title=None,
        yaxis=dict(showticklabels=False),
        legend_title=None,
        legend=dict(orientation="h", yanchor="top", y=-0.18,
                    xanchor="center", x=0.5),
        uniformtext_minsize=8,
        uniformtext_mode="hide",
        margin=dict(l=10, t=30),
    )
    return fig


def _build_pct_change_chart(df_pct):
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
    fig.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
    min_val = df_pct["pct_change"].min()
    max_val = df_pct["pct_change"].max()
    fig.update_layout(
        height=420,
        showlegend=False,
        title="5-Yr % Change",
        xaxis_title="% Change",
        xaxis_range=[
            min_val * 1.8 if min_val < 0 else min_val - 5,
            max_val * 1.8 if max_val > 0 else max_val + 5,
        ],
        yaxis_title=None,
        margin=dict(l=10, t=50),
    )
    return fig


def _build_race_html(df_race, years):
    """Inline data-bar table showing avg units per race per year."""
    piv = df_race.pivot_table(
        index="race_description", columns="academic_year",
        values="avg_units", aggfunc="first",
    )
    max_val = piv.max().max() if not piv.empty else 1.0
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
        bar_color = RACE_COLORS.get(race, "#888")
        rows.append("<tr>")
        rows.append(
            f"<td style='text-align:right; padding:4px 8px; "
            f"white-space:nowrap; font-weight:bold;'>{label}</td>"
        )
        for yr in years:
            val = piv.loc[race, yr] if (
                race in piv.index and yr in piv.columns
            ) else None
            if val is None or pd.isna(val):
                rows.append("<td style='padding:4px 4px;'></td>")
                continue
            bar_w = val / max_val * 100 if max_val > 0 else 0
            rows.append(
                f"<td style='padding:3.6px 4px; min-width:80px;'>"
                f"<div style='background:{bar_color}; width:{bar_w:.0f}%; "
                f"padding:2.6px 6px; color:light-dark(#000000, #FFFFFF); "
                f"font-size:12px; white-space:nowrap; border-radius:2px;'>"
                f"{val:.1f}</div></td>"
            )
        rows.append("</tr>")
    rows.append("</tbody></table>")
    return "\n".join(rows)


def _build_summary_html(
    order, label_map, color_map, piv, first_yr, last_yr,
):
    """Summary: first year avg / last year avg / 5-yr % change."""
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
        f"border-bottom:2px solid #555;'>{first_yr}<br>Avg Units</th>"
    )
    rows.append(
        f"<th style='text-align:center; padding:6px 8px; "
        f"border-bottom:2px solid #555;'>{last_yr}<br>Avg Units</th>"
    )
    rows.append(
        "<th style='text-align:center; padding:6px 8px; "
        "border-bottom:2px solid #555;'>5-Yr %<br>Change</th>"
    )
    rows.append("</tr></thead><tbody>")
    cell_style = (
        "padding:4px 8px; color:light-dark(#000000, #FFFFFF); "
        "background:{bg}; text-align:right; "
        "border-bottom:1px solid #444;"
    )

    for key in order:
        label = label_map.get(key, key) if label_map else key
        color = color_map.get(label, color_map.get(key, "#888"))
        fv = piv.loc[key, first_yr] if (
            key in piv.index and first_yr in piv.columns
            and pd.notna(piv.loc[key, first_yr])
        ) else None
        lv = piv.loc[key, last_yr] if (
            key in piv.index and last_yr in piv.columns
            and pd.notna(piv.loc[key, last_yr])
        ) else None
        fc = f"{fv:.1f}" if fv is not None else ""
        lc = f"{lv:.1f}" if lv is not None else ""
        if fv and lv and fv > 0:
            chg = (lv - fv) / fv * 100
            chg_str = f"{chg:+.0f}%"
        else:
            chg_str = ""
        rows.append("<tr>")
        rows.append(f"<td style='{cell_style.format(bg=color)}'>{fc}</td>")
        rows.append(f"<td style='{cell_style.format(bg=color)}'>{lc}</td>")
        rows.append(
            f"<td style='text-align:right; padding:4px 8px; "
            f"font-weight:bold; color:light-dark(#000000, #FFFFFF); "
            f"background:{color}; "
            f"border-bottom:1px solid #444;'>{chg_str}</td>"
        )
        rows.append("</tr>")
    rows.append("</tbody></table>")
    return "\n".join(rows)


def _build_race_summary(df_race, years):
    if len(years) < 2:
        return ""
    piv = df_race.pivot_table(
        index="race_description", columns="academic_year",
        values="avg_units", aggfunc="first",
    )
    return _build_summary_html(
        _visible_races(df_race), RACE_SHORT, RACE_COLORS,
        piv, years[0], years[-1],
    )


def _build_gender_chart(df_gender, years):
    visible = _visible_genders(df_gender)
    df_plot = df_gender[df_gender["gender"].isin(visible)].copy()
    labels = [GENDER_LABELS[g] for g in visible]
    df_plot["gender_label"] = pd.Categorical(
        df_plot["gender_label"], categories=labels, ordered=True,
    )
    fig = px.bar(
        df_plot.sort_values(["academic_year", "gender_label"]),
        x="avg_units",
        y="academic_year",
        color="gender_label",
        orientation="h",
        barmode="group",
        text="avg_units",
        color_discrete_map=GENDER_COLORS,
        category_orders={
            "academic_year": list(reversed(years)),
            "gender_label": list(reversed(labels)),
        },
    )
    fig.update_traces(texttemplate="%{text:.1f}", textposition="outside")
    max_v = df_plot["avg_units"].max() if not df_plot.empty else 100
    fig.update_layout(
        height=420,
        xaxis_title=None,
        xaxis=dict(range=[0, max_v * 1.2 if pd.notna(max_v) else 100]),
        yaxis_title=None,
        legend_title=None,
        legend=dict(orientation="h", yanchor="top", y=-0.1,
                    xanchor="center", x=0.5),
        margin=dict(t=10),
    )
    return fig


def _build_gender_summary(df_gender, years):
    if len(years) < 2:
        return ""
    piv = df_gender.pivot_table(
        index="gender", columns="academic_year",
        values="avg_units", aggfunc="first",
    )
    return _build_summary_html(
        _visible_genders(df_gender), GENDER_LABELS, GENDER_COLORS,
        piv, years[0], years[-1],
    )


def _build_firstgen_chart(df_fg, years):
    labels = [FIRSTGEN_LABELS[g] for g in FIRSTGEN_ORDER]
    fig = px.line(
        df_fg,
        x="academic_year",
        y="avg_units",
        color="fg_label",
        text="avg_units",
        markers=True,
        color_discrete_map=FIRSTGEN_COLORS,
        category_orders={"academic_year": years, "fg_label": labels},
    )
    fig.update_traces(
        texttemplate="%{y:.1f}",
        textposition="top center",
        mode="lines+markers+text",
    )
    # Zoom y-axis to actual data range so lines are visually separated.
    min_v = df_fg["avg_units"].min() if not df_fg.empty else 0
    max_v = df_fg["avg_units"].max() if not df_fg.empty else 100
    pad = max((max_v - min_v) * 0.25, 2)
    fig.update_layout(
        height=420,
        xaxis_title=None,
        yaxis_title=None,
        yaxis=dict(
            range=[max(0, min_v - pad), max_v + pad]
                  if pd.notna(min_v) else [0, 100],
            showticklabels=False,
        ),
        legend_title=None,
        legend=dict(orientation="h", yanchor="top", y=-0.15,
                    xanchor="center", x=0.5),
        margin=dict(t=10),
    )
    return fig


def _build_firstgen_summary(df_fg, years):
    if len(years) < 2:
        return ""
    piv = df_fg.pivot_table(
        index="fg", columns="academic_year",
        values="avg_units", aggfunc="first",
    )
    return _build_summary_html(
        FIRSTGEN_ORDER, FIRSTGEN_LABELS, FIRSTGEN_COLORS,
        piv, years[0], years[-1],
    )


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


def _draw_section_source(fig, y):
    fig.text(0.06, y, "Source: Banner", fontsize=7, color="grey", va="top")


def _mpl_campus(fig, bbox, df_agg, df_pct):
    left, bottom, width, height = bbox
    ax_bar = fig.add_axes([left, bottom, width * 0.55, height])
    ax_pct = fig.add_axes([left + width * 0.72, bottom, width * 0.26, height])

    years = sorted(df_agg["academic_year"].unique())
    campuses = [c for c in CAMPUS_ORDER
                if c in df_agg["camp_desc"].values]
    n_groups = len(years)
    n_bars = len(campuses)
    bar_w = 0.8 / max(n_bars, 1)

    for i, camp in enumerate(campuses):
        vals = []
        for yr in years:
            row = df_agg[(df_agg["camp_desc"] == camp)
                         & (df_agg["academic_year"] == yr)]
            vals.append(row["avg_units"].iloc[0] if not row.empty else 0)
        xs = np.arange(n_groups) + (i - (n_bars - 1) / 2) * bar_w
        ax_bar.bar(xs, vals, width=bar_w,
                   color=COLOR_MAP.get(camp, "#888"), label=camp)
        for x, v in zip(xs, vals):
            if v > 0:
                ax_bar.text(x, v, f"{v:.1f}", ha="center",
                            va="bottom", fontsize=6)

    ax_bar.set_xticks(range(n_groups))
    ax_bar.set_xticklabels(years, fontsize=7)
    ax_bar.tick_params(axis="y", labelsize=7)
    ax_bar.spines["top"].set_visible(False)
    ax_bar.spines["right"].set_visible(False)
    ax_bar.legend(fontsize=6, loc="upper center",
                  bbox_to_anchor=(0.5, -0.08), ncol=n_bars, frameon=False)
    ymax = df_agg["avg_units"].max() if not df_agg.empty else 0
    ax_bar.set_ylim(0, ymax * 1.15 if ymax else 1)

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
        for y_, v in zip(ys, vals):
            ha = "left" if v >= 0 else "right"
            offset = 0.5 if v >= 0 else -0.5
            ax_pct.text(v + offset, y_, f"{v:.1f}%", va="center",
                        ha=ha, fontsize=6)
        ax_pct.set_yticks(ys)
        ax_pct.set_yticklabels(pct_campuses, fontsize=6)
        ax_pct.tick_params(axis="x", labelsize=6)
        ax_pct.set_title("5-Yr % Change", fontsize=8, fontweight="bold")
        ax_pct.spines["top"].set_visible(False)
        ax_pct.spines["right"].set_visible(False)
        ax_pct.axvline(0, color="#888", linewidth=0.5)
        min_v, max_v = min(vals), max(vals)
        ax_pct.set_xlim(
            min_v * 1.8 if min_v < 0 else min_v - 5,
            max_v * 1.8 if max_v > 0 else max_v + 5,
        )
    else:
        ax_pct.axis("off")


def _mpl_race_table(fig, bbox, df_race, years):
    left, bottom, width, height = bbox
    ax = fig.add_axes([left, bottom, width, height])
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")

    piv = df_race.pivot_table(
        index="race_description", columns="academic_year",
        values="avg_units", aggfunc="first",
    )
    max_val = piv.max().max() if not piv.empty else 1.0

    visible = _visible_races(df_race)
    n_rows = len(visible) + 1
    row_h = 1.0 / n_rows
    label_col_w = 0.30
    data_col_w = (1.0 - label_col_w) / len(years)

    y_top = 1.0 - row_h
    for i, yr in enumerate(years):
        x = label_col_w + i * data_col_w
        ax.text(x + data_col_w / 2, y_top + row_h / 2, yr,
                ha="center", va="center", fontsize=7, fontweight="bold")

    for r, race in enumerate(visible):
        y = 1.0 - (r + 2) * row_h
        label = RACE_SHORT.get(race, race)
        ax.text(label_col_w - 0.01, y + row_h / 2, label,
                ha="right", va="center", fontsize=7, fontweight="bold")
        bar_color = RACE_COLORS.get(race, "#888")
        for i, yr in enumerate(years):
            val = piv.loc[race, yr] if (
                race in piv.index and yr in piv.columns
            ) else None
            if val is None or pd.isna(val):
                continue
            cell_x = label_col_w + i * data_col_w
            bar_w = (val / max_val) * data_col_w if max_val > 0 else 0
            ax.add_patch(Rectangle(
                (cell_x + 0.002, y + row_h * 0.15),
                bar_w - 0.004, row_h * 0.7,
                facecolor=bar_color, edgecolor="none",
            ))
            ax.text(cell_x + 0.006, y + row_h / 2, f"{val:.1f}",
                    ha="left", va="center", fontsize=6, color="black",
                    fontweight="bold")


def _mpl_summary_table(fig, bbox, order, label_map, color_map, piv,
                       first_yr, last_yr):
    left, bottom, width, height = bbox
    ax = fig.add_axes([left, bottom, width, height])
    ax.axis("off")

    headers = [
        f"{first_yr}\nAvg Units",
        f"{last_yr}\nAvg Units",
        "5-Yr %\nChange",
    ]
    rows = []
    cell_colors = []
    for key in order:
        label = label_map.get(key, key) if label_map else key
        color = color_map.get(label, color_map.get(key, "#888"))
        fv = piv.loc[key, first_yr] if (
            key in piv.index and first_yr in piv.columns
            and pd.notna(piv.loc[key, first_yr])
        ) else None
        lv = piv.loc[key, last_yr] if (
            key in piv.index and last_yr in piv.columns
            and pd.notna(piv.loc[key, last_yr])
        ) else None
        fc = f"{fv:.1f}" if fv is not None else ""
        lc = f"{lv:.1f}" if lv is not None else ""
        chg_str = (
            f"{(lv - fv) / fv * 100:+.0f}%"
            if fv and lv and fv > 0 else ""
        )
        rows.append([fc, lc, chg_str])
        cell_colors.append([color, color, color])

    tbl = ax.table(
        cellText=rows, colLabels=headers, cellColours=cell_colors,
        cellLoc="right", colLoc="center", loc="center",
    )
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(7)
    tbl.scale(1, 1.6)
    for col_idx in range(len(headers)):
        cell = tbl[(0, col_idx)]
        cell.set_fontsize(7)
        cell.set_text_props(fontweight="bold")
        cell.set_facecolor("#FFFFFF")
    for row_idx in range(1, len(rows) + 1):
        for col_idx in range(len(headers)):
            cell = tbl[(row_idx, col_idx)]
            cell.set_text_props(color="black", fontweight="bold")


def _mpl_race_summary(fig, bbox, df_race, years):
    if len(years) < 2:
        return
    piv = df_race.pivot_table(
        index="race_description", columns="academic_year",
        values="avg_units", aggfunc="first",
    )
    _mpl_summary_table(fig, bbox, _visible_races(df_race),
                       RACE_SHORT, RACE_COLORS,
                       piv, years[0], years[-1])


def _mpl_gender_chart(fig, bbox, df_gender, years):
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
            vals.append(row["avg_units"].iloc[0] if not row.empty else 0)
        ys = np.arange(n_years) + (i - (n_genders - 1) / 2) * bar_h
        color = GENDER_COLORS.get(g_label, "#888")
        ax.barh(ys, vals, height=bar_h, color=color, label=g_label)
        for y_, v in zip(ys, vals):
            if pd.notna(v) and v > 0:
                ax.text(v, y_, f"{v:.1f}", va="center",
                        ha="left", fontsize=5)

    ax.set_yticks(range(n_years))
    ax.set_yticklabels(years, fontsize=7)
    ax.tick_params(axis="x", labelsize=6)
    max_v = df_gender["avg_units"].max() if not df_gender.empty else 100
    ax.set_xlim(0, max_v * 1.2 if pd.notna(max_v) else 100)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.legend(fontsize=6, loc="upper center",
              bbox_to_anchor=(0.5, -0.08), ncol=n_genders, frameon=False)


def _mpl_gender_summary(fig, bbox, df_gender, years):
    if len(years) < 2:
        return
    piv = df_gender.pivot_table(
        index="gender", columns="academic_year",
        values="avg_units", aggfunc="first",
    )
    _mpl_summary_table(fig, bbox, _visible_genders(df_gender),
                       GENDER_LABELS, GENDER_COLORS,
                       piv, years[0], years[-1])


def _mpl_firstgen_chart(fig, bbox, df_fg, years):
    left, bottom, width, height = bbox
    ax = fig.add_axes([left, bottom, width, height])

    for fg in FIRSTGEN_ORDER:
        label = FIRSTGEN_LABELS[fg]
        color = FIRSTGEN_COLORS.get(label, "#888")
        vals = []
        for yr in years:
            row = df_fg[(df_fg["fg"] == fg)
                        & (df_fg["academic_year"] == yr)]
            vals.append(row["avg_units"].iloc[0] if not row.empty else None)
        xs = list(range(len(years)))
        ax.plot(xs, vals, marker="o", color=color, label=label, linewidth=1.5)
        for x, v in zip(xs, vals):
            if v is not None and pd.notna(v):
                ax.annotate(f"{v:.1f}", (x, v), textcoords="offset points",
                            xytext=(0, 6), ha="center", fontsize=6)

    ax.set_xticks(range(len(years)))
    ax.set_xticklabels(years, fontsize=7)
    ax.tick_params(axis="y", labelsize=6)
    min_v = df_fg["avg_units"].min() if not df_fg.empty else 0
    max_v = df_fg["avg_units"].max() if not df_fg.empty else 100
    pad = max((max_v - min_v) * 0.25, 2)
    if pd.notna(min_v):
        ax.set_ylim(max(0, min_v - pad), max_v + pad)
    else:
        ax.set_ylim(0, 100)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.grid(axis="y", alpha=0.3)
    ax.legend(fontsize=6, loc="upper center",
              bbox_to_anchor=(0.5, -0.08), ncol=3, frameon=False)


def _mpl_firstgen_summary(fig, bbox, df_fg, years):
    if len(years) < 2:
        return
    piv = df_fg.pivot_table(
        index="fg", columns="academic_year",
        values="avg_units", aggfunc="first",
    )
    _mpl_summary_table(fig, bbox, FIRSTGEN_ORDER, FIRSTGEN_LABELS,
                       FIRSTGEN_COLORS, piv, years[0], years[-1])


def _generate_pdf(df) -> bytes:
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
    year_range = (
        f"{years[0]} to {years[-1]}" if len(years) >= 2
        else years[0] if years else ""
    )

    df_campus = _aggregate_campus(df)
    df_pct = _pct_change(df_campus, "camp_desc", CAMPUS_ORDER)
    df_race = _aggregate_race(df)
    df_gender = _aggregate_gender(df)
    df_fg = _aggregate_firstgen(df)
    tab_title = _TITLES["tab_title"]

    buf = io.BytesIO()
    with PdfPages(buf) as pdf:
        # Page 1
        fig = plt.figure(figsize=(PAGE_W, PAGE_H))
        fig.text(0.5, 0.97, tab_title, fontsize=14, fontweight="bold",
                 ha="center", va="top")

        # Section 1: chart bottom raised to 0.58 so legend sits above
        # "Source: Banner" with a clear gap.
        y_after = _draw_section_header(
            fig, 0.935, _TITLES["org"], _TITLES["headcount_title"],
            year_range, _TITLES["headcount_caption"],
        )
        _mpl_campus(fig, (0.06, 0.58, 0.88, y_after - 0.58),
                    df_campus, df_pct)
        _draw_section_source(fig, 0.54)

        # Section 2: raised to 0.50 with tight caption-to-chart padding
        # since the race table has no axis title to overlap.
        y_after = _draw_section_header(
            fig, 0.50, _TITLES["org"], _TITLES["race_title"],
            year_range, _TITLES["race_caption"],
            pad=0.005,
        )
        _mpl_race_table(fig, (0.06, 0.06, 0.54, y_after - 0.06),
                        df_race, years)
        _mpl_race_summary(fig, (0.62, 0.06, 0.32, y_after - 0.06),
                          df_race, years)
        _draw_section_source(fig, 0.04)

        _add_pdf_footer(fig)
        pdf.savefig(fig)
        plt.close(fig)

        # Page 2
        fig = plt.figure(figsize=(PAGE_W, PAGE_H))
        fig.text(0.5, 0.97, tab_title, fontsize=14, fontweight="bold",
                 ha="center", va="top")

        y_after = _draw_section_header(
            fig, 0.935, _TITLES["org"], _TITLES["gender_title"],
            year_range, _TITLES["gender_caption"],
        )
        _mpl_gender_chart(fig, (0.12, 0.56, 0.48, y_after - 0.56),
                          df_gender, years)
        _mpl_gender_summary(fig, (0.62, 0.56, 0.32, y_after - 0.56),
                            df_gender, years)
        _draw_section_source(fig, 0.52)

        y_after = _draw_section_header(
            fig, 0.48, _TITLES["org"], _TITLES["firstgen_title"],
            year_range, _TITLES["firstgen_caption"],
        )
        # Raise chart bottom so legend has room above "Source: Banner".
        # Matches the shared BOT layout in bot_helpers.py.
        _mpl_firstgen_chart(fig, (0.06, 0.13, 0.54, y_after - 0.13),
                            df_fg, years)
        _mpl_firstgen_summary(fig, (0.62, 0.13, 0.32, y_after - 0.13),
                              df_fg, years)
        _draw_section_source(fig, 0.085)

        _add_pdf_footer(fig)
        pdf.savefig(fig)
        plt.close(fig)

    return buf.getvalue()


# ---------------------------------------------------------------------------
# Streamlit render
# ---------------------------------------------------------------------------

_SOURCE_FOOTER = (
    "<div style='text-align:left'><small>Source: Banner</small></div>"
)


def render():
    st.header("BOT Goal 3 - Average Units")

    selected_acyrs = st.sidebar.multiselect(
        "Academic Years",
        options=_DEFAULT_ACYRS,
        default=_DEFAULT_ACYRS,
        key="bg3u_acyr_codes",
    )
    query_btn = st.sidebar.button("Query", key="bg3u_query_btn")

    if query_btn:
        if not selected_acyrs:
            st.warning("Select at least one academic year.")
            return
        fetch_bot_goal3_units.clear()
        df = fetch_bot_goal3_units(tuple(sorted(selected_acyrs)))
        if df.empty:
            st.warning("No data returned for the selected academic years.")
            return
        st.session_state["bg3u_df"] = df

    if "bg3u_df" in st.session_state:
        pdf_bytes = _generate_pdf(st.session_state["bg3u_df"])
        st.sidebar.download_button(
            "Download PDF", data=pdf_bytes,
            file_name="bot_goal3_units.pdf", mime="application/pdf",
            key="bg3u_pdf_btn",
        )

    if "bg3u_df" not in st.session_state:
        st.info("Select Academic Years and press **Query** to load data.")
        return

    df = st.session_state["bg3u_df"]
    years = sorted(df["academic_year"].dropna().unique())
    year_range = (
        f"{years[0]} to {years[-1]}" if len(years) >= 2
        else years[0] if years else ""
    )

    # Chart 1: Average units by campus
    st.subheader(_TITLES["org"])
    st.markdown(f"**{_TITLES['headcount_title']}**  \n{year_range}")
    st.caption(_TITLES["headcount_caption"])

    df_campus = _aggregate_campus(df)
    df_pct = _pct_change(df_campus, "camp_desc", CAMPUS_ORDER)

    col_main, col_pct = st.columns([3, 1])
    with col_main:
        st.plotly_chart(_build_campus_chart(df_campus),
                        use_container_width=True)
    with col_pct:
        if not df_pct.empty:
            st.plotly_chart(_build_pct_change_chart(df_pct),
                            use_container_width=True)
        else:
            st.info("Need at least 2 years for % change.")
    st.markdown(_SOURCE_FOOTER, unsafe_allow_html=True)

    # Chart 2: Avg units by race
    st.divider()
    st.subheader(_TITLES["org"])
    st.markdown(f"**{_TITLES['race_title']}**  \n{year_range}")
    st.caption(_TITLES["race_caption"])
    df_race = _aggregate_race(df)

    col_prop, col_summary = st.columns([3, 2])
    with col_prop:
        st.markdown(_build_race_html(df_race, years),
                    unsafe_allow_html=True)
    with col_summary:
        html = _build_race_summary(df_race, years)
        if html:
            st.markdown(html, unsafe_allow_html=True)
    st.markdown(_SOURCE_FOOTER, unsafe_allow_html=True)

    # Chart 3: Avg units by gender
    st.divider()
    st.subheader(_TITLES["org"])
    st.markdown(f"**{_TITLES['gender_title']}**  \n{year_range}")
    st.caption(_TITLES["gender_caption"])
    df_gender = _aggregate_gender(df)

    col_gc, col_gs = st.columns([3, 2])
    with col_gc:
        st.plotly_chart(_build_gender_chart(df_gender, years),
                        use_container_width=True)
    with col_gs:
        html = _build_gender_summary(df_gender, years)
        if html:
            st.markdown(html, unsafe_allow_html=True)
    st.markdown(_SOURCE_FOOTER, unsafe_allow_html=True)

    # Chart 4: Avg units by first-gen
    st.divider()
    st.subheader(_TITLES["org"])
    st.markdown(f"**{_TITLES['firstgen_title']}**  \n{year_range}")
    st.caption(_TITLES["firstgen_caption"])
    df_fg = _aggregate_firstgen(df)

    col_fc, col_fs = st.columns([3, 2])
    with col_fc:
        st.plotly_chart(_build_firstgen_chart(df_fg, years),
                        use_container_width=True)
    with col_fs:
        html = _build_firstgen_summary(df_fg, years)
        if html:
            st.markdown(html, unsafe_allow_html=True)
    st.markdown(_SOURCE_FOOTER, unsafe_allow_html=True)
