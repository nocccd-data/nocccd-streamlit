import pandas as pd
import plotly.express as px
import streamlit as st

from src.pipeline.config import DATASETS
from src.scripts.data_provider import fetch_class_schedule_heatmap

_CFG = DATASETS["class_schedule_heatmap"]
_DEFAULT_TERMS = _CFG[_CFG["param_name"]]

DAY_ORDER = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
DAY_MAP = {"M": "Mon", "T": "Tue", "W": "Wed", "Th": "Thu", "F": "Fri", "S": "Sat", "Su": "Sun"}


def _parse_meeting_days(s):
    """Parse meeting_days string like 'MWF' into ['M','W','F'], handling two-char codes."""
    if pd.isna(s) or s == "":
        return []
    days = []
    i = 0
    while i < len(s):
        if i + 1 < len(s) and s[i : i + 2] in ("Th", "Su"):
            days.append(s[i : i + 2])
            i += 2
        else:
            days.append(s[i])
            i += 1
    return days


def _time_to_hour_label(h):
    """Convert hour int to label, e.g. 14 → '2:00 PM'."""
    if pd.isna(h):
        return None
    h = int(h)
    period = "AM" if h < 12 else "PM"
    display_hour = h % 12 or 12
    return f"{display_hour}:00 {period}"


def _prepare_heatmap_data(df: pd.DataFrame) -> pd.DataFrame:
    """Parse days, explode, map to day names, compute hour buckets, dedup by CRN/day/hour."""
    out = df.copy()
    out["parsed_days"] = out["meeting_days"].apply(_parse_meeting_days)
    out = out[out["parsed_days"].apply(len) > 0]
    out = out.explode("parsed_days")
    out["day_name"] = out["parsed_days"].map(DAY_MAP)
    out["begin_hour"] = (pd.to_numeric(out["meeting_begin_time"], errors="coerce") // 100).astype("Int64")
    out["hour_label"] = out["begin_hour"].apply(_time_to_hour_label)
    out = out.drop_duplicates(subset=["crn", "day_name", "begin_hour"])
    return out


def _render_day_heatmap(df: pd.DataFrame, term: str):
    """Campus × Day pivot heatmap with per-day total annotations."""
    df_day = df.drop_duplicates(subset=["crn", "campus_description", "day_name"])
    day_campus = (
        df_day.groupby(["campus_description", "day_name"], as_index=False)["current_enrollment"].sum()
    )
    pivot = day_campus.pivot(index="campus_description", columns="day_name", values="current_enrollment")
    pivot = pivot.reindex(columns=DAY_ORDER)

    fig = px.imshow(
        pivot,
        text_auto=True,
        color_continuous_scale="YlOrRd",
        labels={"x": "Day", "y": "Campus", "color": "Enrollment"},
        title=f"{term} — Student Enrollment by Day of Week",
        aspect="auto",
    )
    day_totals = pivot.sum()
    for i, day in enumerate(DAY_ORDER):
        total = day_totals.get(day)
        if pd.notna(total):
            fig.add_annotation(
                x=i,
                y=len(pivot),
                text=f"<b>{int(total):,}</b>",
                showarrow=False,
                font={"size": 12},
                xref="x",
                yref="y",
            )
    st.plotly_chart(fig, use_container_width=True)


def _render_time_heatmap(df: pd.DataFrame, term: str, campus: str):
    """Hour × Day pivot heatmap with per-day total annotations."""
    df_filtered = df[(df["academic_term"] == term) & (df["campus_description"] == campus)]
    if df_filtered.empty:
        st.info("No data for this term/campus combination.")
        return
    time_day = (
        df_filtered.groupby(["hour_label", "begin_hour", "day_name"], as_index=False)["current_enrollment"].sum()
    )
    pivot = time_day.pivot_table(
        index=["begin_hour", "hour_label"],
        columns="day_name",
        values="current_enrollment",
        fill_value=0,
    )
    pivot = pivot.reindex(columns=DAY_ORDER)
    pivot.index = pivot.index.droplevel(0)

    fig = px.imshow(
        pivot,
        text_auto=True,
        color_continuous_scale="YlOrRd",
        labels={"x": "Day", "y": "Start Time", "color": "Enrollment"},
        title=f"{term} — {campus} — Enrollment by Time & Day",
        aspect="auto",
    )
    day_totals = pivot.sum()
    for i, day in enumerate(DAY_ORDER):
        total = day_totals.get(day)
        if pd.notna(total) and total > 0:
            fig.add_annotation(
                x=i,
                y=len(pivot),
                text=f"<b>{int(total):,}</b>",
                showarrow=False,
                font={"size": 12},
                xref="x",
                yref="y",
            )
    st.plotly_chart(fig, use_container_width=True)


def render():
    st.header("Class Schedule Heatmap")

    # --- Sidebar controls ---
    selected_terms = st.sidebar.multiselect(
        "MIS Term IDs",
        options=_DEFAULT_TERMS,
        default=_DEFAULT_TERMS,
        key="csh_term_ids",
    )
    query_btn = st.sidebar.button("Query", key="csh_query_btn")

    if query_btn:
        if not selected_terms:
            st.warning("Select at least one term.")
            return
        fetch_class_schedule_heatmap.clear()
        df = fetch_class_schedule_heatmap(tuple(sorted(selected_terms)))
        if df.empty:
            st.warning("No data returned for the selected terms.")
            return
        st.session_state["csh_df"] = _prepare_heatmap_data(df)

    if "csh_df" not in st.session_state:
        st.info("Select Term IDs and press **Query** to load data.")
        return

    df_heatmap = st.session_state["csh_df"]
    terms = sorted(df_heatmap["academic_term"].dropna().unique())
    campuses = sorted(df_heatmap["campus_description"].dropna().unique())

    sel_term = st.selectbox("Term", terms, key="csh_term")
    df_term = df_heatmap[df_heatmap["academic_term"] == sel_term]

    # --- Section A: Enrollment by Day of Week ---
    st.subheader("Enrollment by Day of Week")
    _render_day_heatmap(df_term, sel_term)

    # --- Section B: Enrollment by Time & Day ---
    st.subheader("Enrollment by Time & Day")
    for campus in ["Cypress", "Fullerton", "NOCE"]:
        _render_time_heatmap(df_heatmap, sel_term, campus)
