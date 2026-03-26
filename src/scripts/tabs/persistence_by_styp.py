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
    if persistence_type == "Fall \u2192 Next Fall":
        dfc = dfc[dfc["next_fall_total_headcount"] > 0]

    fig = px.line(
        dfc,
        x="term_short",
        y=rate_col,
        markers=True,
        text=rate_col,
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


def _build_by_styp_fig(
    df_viz: pd.DataFrame, campus: str, persistence_type: str,
    projection: pd.DataFrame | None = None,
):
    opts = RATE_OPTIONS[persistence_type]
    rate_col = opts["rate_col"]
    dfc = df_viz[df_viz["campus"] == campus].copy()
    if persistence_type == "Fall \u2192 Next Fall":
        dfc = dfc[dfc["next_fall_total_headcount"] > 0]

    fig = px.line(
        dfc,
        x="term_short",
        y=rate_col,
        facet_col="styp_label",
        facet_col_wrap=3,
        markers=True,
        text=rate_col,
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

    if projection is not None and not projection.empty and not dfc.empty:
        proj_campus = projection[projection["campus"] == campus]
        categories = [s for s in dfc["styp_label"].cat.categories
                      if s in dfc["styp_label"].values]

        # Traces are NOT in categorical order — match each trace to its
        # category by comparing y-data against known rates.
        cat_to_axes: dict[str, tuple[str, str]] = {}
        for trace in fig.data:
            trace_y = np.array(trace.y, dtype=float)
            for cat in categories:
                if cat in cat_to_axes:
                    continue
                cat_y = (dfc[dfc["styp_label"] == cat]
                         .sort_values("term_sort")[rate_col].values)
                if len(trace_y) == len(cat_y) and np.allclose(
                    trace_y, cat_y, equal_nan=True
                ):
                    cat_to_axes[cat] = (trace.xaxis or "x",
                                        trace.yaxis or "y")
                    break

        for cat, (src_xaxis, src_yaxis) in cat_to_axes.items():
            proj_r = proj_campus[proj_campus["styp_label"] == cat]
            if proj_r.empty:
                continue
            dfc_cat = dfc[dfc["styp_label"] == cat].sort_values("term_sort")
            if dfc_cat.empty:
                continue
            last = dfc_cat.iloc[-1]

            kw: dict = dict(
                x=[last["term_short"], proj_r.iloc[0]["term_short"]],
                y=[last[rate_col], proj_r.iloc[0][rate_col]],
                mode="lines+markers+text",
                line={"dash": "dash", "color": "grey"},
                marker={"symbol": "diamond", "size": 10},
                text=["", f"{proj_r.iloc[0][rate_col]:.0%}"],
                textposition="top center",
                showlegend=False,
                hovertemplate=(
                    "<b>%{x}</b><br>Projected: %{y:.1%}<extra></extra>"
                ),
            )
            if src_xaxis != "x":
                kw["xaxis"] = src_xaxis
            if src_yaxis != "y":
                kw["yaxis"] = src_yaxis
            fig.add_trace(go.Scatter(**kw))

    return fig


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
    df_viz: pd.DataFrame, df_overall: pd.DataFrame,
    campus: str, persistence_type: str,
    proj_overall: pd.DataFrame | None = None,
    proj_by_styp: pd.DataFrame | None = None,
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

    # Extract projection values for this campus
    def _get_proj(proj_df, campus_val, label_col=None, label_val=None):
        if proj_df is None or proj_df.empty:
            return None, None
        mask = proj_df["campus"] == campus_val
        if label_col and label_val:
            mask = mask & (proj_df[label_col] == label_val)
        row = proj_df[mask]
        if row.empty:
            return None, None
        return row.iloc[0][rate_col], row.iloc[0]["term_short"]

    buf = io.BytesIO()
    with PdfPages(buf) as pdf:
        # Page 1: Overall
        dfc_overall = df_overall[df_overall["campus"] == campus].copy()
        if persistence_type == "Fall \u2192 Next Fall":
            dfc_overall = dfc_overall[dfc_overall["next_fall_total_headcount"] > 0]

        p_rate, p_label = _get_proj(proj_overall, campus)

        overall_title = f"{campus} — All Students — {persistence_type}"
        fig, ax = plt.subplots(figsize=(PAGE_W, PAGE_H))
        fig.text(0.50, 0.97, "Persistence by Student Type",
                 fontsize=16, fontweight="bold", ha="center")
        fig.suptitle(overall_title, fontsize=14, fontweight="bold", y=0.93)
        fig.subplots_adjust(left=0.10, right=0.92, top=0.88, bottom=0.20)
        _mpl_line_chart(ax, dfc_overall, rate_col, "",
                        proj_rate=p_rate, proj_label=p_label)
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
                s_rate, s_label = _get_proj(proj_by_styp, campus,
                                            "styp_label", label)
                _mpl_line_chart(axes[i], df_s, rate_col, label,
                                proj_rate=s_rate, proj_label=s_label)
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

        # Compute projections for PDF (uses current sidebar selections)
        pdf_proj_overall = None
        pdf_proj_by_styp = None
        if show_projection and proj_method:
            opts = RATE_OPTIONS[ptype_val]
            rate_col = opts["rate_col"]
            df_o = st.session_state["pbs_df_overall"].copy()
            if ptype_val == "Fall \u2192 Next Fall":
                df_o = df_o[df_o["next_fall_total_headcount"] > 0]
            if not df_o.empty:
                pdf_proj_overall = _compute_projections(
                    df_o, rate_col, ["campus"], proj_method)
            df_v = st.session_state["pbs_df"].copy()
            if ptype_val == "Fall \u2192 Next Fall":
                df_v = df_v[df_v["next_fall_total_headcount"] > 0]
            if not df_v.empty:
                pdf_proj_by_styp = _compute_projections(
                    df_v, rate_col, ["campus", "styp_label"], proj_method)

        pdf_bytes = _generate_pdf(
            st.session_state["pbs_df"],
            st.session_state["pbs_df_overall"],
            campus_val,
            ptype_val,
            proj_overall=pdf_proj_overall,
            proj_by_styp=pdf_proj_by_styp,
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

    # --- Compute projections for charts ---
    proj_overall = None
    proj_by_styp = None
    if show_projection and proj_method:
        opts = RATE_OPTIONS[persistence_type]
        rate_col = opts["rate_col"]
        df_o = df_overall.copy()
        if persistence_type == "Fall \u2192 Next Fall":
            df_o = df_o[df_o["next_fall_total_headcount"] > 0]
        if not df_o.empty:
            proj_overall = _compute_projections(
                df_o, rate_col, ["campus"], proj_method)
        df_v = df_viz.copy()
        if persistence_type == "Fall \u2192 Next Fall":
            df_v = df_v[df_v["next_fall_total_headcount"] > 0]
        if not df_v.empty:
            proj_by_styp = _compute_projections(
                df_v, rate_col, ["campus", "styp_label"], proj_method)

    # --- Section A: Overall persistence ---
    st.subheader("All Students")
    st.plotly_chart(
        _build_overall_fig(df_overall, campus, persistence_type,
                           projection=proj_overall),
        use_container_width=True,
    )

    # --- Section B: By student type ---
    st.subheader("By Student Type")
    st.plotly_chart(
        _build_by_styp_fig(df_viz, campus, persistence_type,
                           projection=proj_by_styp),
        use_container_width=True,
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
                    "**R\u00b2** indicates how well the linear model fits the "
                    "historical data. Values closer to 1.0 mean a stronger "
                    "linear trend; values near 0 suggest no clear trend and "
                    "the projection should be treated with caution."
                )
            else:
                st.markdown(
                    "**Weighted Moving Average** uses the last 3 data points "
                    "with increasing weights (1\u00d7, 2\u00d7, 3\u00d7), "
                    "giving the most recent year triple the influence of the "
                    "oldest year in the window. This method responds quickly "
                    "to recent changes without assuming a long-term trend."
                )

            st.caption(
                "Projections are estimates based on historical patterns "
                "and should be interpreted with caution. Projected values "
                "are clipped to the 0\u2013100% range."
            )

            # R² table for linear regression
            if proj_method == "Linear Regression":
                r_sq_rows: list[dict] = []
                if proj_overall is not None and "_r_squared" in proj_overall.columns:
                    for _, row in proj_overall[
                        proj_overall["campus"] == campus
                    ].iterrows():
                        r_sq_rows.append({
                            "Group": "All Students",
                            "R\u00b2": f"{row['_r_squared']:.3f}",
                        })
                if proj_by_styp is not None and "_r_squared" in proj_by_styp.columns:
                    for _, row in proj_by_styp[
                        proj_by_styp["campus"] == campus
                    ].iterrows():
                        r_sq_rows.append({
                            "Group": row["styp_label"],
                            "R\u00b2": f"{row['_r_squared']:.3f}",
                        })
                if r_sq_rows:
                    st.dataframe(
                        pd.DataFrame(r_sq_rows),
                        hide_index=True,
                        use_container_width=False,
                    )
