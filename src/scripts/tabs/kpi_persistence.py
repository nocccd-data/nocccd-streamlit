import io

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from matplotlib.backends.backend_pdf import PdfPages

from src.pipeline.config import DATASETS
from src.scripts.data_provider import fetch_kpi_persistence
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

_CFG = DATASETS["kpi_persistence"]
_DEFAULT_TERMS = _CFG[_CFG["param_name"]]

CAMP_MAP = {"1": "Cypress", "2": "Fullerton", "3": "NOCE"}

RATE_OPTIONS = {
    "Fall → Spring": {
        "rate_col": "spring_persistence_rate",
        "p_count_col": "curr_fall_p_count",
        "headcount_col": "spring_total_headcount",
    },
    "Fall → Next Fall": {
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
# Projection helpers
# ---------------------------------------------------------------------------

def _compute_next_term(df: pd.DataFrame) -> tuple[str, int]:
    """Return (term_short, term_sort) for the next projected fall term."""
    max_sort = int(df["term_sort"].max())
    next_sort = max_sort + 10
    year = 2000 + (next_sort // 10)
    return f"{year}-{str(year + 1)[-2:]}", next_sort


def _project_rate(
    rates: list[float], method: str,
) -> tuple[float | None, float | None]:
    """Project one step ahead. Returns (projected_rate, r_squared|None)."""
    valid = [(i, r) for i, r in enumerate(rates) if pd.notna(r)]

    if method == "Linear Regression":
        if len(valid) < 2:
            return None, None
        x = np.array([v[0] for v in valid], dtype=float)
        y = np.array([v[1] for v in valid])
        coeffs = np.polyfit(x, y, 1)
        projected = float(np.polyval(coeffs, len(rates)))
        y_pred = np.polyval(coeffs, x)
        ss_res = float(np.sum((y - y_pred) ** 2))
        ss_tot = float(np.sum((y - np.mean(y)) ** 2))
        r_sq = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0
        return float(np.clip(projected, 0, 1)), r_sq

    # Weighted Moving Average
    if len(valid) < 3:
        return None, None
    last3 = [v[1] for v in valid[-3:]]
    projected = float(np.average(last3, weights=[1, 2, 3]))
    return float(np.clip(projected, 0, 1)), None


def _compute_projections(
    df: pd.DataFrame,
    rate_col: str,
    group_cols: list[str],
    method: str,
) -> pd.DataFrame:
    """Compute one projected row per group."""
    next_label, next_sort = _compute_next_term(df)
    rows: list[dict] = []
    for keys, grp in df.groupby(group_cols, observed=True):
        grp_sorted = grp.sort_values("term_sort")
        rates = grp_sorted[rate_col].tolist()
        proj_val, r_sq = _project_rate(rates, method)
        if proj_val is None:
            continue
        if not isinstance(keys, tuple):
            keys = (keys,)
        row = dict(zip(group_cols, keys))
        row["term_short"] = next_label
        row["term_sort"] = next_sort
        row[rate_col] = proj_val
        row["_r_squared"] = r_sq
        rows.append(row)
    return pd.DataFrame(rows) if rows else pd.DataFrame()


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


def _build_overall_fig(
    df_overall: pd.DataFrame, campus: str, persistence_type: str,
    projection: pd.DataFrame | None = None,
):
    opts = RATE_OPTIONS[persistence_type]
    rate_col = opts["rate_col"]
    dfc = df_overall[df_overall["campus"] == campus].copy()
    if persistence_type == "Fall → Next Fall":
        dfc = dfc[dfc["next_fall_total_headcount"] > 0]

    fig = px.line(
        dfc,
        x="term_short",
        y=rate_col,
        markers=True,
        text=rate_col,
        title=f"{campus} — {persistence_type}",
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

    if projection is not None and not projection.empty and not dfc.empty:
        proj_row = projection[projection["campus"] == campus]
        if not proj_row.empty:
            last = dfc.iloc[-1]
            fig.add_trace(go.Scatter(
                x=[last["term_short"], proj_row.iloc[0]["term_short"]],
                y=[last[rate_col], proj_row.iloc[0][rate_col]],
                mode="lines+markers+text",
                line={"dash": "dash", "color": "grey"},
                marker={"symbol": "diamond", "size": 10},
                text=["", f"{proj_row.iloc[0][rate_col]:.0%}"],
                textposition="top center",
                showlegend=False,
                hovertemplate="<b>%{x}</b><br>Projected: %{y:.1%}<extra></extra>",
            ))

    return fig


# ---------------------------------------------------------------------------
# Excel export (underlying chart data)
# ---------------------------------------------------------------------------

def _build_excel_sections(df_overall: pd.DataFrame) -> list[ExcelSection]:
    """One section: overall (all-students) persistence rates + counts."""
    out = df_overall.sort_values(["campus", "term_sort"]).rename(columns={
        "campus": "Campus",
        "term_short": "Term",
        "curr_fall_p_count": "Fall P-Count",
        "spring_total_headcount": "Spring Headcount",
        "next_fall_total_headcount": "Next Fall Headcount",
        "spring_persistence_rate": "Fall → Spring Rate",
        "next_fall_persistence_rate": "Fall → Next Fall Rate",
    })[[
        "Campus", "Term", "Fall P-Count",
        "Spring Headcount", "Fall → Spring Rate",
        "Next Fall Headcount", "Fall → Next Fall Rate",
    ]]
    return [ExcelSection(
        "Persistence Rates (All Students)",
        out,
        percent_cols=("Fall → Spring Rate", "Fall → Next Fall Rate"),
        integer_cols=("Fall P-Count", "Spring Headcount", "Next Fall Headcount"),
    )]


def _generate_excel(df_overall: pd.DataFrame) -> bytes:
    return sections_to_excel_bytes(
        _build_excel_sections(df_overall),
        title="KPI - Persistence - Chart Table Data",
    )


# ---------------------------------------------------------------------------
# PDF export (matplotlib)
# ---------------------------------------------------------------------------

_PDF_FOOTER_LEFT = "https://nocccd.streamlit.app/"
_PDF_FOOTER_RIGHT = "Author: Jihoon Ahn  jahn@nocccd.edu"


def _add_pdf_footer(fig):
    fig.text(0.06, 0.02, _PDF_FOOTER_LEFT, fontsize=7, color="grey", ha="left")
    fig.text(0.94, 0.02, _PDF_FOOTER_RIGHT, fontsize=7, color="grey", ha="right")


def _mpl_line_chart(
    ax, df_plot: pd.DataFrame, rate_col: str, title: str,
    proj_rate: float | None = None, proj_label: str | None = None,
):
    """Draw a single persistence line chart on a matplotlib Axes."""
    terms = df_plot["term_short"].tolist()
    rates = df_plot[rate_col].tolist()
    ax.plot(terms, rates, marker="o", linewidth=2)
    for i, (t, r) in enumerate(zip(terms, rates)):
        if pd.notna(r):
            ax.annotate(f"{r:.0%}", (i, r), textcoords="offset points",
                        xytext=(0, 10), ha="center", fontsize=8)

    if proj_rate is not None and proj_label is not None and terms:
        all_terms = terms + [proj_label]
        ax.plot(
            [terms[-1], proj_label],
            [rates[-1], proj_rate],
            marker="D", markersize=8, linewidth=2,
            linestyle="--", color="grey",
        )
        ax.annotate(
            f"{proj_rate:.0%}", (len(terms), proj_rate),
            textcoords="offset points", xytext=(0, 10),
            ha="center", fontsize=8, color="grey",
        )
        ax.set_xticks(range(len(all_terms)))
        ax.set_xticklabels(all_terms)

    ax.set_ylim(0, 1)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:.0%}"))
    ax.set_title(title, fontsize=10, fontweight="bold")
    ax.tick_params(axis="x", rotation=45)
    ax.grid(axis="y", alpha=0.3)


def _generate_pdf(
    df_overall: pd.DataFrame,
    persistence_type: str,
    proj_overall: pd.DataFrame | None = None,
    proj_method: str | None = None,
) -> bytes:
    matplotlib.rcParams.update({
        "figure.facecolor": "white",
        "axes.facecolor": "white",
        "text.color": "black",
        "savefig.facecolor": "white",
    })

    opts = RATE_OPTIONS[persistence_type]
    rate_col = opts["rate_col"]
    PAGE_W, PAGE_H = 11.0, 8.5

    # Extract projection value for a campus
    def _get_proj(proj_df, campus_val):
        if proj_df is None or proj_df.empty:
            return None, None
        row = proj_df[proj_df["campus"] == campus_val]
        if row.empty:
            return None, None
        return row.iloc[0][rate_col], row.iloc[0]["term_short"]

    buf = io.BytesIO()
    with PdfPages(buf) as pdf:
        # One page per campus: overall (all students) persistence
        for campus in CAMP_MAP.values():
            dfc_overall = df_overall[df_overall["campus"] == campus].copy()
            if persistence_type == "Fall → Next Fall":
                dfc_overall = dfc_overall[dfc_overall["next_fall_total_headcount"] > 0]
            if dfc_overall.empty:
                continue

            p_rate, p_label = _get_proj(proj_overall, campus)

            fig, ax = plt.subplots(figsize=(PAGE_W, PAGE_H))
            fig.text(0.50, 0.97, "KPI - Persistence",
                     fontsize=16, fontweight="bold", ha="center")
            fig.suptitle(f"{campus} — {persistence_type}",
                         fontsize=14, fontweight="bold", y=0.93)
            fig.subplots_adjust(left=0.10, right=0.92, top=0.88, bottom=0.20)
            _mpl_line_chart(ax, dfc_overall, rate_col, "",
                            proj_rate=p_rate, proj_label=p_label)
            _add_pdf_footer(fig)
            pdf.savefig(fig)
            plt.close(fig)

        # Methodology page (only when projections are active)
        if proj_method and proj_overall is not None:
            fig = plt.figure(figsize=(PAGE_W, PAGE_H))
            fig.text(0.50, 0.95, "Projection Methodology",
                     fontsize=16, fontweight="bold", ha="center")

            y = 0.85
            if proj_method == "Linear Regression":
                lines = [
                    "Method: Linear Regression",
                    "",
                    "A straight line (y = mx + b) is fit through all available",
                    "historical data points using least-squares regression.",
                    "The projected value is the extrapolated point for the",
                    "next fall term.",
                    "",
                    "R² (goodness of fit) indicates how well the linear",
                    "model fits the historical data. Values closer to 1.0",
                    "mean a stronger linear trend; values near 0 suggest no",
                    "clear trend and the projection should be treated with",
                    "caution.",
                ]
            else:
                lines = [
                    "Method: Weighted Moving Average",
                    "",
                    "The last 3 data points are averaged with increasing",
                    "weights (1×, 2×, 3×), giving the most recent",
                    "year triple the influence of the oldest year in the",
                    "window. This method responds quickly to recent changes",
                    "without assuming a long-term trend.",
                ]

            for line in lines:
                if line == "":
                    y -= 0.015
                    continue
                weight = "bold" if line.startswith("Method:") else "normal"
                fig.text(0.10, y, line, fontsize=11, fontweight=weight,
                         va="top")
                y -= 0.03

            y -= 0.02
            fig.text(0.10, y,
                     "Projections are estimates based on historical patterns "
                     "and should be interpreted with caution.\n"
                     "Projected values are clipped to the 0–100% range.",
                     fontsize=9, color="grey", va="top")

            # R² table for linear regression
            if proj_method == "Linear Regression":
                r_sq_data: list[tuple[str, str]] = []
                if "_r_squared" in proj_overall.columns:
                    for campus in CAMP_MAP.values():
                        row = proj_overall[proj_overall["campus"] == campus]
                        if not row.empty:
                            r_sq_data.append(
                                (campus, f"{row.iloc[0]['_r_squared']:.3f}"))

                if r_sq_data:
                    y -= 0.05
                    fig.text(0.10, y, "R² by Campus", fontsize=12,
                             fontweight="bold", va="top")
                    y -= 0.035
                    col_w = [0.30, 0.10]
                    # Header
                    fig.text(0.10, y, "Campus", fontsize=10,
                             fontweight="bold", va="top")
                    fig.text(0.10 + col_w[0], y, "R²", fontsize=10,
                             fontweight="bold", va="top")
                    y -= 0.025
                    for grp, rsq in r_sq_data:
                        fig.text(0.10, y, grp, fontsize=10, va="top")
                        fig.text(0.10 + col_w[0], y, rsq, fontsize=10,
                                 va="top")
                        y -= 0.025

            _add_pdf_footer(fig)
            pdf.savefig(fig)
            plt.close(fig)

    return buf.getvalue()


# ---------------------------------------------------------------------------
# Streamlit render
# ---------------------------------------------------------------------------

def render():
    st.header("KPI - Persistence")

    # --- Sidebar controls ---
    selected_terms = st.sidebar.multiselect(
        "MIS Term IDs",
        options=_DEFAULT_TERMS,
        default=_DEFAULT_TERMS,
        key="pbs_term_ids",
    )
    query_btn = st.sidebar.button("Query", key="pbs_query_btn")

    show_projection = st.sidebar.checkbox(
        "Show Projection", value=False, key="pbs_show_proj",
    )
    proj_method = None
    if show_projection:
        proj_method = st.sidebar.radio(
            "Projection Method",
            ["Linear Regression", "Weighted Moving Average"],
            key="pbs_proj_method",
        )

    if query_btn:
        if not selected_terms:
            st.warning("Select at least one term.")
            return
        fetch_kpi_persistence.clear()
        df = fetch_kpi_persistence(tuple(sorted(selected_terms)))
        if df.empty:
            st.warning("No data returned for the selected terms.")
            return
        df_prepared = _prepare_data(df)
        st.session_state["pbs_df_overall"] = _build_overall(df_prepared)
        clear_pdf_cache("pbs")
        clear_excel_cache("pbs")

    # --- PDF download in sidebar (after query block) ---
    if "pbs_df_overall" in st.session_state:
        ptype_val = st.session_state.get("pbs_ptype", "Fall → Spring")

        # Compute projections for PDF (uses current sidebar selections)
        pdf_proj_overall = None
        if show_projection and proj_method:
            opts = RATE_OPTIONS[ptype_val]
            rate_col = opts["rate_col"]
            df_o = st.session_state["pbs_df_overall"].copy()
            if ptype_val == "Fall → Next Fall":
                df_o = df_o[df_o["next_fall_total_headcount"] > 0]
            if not df_o.empty:
                pdf_proj_overall = _compute_projections(
                    df_o, rate_col, ["campus"], proj_method)

        pdf_bytes = cached_pdf_bytes(
            "pbs",
            (
                id(st.session_state["pbs_df_overall"]),
                ptype_val,
                show_projection,
                proj_method,
            ),
            lambda: _generate_pdf(
                st.session_state["pbs_df_overall"],
                ptype_val,
                proj_overall=pdf_proj_overall,
                proj_method=proj_method if show_projection else None,
            ),
        )
        st.sidebar.download_button(
            "Download PDF",
            data=pdf_bytes,
            file_name="kpi_persistence.pdf",
            mime="application/pdf",
            key="pbs_pdf_btn",
        )
        excel_bytes = cached_excel_bytes(
            "pbs",
            (id(st.session_state["pbs_df_overall"]),),
            lambda: _generate_excel(st.session_state["pbs_df_overall"]),
        )
        st.sidebar.download_button(
            "Download Excel",
            data=excel_bytes,
            file_name="kpi_persistence.xlsx",
            mime=EXCEL_MIME,
            key="pbs_excel_btn",
        )

    if "pbs_df_overall" not in st.session_state:
        st.info("Select Term IDs and press **Query** to load data.")
        return

    df_overall = st.session_state["pbs_df_overall"]

    # --- Filter: persistence type ---
    persistence_type = st.radio(
        "Persistence Type",
        list(RATE_OPTIONS.keys()),
        key="pbs_ptype",
        horizontal=True,
    )

    # --- Compute projections for charts ---
    proj_overall = None
    if show_projection and proj_method:
        opts = RATE_OPTIONS[persistence_type]
        rate_col = opts["rate_col"]
        df_o = df_overall.copy()
        if persistence_type == "Fall → Next Fall":
            df_o = df_o[df_o["next_fall_total_headcount"] > 0]
        if not df_o.empty:
            proj_overall = _compute_projections(
                df_o, rate_col, ["campus"], proj_method)

    # --- Persistence by campus (all three) ---
    for campus in CAMP_MAP.values():
        st.plotly_chart(
            _build_overall_fig(df_overall, campus, persistence_type,
                               projection=proj_overall),
            width="stretch",
        )

    # --- Projection methodology expander ---
    if show_projection and proj_method:
        with st.expander("Projection Methodology"):
            if proj_method == "Linear Regression":
                st.markdown(
                    "**Linear Regression** fits a straight line through all "
                    "available historical data points using least-squares "
                    "regression. The projected value is the extrapolated point "
                    "for the next fall term.\n\n"
                    "**R²** indicates how well the linear model fits the "
                    "historical data. Values closer to 1.0 mean a stronger "
                    "linear trend; values near 0 suggest no clear trend and "
                    "the projection should be treated with caution."
                )
            else:
                st.markdown(
                    "**Weighted Moving Average** uses the last 3 data points "
                    "with increasing weights (1×, 2×, 3×), "
                    "giving the most recent year triple the influence of the "
                    "oldest year in the window. This method responds quickly "
                    "to recent changes without assuming a long-term trend."
                )

            st.caption(
                "Projections are estimates based on historical patterns "
                "and should be interpreted with caution. Projected values "
                "are clipped to the 0–100% range."
            )

            # R² table for linear regression
            if proj_method == "Linear Regression":
                r_sq_rows: list[dict] = []
                if proj_overall is not None and "_r_squared" in proj_overall.columns:
                    for campus in CAMP_MAP.values():
                        row = proj_overall[proj_overall["campus"] == campus]
                        if not row.empty:
                            r_sq_rows.append({
                                "Campus": campus,
                                "R²": f"{row.iloc[0]['_r_squared']:.3f}",
                            })
                if r_sq_rows:
                    st.dataframe(
                        pd.DataFrame(r_sq_rows),
                        hide_index=True,
                        width="content",
                    )
