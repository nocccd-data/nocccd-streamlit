import io

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st
from matplotlib.backends.backend_pdf import PdfPages

from src.pipeline.config import DATASETS
from src.scripts.data_provider import fetch_class_schedule_heatmap

_CFG = DATASETS["class_schedule_heatmap"]
_DEFAULT_TERMS = _CFG[_CFG["param_name"]]

DAY_ORDER = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
DAY_MAP = {"M": "Mon", "T": "Tue", "W": "Wed", "Th": "Thu", "F": "Fri", "S": "Sat", "Su": "Sun"}

_CAMPUSES = ["Cypress", "Fullerton", "NOCE"]


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


# ---------------------------------------------------------------------------
# Plotly figures (for interactive display)
# ---------------------------------------------------------------------------

def _build_day_heatmap_fig(df: pd.DataFrame, term: str):
    """Build Campus × Day pivot heatmap figure."""
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
    return fig


def _build_time_heatmap_fig(df: pd.DataFrame, term: str, campus: str):
    """Build Hour × Day pivot heatmap figure, or None if no data."""
    df_filtered = df[(df["academic_term"] == term) & (df["campus_description"] == campus)]
    if df_filtered.empty:
        return None
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
    return fig


# ---------------------------------------------------------------------------
# PDF export (matplotlib — no kaleido/Chrome dependency)
# ---------------------------------------------------------------------------

def _mpl_heatmap(ax, pivot: pd.DataFrame, title: str):
    """Render a heatmap on a matplotlib Axes with cell annotations and day totals."""
    data = pivot.fillna(0).values.astype(float)
    im = ax.imshow(data, cmap="YlOrRd", aspect="auto")

    ax.set_xticks(range(len(pivot.columns)))
    ax.set_xticklabels(pivot.columns, fontsize=9)
    ax.set_yticks(range(len(pivot.index)))
    ax.set_yticklabels(pivot.index, fontsize=9)
    ax.set_title(title, fontsize=12, fontweight="bold", pad=10)

    # Cell annotations
    vmax = np.nanmax(data) if np.nanmax(data) > 0 else 1
    for i in range(data.shape[0]):
        for j in range(data.shape[1]):
            val = data[i, j]
            if val > 0:
                color = "white" if val > vmax * 0.65 else "black"
                ax.text(j, i, f"{int(val):,}", ha="center", va="center", fontsize=8, color=color)

    # Day totals below the heatmap
    day_totals = pivot.fillna(0).sum()
    for j, col in enumerate(pivot.columns):
        total = day_totals[col]
        if total > 0:
            ax.annotate(
                f"{int(total):,}", xy=(j, len(pivot.index) - 0.5),
                xytext=(0, 14), textcoords="offset points",
                ha="center", va="top", fontsize=9, fontweight="bold",
            )

    return im


def _generate_pdf(df_heatmap: pd.DataFrame, term: str) -> bytes:
    """Render heatmaps for a term into an in-memory PDF using matplotlib."""
    matplotlib.rcParams.update({
        "figure.facecolor": "white",
        "axes.facecolor": "white",
        "text.color": "black",
        "savefig.facecolor": "white",
    })

    buf = io.BytesIO()
    with PdfPages(buf) as pdf:
        # --- Day heatmap ---
        df_term = df_heatmap[df_heatmap["academic_term"] == term]
        df_day = df_term.drop_duplicates(subset=["crn", "campus_description", "day_name"])
        day_campus = df_day.groupby(
            ["campus_description", "day_name"], as_index=False
        )["current_enrollment"].sum()
        pivot_day = day_campus.pivot(
            index="campus_description", columns="day_name", values="current_enrollment"
        )
        pivot_day = pivot_day.reindex(columns=DAY_ORDER)

        fig, ax = plt.subplots(figsize=(10, 3.5))
        _mpl_heatmap(ax, pivot_day, f"{term} — Student Enrollment by Day of Week")
        fig.tight_layout()
        pdf.savefig(fig)
        plt.close(fig)

        # --- Time heatmaps per campus ---
        for campus in _CAMPUSES:
            df_filtered = df_heatmap[
                (df_heatmap["academic_term"] == term) & (df_heatmap["campus_description"] == campus)
            ]
            if df_filtered.empty:
                continue
            time_day = df_filtered.groupby(
                ["hour_label", "begin_hour", "day_name"], as_index=False
            )["current_enrollment"].sum()
            pivot_time = time_day.pivot_table(
                index=["begin_hour", "hour_label"], columns="day_name",
                values="current_enrollment", fill_value=0,
            )
            pivot_time = pivot_time.reindex(columns=DAY_ORDER)
            pivot_time.index = pivot_time.index.droplevel(0)

            n_rows = len(pivot_time)
            fig, ax = plt.subplots(figsize=(10, max(4, n_rows * 0.45)))
            _mpl_heatmap(ax, pivot_time, f"{term} — {campus} — Enrollment by Time & Day")
            fig.tight_layout()
            pdf.savefig(fig)
            plt.close(fig)

    return buf.getvalue()


# ---------------------------------------------------------------------------
# Streamlit render
# ---------------------------------------------------------------------------

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

    # --- PDF download in sidebar (only when data is loaded) ---
    if "csh_df" in st.session_state:
        df_heatmap = st.session_state["csh_df"]
        terms = sorted(df_heatmap["academic_term"].dropna().unique())
        sel = st.session_state.get("csh_term", terms[0] if terms else None)
        if sel:
            pdf_bytes = _generate_pdf(df_heatmap, sel)
            st.sidebar.download_button(
                "Download PDF",
                data=pdf_bytes,
                file_name="class_schedule_heatmap.pdf",
                mime="application/pdf",
                key="csh_pdf_btn",
            )

    if "csh_df" not in st.session_state:
        st.info("Select Term IDs and press **Query** to load data.")
        return

    df_heatmap = st.session_state["csh_df"]
    terms = sorted(df_heatmap["academic_term"].dropna().unique())

    sel_term = st.selectbox("Term", terms, key="csh_term")
    df_term = df_heatmap[df_heatmap["academic_term"] == sel_term]

    # --- Section A: Enrollment by Day of Week ---
    st.subheader("Enrollment by Day of Week")
    st.plotly_chart(_build_day_heatmap_fig(df_term, sel_term), use_container_width=True)

    # --- Section B: Enrollment by Time & Day ---
    st.subheader("Enrollment by Time & Day")
    for campus in _CAMPUSES:
        fig = _build_time_heatmap_fig(df_heatmap, sel_term, campus)
        if fig:
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info(f"No data for {campus}.")
