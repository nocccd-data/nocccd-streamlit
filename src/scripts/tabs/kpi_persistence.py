import io

import matplotlib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.ticker import FuncFormatter

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

# Display labels for student types, ordered as they should appear in legends.
STYP_MAP = {
    "first_time": "First-Time",
    "first_time_trans": "First-Time Transfer",
    "returning": "Returning",
    "continuing": "Continuing",
    "adult": "Adult",
    "concurrent": "Concurrent",
    "dual_enroll": "Dual Enrollment",
}

OVERALL_LABEL = "Overall"

# The two rates do NOT share a denominator. Fall → Spring divides by the fall
# cohort minus that fall's completers (``curr_fall_p_count``); Fall → Next Fall
# divides by the fall cohort minus anyone who completed in the fall *or the
# following spring* (``next_fall_p_denominator``), since a student who already
# earned a credential would not be expected to re-enroll. Using
# ``curr_fall_p_count`` for both — as this tab did before the MV was rebuilt —
# understates Fall → Next Fall by several points and makes the chart disagree
# with the MV's own rate columns.
RATE_OPTIONS = {
    "Fall → Spring": {
        "rate_col": "spring_persistence_rate",
        "p_count_col": "curr_fall_p_count",
        "p_count_label": "Fall P-Count",
        "headcount_col": "spring_total_headcount",
        "follow_up": "the following spring",
    },
    "Fall → Next Fall": {
        "rate_col": "next_fall_persistence_rate",
        "p_count_col": "next_fall_p_denominator",
        "p_count_label": "Fall P-Count (less spring completers)",
        "headcount_col": "next_fall_total_headcount",
        "follow_up": "the next fall",
    },
}

# Columns `_prepare_data` / `_build_overall` cannot work without. An extract
# built before the MV rebuild has no `next_fall_p_denominator`, which would
# otherwise surface as a bare KeyError traceback.
_REQUIRED_COLS = frozenset({
    "mis_term_id",
    "camp_code",
    "styp_code",
    "curr_fall_p_count",
    "next_fall_p_denominator",
    "spring_total_headcount",
    "next_fall_total_headcount",
})


# ---------------------------------------------------------------------------
# Data preparation
# ---------------------------------------------------------------------------

def _term_label(term_id: int) -> str:
    """``247`` -> ``Fall 2024`` — the fall term the cohort *starts* in.

    The MV labels this ``2024-25 Fall`` and the tab used to strip the
    ``" Fall"`` suffix, leaving a bare ``2024-25`` that reads as though it
    might mean the spring. It is the fall cohort: ``Fall 2024`` persists into
    Spring 2025 (Fall → Spring) or Fall 2025 (Fall → Next Fall). Naming it the
    same way as the Applied-to-Enrolled tab keeps one MIS term reading
    identically across both.
    """
    return f"Fall {2000 + int(term_id) // 10}"


def _prepare_data(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["campus"] = out["camp_code"].astype(str).map(CAMP_MAP)
    out["term_sort"] = out["mis_term_id"].astype(int)
    out["term_short"] = out["term_sort"].map(_term_label)
    out["styp_label"] = out["styp_code"].astype(str).map(STYP_MAP).fillna(
        out["styp_code"].astype(str)
    )
    for col in ("curr_fall_p_count", "next_fall_p_denominator",
                "spring_total_headcount", "next_fall_total_headcount"):
        out[col] = pd.to_numeric(out[col], errors="coerce")
    # Recompute per-type rates from the raw counts. The MV's own rate columns
    # are rounded to 2 dp, and the Overall line divides summed counts, so
    # recomputing keeps every line on one unrounded methodology. Each rate uses
    # its own denominator — see RATE_OPTIONS.
    spring_denom = out["curr_fall_p_count"].where(out["curr_fall_p_count"] > 0)
    next_fall_denom = out["next_fall_p_denominator"].where(
        out["next_fall_p_denominator"] > 0
    )
    out["spring_persistence_rate"] = (
        out["spring_total_headcount"] / spring_denom
    )
    out["next_fall_persistence_rate"] = (
        out["next_fall_total_headcount"] / next_fall_denom
    )
    return out.sort_values(["term_sort", "campus", "styp_label"])


def _build_overall(df: pd.DataFrame) -> pd.DataFrame:
    """Compute overall persistence per campus/term (weighted average)."""
    agg = (
        df.groupby(["campus", "term_short", "term_sort"], as_index=False)
        .agg(
            curr_fall_p_count=("curr_fall_p_count", "sum"),
            next_fall_p_denominator=("next_fall_p_denominator", "sum"),
            spring_total_headcount=("spring_total_headcount", "sum"),
            next_fall_total_headcount=("next_fall_total_headcount", "sum"),
        )
    )
    spring_denom = agg["curr_fall_p_count"].where(agg["curr_fall_p_count"] > 0)
    next_fall_denom = agg["next_fall_p_denominator"].where(
        agg["next_fall_p_denominator"] > 0
    )
    agg["spring_persistence_rate"] = (
        agg["spring_total_headcount"] / spring_denom
    )
    agg["next_fall_persistence_rate"] = (
        agg["next_fall_total_headcount"] / next_fall_denom
    )
    agg["styp_label"] = OVERALL_LABEL
    return agg.sort_values("term_sort")


def _styp_order(df: pd.DataFrame) -> list[str]:
    present = set(df["styp_label"].unique())
    return [label for label in STYP_MAP.values() if label in present]


def _drop_incomplete(
    df_types: pd.DataFrame, df_overall: pd.DataFrame, headcount_col: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Drop campus/term points whose follow-up term has not happened yet.

    The newest fall cohort has no spring (or next-fall) registrations yet, so
    its rate computes to a flat 0% and plots as a cliff. Completeness is
    decided per campus/term from the *summed* follow-up headcount, so a single
    student type that genuinely fell to zero still shows as 0%.
    """
    keep = df_overall.loc[df_overall[headcount_col] > 0, ["campus", "term_sort"]]
    return (
        df_types.merge(keep, on=["campus", "term_sort"], how="inner"),
        df_overall.merge(keep, on=["campus", "term_sort"], how="inner"),
    )


# ---------------------------------------------------------------------------
# Projection helpers
# ---------------------------------------------------------------------------

def _compute_next_term(df: pd.DataFrame) -> tuple[str, int]:
    """Return (term_short, term_sort) for the next projected fall term."""
    next_sort = int(df["term_sort"].max()) + 10
    return _term_label(next_sort), next_sort


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

def _hover_template(persistence_type: str) -> str:
    """Hover text for one persistence mode.

    The denominator label is per-mode: the two rates divide by different
    counts, so a single hard-coded "Fall P-Count" would print a number that
    does not reproduce the rate shown above it.
    """
    return (
        "<b>%{x}</b><br>"
        "Rate: %{y:.1%}<br>"
        "Persisted: %{customdata[0]:,}<br>"
        f"{RATE_OPTIONS[persistence_type]['p_count_label']}: "
        "%{customdata[1]:,}"
        "<extra>%{fullData.name}</extra>"
    )


def _is_dark_theme() -> bool:
    """True when Streamlit reports a dark theme.

    Plotly traces don't honor the app's CSS ``light-dark()``, so the Overall
    line's color is chosen at render time. ``type`` is None until the frontend
    reports it; treat that as light — it corrects on the next rerun.
    """
    try:
        return st.context.theme.type == "dark"
    except Exception:
        return False


def _overall_line_color(dark: bool) -> str:
    return "white" if dark else "black"


def _term_order(df: pd.DataFrame) -> list[str]:
    return (
        df[["term_short", "term_sort"]]
        .drop_duplicates()
        .sort_values("term_sort")["term_short"]
        .tolist()
    )


def _axis_tick(term_id: int, persistence_type: str, sep: str) -> str:
    """Two-line tick: the fall cohort, then the term it persists into.

    ``247`` + ``Fall → Spring`` -> ``Fall 2024`` / ``→Spr 2025``. Both
    follow-ups land in the next calendar year (Fall 2024 → Spring 2025, and
    Fall 2024 → Fall 2025), so only the season differs. The cohort stays on
    the first line and drives the data identity; the second line exists purely
    so a chart pasted into a deck still says which term the rate measures.
    """
    year = 2000 + int(term_id) // 10
    dest = "Spr" if persistence_type == "Fall → Spring" else "Fall"
    return f"Fall {year}{sep}→{dest} {year + 1}"


def _axis_ticks(
    df: pd.DataFrame, persistence_type: str, sep: str,
    extra: tuple[str, int] | None = None,
) -> tuple[list[str], list[str]]:
    """``(tickvals, ticktext)`` for the cohort axis, ``extra`` = projected term."""
    pairs = (
        df[["term_short", "term_sort"]]
        .drop_duplicates()
        .sort_values("term_sort")
    )
    vals = pairs["term_short"].tolist()
    sorts = pairs["term_sort"].tolist()
    if extra is not None and extra[0] not in vals:
        vals.append(extra[0])
        sorts.append(extra[1])
    return vals, [_axis_tick(s, persistence_type, sep) for s in sorts]


def _build_campus_fig(
    df_types: pd.DataFrame, df_overall: pd.DataFrame, campus: str,
    persistence_type: str, projection: pd.DataFrame | None = None,
    overall_color: str = "black",
):
    """One campus chart: a line per student type plus a bold Overall line."""
    opts = RATE_OPTIONS[persistence_type]
    rate_col = opts["rate_col"]
    hover = _hover_template(persistence_type)
    dfc = df_types[df_types["campus"] == campus].copy()
    dfo = df_overall[df_overall["campus"] == campus].sort_values("term_sort")

    fig = px.line(
        dfc,
        x="term_short",
        y=rate_col,
        color="styp_label",
        markers=True,
        title=f"{campus} — {persistence_type}",
        custom_data=[opts["headcount_col"], opts["p_count_col"]],
        category_orders={
            "term_short": _term_order(df_types),
            "styp_label": _styp_order(df_types),
        },
    )
    fig.update_traces(hovertemplate=hover, mode="lines+markers")

    if not dfo.empty:
        # Only the Overall line prints its values — with eight series on one
        # chart, per-point labels on every line collide into noise.
        fig.add_trace(go.Scatter(
            x=dfo["term_short"],
            y=dfo[rate_col],
            mode="lines+markers+text",
            name=OVERALL_LABEL,
            line={"color": overall_color, "width": 3, "dash": "dash"},
            marker={"symbol": "diamond", "size": 9, "color": overall_color},
            text=[f"{v:.0%}" if pd.notna(v) else "" for v in dfo[rate_col]],
            textposition="top center",
            customdata=dfo[[opts["headcount_col"], opts["p_count_col"]]].to_numpy(),
            hovertemplate=hover,
        ))

    fig.update_yaxes(range=[0, 1], tickformat=".0%")
    fig.update_layout(
        height=450,
        xaxis_title=None,
        yaxis_title="Persistence Rate",
        legend_title_text="Student Type",
    )

    proj_term: tuple[str, int] | None = None
    if projection is not None and not projection.empty and not dfo.empty:
        proj_row = projection[projection["campus"] == campus]
        if not proj_row.empty:
            last = dfo.iloc[-1]
            proj_term = (
                proj_row.iloc[0]["term_short"], int(proj_row.iloc[0]["term_sort"])
            )
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

    # Set ticks last so the projected term gets a label too.
    tickvals, ticktext = _axis_ticks(
        df_overall, persistence_type, "<br>", extra=proj_term,
    )
    fig.update_xaxes(
        tickangle=-45, tickmode="array", tickvals=tickvals, ticktext=ticktext,
    )
    return fig


# ---------------------------------------------------------------------------
# Excel export (underlying chart data)
# ---------------------------------------------------------------------------

# Each rate sits next to the P-Count it actually divides by. The two counts are
# both fall-cohort counts but are not interchangeable — the next-fall one also
# removes the following spring's completers — so neither is labelled with a bare
# "Fall P-Count" that would invite reconciling a rate against the wrong column.
_EXCEL_COLS = {
    "campus": "Campus",
    "term_short": "Term",
    "styp_label": "Student Type",
    "curr_fall_p_count": "Fall P-Count (→Spring)",
    "next_fall_p_denominator": "Fall P-Count (→Next Fall)",
    "spring_total_headcount": "Spring Headcount",
    "next_fall_total_headcount": "Next Fall Headcount",
    "spring_persistence_rate": "Fall → Spring Rate",
    "next_fall_persistence_rate": "Fall → Next Fall Rate",
}
_EXCEL_ORDER = [
    "Campus", "Term", "Student Type",
    "Fall P-Count (→Spring)", "Spring Headcount", "Fall → Spring Rate",
    "Fall P-Count (→Next Fall)", "Next Fall Headcount", "Fall → Next Fall Rate",
]
_EXCEL_PERCENTS = ("Fall → Spring Rate", "Fall → Next Fall Rate")
_EXCEL_INTEGERS = (
    "Fall P-Count (→Spring)", "Fall P-Count (→Next Fall)",
    "Spring Headcount", "Next Fall Headcount",
)


def _blank_incomplete_rates(
    df: pd.DataFrame, df_overall: pd.DataFrame,
) -> pd.DataFrame:
    """Blank rates whose follow-up term hasn't happened yet.

    The charts drop those cohorts outright, but the workbook holds both rate
    columns side by side and its fall counts are real, so the row stays and
    only the meaningless rate is emptied — a blank cell rather than a 0% that
    reads as "nobody persisted". Emptiness is judged per campus/term from the
    summed headcount, so a student type that genuinely hit zero keeps its 0%.
    """
    out = df.copy()
    for rate_col, hc_col in (
        ("spring_persistence_rate", "spring_total_headcount"),
        ("next_fall_persistence_rate", "next_fall_total_headcount"),
    ):
        empty = df_overall.loc[df_overall[hc_col] == 0, ["campus", "term_sort"]]
        if empty.empty:
            continue
        keys = set(zip(empty["campus"], empty["term_sort"]))
        mask = [
            (campus, term) in keys
            for campus, term in zip(out["campus"], out["term_sort"])
        ]
        out.loc[mask, rate_col] = float("nan")
    return out


def _build_excel_sections(
    df_types: pd.DataFrame, df_overall: pd.DataFrame,
) -> list[ExcelSection]:
    """Overall rates, then the same rates broken out by student type."""
    overall = _blank_incomplete_rates(df_overall, df_overall).sort_values(
        ["campus", "term_sort"]
    ).rename(columns=_EXCEL_COLS)[
        [col for col in _EXCEL_ORDER if col != "Student Type"]
    ]

    by_type = _blank_incomplete_rates(df_types, df_overall).sort_values(
        ["campus", "term_sort", "styp_label"]
    ).rename(columns=_EXCEL_COLS)[_EXCEL_ORDER]

    return [
        ExcelSection(
            "Persistence Rates (All Students)",
            overall,
            percent_cols=_EXCEL_PERCENTS,
            integer_cols=_EXCEL_INTEGERS,
        ),
        ExcelSection(
            "Persistence Rates by Student Type",
            by_type,
            percent_cols=_EXCEL_PERCENTS,
            integer_cols=_EXCEL_INTEGERS,
        ),
    ]


def _generate_excel(
    df_types: pd.DataFrame, df_overall: pd.DataFrame,
) -> bytes:
    return sections_to_excel_bytes(
        _build_excel_sections(df_types, df_overall),
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
    ax, df_types: pd.DataFrame, df_overall: pd.DataFrame, rate_col: str,
    campus: str, title: str, persistence_type: str,
    proj_rate: float | None = None, proj_label: str | None = None,
    proj_sort: int | None = None,
):
    """Draw the multi-line persistence chart for one campus on an Axes."""
    terms = _term_order(df_overall)
    dfc = df_types[df_types["campus"] == campus]

    for styp in _styp_order(df_types):
        sub = (
            dfc[dfc["styp_label"] == styp]
            .set_index("term_short")
            .reindex(terms)
        )
        ax.plot(terms, sub[rate_col], marker="o", linewidth=1.5, label=styp)

    dfo = (
        df_overall[df_overall["campus"] == campus]
        .set_index("term_short")
        .reindex(terms)
    )
    rates = dfo[rate_col].tolist()
    ax.plot(terms, rates, marker="D", markersize=7, linewidth=2.5,
            linestyle="--", color="black", label=OVERALL_LABEL)
    # Values are printed for the Overall line only — eight sets of point
    # labels would overlap into noise.
    for i, r in enumerate(rates):
        if pd.notna(r):
            ax.annotate(f"{r:.0%}", (i, r), textcoords="offset points",
                        xytext=(0, 10), ha="center", fontsize=8,
                        fontweight="bold")

    proj_term: tuple[str, int] | None = None
    if proj_rate is not None and proj_label is not None and terms:
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
        if proj_sort is not None:
            proj_term = (proj_label, proj_sort)

    tickvals, ticktext = _axis_ticks(
        df_overall, persistence_type, "\n", extra=proj_term,
    )
    ax.set_xticks(range(len(tickvals)))
    ax.set_xticklabels(ticktext)

    ax.set_ylim(0, 1)
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:.0%}"))
    ax.set_ylabel("Persistence Rate")
    ax.set_title(title, fontsize=10, fontweight="bold")
    ax.legend(fontsize=8, loc="best", title="Student Type", ncol=2)
    ax.tick_params(axis="x", rotation=45)
    ax.grid(axis="y", alpha=0.3)


def _generate_pdf(
    df_types: pd.DataFrame,
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
            return None, None, None
        row = proj_df[proj_df["campus"] == campus_val]
        if row.empty:
            return None, None, None
        return (
            row.iloc[0][rate_col],
            row.iloc[0]["term_short"],
            int(row.iloc[0]["term_sort"]),
        )

    buf = io.BytesIO()
    with PdfPages(buf) as pdf:
        # One page per campus: a line per student type plus Overall
        for campus in CAMP_MAP.values():
            dfc_overall = df_overall[df_overall["campus"] == campus]
            if dfc_overall.empty:
                continue

            p_rate, p_label, p_sort = _get_proj(proj_overall, campus)

            fig, ax = plt.subplots(figsize=(PAGE_W, PAGE_H))
            fig.text(0.50, 0.97, "KPI - Persistence",
                     fontsize=16, fontweight="bold", ha="center")
            fig.suptitle(f"{campus} — {persistence_type}",
                         fontsize=14, fontweight="bold", y=0.93)
            fig.subplots_adjust(left=0.10, right=0.92, top=0.88, bottom=0.22)
            _mpl_line_chart(ax, df_types, dfc_overall, rate_col, campus, "",
                            persistence_type,
                            proj_rate=p_rate, proj_label=p_label,
                            proj_sort=p_sort)
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
        missing = _REQUIRED_COLS.difference(df.columns)
        if missing:
            st.error(
                "The persistence extract is missing "
                f"`{'`, `'.join(sorted(missing))}` — it predates the "
                "`dwh.mv_persistence_by_styp` rebuild. Refresh the MV, then "
                "run `python -m src.pipeline.run kpi_persistence`."
            )
            return
        df_prepared = _prepare_data(df)
        st.session_state["pbs_df_types"] = df_prepared
        st.session_state["pbs_df_overall"] = _build_overall(df_prepared)
        clear_pdf_cache("pbs")
        clear_excel_cache("pbs")

    # --- PDF download in sidebar (after query block) ---
    if "pbs_df_overall" in st.session_state:
        ptype_val = st.session_state.get("pbs_ptype", "Fall → Spring")

        pdf_types, pdf_overall = _drop_incomplete(
            st.session_state["pbs_df_types"],
            st.session_state["pbs_df_overall"],
            RATE_OPTIONS[ptype_val]["headcount_col"],
        )

        # Compute projections for PDF (uses current sidebar selections)
        pdf_proj_overall = None
        if show_projection and proj_method and not pdf_overall.empty:
            pdf_proj_overall = _compute_projections(
                pdf_overall, RATE_OPTIONS[ptype_val]["rate_col"],
                ["campus"], proj_method,
            )

        pdf_bytes = cached_pdf_bytes(
            "pbs",
            (
                id(st.session_state["pbs_df_overall"]),
                ptype_val,
                show_projection,
                proj_method,
            ),
            lambda: _generate_pdf(
                pdf_types,
                pdf_overall,
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
            lambda: _generate_excel(
                st.session_state["pbs_df_types"],
                st.session_state["pbs_df_overall"],
            ),
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

    # --- Filter: persistence type ---
    persistence_type = st.radio(
        "Persistence Type",
        list(RATE_OPTIONS.keys()),
        key="pbs_ptype",
        horizontal=True,
    )
    opts = RATE_OPTIONS[persistence_type]

    # Cohorts whose follow-up term hasn't happened yet would plot as 0%.
    df_types, df_overall = _drop_incomplete(
        st.session_state["pbs_df_types"],
        st.session_state["pbs_df_overall"],
        opts["headcount_col"],
    )
    if df_overall.empty:
        st.warning(
            f"No cohort in the selected terms has reached "
            f"{opts['follow_up']} yet."
        )
        return

    denominator_note = (
        "that fall's headcount **minus students who completed a degree that "
        "fall**"
        if persistence_type == "Fall → Spring" else
        "that fall's headcount **minus students who completed a degree that "
        "fall or the following spring** (a completer would not be expected to "
        "re-enroll)"
    )
    st.caption(
        "Each point is a **fall cohort**: *Fall 2024* means students enrolled "
        "in Fall 2024, persisting into Spring 2025 (Fall → Spring) or Fall "
        f"2025 (Fall → Next Fall). The denominator is {denominator_note}; the "
        "numerator is the follow-up term's headcount. Lines show each student "
        "type, with a count-weighted **Overall** line across all types. "
        "Special admits who are neither CCAP nor early-college — concurrent "
        "enrollment — are excluded, since they are not expected to persist "
        "past one term."
    )

    # --- Compute projections for charts ---
    proj_overall = None
    if show_projection and proj_method:
        proj_overall = _compute_projections(
            df_overall, opts["rate_col"], ["campus"], proj_method)

    # --- Persistence by campus (all three) ---
    dark = _is_dark_theme()
    overall_color = _overall_line_color(dark)
    for campus in CAMP_MAP.values():
        if campus not in set(df_overall["campus"].unique()):
            continue
        st.plotly_chart(
            _build_campus_fig(
                df_types, df_overall, campus, persistence_type,
                projection=proj_overall, overall_color=overall_color,
            ),
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
