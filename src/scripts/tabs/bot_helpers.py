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
import streamlit as st
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.patches import Rectangle

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
    for camp in CAMPUS_ORDER:
        grp = df_agg[df_agg["camp_desc"] == camp].sort_values("academic_year")
        grp = grp[grp["headcount"] > 0]
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


# Categories whose first-year AND last-year counts both fall below this
# threshold are suppressed from proportion charts and summary tables
# (if either boundary year is >= threshold, the category is still shown).
CATEGORY_MIN_COUNT = 10
# Legacy alias kept for backward compatibility
RACE_MIN_COUNT = CATEGORY_MIN_COUNT


def _visible_categories(df, key_col, order,
                        threshold: int = CATEGORY_MIN_COUNT) -> list:
    """Return *order* filtered to categories where first-year OR last-year count >= threshold.

    A category is hidden only when BOTH the first and last year's counts
    are below the threshold; middle years are ignored by this rule.
    """
    if df is None or df.empty or "count" not in df.columns:
        return list(order)
    years = sorted(df["academic_year"].dropna().unique())
    if len(years) < 2:
        max_by_cat = df.groupby(key_col)["count"].max()
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
        return fc >= threshold or lc >= threshold

    return [c for c in order if _keep(c)]


def _visible_races(df_race: pd.DataFrame,
                   threshold: int = CATEGORY_MIN_COUNT) -> list[str]:
    return _visible_categories(df_race, "race_description", RACE_ORDER,
                               threshold)


def _visible_genders(df_gender: pd.DataFrame,
                     threshold: int = CATEGORY_MIN_COUNT) -> list[str]:
    return _visible_categories(df_gender, "gender", GENDER_ORDER, threshold)


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
    stu = subset.drop_duplicates(subset=["pidm", "academic_year"])
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
        base_stu = base_subset.drop_duplicates(subset=["pidm", "academic_year"])
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

def build_headcount_chart(df_agg: pd.DataFrame):
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
    fig.update_traces(texttemplate="%{text:,}", textposition="outside")
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
    if len(years) < 2:
        return ""
    piv = df_race.pivot_table(
        index="race_description", columns="academic_year",
        values="count", aggfunc="first",
    )
    return _build_summary_table(
        _visible_races(df_race), RACE_SHORT, RACE_COLORS,
        piv, years[0], years[-1],
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
    fig.update_traces(texttemplate="%{text:.1%}", textposition="outside")
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
    if len(years) < 2:
        return ""
    piv = df_gender.pivot_table(
        index="gender", columns="academic_year",
        values="count", aggfunc="first",
    )
    return _build_summary_table(
        _visible_genders(df_gender), GENDER_LABELS, GENDER_COLORS,
        piv, years[0], years[-1],
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
    if len(years) < 2:
        return ""
    piv = df_fg.pivot_table(
        index="fg", columns="academic_year",
        values="count", aggfunc="first",
    )
    return _build_summary_table(
        FIRSTGEN_ORDER, FIRSTGEN_LABELS, FIRSTGEN_COLORS,
        piv, years[0], years[-1],
    )


# ---------------------------------------------------------------------------
# Shared render layout
# ---------------------------------------------------------------------------

_SOURCE_FOOTER = (
    "<div style='text-align:left'><small>Source: Banner</small></div>"
)


def render_bot_charts(
    df: pd.DataFrame, titles: dict,
    base_df: pd.DataFrame | None = None,
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
        firstgen_note (optional, None to skip)
        include_nocccd (optional, default True) — show NOCCCD unduplicated bar
        credit_only_firstgen (optional, default True) — filter first-gen to credit
        headcount_only (optional, default False) — show only chart 1, skip race/gender/first-gen
    """
    years = sorted(df["academic_year"].dropna().unique())
    year_range = (
        f"{years[0]} to {years[-1]}" if len(years) >= 2
        else years[0] if years else ""
    )
    org = titles["org"]

    # --- Chart 1: Headcount by Campus ---
    st.subheader(org)
    st.markdown(f"**{titles['headcount_title']}**  \n{year_range}")
    st.caption(titles["headcount_caption"])
    df_agg = aggregate_headcount(
        df, include_nocccd=titles.get("include_nocccd", True),
    )
    df_pct = compute_pct_change(df_agg)

    col_main, col_pct = st.columns([3, 1])
    with col_main:
        st.plotly_chart(build_headcount_chart(df_agg), use_container_width=True)
    with col_pct:
        if not df_pct.empty:
            st.plotly_chart(
                build_pct_change_chart(df_pct), use_container_width=True,
            )
        else:
            st.info("Need at least 2 years for % change.")
    st.markdown(_SOURCE_FOOTER, unsafe_allow_html=True)

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
    st.markdown(_SOURCE_FOOTER, unsafe_allow_html=True)

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
            use_container_width=True,
        )
    with col_gs:
        html = build_gender_summary_html(df_gender, years)
        if html:
            st.markdown(html, unsafe_allow_html=True)
    st.markdown(_SOURCE_FOOTER, unsafe_allow_html=True)

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
            use_container_width=True,
        )
    with col_fs:
        html = build_firstgen_summary_html(df_fg, years)
        if html:
            st.markdown(html, unsafe_allow_html=True)
    st.markdown(_SOURCE_FOOTER, unsafe_allow_html=True)
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


def _draw_section_header(fig, section_top, org, title, year_range, caption):
    """Draw section header (org, title, year range, caption) at paper coords."""
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
    return y - 0.022 * (wrapped.count("\n") + 1)


def _draw_section_source(fig, y):
    fig.text(0.06, y, "Source: Banner", fontsize=7, color="grey", va="top")


def _mpl_headcount(fig, bbox, df_agg, df_pct):
    """Draw grouped bar (counts) + horizontal bar (5-yr % change) side by side.

    bbox = (left, bottom, width, height) in paper coords.
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

    for i, camp in enumerate(campuses):
        vals = []
        for yr in years:
            row = df_agg[(df_agg["camp_desc"] == camp)
                         & (df_agg["academic_year"] == yr)]
            vals.append(row["headcount"].iloc[0] if not row.empty else 0)
        xs = np.arange(n_groups) + (i - (n_bars - 1) / 2) * bar_w
        ax_bar.bar(xs, vals, width=bar_w,
                   color=COLOR_MAP.get(camp, "#888"), label=camp)
        for x, v in zip(xs, vals):
            if v > 0:
                ax_bar.text(x, v, f"{int(v):,}", ha="center",
                            va="bottom", fontsize=6)

    ax_bar.set_xticks(range(n_groups))
    ax_bar.set_xticklabels(years, fontsize=7)
    ax_bar.tick_params(axis="y", labelsize=7)
    ax_bar.spines["top"].set_visible(False)
    ax_bar.spines["right"].set_visible(False)
    ax_bar.legend(fontsize=6, loc="upper center",
                  bbox_to_anchor=(0.5, -0.08), ncol=n_bars, frameon=False)
    ymax = df_agg["headcount"].max() if not df_agg.empty else 0
    ax_bar.set_ylim(0, ymax * 1.15 if ymax else 1)

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
                ha="center", va="center", fontsize=7, fontweight="bold")

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
    if len(years) < 2:
        return
    piv = df_race.pivot_table(
        index="race_description", columns="academic_year",
        values="count", aggfunc="first",
    )
    _mpl_summary_table(fig, bbox, _visible_races(df_race),
                       RACE_SHORT, RACE_COLORS,
                       piv, years[0], years[-1])


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
                        ha="left", fontsize=5)

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
    if len(years) < 2:
        return
    piv = df_gender.pivot_table(
        index="gender", columns="academic_year",
        values="count", aggfunc="first",
    )
    _mpl_summary_table(fig, bbox, _visible_genders(df_gender),
                       GENDER_LABELS, GENDER_COLORS,
                       piv, years[0], years[-1])


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
    max_pct = df_fg["pct"].max() if not df_fg.empty else 0.5
    ax.set_ylim(0, max(max_pct * 1.4, 0.1) if pd.notna(max_pct) else 0.5)
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
        values="count", aggfunc="first",
    )
    _mpl_summary_table(fig, bbox, FIRSTGEN_ORDER, FIRSTGEN_LABELS,
                       FIRSTGEN_COLORS, piv, years[0], years[-1])


def generate_bot_pdf(df, titles, base_df=None) -> bytes:
    """Generate a portrait PDF with 2 BOT sections per page.

    Page 1: Headcount + Race
    Page 2: Gender + First-Gen
    If titles['headcount_only'] is True, only page 1 with just Headcount.
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
    year_range = (
        f"{years[0]} to {years[-1]}" if len(years) >= 2
        else years[0] if years else ""
    )
    headcount_only = titles.get("headcount_only", False)

    # Precompute aggregates
    df_agg = aggregate_headcount(
        df, include_nocccd=titles.get("include_nocccd", True))
    df_pct = compute_pct_change(df_agg)
    if not headcount_only:
        df_race = aggregate_race(df, base_df=base_df)
        df_gender = aggregate_gender(df, base_df=base_df)
        df_fg = aggregate_firstgen(
            df, credit_only=titles.get("credit_only_firstgen", True),
            base_df=base_df)

    buf = io.BytesIO()
    with PdfPages(buf) as pdf:
        # --- Page 1 ---
        fig = plt.figure(figsize=(PAGE_W, PAGE_H))
        tab_title = titles.get("tab_title", "BOT Goal")
        fig.text(0.5, 0.97, tab_title, fontsize=14, fontweight="bold",
                 ha="center", va="top")

        # Section 1: Headcount (top half)
        y_after_header = _draw_section_header(
            fig, 0.935, titles["org"], titles["headcount_title"],
            year_range, titles["headcount_caption"],
        )
        _mpl_headcount(
            fig,
            (0.06, 0.54, 0.88, y_after_header - 0.54),
            df_agg, df_pct,
        )
        _draw_section_source(fig, 0.52)

        if not headcount_only:
            # Section 2: Race (bottom half)
            y_after_header = _draw_section_header(
                fig, 0.48, titles["org"], titles["race_title"],
                year_range, titles["race_caption"],
            )
            # Chart area (left 60%)
            chart_bbox = (0.06, 0.06, 0.54, y_after_header - 0.06)
            _mpl_race_proportion_table(fig, chart_bbox, df_race, years)
            # Summary table (right 40%)
            table_bbox = (0.62, 0.06, 0.32, y_after_header - 0.06)
            _mpl_race_summary(fig, table_bbox, df_race, years)
            _draw_section_source(fig, 0.04)

        _add_pdf_footer(fig)
        pdf.savefig(fig)
        plt.close(fig)

        if headcount_only:
            return buf.getvalue()

        # --- Page 2: Gender + First-Gen ---
        fig = plt.figure(figsize=(PAGE_W, PAGE_H))
        fig.text(0.5, 0.97, tab_title, fontsize=14, fontweight="bold",
                 ha="center", va="top")

        # Section 3: Gender (top half) — shift chart right so long y-axis
        # year labels (e.g. "2024-2025") aren't clipped at the page edge.
        y_after_header = _draw_section_header(
            fig, 0.935, titles["org"], titles["gender_title"],
            year_range, titles["gender_caption"],
        )
        chart_bbox = (0.12, 0.56, 0.48, y_after_header - 0.56)
        _mpl_gender_chart(fig, chart_bbox, df_gender, years)
        table_bbox = (0.62, 0.56, 0.32, y_after_header - 0.56)
        _mpl_gender_summary(fig, table_bbox, df_gender, years)
        _draw_section_source(fig, 0.52)

        # Section 4: First-Gen (bottom half)
        fg_org = titles.get("firstgen_org", titles["org"])
        y_after_header = _draw_section_header(
            fig, 0.48, fg_org, titles["firstgen_title"],
            year_range, titles["firstgen_caption"],
        )
        chart_bbox = (0.06, 0.08, 0.54, y_after_header - 0.08)
        _mpl_firstgen_chart(fig, chart_bbox, df_fg, years)
        table_bbox = (0.62, 0.08, 0.32, y_after_header - 0.08)
        _mpl_firstgen_summary(fig, table_bbox, df_fg, years)
        _draw_section_source(fig, 0.06)

        if titles.get("firstgen_note"):
            note_wrapped = textwrap.fill(titles["firstgen_note"], width=140)
            fig.text(0.06, 0.04, note_wrapped,
                     fontsize=6, color="grey", va="top", style="italic")

        _add_pdf_footer(fig)
        pdf.savefig(fig)
        plt.close(fig)

    return buf.getvalue()
