import io

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from matplotlib.backends.backend_pdf import PdfPages
from streamlit_plotly_events import plotly_events

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

def _pivot_day(df: pd.DataFrame):
    """Return Campus × Day pivot of enrollment."""
    df_day = df.drop_duplicates(subset=["crn", "campus_description", "day_name"])
    day_campus = (
        df_day.groupby(["campus_description", "day_name"], as_index=False)["current_enrollment"].sum()
    )
    pivot = day_campus.pivot(index="campus_description", columns="day_name", values="current_enrollment")
    return pivot.reindex(columns=DAY_ORDER).fillna(0)


def _pivot_time(df: pd.DataFrame, term: str, campus: str):
    """Return Hour × Day pivot of enrollment, or None if no data."""
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
    pivot = pivot.reindex(columns=DAY_ORDER).fillna(0)
    pivot.index = pivot.index.droplevel(0)
    return pivot


def _make_heatmap_fig(pivot: pd.DataFrame, title: str):
    """Build a go.Heatmap figure with text annotations and day totals."""
    data = pivot.values
    vmax = np.nanmax(data) if np.nanmax(data) > 0 else 1

    fig = go.Figure(data=go.Heatmap(
        z=data,
        x=list(pivot.columns),
        y=list(pivot.index),
        colorscale="YlOrRd",
        colorbar={"title": "Enrollment"},
        hovertemplate="Day: %{x}<br>%{y}<br>Enrollment: %{z:,.0f}<extra></extra>",
    ))
    fig.update_layout(
        title=title,
        xaxis_title="Day",
        yaxis={"autorange": "reversed"},
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font={"color": "gray"},
    )
    # Cell value annotations
    for i, row_label in enumerate(pivot.index):
        for j, col_label in enumerate(pivot.columns):
            val = data[i][j]
            color = "white" if val > vmax * 0.6 else "black"
            fig.add_annotation(
                x=col_label, y=row_label,
                text=f"{int(val):,}",
                showarrow=False,
                font={"size": 10, "color": color},
            )
    # Day totals below x-axis
    day_totals = pivot.sum()
    for day in pivot.columns:
        total = day_totals.get(day, 0)
        if total > 0:
            fig.add_annotation(
                x=day,
                y=len(pivot),
                text=f"<b>{int(total):,}</b>",
                showarrow=False,
                font={"size": 12},
                yref="y",
            )
    return fig


def _build_day_heatmap_fig(df: pd.DataFrame, term: str):
    """Build Campus × Day heatmap figure."""
    pivot = _pivot_day(df)
    return _make_heatmap_fig(pivot, f"{term} — Student Enrollment by Day of Week")


def _build_time_heatmap_fig(df: pd.DataFrame, term: str, campus: str):
    """Build Hour × Day heatmap figure, or None if no data."""
    pivot = _pivot_time(df, term, campus)
    if pivot is None:
        return None
    return _make_heatmap_fig(pivot, f"{term} — {campus} — Enrollment by Time & Day")


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

    # Day totals below the x-axis labels
    from matplotlib.transforms import blended_transform_factory
    trans = blended_transform_factory(ax.transData, ax.transAxes)
    day_totals = pivot.fillna(0).sum()
    for j, col in enumerate(pivot.columns):
        total = day_totals[col]
        if total > 0:
            ax.text(
                j, -0.08, f"{int(total):,}", transform=trans,
                ha="center", va="top", fontsize=9, fontweight="bold",
                clip_on=False,
            )

    return im


_PDF_FOOTER_LEFT = "https://nocccd.streamlit.app/"
_PDF_FOOTER_RIGHT = "Author: Jihoon Ahn  jahn@nocccd.edu"


def _add_pdf_footer(fig):
    """Add URL (left) and author (right) footer to a matplotlib figure."""
    fig.text(0.06, 0.02, _PDF_FOOTER_LEFT, fontsize=7, color="grey", ha="left")
    fig.text(0.94, 0.02, _PDF_FOOTER_RIGHT, fontsize=7, color="grey", ha="right")


def _generate_pdf(df_heatmap: pd.DataFrame, term: str) -> bytes:
    """Render heatmaps for a term into an in-memory PDF using matplotlib."""
    matplotlib.rcParams.update({
        "figure.facecolor": "white",
        "axes.facecolor": "white",
        "text.color": "black",
        "savefig.facecolor": "white",
    })

    PAGE_W, PAGE_H = 11.0, 8.5  # landscape letter

    buf = io.BytesIO()
    with PdfPages(buf) as pdf:
        # --- Day heatmap (first page — include tab title) ---
        df_term = df_heatmap[df_heatmap["academic_term"] == term]
        df_day = df_term.drop_duplicates(subset=["crn", "campus_description", "day_name"])
        day_campus = df_day.groupby(
            ["campus_description", "day_name"], as_index=False
        )["current_enrollment"].sum()
        pivot_day = day_campus.pivot(
            index="campus_description", columns="day_name", values="current_enrollment"
        )
        pivot_day = pivot_day.reindex(columns=DAY_ORDER)

        fig, ax = plt.subplots(figsize=(PAGE_W, PAGE_H))
        fig.suptitle("Class Schedule Heatmap", fontsize=16, fontweight="bold", y=0.96)
        fig.subplots_adjust(left=0.10, right=0.92, top=0.85, bottom=0.15)
        _mpl_heatmap(ax, pivot_day, f"{term} — Student Enrollment by Day of Week")
        _add_pdf_footer(fig)
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

            fig, ax = plt.subplots(figsize=(PAGE_W, PAGE_H))
            fig.subplots_adjust(left=0.10, right=0.92, top=0.90, bottom=0.15)
            _mpl_heatmap(ax, pivot_time, f"{term} — {campus} — Enrollment by Time & Day")
            _add_pdf_footer(fig)
            pdf.savefig(fig)
            plt.close(fig)

    return buf.getvalue()


# ---------------------------------------------------------------------------
# Drill-down tables
# ---------------------------------------------------------------------------

def _render_drilldown(df_slice: pd.DataFrame, context: str):
    """Show top 10 subjects and modality breakdown for a heatmap cell selection."""
    if df_slice.empty:
        return

    st.markdown(f"**Drill-down: {context}**")
    c1, c2 = st.columns(2)

    with c1:
        st.markdown("**Top 10 Subjects by Enrollment**")
        top_subj = (
            df_slice.groupby("subject_desc", as_index=False)["current_enrollment"]
            .sum()
            .sort_values("current_enrollment", ascending=False)
            .head(10)
            .rename(columns={"subject_desc": "Subject", "current_enrollment": "Enrollment"})
        )
        st.dataframe(top_subj, hide_index=True, use_container_width=True)

    with c2:
        st.markdown("**Modality Breakdown**")
        modality = (
            df_slice.groupby("modality_desc", as_index=False)["current_enrollment"]
            .sum()
            .sort_values("current_enrollment", ascending=False)
            .rename(columns={"modality_desc": "Modality", "current_enrollment": "Enrollment"})
        )
        st.dataframe(modality, hide_index=True, use_container_width=True)


# ---------------------------------------------------------------------------
# Streamlit render
# ---------------------------------------------------------------------------

def _resolve_click(clicked, pivot):
    """Resolve a plotly_events click to (row_label, col_label) or (None, None)."""
    if not clicked:
        return None, None
    pt = clicked[0]
    x_idx = pt.get("pointIndex", [None, None])
    if isinstance(x_idx, list) and len(x_idx) == 2:
        row_idx, col_idx = x_idx
        try:
            return pivot.index[int(row_idx)], pivot.columns[int(col_idx)]
        except (IndexError, TypeError):
            return None, None
    col_val = pt.get("x")
    row_val = pt.get("y")
    if isinstance(col_val, str) and isinstance(row_val, str):
        return row_val, col_val
    return None, None


def _handle_click(clicked, chart_key, df_term, pivot, campus=None):
    """Handle a heatmap click, only triggering dialog on genuinely new clicks.

    Each chart tracks its own last-click signature. Only a chart whose
    click changed since last run writes to csh_drilldown.
    """
    row_label, col_label = _resolve_click(clicked, pivot)
    if row_label is None:
        return

    # Per-chart signature to detect which chart actually changed
    click_sig = f"{row_label}:{col_label}"
    prev_key = f"csh_prev_click_{chart_key}"
    if st.session_state.get(prev_key) == click_sig:
        return  # This chart's click hasn't changed — stale data
    st.session_state[prev_key] = click_sig

    if campus is None:
        df_drill = df_term[
            (df_term["campus_description"] == row_label)
            & (df_term["day_name"] == col_label)
        ]
        context = f"{row_label} / {col_label}"
    else:
        df_drill = df_term[
            (df_term["campus_description"] == campus)
            & (df_term["day_name"] == col_label)
            & (df_term["hour_label"] == row_label)
        ]
        context = f"{campus} / {col_label} / {row_label}"

    if not df_drill.empty:
        st.session_state["csh_drilldown"] = {"df": df_drill, "context": context}


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
    st.caption("Click any cell to drill down into top subjects and modalities.")
    day_pivot = _pivot_day(df_term)
    day_fig = _build_day_heatmap_fig(df_term, sel_term)
    day_clicked = plotly_events(day_fig, click_event=True, key="csh_day_click")
    _handle_click(day_clicked, "day", df_term, day_pivot)

    # --- Section B: Enrollment by Time & Day ---
    st.subheader("Enrollment by Time & Day")
    for campus in _CAMPUSES:
        time_pivot = _pivot_time(df_heatmap, sel_term, campus)
        if time_pivot is not None:
            fig = _build_time_heatmap_fig(df_heatmap, sel_term, campus)
            clicked = plotly_events(fig, click_event=True, key=f"csh_time_click_{campus}")
            _handle_click(clicked, f"time_{campus}", df_term, time_pivot, campus=campus)
        else:
            st.info(f"No data for {campus}.")

    # --- Show drill-down dialog if triggered ---
    if "csh_drilldown" in st.session_state:
        dd = st.session_state.pop("csh_drilldown")

        @st.dialog(f"Drill Down: {dd['context']}", width="large")
        def _dialog():
            _render_drilldown(dd["df"], dd["context"])

        _dialog()
