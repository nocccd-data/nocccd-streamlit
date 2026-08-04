import io
from dataclasses import dataclass
from typing import Any

import matplotlib
import matplotlib.pyplot as plt
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.ticker import FuncFormatter

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

# Fixed KPI baseline. The change column always compares back to Fall 2024 —
# not to the earliest selected term — so the comparison keeps its meaning as
# new terms are added (Fall 2027 will still be measured against Fall 2024).
BASELINE_TERM_ID = 247


# ---------------------------------------------------------------------------
# Data preparation
# ---------------------------------------------------------------------------

def _term_label(term_id: int) -> str:
    """``247`` -> ``Fall 2024`` (MIS term IDs increment by 10 per year)."""
    return f"Fall {2000 + int(term_id) // 10}"


def _prepare_data(df: pd.DataFrame) -> pd.DataFrame:
    """Add display columns and a recomputed enrollment rate per student type."""
    out = df.copy()
    out["campus"] = out["camp_code"].astype(str).map(CAMP_MAP)
    out["styp_label"] = out["styp_code"].astype(str).map(STYP_MAP).fillna(
        out["styp_code"].astype(str)
    )
    out["term_sort"] = out["mis_term_id"].astype(int)
    out["term_short"] = out["term_sort"].map(_term_label)
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
# Change-vs-baseline tables
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class _TableSpec:
    """One change-vs-baseline table: which metric, and how its change reads.

    ``relative`` is the important distinction between the two tables. The yield
    table subtracts two *rates*, so its change is in **percentage points**
    (37.5% → 30.0% is "-7.5 pts"). The applied table divides two *headcounts*,
    so its change is a **relative percent** (15,252 → 12,400 is "-18.7%").
    Mixing the two up understates or overstates the movement badly, so they are
    labelled and formatted differently on every surface.
    """

    key: str            # cache/session prefix, e.g. "yield"
    label: str          # heading shown above the table
    value_col: str      # column in the prepared frame
    value_fmt: str      # on-screen format for the per-term columns
    value_excel: str    # "percent" | "integer" — Excel number format
    relative: bool      # True = % change, False = percentage-point change


# Order matters: this is the render order on screen, in the PDF, and in the
# Excel sections. Applied (the top of the funnel) comes before the yield it
# feeds.
TABLE_SPECS = (
    _TableSpec(
        key="applied",
        label="Applied (Headcount)",
        value_col="app_pidm_count",
        value_fmt="{:,.0f}",
        value_excel="integer",
        relative=True,
    ),
    _TableSpec(
        key="yield",
        label="% Enrolled (Yield)",
        value_col="rate",
        value_fmt="{:.1%}",
        value_excel="percent",
        relative=False,
    ),
)


def _change_col_label(latest_term_id: int, spec: _TableSpec) -> str:
    """``3-Yr Change vs Fall 2024 (pts)`` / ``3-Yr % Change vs Fall 2024``.

    The span grows as terms are added and is counted inclusively (Fall 2024
    through Fall 2026 = 3 years), matching how the change is described in the
    KPI reporting.
    """
    span = (int(latest_term_id) - BASELINE_TERM_ID) // 10 + 1
    baseline = _term_label(BASELINE_TERM_ID)
    if spec.relative:
        return f"{span}-Yr % Change vs {baseline}"
    return f"{span}-Yr Change vs {baseline} (pts)"


def _build_change_table(
    df_types: pd.DataFrame, df_overall: pd.DataFrame, campus: str,
    spec: _TableSpec,
) -> tuple[pd.DataFrame, str | None, list[str]]:
    """One campus's table for ``spec``: baseline, latest, and their change.

    Returns ``(table, change_col, term_cols)``. Rows are the campus's student
    types in legend order with **Overall** last; values are the same numbers the
    chart is built from. Only the fixed Fall 2024 baseline and the latest term
    get columns — the intermediate years stay on the chart, which keeps the
    table three columns wide however many terms accumulate. ``change_col`` is
    ``None`` when the baseline is not among the selected terms, or when it is
    itself the latest term — there is nothing to compare against either way.
    """
    cols = ["campus", "term_short", "term_sort", "styp_label", spec.value_col]
    combined = pd.concat([df_types[cols], df_overall[cols]], ignore_index=True)
    dfc = combined[combined["campus"] == campus]

    baseline_label = _term_label(BASELINE_TERM_ID)
    latest_id = int(max(df_types["term_sort"]))
    latest_label = _term_label(latest_id)
    # Term columns come from the full dataset so every campus table lines up.
    # dict.fromkeys dedupes the case where the baseline *is* the latest term.
    selected = _term_order(df_types)
    term_cols = list(dict.fromkeys(
        term for term in (baseline_label, latest_label) if term in selected
    ))

    piv = dfc.pivot_table(
        index="styp_label", columns="term_short", values=spec.value_col,
        aggfunc="first",
    ).reindex(
        # Only the student types this campus actually reports (NOCE has one).
        index=[*_styp_order(dfc), OVERALL_LABEL],
        columns=term_cols,
    )

    change_col = None
    if baseline_label in term_cols and latest_id > BASELINE_TERM_ID:
        change_col = _change_col_label(latest_id, spec)
        baseline = piv[baseline_label]
        latest = piv[latest_label]
        if spec.relative:
            # Stored as a fraction (-0.226) so Excel can carry a real percent
            # format; a zero baseline yields NaN rather than inf.
            piv[change_col] = latest / baseline.where(baseline != 0) - 1
        else:
            piv[change_col] = (latest - baseline) * 100

    table = piv.reset_index().rename(columns={"styp_label": "Student Type"})
    return table, change_col, term_cols


def _delta_colors(dark: bool) -> tuple[str, str]:
    """``(positive, negative)`` change-column text colors for the active theme."""
    return ("#66BB6A", "#EF5350") if dark else ("#1B7F30", "#C62828")


def _style_change_table(
    table: pd.DataFrame, change_col: str | None, term_cols: list[str],
    spec: _TableSpec, dark: bool = False,
):
    """Format the per-term columns, bold Overall, color the change column."""
    fmt: dict[Any, Any] = {col: spec.value_fmt for col in term_cols}
    if change_col:
        fmt[change_col] = "{:+.1%}" if spec.relative else "{:+.1f}"
    styler = table.style.format(fmt, na_rep="—").apply(
        lambda row: [
            "font-weight: bold" if row["Student Type"] == OVERALL_LABEL else ""
        ] * len(row),
        axis=1,
    )
    if change_col:
        positive, negative = _delta_colors(dark)

        def _change_color(value: Any) -> str:
            if pd.isna(value):
                return ""
            return f"color: {positive if value >= 0 else negative}"

        styler = styler.map(_change_color, subset=[change_col])
    return styler


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


def _is_dark_theme() -> bool:
    """True when Streamlit reports a dark theme.

    Plotly traces and Styler colors don't honor the app's CSS ``light-dark()``,
    so they have to be chosen at render time from the active theme. ``type`` is
    None until the frontend reports it (first load / mid theme-switch); treat
    that as light — it corrects on the next rerun.
    """
    try:
        return st.context.theme.type == "dark"
    except Exception:
        return False


def _overall_line_color(dark: bool) -> str:
    """Overall line color: black on light themes, white on dark themes."""
    return "white" if dark else "black"


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
        title=f"{campus} — 1st Time Applied to Enrolled",
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
    sections = [ExcelSection(
        "1st Time Applied to Enrolled by Student Type",
        out,
        percent_cols=("% Enrolled",),
        integer_cols=("Applied", "Enrolled"),
    )]

    # The change-vs-baseline tables per campus, matching the on-screen ones.
    for campus in CAMP_MAP.values():
        if campus not in set(df_types["campus"].unique()):
            continue
        for spec in TABLE_SPECS:
            table, change_col, term_cols = _build_change_table(
                df_types, df_overall, campus, spec
            )
            percent_cols = list(term_cols) if spec.value_excel == "percent" else []
            integer_cols = list(term_cols) if spec.value_excel == "integer" else []
            decimal_cols = []
            if change_col:
                # A relative change is a true percentage in Excel; a
                # percentage-point change is a plain number.
                (percent_cols if spec.relative else decimal_cols).append(change_col)
            sections.append(ExcelSection(
                f"{campus} — {spec.label} by Term",
                table,
                percent_cols=tuple(percent_cols),
                integer_cols=tuple(integer_cols),
                decimal_cols=tuple(decimal_cols),
            ))
    return sections


def _generate_excel(df_types: pd.DataFrame, df_overall: pd.DataFrame) -> bytes:
    return sections_to_excel_bytes(
        _build_excel_sections(df_types, df_overall),
        title="KPI - 1st Time Applied to Enrolled - Chart Table Data",
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
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:.0%}"))
    ax.set_ylabel("% Enrolled")
    ax.set_title(title, fontsize=10, fontweight="bold")
    ax.tick_params(axis="x", rotation=45)
    ax.grid(axis="y", alpha=0.3)
    ax.legend(fontsize=8, loc="best", title="Student Type")


_PDF_POS_COLOR = "#1B7F30"
_PDF_NEG_COLOR = "#C62828"


def _fmt_cell(value, fmt: str) -> str:
    return "—" if pd.isna(value) else fmt.format(value)


def _mpl_change_table(fig, bbox, table, change_col, term_cols, spec):
    """Draw one change-vs-baseline table below a campus chart."""
    ax = fig.add_axes(bbox)
    ax.axis("off")
    ax.set_title(spec.label, fontsize=10, fontweight="bold", pad=6)

    headers = ["Student Type", *term_cols]
    widths = [0.26] + [(0.74 - 0.22) / len(term_cols)] * len(term_cols)
    if change_col:
        # Two lines so the long header fits its column.
        headers.append(change_col.replace(" vs ", "\nvs "))
        widths.append(0.22)
    else:
        widths = [0.26] + [0.74 / len(term_cols)] * len(term_cols)

    change_fmt = "{:+.1%}" if spec.relative else "{:+.1f}"
    rows = []
    for _, row in table.iterrows():
        cells = [
            row["Student Type"],
            *(_fmt_cell(row[col], spec.value_fmt) for col in term_cols),
        ]
        if change_col:
            cells.append(_fmt_cell(row[change_col], change_fmt))
        rows.append(cells)

    tbl = ax.table(
        cellText=rows, colLabels=headers, cellLoc="center", loc="center",
        colWidths=widths,
    )
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(8)
    tbl.scale(1, 1.35)

    for col_idx in range(len(headers)):
        cell = tbl[(0, col_idx)]
        cell.set_text_props(fontweight="bold")
        cell.set_facecolor("#D9EAF7")

    last_col = len(headers) - 1
    for row_idx in range(1, len(rows) + 1):
        is_overall = rows[row_idx - 1][0] == OVERALL_LABEL
        for col_idx in range(len(headers)):
            cell = tbl[(row_idx, col_idx)]
            props = {}
            if is_overall:
                props["fontweight"] = "bold"
                cell.set_facecolor("#F0F0F0")
            if change_col and col_idx == last_col:
                value = table.iloc[row_idx - 1][change_col]
                if pd.notna(value):
                    props["color"] = (
                        _PDF_POS_COLOR if value >= 0 else _PDF_NEG_COLOR
                    )
            if props:
                cell.set_text_props(**props)


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
            fig = plt.figure(figsize=(PAGE_W, PAGE_H))
            fig.text(0.50, 0.97, "KPI - 1st Time Applied to Enrolled",
                     fontsize=16, fontweight="bold", ha="center")
            fig.suptitle(f"{campus} — 1st Time Applied to Enrolled",
                         fontsize=14, fontweight="bold", y=0.93)
            # Chart on top, then the change-vs-baseline tables stacked below.
            # The gap under the chart leaves room for the rotated term labels.
            ax = fig.add_axes((0.10, 0.60, 0.82, 0.28))
            _mpl_campus_chart(ax, df_types, df_overall, campus, "")
            table_bboxes = ((0.08, 0.30, 0.86, 0.16), (0.08, 0.07, 0.86, 0.16))
            for spec, bbox in zip(TABLE_SPECS, table_bboxes):
                table, change_col, term_cols = _build_change_table(
                    df_types, df_overall, campus, spec
                )
                _mpl_change_table(fig, bbox, table, change_col, term_cols, spec)
            _add_pdf_footer(fig)
            pdf.savefig(fig)
            plt.close(fig)

    return buf.getvalue()


# ---------------------------------------------------------------------------
# Streamlit render
# ---------------------------------------------------------------------------

def render():
    st.header("KPI - 1st Time Applied to Enrolled")

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

    baseline_label = _term_label(BASELINE_TERM_ID)
    st.caption(
        "Enrollment yield (% of applicants who enrolled) by student type, with a "
        "count-weighted **Overall** line summing all student types. Each chart is "
        f"followed by two tables measured against the {baseline_label} baseline: "
        "**Applied**, whose change is a *relative percent* of the baseline "
        "headcount, and **% Enrolled**, whose change is in *percentage points*."
    )
    if baseline_label not in set(df_types["term_short"].unique()):
        st.info(
            f"{baseline_label} is not in the selected terms, so the change "
            "column is hidden. Re-select it in the sidebar to compare against "
            "the baseline."
        )

    # --- One chart + the change tables per campus ---
    dark = _is_dark_theme()
    overall_color = _overall_line_color(dark)
    for campus in CAMP_MAP.values():
        if campus not in set(df_types["campus"].unique()):
            continue
        st.plotly_chart(
            _build_campus_fig(df_types, df_overall, campus, overall_color),
            width="stretch",
        )
        for spec in TABLE_SPECS:
            table, change_col, term_cols = _build_change_table(
                df_types, df_overall, campus, spec
            )
            st.markdown(f"**{campus} — {spec.label}**")
            st.dataframe(
                _style_change_table(table, change_col, term_cols, spec, dark),
                width="stretch",
                hide_index=True,
            )
