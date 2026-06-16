import io

import matplotlib
import matplotlib.pyplot as plt
import pandas as pd
import plotly.express as px
import streamlit as st
from matplotlib.backends.backend_pdf import PdfPages

from src.pipeline.config import DATASETS
from src.scripts.data_provider import fetch_kpi_dual_enrollment
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

_CFG = DATASETS["kpi_dual_enrollment"]
_DEFAULT_ACYRS = _CFG[_CFG["param_name"]]

# Credit campuses only — this MV has no NOCE (camp_code 3).
CAMP_MAP = {"1": "Cypress", "2": "Fullerton"}

METRIC_COL = "dual_enroll_count"


# ---------------------------------------------------------------------------
# Data preparation
# ---------------------------------------------------------------------------

def _acyr_label(acyr_code: int) -> str:
    """``2024`` -> ``2024-25`` (matches config.max_acyr_label())."""
    return f"{acyr_code}-{(acyr_code + 1) % 100:02d}"


def _prepare_data(df: pd.DataFrame) -> pd.DataFrame:
    """Add campus + academic-year display columns; keep only dual enrollment."""
    out = df.copy()
    out["campus"] = out["camp_code"].astype(str).map(CAMP_MAP)
    out["acyr_sort"] = out["acyr_code"].astype(int)
    out["acyr_label"] = out["acyr_sort"].map(_acyr_label)
    out[METRIC_COL] = pd.to_numeric(out[METRIC_COL], errors="coerce")
    out = out[out["campus"].notna()]
    return out.sort_values(["acyr_sort", "campus"])


def _acyr_order(df: pd.DataFrame) -> list[str]:
    return (
        df[["acyr_label", "acyr_sort"]]
        .drop_duplicates()
        .sort_values("acyr_sort")["acyr_label"]
        .tolist()
    )


# ---------------------------------------------------------------------------
# Plotly figure
# ---------------------------------------------------------------------------

def _build_campus_fig(df: pd.DataFrame, campus: str):
    """One campus chart: a single dual-enrollment count line."""
    dfc = df[df["campus"] == campus].copy()

    fig = px.line(
        dfc,
        x="acyr_label",
        y=METRIC_COL,
        markers=True,
        text=METRIC_COL,
        title=f"{campus} — Dual Enrollment",
        category_orders={"acyr_label": _acyr_order(df)},
    )
    fig.update_traces(
        texttemplate="%{y:,}",
        textposition="top center",
        hovertemplate="<b>%{x}</b><br>Dual Enrollment: %{y:,}<extra></extra>",
        mode="lines+markers+text",
    )
    # Headroom above the peak so the top data label isn't clipped.
    ymax = dfc[METRIC_COL].max()
    fig.update_yaxes(range=[0, ymax * 1.15 if pd.notna(ymax) and ymax > 0 else 1])
    fig.update_xaxes(tickangle=-45)
    fig.update_layout(
        height=400,
        xaxis_title=None,
        yaxis_title="Dual Enrollment Count",
    )
    return fig


# ---------------------------------------------------------------------------
# Excel export (underlying chart data)
# ---------------------------------------------------------------------------

def _build_excel_sections(df: pd.DataFrame) -> list[ExcelSection]:
    """One section: dual-enrollment count by academic year × campus."""
    order = _acyr_order(df)
    piv = df.pivot_table(
        index="acyr_label",
        columns="campus",
        values=METRIC_COL,
        aggfunc="first",
        observed=True,
    ).reindex(order)
    campuses = [c for c in CAMP_MAP.values() if c in piv.columns]
    out = piv.reindex(columns=campuses).reset_index()
    out = out.rename(columns={"acyr_label": "Academic Year"})
    return [ExcelSection(
        "Dual Enrollment by Campus",
        out,
        integer_cols=tuple(campuses),
    )]


def _generate_excel(df: pd.DataFrame) -> bytes:
    return sections_to_excel_bytes(
        _build_excel_sections(df),
        title="KPI - Dual Enrollment - Chart Table Data",
    )


# ---------------------------------------------------------------------------
# PDF export (matplotlib)
# ---------------------------------------------------------------------------

_PDF_FOOTER_LEFT = "https://nocccd.streamlit.app/"
_PDF_FOOTER_RIGHT = "Author: Jihoon Ahn  jahn@nocccd.edu"


def _add_pdf_footer(fig):
    fig.text(0.06, 0.02, _PDF_FOOTER_LEFT, fontsize=7, color="grey", ha="left")
    fig.text(0.94, 0.02, _PDF_FOOTER_RIGHT, fontsize=7, color="grey", ha="right")


def _mpl_campus_chart(ax, df, campus, title):
    """Draw a single dual-enrollment count line on a matplotlib Axes."""
    order = _acyr_order(df)
    dfc = df[df["campus"] == campus].set_index("acyr_label").reindex(order)
    counts = dfc[METRIC_COL]
    ax.plot(order, counts, marker="o", linewidth=2)
    for i, c in enumerate(counts):
        if pd.notna(c):
            ax.annotate(f"{int(c):,}", (i, c), textcoords="offset points",
                        xytext=(0, 10), ha="center", fontsize=8)

    ymax = counts.max()
    ax.set_ylim(0, ymax * 1.15 if pd.notna(ymax) and ymax > 0 else 1)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{int(v):,}"))
    ax.set_ylabel("Dual Enrollment Count")
    ax.set_title(title, fontsize=10, fontweight="bold")
    ax.tick_params(axis="x", rotation=45)
    ax.grid(axis="y", alpha=0.3)


def _generate_pdf(df: pd.DataFrame) -> bytes:
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
            if campus not in set(df["campus"].unique()):
                continue
            fig, ax = plt.subplots(figsize=(PAGE_W, PAGE_H))
            fig.text(0.50, 0.97, "KPI - Dual Enrollment",
                     fontsize=16, fontweight="bold", ha="center")
            fig.suptitle(f"{campus} — Dual Enrollment",
                         fontsize=14, fontweight="bold", y=0.93)
            fig.subplots_adjust(left=0.10, right=0.92, top=0.88, bottom=0.20)
            _mpl_campus_chart(ax, df, campus, "")
            _add_pdf_footer(fig)
            pdf.savefig(fig)
            plt.close(fig)

    return buf.getvalue()


# ---------------------------------------------------------------------------
# Streamlit render
# ---------------------------------------------------------------------------

def render():
    st.header("KPI - Dual Enrollment")

    # --- Sidebar controls ---
    selected_acyrs = st.sidebar.multiselect(
        "Academic Year Codes",
        options=_DEFAULT_ACYRS,
        default=_DEFAULT_ACYRS,
        key="kde_acyr_codes",
    )
    query_btn = st.sidebar.button("Query", key="kde_query_btn")

    if query_btn:
        if not selected_acyrs:
            st.warning("Select at least one academic year.")
            return
        fetch_kpi_dual_enrollment.clear()
        df = fetch_kpi_dual_enrollment(tuple(sorted(selected_acyrs)))
        if df.empty:
            st.warning("No data returned for the selected academic years.")
            return
        st.session_state["kde_df"] = _prepare_data(df)
        clear_pdf_cache("kde")
        clear_excel_cache("kde")

    # --- Downloads in sidebar (after query block) ---
    if "kde_df" in st.session_state:
        cache_key = (id(st.session_state["kde_df"]),)
        pdf_bytes = cached_pdf_bytes(
            "kde",
            cache_key,
            lambda: _generate_pdf(st.session_state["kde_df"]),
        )
        st.sidebar.download_button(
            "Download PDF",
            data=pdf_bytes,
            file_name="kpi_dual_enrollment.pdf",
            mime="application/pdf",
            key="kde_pdf_btn",
        )
        excel_bytes = cached_excel_bytes(
            "kde",
            cache_key,
            lambda: _generate_excel(st.session_state["kde_df"]),
        )
        st.sidebar.download_button(
            "Download Excel",
            data=excel_bytes,
            file_name="kpi_dual_enrollment.xlsx",
            mime=EXCEL_MIME,
            key="kde_excel_btn",
        )

    if "kde_df" not in st.session_state:
        st.info("Select Academic Year Codes and press **Query** to load data.")
        return

    df = st.session_state["kde_df"]

    st.caption(
        "Dual enrollment headcount by academic year for the credit campuses "
        "(Cypress and Fullerton)."
    )

    # --- One chart per credit campus ---
    for campus in CAMP_MAP.values():
        if campus not in set(df["campus"].unique()):
            continue
        st.plotly_chart(
            _build_campus_fig(df, campus),
            use_container_width=True,
        )
