import io

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import plotly.graph_objects as go
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

def _top_n_pct(df: pd.DataFrame, group_col: str, val_col: str, label: str, n: int = 10) -> pd.DataFrame:
    """Group, sum, compute percentage, return top N rows."""
    agg = (
        df.groupby(group_col, as_index=False)[val_col]
        .sum()
        .sort_values(val_col, ascending=False)
    )
    total = agg[val_col].sum()
    agg["Pct"] = (agg[val_col] / total * 100).round(1).astype(str) + "%" if total > 0 else "0%"
    return (
        agg.head(n)
        .rename(columns={group_col: label, val_col: "Enrollment"})
        [[ label, "Enrollment", "Pct"]]
    )


def _render_drilldown(df_slice: pd.DataFrame, context: str):
    """Show top 10 divisions, departments, subjects, and modality breakdown.

    Deduplicates by CRN to avoid inflated counts from multiple meeting rows.
    """
    if df_slice.empty:
        st.info(f"No data for {context}.")
        return

    deduped = df_slice.drop_duplicates(subset=["crn"])
    total_enrl = deduped["current_enrollment"].sum()

    st.markdown(f"**{context}** — {total_enrl:,} total enrollment")

    c1, c2, c3, c4 = st.columns(4)

    with c1:
        st.markdown("**Top 10 Divisions**")
        st.dataframe(
            _top_n_pct(deduped, "division_desc", "current_enrollment", "Division"),
            hide_index=True, use_container_width=True,
        )

    with c2:
        st.markdown("**Top 10 Departments**")
        st.dataframe(
            _top_n_pct(deduped, "department_desc", "current_enrollment", "Department"),
            hide_index=True, use_container_width=True,
        )

    with c3:
        st.markdown("**Top 10 Subjects**")
        st.dataframe(
            _top_n_pct(deduped, "subject_desc", "current_enrollment", "Subject"),
            hide_index=True, use_container_width=True,
        )

    with c4:
        st.markdown("**Modality Breakdown**")
        st.dataframe(
            _top_n_pct(deduped, "modality_desc", "current_enrollment", "Modality", n=20),
            hide_index=True, use_container_width=True,
        )


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

    # Day drill-down
    with st.expander("Explore by Campus & Day"):
        d1, d2 = st.columns(2)
        campuses_in_data = sorted(df_term["campus_description"].dropna().unique())
        dd_campus = d1.selectbox("Campus", campuses_in_data, key="csh_dd_campus")
        dd_day = d2.selectbox("Day", DAY_ORDER, key="csh_dd_day")

        df_day_drill = df_term[
            (df_term["campus_description"] == dd_campus)
            & (df_term["day_name"] == dd_day)
        ]
        _render_drilldown(df_day_drill, f"{dd_campus} / {dd_day}")

    # --- Section B: Enrollment by Time & Day ---
    st.subheader("Enrollment by Time & Day")
    for campus in _CAMPUSES:
        fig = _build_time_heatmap_fig(df_heatmap, sel_term, campus)
        if fig:
            st.plotly_chart(fig, use_container_width=True)

            # Time drill-down
            with st.expander(f"Explore — {campus}"):
                t1, t2 = st.columns(2)
                td_day = t1.selectbox("Day", DAY_ORDER, key=f"csh_td_day_{campus}")
                hours_available = sorted(
                    df_term[
                        (df_term["campus_description"] == campus)
                        & (df_term["hour_label"].notna())
                    ]["hour_label"].unique(),
                    key=lambda h: df_term[df_term["hour_label"] == h]["begin_hour"].iloc[0],
                )
                if hours_available:
                    td_hour = t2.selectbox("Start Time", hours_available, key=f"csh_td_hour_{campus}")
                    df_time_drill = df_term[
                        (df_term["campus_description"] == campus)
                        & (df_term["day_name"] == td_day)
                        & (df_term["hour_label"] == td_hour)
                    ]
                    _render_drilldown(df_time_drill, f"{campus} / {td_day} / {td_hour}")
        else:
            st.info(f"No data for {campus}.")
