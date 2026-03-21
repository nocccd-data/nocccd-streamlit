import io

import matplotlib
import matplotlib.pyplot as plt
import pandas as pd
import plotly.express as px
import streamlit as st
from matplotlib.backends.backend_pdf import PdfPages

from src.pipeline.config import DATASETS
from src.scripts.data_provider import fetch_persistence_by_styp

_CFG = DATASETS["persistence_by_styp"]
_DEFAULT_TERMS = _CFG[_CFG["param_name"]]

CAMP_MAP = {"1": "Cypress", "2": "Fullerton", "3": "NOCE"}

STYP_ORDER = [
    "first_time",
    "first_time_trans",
    "continuing",
    "returning",
    "adult",
    "dual_enroll",
    "concurrent",
]
STYP_LABELS = {
    "first_time": "First-Time",
    "first_time_trans": "First-Time Transfer",
    "continuing": "Continuing",
    "returning": "Returning",
    "adult": "Adult",
    "dual_enroll": "Dual Enrollment",
    "concurrent": "Concurrent",
}

RATE_OPTIONS = {
    "Fall \u2192 Spring": {
        "rate_col": "spring_persistence_rate",
        "p_count_col": "curr_fall_p_count",
        "headcount_col": "spring_total_headcount",
    },
    "Fall \u2192 Next Fall": {
        "rate_col": "next_fall_persistence_rate",
        "p_count_col": "curr_fall_p_count",
        "headcount_col": "next_fall_total_headcount",
    },
}


# ---------------------------------------------------------------------------
# Data preparation
# ---------------------------------------------------------------------------

def _prepare_data(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["campus"] = out["camp_code"].astype(str).map(CAMP_MAP)
    out["styp_label"] = pd.Categorical(
        out["styp_code"].map(STYP_LABELS),
        categories=[STYP_LABELS[s] for s in STYP_ORDER],
        ordered=True,
    )
    out["term_short"] = out["academic_term"].str.replace(" Fall", "", regex=False)
    out["term_sort"] = out["mis_term_id"].astype(int)
    out = out.sort_values("term_sort")
    return out


def _build_overall(df: pd.DataFrame) -> pd.DataFrame:
    """Compute overall persistence per campus/term (weighted average)."""
    agg = (
        df.groupby(["campus", "term_short", "term_sort"], as_index=False)
        .agg(
            curr_fall_p_count=("curr_fall_p_count", "sum"),
            spring_total_headcount=("spring_total_headcount", "sum"),
            next_fall_total_headcount=("next_fall_total_headcount", "sum"),
        )
    )
    agg["spring_persistence_rate"] = agg["spring_total_headcount"] / agg["curr_fall_p_count"]
    agg["next_fall_persistence_rate"] = agg["next_fall_total_headcount"] / agg["curr_fall_p_count"]
    return agg.sort_values("term_sort")


# ---------------------------------------------------------------------------
# Plotly figures
# ---------------------------------------------------------------------------

_HOVER_TEMPLATE = (
    "<b>%{x}</b><br>"
    "Rate: %{y:.1%}<br>"
    "Headcount: %{customdata[0]:,}<br>"
    "P-Count: %{customdata[1]:,}"
    "<extra></extra>"
)


def _build_overall_fig(df_overall: pd.DataFrame, campus: str, persistence_type: str):
    opts = RATE_OPTIONS[persistence_type]
    dfc = df_overall[df_overall["campus"] == campus].copy()
    if persistence_type == "Fall \u2192 Next Fall":
        dfc = dfc[dfc["next_fall_total_headcount"] > 0]

    fig = px.line(
        dfc,
        x="term_short",
        y=opts["rate_col"],
        markers=True,
        text=opts["rate_col"],
        title=f"{campus} — All Students — {persistence_type}",
        custom_data=[opts["headcount_col"], opts["p_count_col"]],
    )
    fig.update_traces(
        texttemplate="%{y:.0%}",
        textposition="top center",
        hovertemplate=_HOVER_TEMPLATE,
        mode="lines+markers+text",
    )
    fig.update_yaxes(range=[0, 1], tickformat=".0%")
    fig.update_xaxes(tickangle=-45)
    fig.update_layout(height=350, xaxis_title=None, yaxis_title="Persistence Rate")
    return fig


def _build_by_styp_fig(df_viz: pd.DataFrame, campus: str, persistence_type: str):
    opts = RATE_OPTIONS[persistence_type]
    dfc = df_viz[df_viz["campus"] == campus].copy()
    if persistence_type == "Fall \u2192 Next Fall":
        dfc = dfc[dfc["next_fall_total_headcount"] > 0]

    fig = px.line(
        dfc,
        x="term_short",
        y=opts["rate_col"],
        facet_col="styp_label",
        facet_col_wrap=3,
        markers=True,
        text=opts["rate_col"],
        title=f"{campus} — By Student Type — {persistence_type}",
        custom_data=[opts["headcount_col"], opts["p_count_col"]],
    )
    fig.update_traces(
        texttemplate="%{y:.0%}",
        textposition="top center",
        hovertemplate=_HOVER_TEMPLATE,
        mode="lines+markers+text",
    )
    fig.update_yaxes(range=[0, 1], tickformat=".0%", title_text="")
    fig.update_xaxes(tickangle=-45)
    fig.update_layout(height=900)
    # Single centered y-axis label via annotation
    fig.add_annotation(
        text="Persistence Rate",
        xref="paper", yref="paper",
        x=-0.06, y=0.5,
        textangle=-90,
        showarrow=False,
        font={"size": 14},
    )
    fig.for_each_annotation(
        lambda a: a.update(text=a.text.split("=")[-1])
        if "=" in a.text else None
    )
    return fig


# ---------------------------------------------------------------------------
# PDF export (matplotlib)
# ---------------------------------------------------------------------------

_PDF_FOOTER_LEFT = "https://nocccd.streamlit.app/"
_PDF_FOOTER_RIGHT = "Author: Jihoon Ahn  jahn@nocccd.edu"


def _add_pdf_footer(fig):
    fig.text(0.06, 0.02, _PDF_FOOTER_LEFT, fontsize=7, color="grey", ha="left")
    fig.text(0.94, 0.02, _PDF_FOOTER_RIGHT, fontsize=7, color="grey", ha="right")


def _mpl_line_chart(ax, df_plot: pd.DataFrame, rate_col: str, title: str):
    """Draw a single persistence line chart on a matplotlib Axes."""
    terms = df_plot["term_short"].tolist()
    rates = df_plot[rate_col].tolist()
    ax.plot(terms, rates, marker="o", linewidth=2)
    for i, (t, r) in enumerate(zip(terms, rates)):
        if pd.notna(r):
            ax.annotate(f"{r:.0%}", (i, r), textcoords="offset points",
                        xytext=(0, 10), ha="center", fontsize=8)
    ax.set_ylim(0, 1)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:.0%}"))
    ax.set_title(title, fontsize=10, fontweight="bold")
    ax.tick_params(axis="x", rotation=45)
    ax.grid(axis="y", alpha=0.3)


def _generate_pdf(df_viz: pd.DataFrame, df_overall: pd.DataFrame,
                  campus: str, persistence_type: str) -> bytes:
    matplotlib.rcParams.update({
        "figure.facecolor": "white",
        "axes.facecolor": "white",
        "text.color": "black",
        "savefig.facecolor": "white",
    })

    opts = RATE_OPTIONS[persistence_type]
    rate_col = opts["rate_col"]
    PAGE_W, PAGE_H = 11.0, 8.5

    buf = io.BytesIO()
    with PdfPages(buf) as pdf:
        # Page 1: Overall
        dfc_overall = df_overall[df_overall["campus"] == campus].copy()
        if persistence_type == "Fall \u2192 Next Fall":
            dfc_overall = dfc_overall[dfc_overall["next_fall_total_headcount"] > 0]

        overall_title = f"{campus} — All Students — {persistence_type}"
        fig, ax = plt.subplots(figsize=(PAGE_W, PAGE_H))
        fig.text(0.50, 0.97, "Persistence by Student Type",
                 fontsize=16, fontweight="bold", ha="center")
        fig.suptitle(overall_title, fontsize=14, fontweight="bold", y=0.93)
        fig.subplots_adjust(left=0.10, right=0.92, top=0.88, bottom=0.20)
        _mpl_line_chart(ax, dfc_overall, rate_col, "")
        _add_pdf_footer(fig)
        pdf.savefig(fig)
        plt.close(fig)

        # Page 2+: By student type (2x2 grid per page)
        dfc = df_viz[df_viz["campus"] == campus].copy()
        if persistence_type == "Fall \u2192 Next Fall":
            dfc = dfc[dfc["next_fall_total_headcount"] > 0]

        styp_labels = [s for s in dfc["styp_label"].cat.categories if s in dfc["styp_label"].values]
        styp_title = f"{campus} — By Student Type — {persistence_type}"
        for page_start in range(0, len(styp_labels), 4):
            page_labels = styp_labels[page_start : page_start + 4]
            nrows = (len(page_labels) + 1) // 2
            fig, axes = plt.subplots(nrows, 2, figsize=(PAGE_W, PAGE_H))
            fig.suptitle(styp_title, fontsize=14, fontweight="bold", y=0.97)
            fig.subplots_adjust(left=0.10, right=0.92, top=0.90, bottom=0.20,
                                hspace=0.45, wspace=0.30)
            axes = axes.flatten()
            for i, label in enumerate(page_labels):
                df_s = dfc[dfc["styp_label"] == label]
                _mpl_line_chart(axes[i], df_s, rate_col, label)
            for j in range(len(page_labels), len(axes)):
                axes[j].set_visible(False)
            _add_pdf_footer(fig)
            pdf.savefig(fig)
            plt.close(fig)

    return buf.getvalue()


# ---------------------------------------------------------------------------
# Streamlit render
# ---------------------------------------------------------------------------

def render():
    st.header("Persistence by Student Type")

    # --- Sidebar controls ---
    selected_terms = st.sidebar.multiselect(
        "MIS Term IDs",
        options=_DEFAULT_TERMS,
        default=_DEFAULT_TERMS,
        key="pbs_term_ids",
    )
    query_btn = st.sidebar.button("Query", key="pbs_query_btn")

    if query_btn:
        if not selected_terms:
            st.warning("Select at least one term.")
            return
        fetch_persistence_by_styp.clear()
        df = fetch_persistence_by_styp(tuple(sorted(selected_terms)))
        if df.empty:
            st.warning("No data returned for the selected terms.")
            return
        df_prepared = _prepare_data(df)
        st.session_state["pbs_df"] = df_prepared
        st.session_state["pbs_df_overall"] = _build_overall(df_prepared)

    # --- PDF download in sidebar (after query block) ---
    if "pbs_df" in st.session_state:
        campus_val = st.session_state.get("pbs_campus", "Cypress")
        ptype_val = st.session_state.get("pbs_ptype", "Fall \u2192 Spring")
        pdf_bytes = _generate_pdf(
            st.session_state["pbs_df"],
            st.session_state["pbs_df_overall"],
            campus_val,
            ptype_val,
        )
        st.sidebar.download_button(
            "Download PDF",
            data=pdf_bytes,
            file_name="persistence_by_styp.pdf",
            mime="application/pdf",
            key="pbs_pdf_btn",
        )

    if "pbs_df" not in st.session_state:
        st.info("Select Term IDs and press **Query** to load data.")
        return

    df_viz = st.session_state["pbs_df"]
    df_overall = st.session_state["pbs_df_overall"]

    # --- Filters ---
    col1, col2 = st.columns(2)
    with col1:
        campus = st.selectbox("Campus", list(CAMP_MAP.values()), key="pbs_campus")
    with col2:
        persistence_type = st.radio(
            "Persistence Type",
            list(RATE_OPTIONS.keys()),
            key="pbs_ptype",
            horizontal=True,
        )

    # --- Section A: Overall persistence ---
    st.subheader("All Students")
    st.plotly_chart(
        _build_overall_fig(df_overall, campus, persistence_type),
        use_container_width=True,
    )

    # --- Section B: By student type ---
    st.subheader("By Student Type")
    st.plotly_chart(
        _build_by_styp_fig(df_viz, campus, persistence_type),
        use_container_width=True,
    )
