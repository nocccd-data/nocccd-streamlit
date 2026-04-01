import pandas as pd
import plotly.express as px
import streamlit as st

from src.pipeline.config import DATASETS
from src.scripts.data_provider import fetch_bot_goal1_students

_CFG = DATASETS["bot_goal1_students"]
_DEFAULT_ACYRS = _CFG[_CFG["param_name"]]

_COLOR_MAP = {
    "Cypress": "#50b913",
    "Fullerton": "#f99d40",
    "NOCE": "#004062",
    "NOCCCD (Unduplicated)": "#50b9c3",
}
_CAMPUS_ORDER = ["Cypress", "Fullerton", "NOCE", "NOCCCD (Unduplicated)"]


# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------

def _aggregate_headcount(df: pd.DataFrame) -> pd.DataFrame:
    """Distinct PIDM count per campus per academic year + NOCCCD unduplicated."""
    by_campus = (
        df.groupby(["academic_year", "camp_desc"])["pidm"]
        .nunique()
        .reset_index(name="headcount")
    )

    nocccd = (
        df.groupby("academic_year")["pidm"]
        .nunique()
        .reset_index(name="headcount")
    )
    nocccd["camp_desc"] = "NOCCCD (Unduplicated)"

    out = pd.concat([by_campus, nocccd], ignore_index=True)
    out["camp_desc"] = pd.Categorical(
        out["camp_desc"], categories=_CAMPUS_ORDER, ordered=True,
    )
    return out.sort_values(["academic_year", "camp_desc"])


def _compute_pct_change(df_agg: pd.DataFrame) -> pd.DataFrame:
    """5-year % change: (last - first) / first * 100 per campus."""
    rows: list[dict] = []
    for camp in _CAMPUS_ORDER:
        grp = df_agg[df_agg["camp_desc"] == camp].sort_values("academic_year")
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


_RACE_ORDER = [
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

_RACE_SHORT = {
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

# Year column header colors (cycle through NOCCCD palette)
_YEAR_COLORS = ["#50b9c3", "#004062", "#0081b7", "#f99d40", "#5faed3"]

# Bar colors per race/ethnicity
_RACE_COLORS = {
    "Hispanic or Latino": "#50b9c3",
    "Asian": "#004062",
    "White Non-Hispanic": "#0081b7",
    "Multiethnicity": "#5faed3",
    "Black or African American": "#f99d40",
    "Filipino": "#00b3a0",
    "American Indian or Alaska Native": "#11234f",
    "Pacific Islander or Native Hawaiian": "#575a5d",
    "Unreported": "#50b913",
}

# Gender constants
_GENDER_ORDER = ["F", "M", "NB", "N"]
_GENDER_LABELS = {"F": "Female", "M": "Male", "NB": "Non-Binary", "N": "Unknown"}
_GENDER_COLORS = {
    "Female": "#004062",
    "Male": "#5faed3",
    "Non-Binary": "#50b9c3",
    "Unknown": "#f99d40",
}


def _aggregate_race(df: pd.DataFrame) -> pd.DataFrame:
    """District-wide unduplicated PIDM count by race/ethnicity by academic year."""
    # Deduplicate to one row per pidm per academic year (district-level)
    stu = df.drop_duplicates(subset=["pidm", "academic_year"])
    by_race = (
        stu.groupby(["academic_year", "race_description"])
        .size()
        .reset_index(name="count")
    )
    totals = stu.groupby("academic_year").size().reset_index(name="total")
    out = by_race.merge(totals, on="academic_year")
    out["pct"] = out["count"] / out["total"]
    return out


def _build_race_proportion_html(df_race: pd.DataFrame, years: list[str]) -> str:
    """Table with inline data bars: race rows × year columns."""
    piv = df_race.pivot_table(
        index="race_description", columns="academic_year",
        values="pct", aggfunc="first",
    )
    # Max pct across all cells for scaling bar widths
    max_pct = piv.max().max() if not piv.empty else 1.0

    rows: list[str] = []
    rows.append('<table style="border-collapse:collapse; font-size:13px;">')
    # Header
    rows.append("<thead><tr>")
    rows.append("<th style='padding:4px 8px; border-bottom:2px solid #555;'></th>")
    for yr in years:
        rows.append(
            f"<th style='text-align:center; padding:4px 10px; "
            f"border-bottom:2px solid #555;'>{yr}</th>"
        )
    rows.append("</tr></thead><tbody>")
    # Data rows
    for race in _RACE_ORDER:
        label = _RACE_SHORT.get(race, race)
        rows.append("<tr>")
        rows.append(
            f"<td style='text-align:right; padding:4px 8px; "
            f"white-space:nowrap; font-weight:bold;'>{label}</td>"
        )
        bar_color = _RACE_COLORS.get(race, "#555555")
        for i, yr in enumerate(years):
            pct = piv.loc[race, yr] if race in piv.index and yr in piv.columns else None
            if pct is not None and pd.notna(pct):
                bar_w = pct / max_pct * 100 if max_pct > 0 else 0
                rows.append(
                    f"<td style='padding:3.6px 4px; min-width:80px;'>"
                    f"<div style='background:{bar_color}; width:{bar_w:.0f}%; "
                    f"padding:2.6px 6px; color:white; font-size:12px; "
                    f"white-space:nowrap; border-radius:2px;'>"
                    f"{pct:.1%}</div></td>"
                )
            else:
                rows.append("<td style='padding:4px 4px;'></td>")
        rows.append("</tr>")
    rows.append("</tbody></table>")
    return "\n".join(rows)


def _build_race_summary_html(df_race: pd.DataFrame, years: list[str]) -> str:
    """Summary HTML table with race colors: counts and 5-yr % change."""
    if len(years) < 2:
        return ""
    first_yr, last_yr = years[0], years[-1]
    piv = df_race.pivot_table(
        index="race_description", columns="academic_year",
        values="count", aggfunc="first",
    )
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

    for race in _RACE_ORDER:
        color = _RACE_COLORS.get(race, "#555555")
        fc = int(piv.loc[race, first_yr]) if race in piv.index and first_yr in piv.columns and pd.notna(piv.loc[race, first_yr]) else 0
        lc = int(piv.loc[race, last_yr]) if race in piv.index and last_yr in piv.columns and pd.notna(piv.loc[race, last_yr]) else 0
        chg_str = f"{(lc - fc) / fc * 100:+.0f}%" if fc > 0 else ""

        cell = (
            "padding:4px 8px; color:white; background:{bg}; "
            "text-align:right; border-bottom:1px solid #444;"
        )
        rows.append("<tr>")
        rows.append(f"<td style='{cell.format(bg=color)}'>{fc:,}</td>")
        rows.append(f"<td style='{cell.format(bg=color)}'>{lc:,}</td>")
        rows.append(
            f"<td style='text-align:right; padding:4px 8px; "
            f"font-weight:bold; color:white; background:{color}; "
            f"border-bottom:1px solid #444;'>{chg_str}</td>"
        )
        rows.append("</tr>")

    rows.append("</tbody></table>")
    return "\n".join(rows)


def _aggregate_gender(df: pd.DataFrame) -> pd.DataFrame:
    """District-wide unduplicated PIDM count by gender by academic year."""
    stu = df.drop_duplicates(subset=["pidm", "academic_year"])
    by_gender = (
        stu.groupby(["academic_year", "gender"])
        .size()
        .reset_index(name="count")
    )
    totals = stu.groupby("academic_year").size().reset_index(name="total")
    out = by_gender.merge(totals, on="academic_year")
    out["pct"] = out["count"] / out["total"]
    out["gender_label"] = out["gender"].map(_GENDER_LABELS)
    return out


def _build_gender_bar_chart(df_gender: pd.DataFrame, years: list[str]):
    """Horizontal grouped bar chart: gender proportion by academic year."""
    df_plot = df_gender.copy()
    labels = [_GENDER_LABELS[g] for g in _GENDER_ORDER]
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
        color_discrete_map=_GENDER_COLORS,
        category_orders={
            "academic_year": list(reversed(years)),
            "gender_label": list(reversed(labels)),
        },
    )
    fig.update_traces(texttemplate="%{text:.1%}", textposition="outside")
    fig.update_layout(
        height=420,
        xaxis_title=None,
        xaxis=dict(tickformat=".0%", range=[0, 0.75]),
        yaxis_title=None,
        legend_title=None,
        legend=dict(orientation="h", yanchor="top", y=-0.1, xanchor="center", x=0.5),
        margin=dict(t=10),
    )
    return fig


def _build_gender_summary_html(df_gender: pd.DataFrame, years: list[str]) -> str:
    """Summary HTML table for gender: counts and 5-yr % change."""
    if len(years) < 2:
        return ""
    first_yr, last_yr = years[0], years[-1]
    piv = df_gender.pivot_table(
        index="gender", columns="academic_year",
        values="count", aggfunc="first",
    )
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

    for g in _GENDER_ORDER:
        label = _GENDER_LABELS[g]
        color = _GENDER_COLORS.get(label, "#555555")
        fc = int(piv.loc[g, first_yr]) if g in piv.index and first_yr in piv.columns and pd.notna(piv.loc[g, first_yr]) else 0
        lc = int(piv.loc[g, last_yr]) if g in piv.index and last_yr in piv.columns and pd.notna(piv.loc[g, last_yr]) else 0
        chg_str = f"{(lc - fc) / fc * 100:+.0f}%" if fc > 0 else ""

        cell = (
            "padding:4px 8px; color:white; background:{bg}; "
            "text-align:right; border-bottom:1px solid #444;"
        )
        rows.append("<tr>")
        rows.append(f"<td style='{cell.format(bg=color)}'>{fc:,}</td>")
        rows.append(f"<td style='{cell.format(bg=color)}'>{lc:,}</td>")
        rows.append(
            f"<td style='text-align:right; padding:4px 8px; "
            f"font-weight:bold; color:white; background:{color}; "
            f"border-bottom:1px solid #444;'>{chg_str}</td>"
        )
        rows.append("</tr>")

    rows.append("</tbody></table>")
    return "\n".join(rows)


# ---------------------------------------------------------------------------
# Charts
# ---------------------------------------------------------------------------

def _build_headcount_chart(df_agg: pd.DataFrame):
    years = sorted(df_agg["academic_year"].unique())
    fig = px.bar(
        df_agg,
        x="academic_year",
        y="headcount",
        color="camp_desc",
        barmode="group",
        text="headcount",
        color_discrete_map=_COLOR_MAP,
        category_orders={"camp_desc": _CAMPUS_ORDER, "academic_year": years},
    )
    fig.update_traces(
        texttemplate="%{text:,}",
        textposition="outside",
    )
    fig.update_layout(
        height=420,
        xaxis_title=None,
        yaxis_title="Distinct Student Headcount",
        legend_title=None,
        legend=dict(orientation="h", yanchor="top", y=-0.18, xanchor="center", x=0.5),
        uniformtext_minsize=8,
        uniformtext_mode="hide",
        margin=dict(t=30),
    )
    return fig


def _build_pct_change_chart(df_pct: pd.DataFrame):
    fig = px.bar(
        df_pct,
        x="pct_change",
        y="camp_desc",
        orientation="h",
        text="pct_change",
        color="camp_desc",
        color_discrete_map=_COLOR_MAP,
        category_orders={"camp_desc": _CAMPUS_ORDER},
    )
    fig.update_traces(
        texttemplate="%{text:.1f}%",
        textposition="outside",
    )
    # Extend x-axis range to fit text labels beyond the bars
    max_val = df_pct["pct_change"].max()
    fig.update_layout(
        height=420,
        showlegend=False,
        title="5-Yr % Change",
        xaxis_title="% Change",
        xaxis_range=[df_pct["pct_change"].min() - 5, max_val * 1.4 if max_val > 0 else 5],
        yaxis_title=None,
        margin=dict(l=10, t=50),
    )
    return fig


# ---------------------------------------------------------------------------
# Streamlit render
# ---------------------------------------------------------------------------

def render():
    st.header("BOT Goal 1 - Students")

    # --- Sidebar ---
    selected_acyrs = st.sidebar.multiselect(
        "Academic Years",
        options=_DEFAULT_ACYRS,
        default=_DEFAULT_ACYRS,
        key="bg1_acyr_codes",
    )
    query_btn = st.sidebar.button("Query", key="bg1_query_btn")

    if query_btn:
        if not selected_acyrs:
            st.warning("Select at least one academic year.")
            return
        fetch_bot_goal1_students.clear()
        df = fetch_bot_goal1_students(tuple(sorted(selected_acyrs)))
        if df.empty:
            st.warning("No data returned for the selected academic years.")
            return
        st.session_state["bg1_df"] = df

    if "bg1_df" not in st.session_state:
        st.info("Select Academic Years and press **Query** to load data.")
        return

    df = st.session_state["bg1_df"]

    # --- Chart 1: Headcount by Campus ---
    years = sorted(df["academic_year"].dropna().unique())
    year_range = f"{years[0]} to {years[-1]}" if len(years) >= 2 else years[0] if years else ""
    st.subheader("NOCCCD")
    st.markdown(f"**Headcount of Students**  \n{year_range}")
    st.caption(
        "The unduplicated number of students enrolled as of census in "
        "Cypress College, Fullerton College, and North Orange Continuing "
        "Education in the reporting year."
    )
    df_agg = _aggregate_headcount(df)
    df_pct = _compute_pct_change(df_agg)

    col_main, col_pct = st.columns([3, 1])
    with col_main:
        st.plotly_chart(
            _build_headcount_chart(df_agg),
            use_container_width=True,
        )
    with col_pct:
        if not df_pct.empty:
            st.plotly_chart(
                _build_pct_change_chart(df_pct),
                use_container_width=True,
            )
        else:
            st.info("Need at least 2 years for % change.")

    st.markdown(
        "<div style='text-align:left'><small>Source: Banner</small></div>",
        unsafe_allow_html=True,
    )

    # --- Chart 2: Proportion by Race/Ethnicity ---
    st.divider()
    st.subheader("NOCCCD")
    st.markdown(f"**Proportion of Enrolled Students by Race/Ethnicity**  \n{year_range}")
    st.caption(
        "Among all unduplicated students enrolled as of census in NOCCCD "
        "in the reporting year, the proportion of students by race/ethnicity."
    )
    df_race = _aggregate_race(df)

    col_prop, col_summary = st.columns([3, 2])
    with col_prop:
        st.markdown(
            _build_race_proportion_html(df_race, years),
            unsafe_allow_html=True,
        )
    with col_summary:
        summary_html = _build_race_summary_html(df_race, years)
        if summary_html:
            st.markdown(summary_html, unsafe_allow_html=True)
    st.markdown(
        "<div style='text-align:left'><small>Source: Banner</small></div>",
        unsafe_allow_html=True,
    )

    # --- Chart 3: Proportion by Gender ---
    st.divider()
    st.subheader("NOCCCD")
    st.markdown(f"**Proportion of Enrolled Students by Gender**  \n{year_range}")
    st.caption(
        "Among all unduplicated students enrolled as of census in NOCCCD "
        "in the reporting year, the proportion of students by gender."
    )
    df_gender = _aggregate_gender(df)

    col_gchart, col_gsummary = st.columns([3, 2])
    with col_gchart:
        st.plotly_chart(
            _build_gender_bar_chart(df_gender, years),
            use_container_width=True,
        )
    with col_gsummary:
        gender_html = _build_gender_summary_html(df_gender, years)
        if gender_html:
            st.markdown(gender_html, unsafe_allow_html=True)
    st.markdown(
        "<div style='text-align:left'><small>Source: Banner</small></div>",
        unsafe_allow_html=True,
    )
