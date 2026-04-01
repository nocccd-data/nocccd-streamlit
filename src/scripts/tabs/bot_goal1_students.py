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
