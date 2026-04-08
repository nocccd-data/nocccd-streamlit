"""Shared chart builders and aggregation helpers for BOT (Board of Trustees) tabs.

Each BOT goal tab imports from this module and calls render_bot_charts()
with its own titles dict. This avoids duplicating ~600 lines per tab.
"""

import pandas as pd
import plotly.express as px
import streamlit as st

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
    for race in RACE_ORDER:
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
        RACE_ORDER, RACE_SHORT, RACE_COLORS, piv, years[0], years[-1],
    )


def build_gender_bar_chart(df_gender: pd.DataFrame, years: list[str]):
    df_plot = df_gender.copy()
    labels = [GENDER_LABELS[g] for g in GENDER_ORDER]
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
        GENDER_ORDER, GENDER_LABELS, GENDER_COLORS, piv, years[0], years[-1],
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
    fig.update_layout(
        height=420,
        xaxis_title=None,
        yaxis_title=None,
        yaxis=dict(
            tickformat=".0%",
            range=[0, max(df_fg["pct"].max() * 1.4, 0.1)],
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
