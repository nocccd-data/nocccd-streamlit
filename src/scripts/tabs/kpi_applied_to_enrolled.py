import io

import matplotlib
import matplotlib.pyplot as plt
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from matplotlib.backends.backend_pdf import PdfPages

from src.pipeline.config import DATASETS
from src.scripts.data_provider import fetch_kpi_applied_to_enrolled
from src.scripts.pdf_cache import (
    cached_excel_bytes,
    cached_pdf_bytes,
    clear_excel_cache,
    clear_pdf_cache,
)
# Generic Excel writer shared with the BOT tabs (ExcelSection /
# sections_to_excel_bytes are not BOT-specific).
from src.scripts.tabs.bot_excel_helpers import (
    EXCEL_MIME,
    ExcelSection,
    sections_to_excel_bytes,
)

_CFG = DATASETS["kpi_applied_to_enrolled"]
_DEFAULT_TERMS = _CFG[_CFG["param_name"]]

CAMP_MAP = {"1": "Cypress", "2": "Fullerton", "3": "NOCE"}

# Display labels for student types, ordered as they should appear in legends.
STYP_MAP = {
    "first_time": "First-Time",
    "first_time_trans": "First-Time Transfer",
    "concurrent": "Concurrent",
    "adult": "Adult",
}

OVERALL_LABEL = "Overall"


# ---------------------------------------------------------------------------
# Data preparation
# ---------------------------------------------------------------------------

def _prepare_data(df: pd.DataFrame) -> pd.DataFrame:
    """Add display columns and a recomputed enrollment rate per student type."""
    out = df.copy()
    out["campus"] = out["camp_code"].astype(str).map(CAMP_MAP)
    out["styp_label"] = out["styp_code"].astype(str).map(STYP_MAP).fillna(
        out["styp_code"].astype(str)
    )
    out["term_sort"] = out["mis_term_id"].astype(int)
    out["term_short"] = "Fall " + (2000 + out["term_sort"] // 10).astype(str)
    out["app_pidm_count"] = pd.to_numeric(out["app_pidm_count"], errors="coerce")
    out["enrl_pidm_count"] = pd.to_numeric(out["enrl_pidm_count"], errors="coerce")
    # Recompute from raw counts so per-type lines and the summed Overall line
    # use the same (unrounded) methodology. NULL denom -> NaN, never inf.
    out["rate"] = out["enrl_pidm_count"] / out["app_pidm_count"].where(
        out["app_pidm_count"] > 0
    )
    return out.sort_values(["term_sort", "campus", "styp_label"])


def _build_overall(df: pd.DataFrame) -> pd.DataFrame:
    """Compute the all-student-types overall rate per campus/term.

    Overall = SUM(enrolled) / SUM(applied) across student types — a count-
    weighted rate, not an average of the per-type rates.
    """
    agg = (
        df.groupby(["campus", "term_short", "term_sort"], as_index=False)
        .agg(
            app_pidm_count=("app_pidm_count", "sum"),
            enrl_pidm_count=("enrl_pidm_count", "sum"),
        )
    )
    agg["rate"] = agg["enrl_pidm_count"] / agg["app_pidm_count"].where(
        agg["app_pidm_count"] > 0
    )
    agg["styp_label"] = OVERALL_LABEL
    return agg.sort_values("term_sort")


def _term_order(df: pd.DataFrame) -> list[str]:
    return (
        df[["term_short", "term_sort"]]
        .drop_duplicates()
        .sort_values("term_sort")["term_short"]
        .tolist()
    )


def _styp_order(df: pd.DataFrame) -> list[str]:
    present = set(df["styp_label"].unique())
    return [label for label in STYP_MAP.values() if label in present]


# ---------------------------------------------------------------------------
# Plotly figure
# ---------------------------------------------------------------------------

_HOVER_TEMPLATE = (
    "<b>%{x}</b><br>"
    "Rate: %{y:.1%}<br>"
    "Applied: %{customdata[0]:,}<br>"
    "Enrolled: %{customdata[1]:,}"
    "<extra>%{fullData.name}</extra>"
)


def _overall_line_color() -> str:
    """Overall line color: black on light themes, white on dark themes.

    Plotly traces don't honor the app's CSS ``light-dark()``, so the color has
    to be chosen at render time from the active Streamlit theme. ``type`` is
    None until the frontend reports it (first load / mid theme-switch); default
    to black then — it corrects on the next rerun.
    """
    try:
        if st.context.theme.type == "dark":
            return "white"
    except Exception:
        pass
    return "black"


def _build_campus_fig(
    df_types: pd.DataFrame, df_overall: pd.DataFrame, campus: str,
    overall_color: str = "black",
):
    """One campus chart: a line per student type plus a bold Overall line."""
    dfc = df_types[df_types["campus"] == campus].copy()

    fig = px.line(
        dfc,
        x="term_short",
        y="rate",
        color="styp_label",
        markers=True,
        title=f"{campus} — Applied to Enrolled",
        custom_data=["app_pidm_count", "enrl_pidm_count"],
        category_orders={
            "term_short": _term_order(df_types),
            "styp_label": _styp_order(df_types),
        },
    )
    fig.update_traces(hovertemplate=_HOVER_TEMPLATE, mode="lines+markers")

    dfo = df_overall[df_overall["campus"] == campus].sort_values("term_sort")
    if not dfo.empty:
        fig.add_trace(go.Scatter(
            x=dfo["term_short"],
            y=dfo["rate"],
            mode="lines+markers",
            name=OVERALL_LABEL,
            line={"color": overall_color, "width": 3, "dash": "dash"},
            marker={"symbol": "diamond", "size": 9, "color": overall_color},
            customdata=dfo[["app_pidm_count", "enrl_pidm_count"]].to_numpy(),
            hovertemplate=_HOVER_TEMPLATE,
        ))

    fig.update_yaxes(range=[0, 1], tickformat=".0%")
    fig.update_xaxes(tickangle=-45)
    fig.update_layout(
        height=400,
        xaxis_title=None,
        yaxis_title="% Enrolled",
        legend_title_text="Student Type",
    )
    return fig


# ---------------------------------------------------------------------------
# Excel export (underlying chart data)
# ---------------------------------------------------------------------------

def _build_excel_sections(
    df_types: pd.DataFrame, df_overall: pd.DataFrame,
) -> list[ExcelSection]:
    """One tidy section: per-student-type rows plus the computed Overall rows."""
    cols = ["campus", "term_short", "term_sort", "styp_label",
            "app_pidm_count", "enrl_pidm_count", "rate"]
    combined = pd.concat(
        [df_types[cols], df_overall[cols]], ignore_index=True
    )
    # Sort campus → term, with the Overall row last within each campus/term.
    combined["_is_overall"] = (combined["styp_label"] == OVERALL_LABEL).astype(int)
    combined = combined.sort_values(
        ["campus", "term_sort", "_is_overall", "styp_label"]
    )
    out = combined.rename(columns={
        "campus": "Campus",
        "term_short": "Term",
        "styp_label": "Student Type",
        "app_pidm_count": "Applied",
        "enrl_pidm_count": "Enrolled",
        "rate": "% Enrolled",
    })[["Campus", "Term", "Student Type", "Applied", "Enrolled", "% Enrolled"]]
    return [ExcelSection(
        "Applied to Enrolled by Student Type",
        out,
        percent_cols=("% Enrolled",),
        integer_cols=("Applied", "Enrolled"),
    )]


def _generate_excel(df_types: pd.DataFrame, df_overall: pd.DataFrame) -> bytes:
    return sections_to_excel_bytes(
        _build_excel_sections(df_types, df_overall),
        title="KPI - Applied to Enrolled - Chart Table Data",
    )


# ---------------------------------------------------------------------------
# PDF export (matplotlib)
# ---------------------------------------------------------------------------

_PDF_FOOTER_LEFT = "https://nocccd.streamlit.app/"
_PDF_FOOTER_RIGHT = "Author: Jihoon Ahn  jahn@nocccd.edu"


def _add_pdf_footer(fig):
    fig.text(0.06, 0.02, _PDF_FOOTER_LEFT, fontsize=7, color="grey", ha="left")
    fig.text(0.94, 0.02, _PDF_FOOTER_RIGHT, fontsize=7, color="grey", ha="right")


def _mpl_campus_chart(ax, df_types, df_overall, campus, title):
    """Draw a multi-line applied-to-enrolled chart on a matplotlib Axes."""
    terms = _term_order(df_types)
    dfc = df_types[df_types["campus"] == campus]

    for styp in _styp_order(df_types):
        sub = (
            dfc[dfc["styp_label"] == styp]
            .set_index("term_short")
            .reindex(terms)
        )
        ax.plot(terms, sub["rate"], marker="o", linewidth=1.5, label=styp)

    dfo = (
        df_overall[df_overall["campus"] == campus]
        .set_index("term_short")
        .reindex(terms)
    )
    ax.plot(terms, dfo["rate"], marker="D", markersize=7, linewidth=2.5,
            linestyle="--", color="black", label=OVERALL_LABEL)

    ax.set_ylim(0, 1)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:.0%}"))
    ax.set_ylabel("% Enrolled")
    ax.set_title(title, fontsize=10, fontweight="bold")
    ax.tick_params(axis="x", rotation=45)
    ax.grid(axis="y", alpha=0.3)
    ax.legend(fontsize=8, loc="best", title="Student Type")


def _generate_pdf(df_types: pd.DataFrame, df_overall: pd.DataFrame) -> bytes:
    matplotlib.rcParams.update({
        "figure.facecolor": "white",
        "axes.facecolor": "white",
        "text.color": "black",
        "savefig.facecolor": "white",
    })

    PAGE_W, PAGE_H = 11.0, 8.5
    buf = io.BytesIO()
    with PdfPages(buf) as pdf:
        for campus in CAMP_MAP.values():
            if campus not in set(df_types["campus"].unique()):
                continue
            fig, ax = plt.subplots(figsize=(PAGE_W, PAGE_H))
            fig.text(0.50, 0.97, "KPI - Applied to Enrolled",
                     fontsize=16, fontweight="bold", ha="center")
            fig.suptitle(f"{campus} — Applied to Enrolled",
                         fontsize=14, fontweight="bold", y=0.93)
            fig.subplots_adjust(left=0.10, right=0.92, top=0.88, bottom=0.20)
            _mpl_campus_chart(ax, df_types, df_overall, campus, "")
            _add_pdf_footer(fig)
            pdf.savefig(fig)
            plt.close(fig)

    return buf.getvalue()


# ---------------------------------------------------------------------------
# Streamlit render
# ---------------------------------------------------------------------------

def render():
    st.header("KPI - Applied to Enrolled")

    # --- Sidebar controls ---
    selected_terms = st.sidebar.multiselect(
        "MIS Term IDs",
        options=_DEFAULT_TERMS,
        default=_DEFAULT_TERMS,
        key="ate_term_ids",
    )
    query_btn = st.sidebar.button("Query", key="ate_query_btn")

    if query_btn:
        if not selected_terms:
            st.warning("Select at least one term.")
            return
        fetch_kpi_applied_to_enrolled.clear()
        df = fetch_kpi_applied_to_enrolled(tuple(sorted(selected_terms)))
        if df.empty:
            st.warning("No data returned for the selected terms.")
            return
        df_prepared = _prepare_data(df)
        st.session_state["ate_df_types"] = df_prepared
        st.session_state["ate_df_overall"] = _build_overall(df_prepared)
        clear_pdf_cache("ate")
        clear_excel_cache("ate")

    # --- Downloads in sidebar (after query block) ---
    if "ate_df_types" in st.session_state:
        cache_key = (id(st.session_state["ate_df_types"]),)
        pdf_bytes = cached_pdf_bytes(
            "ate",
            cache_key,
            lambda: _generate_pdf(
                st.session_state["ate_df_types"],
                st.session_state["ate_df_overall"],
            ),
        )
        st.sidebar.download_button(
            "Download PDF",
            data=pdf_bytes,
            file_name="kpi_applied_to_enrolled.pdf",
            mime="application/pdf",
            key="ate_pdf_btn",
        )
        excel_bytes = cached_excel_bytes(
            "ate",
            cache_key,
            lambda: _generate_excel(
                st.session_state["ate_df_types"],
                st.session_state["ate_df_overall"],
            ),
        )
        st.sidebar.download_button(
            "Download Excel",
            data=excel_bytes,
            file_name="kpi_applied_to_enrolled.xlsx",
            mime=EXCEL_MIME,
            key="ate_excel_btn",
        )

    if "ate_df_types" not in st.session_state:
        st.info("Select Term IDs and press **Query** to load data.")
        return

    df_types = st.session_state["ate_df_types"]
    df_overall = st.session_state["ate_df_overall"]

    st.caption(
        "Enrollment yield (% of applicants who enrolled) by student type, with a "
        "count-weighted **Overall** line summing all student types."
    )

    # --- One chart per campus ---
    overall_color = _overall_line_color()
    for campus in CAMP_MAP.values():
        if campus not in set(df_types["campus"].unique()):
            continue
        st.plotly_chart(
            _build_campus_fig(df_types, df_overall, campus, overall_color),
            width="stretch",
        )
