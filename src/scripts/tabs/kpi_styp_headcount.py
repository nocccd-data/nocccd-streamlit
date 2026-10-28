"""KPI - Student Headcount by Type: Fall headcount, one small chart per type.

Credit (Cypress + Fullerton combined) gets one card per student type; NOCE
gets a single card. The extract arrives final -- one distinct headcount per
Fall x college group x type (see kpi_styp_headcount.sql) -- so the cards plot
its rows as-is. Never rebuild the credit numbers from per-college counts: a
student registered at both colleges would be counted twice.
"""

import io
import textwrap
from dataclasses import dataclass
from typing import Any

import matplotlib
import matplotlib.pyplot as plt
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.patches import FancyBboxPatch, Rectangle

from src.pipeline.config import DATASETS
from src.scripts.data_provider import fetch_kpi_styp_headcount
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

_CFG = DATASETS["kpi_styp_headcount"]
_DEFAULT_TERMS = _CFG[_CFG["param_name"]]

TAB_TITLE = "KPI - Student Headcount by Type"


@dataclass(frozen=True)
class _CardSpec:
    group: str        # college_group in the extract
    styp: str         # styp_code in the extract
    title: str
    description: str


# Card order and wording follow the district's "Who Is Driving Enrollment?" slide.
CREDIT_CARDS = (
    _CardSpec("credit", "adult", "Adult",
              "New students age 25 and older"),
    _CardSpec("credit", "continuing", "Continuing",
              "Students who remain enrolled from one term to the next"),
    _CardSpec("credit", "first_time", "First-Time",
              "New students under 25, typically coming directly from high school"),
    _CardSpec("credit", "first_time_trans", "First-Time Transfer",
              "New students under 25 who have completed some college elsewhere"),
    _CardSpec("credit", "returning", "Returning",
              "Students re-enrolling after two or more semesters away"),
    _CardSpec("credit", "special_admit_dual", "Special Admit / Dual Enrollment",
              "High school students taking college courses"),
)
NOCE_CARD = _CardSpec("noce", "adult", "NOCE (Noncredit)",
                      "All noncredit students at North Orange Continuing Education")
ALL_CARDS = (*CREDIT_CARDS, NOCE_CARD)

# The credit cards with the largest gains get the highlighted (orange) style.
HIGHLIGHT_COUNT = 2

# Sum of the six credit cards. Not "credit headcount": the few credit students
# with no usable type are in no card (1 each in Fall 2025 and 2026, as of 2026-10-28).
CREDIT_TOTAL_LABEL = "Total (six types)"

CREDIT_SECTION = "Credit colleges: Cypress and Fullerton combined"
NOCE_SECTION = "NOCE: noncredit"

# Line colors from the slide: orange for highlighted cards, steel blue otherwise.
_HL_COLOR = "#E0892B"
_BASE_COLOR = "#9DB2CE"


# ---------------------------------------------------------------------------
# Data preparation
# ---------------------------------------------------------------------------

def _fall_year(mis_term_id: object) -> int:
    """MIS Fall term id -> calendar year (``257`` -> ``2025``)."""
    return 2000 + int(str(mis_term_id)) // 10


def _prepare_data(df: pd.DataFrame) -> pd.DataFrame:
    """Add the Fall year and fail on any group/type the cards don't know.

    A type the SQL emits but no card shows would vanish from the tab with no
    sign anything was missing, so it raises instead.
    """
    required = {"mis_term_id", "college_group", "styp_code", "pidm_count"}
    missing = required - set(df.columns)
    if missing:
        raise KeyError(f"kpi_styp_headcount extract is missing columns: {sorted(missing)}")

    out = df.copy()
    out["mis_term_id"] = out["mis_term_id"].astype(str)
    out["college_group"] = out["college_group"].astype(str)
    out["styp_code"] = out["styp_code"].astype(str)
    out["year"] = out["mis_term_id"].map(_fall_year)
    out["pidm_count"] = pd.to_numeric(out["pidm_count"], errors="coerce")

    known = {(c.group, c.styp) for c in ALL_CARDS}
    seen = set(zip(out["college_group"], out["styp_code"]))
    unknown = sorted(seen - known)
    if unknown:
        raise ValueError(f"kpi_styp_headcount has student types no card shows: {unknown}")
    return out.sort_values(["year", "college_group", "styp_code"])


def _years(df: pd.DataFrame) -> list[int]:
    return sorted(df["year"].unique().tolist())


def _card_series(df: pd.DataFrame, spec: _CardSpec) -> pd.Series:
    """Headcount by Fall year for one card.

    A Fall in the extract with no row for this type had no such students:
    the SQL's GROUP BY never emits a zero count. So the gap is 0, which also
    keeps the credit total equal to the sum of the cards.
    """
    rows = df[(df["college_group"] == spec.group) & (df["styp_code"] == spec.styp)]
    return rows.set_index("year")["pidm_count"].reindex(_years(df), fill_value=0).astype(float)


def _pct_change(series: pd.Series) -> float:
    """Earliest selected Fall -> latest, as a fraction; NaN when undefined."""
    if len(series) < 2:
        return float("nan")
    first, last = series.iloc[0], series.iloc[-1]
    if pd.isna(first) or pd.isna(last) or first == 0:
        return float("nan")
    return float((last - first) / first)


def _highlighted(changes: dict[_CardSpec, float]) -> set[_CardSpec]:
    """The HIGHLIGHT_COUNT cards with the largest gains; declines never qualify,
    nor does a gain that displays as 0.0%.

    ``sorted`` is stable, so a tie goes to the card that comes first.
    """
    gains = [spec for spec, c in changes.items()
             if pd.notna(c) and c > 0 and not _is_flat(c)]
    gains = sorted(gains, key=lambda spec: -changes[spec])
    return set(gains[:HIGHLIGHT_COUNT])


@dataclass(frozen=True)
class _CardState:
    """What every card needs beyond its own series; shared by screen and PDF."""
    years: list[int]
    baseline_label: str | None
    changes: dict[_CardSpec, float]
    highlighted: set[_CardSpec]


def _card_state(df: pd.DataFrame, highlight: bool = True) -> _CardState:
    """``highlight=False`` (the sidebar toggle) leaves every card plain."""
    years = _years(df)
    changes = {spec: _pct_change(_card_series(df, spec)) for spec in ALL_CARDS}
    return _CardState(
        years=years,
        baseline_label=f"Fall {years[0]}" if len(years) >= 2 else None,
        changes=changes,
        highlighted=(_highlighted({s: changes[s] for s in CREDIT_CARDS})
                     if highlight else set()),
    )


def _is_flat(change: float) -> bool:
    """True when the change displays as 0.0%, so it gets no up/down color."""
    return round(change, 3) == 0


def _change_text(change: float) -> str:
    """``▲ 15.7%`` / ``▼ 21.2%``; an em dash when undefined."""
    if pd.isna(change):
        return "—"
    if _is_flat(change):
        return "0.0%"
    return f"{'▲' if change > 0 else '▼'} {abs(change):.1%}"


def _fall_range(years: list[int]) -> str:
    """``Fall 2022 to Fall 2026``, or just ``Fall 2026`` for one Fall."""
    if len(years) == 1:
        return f"Fall {years[0]}"
    return f"Fall {years[0]} to Fall {years[-1]}"


def _change_col(df: pd.DataFrame) -> str | None:
    years = _years(df)
    return f"% Change vs Fall {years[0]}" if len(years) >= 2 else None


def _build_table(df: pd.DataFrame, specs: tuple[_CardSpec, ...],
                 total_label: str | None = None) -> pd.DataFrame:
    """One row per card: headcount per Fall plus the change since the first Fall.

    ``total_label`` appends a total row. That is only valid for the credit
    cards: a credit student lands in at most one type, so the sum counts no
    one twice. It leaves out the few with no type (see CREDIT_TOTAL_LABEL).
    """
    years = _years(df)
    fall_cols = [f"Fall {y}" for y in years]
    change_col = _change_col(df)

    series = {spec.title: _card_series(df, spec) for spec in specs}
    if total_label:
        series[total_label] = pd.concat(series.values(), axis=1).sum(axis=1)

    rows = []
    for label, s in series.items():
        row: dict[str, object] = {"Student Type": label}
        row.update(dict(zip(fall_cols, s.tolist())))
        if change_col:
            row[change_col] = _pct_change(s)
        rows.append(row)
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Plotly figure
# ---------------------------------------------------------------------------

def _is_dark_theme() -> bool:
    """True when Streamlit reports a dark theme.

    Plotly traces don't honor the app's CSS ``light-dark()``, so their colors
    are picked at render time. ``type`` is None until the frontend reports it;
    treat that as light -- it corrects on the next rerun.
    """
    try:
        return st.context.theme.type == "dark"
    except Exception:  # noqa: BLE001 - outside a script run there is no context
        return False


def _y_range(series: pd.Series) -> list[float] | None:
    """Fit the line to the card with room above for the labels.

    Each card is scaled to its own data, as on the slide; the y-axis is hidden,
    so no card implies a scale it doesn't have.
    """
    values = series.dropna()
    if values.empty:
        return None
    lo, hi = float(values.min()), float(values.max())
    span = hi - lo or max(hi, 1.0) * 0.1
    return [lo - 0.35 * span, hi + 0.55 * span]


def _card_fig(series: pd.Series, highlighted: bool, dark: bool) -> go.Figure:
    color = _HL_COLOR if highlighted else _BASE_COLOR
    text_color = "#FFFFFF" if dark else "#1F2A44"
    axis_color = "#555555" if dark else "#CCCCCC"
    labels = [f"{v:,.0f}" if pd.notna(v) else "" for v in series]

    fig = go.Figure(go.Scatter(
        x=[str(y) for y in series.index],
        y=series.tolist(),
        mode="lines+markers+text",
        text=labels,
        textposition="top center",
        textfont={"size": 12, "color": text_color, "weight": "bold"},
        line={"color": color, "width": 3},
        marker={"size": 10, "color": color},
        hovertemplate="<b>Fall %{x}</b><br>Headcount: %{y:,}<extra></extra>",
    ))
    fig.update_yaxes(visible=False, range=_y_range(series), fixedrange=True)
    fig.update_xaxes(
        type="category", showgrid=False, showline=True, linecolor=axis_color,
        ticks="outside", tickcolor=axis_color, fixedrange=True,
    )
    fig.update_layout(
        height=200,
        margin={"l": 8, "r": 8, "t": 8, "b": 8},
        showlegend=False,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
    )
    return fig


# ---------------------------------------------------------------------------
# Excel export (underlying chart data)
# ---------------------------------------------------------------------------

def _build_excel_sections(df: pd.DataFrame) -> list[ExcelSection]:
    """Credit table (with its total) and the NOCE row, Falls as columns."""
    fall_cols = tuple(f"Fall {y}" for y in _years(df))
    change_col = _change_col(df)
    percent_cols = (change_col,) if change_col else ()
    return [
        ExcelSection(
            CREDIT_SECTION,
            _build_table(df, CREDIT_CARDS, total_label=CREDIT_TOTAL_LABEL),
            integer_cols=fall_cols,
            percent_cols=percent_cols,
        ),
        ExcelSection(
            NOCE_SECTION,
            _build_table(df, (NOCE_CARD,)),
            integer_cols=fall_cols,
            percent_cols=percent_cols,
        ),
    ]


def _generate_excel(df: pd.DataFrame) -> bytes:
    return sections_to_excel_bytes(
        _build_excel_sections(df),
        title=f"{TAB_TITLE} - Chart Table Data",
    )


# ---------------------------------------------------------------------------
# PDF export (matplotlib)
# ---------------------------------------------------------------------------

_PDF_FOOTER_LEFT = "https://nocccd.streamlit.app/"
_PDF_FOOTER_RIGHT = "Author: Jihoon Ahn  jahn@nocccd.edu"
_PDF_POS_COLOR = "#1B7F30"
_PDF_NEG_COLOR = "#C62828"
_PDF_NAVY = "#003056"
_PDF_MUTED = "#555555"

# Card grid in figure fractions of an 11x8.5 landscape page: three columns,
# two credit rows and one NOCE row, each row under its own section label.
_PDF_LEFT, _PDF_RIGHT = 0.04, 0.96
_PDF_COL_GAP = 0.02
_PDF_CARD_H = 0.245
_PDF_ROW_GAP = 0.02
_PDF_LABEL_H = 0.035


def _add_pdf_footer(fig):
    fig.text(0.06, 0.02, _PDF_FOOTER_LEFT, fontsize=7, color="grey", ha="left")
    fig.text(0.94, 0.02, _PDF_FOOTER_RIGHT, fontsize=7, color="grey", ha="right")


def _mpl_card(fig, x: float, y: float, w: float, h: float, spec: _CardSpec,
              series: pd.Series, change: float, highlighted: bool,
              baseline_label: str | None) -> None:
    """Draw one card (box, header, line chart) with its lower-left at (x, y)."""
    color = _HL_COLOR if highlighted else _BASE_COLOR
    # Below zorder 0, or the box's fill is painted over the chart axes.
    fig.patches.append(FancyBboxPatch(
        (x, y), w, h, boxstyle="round,pad=0,rounding_size=0.008",
        transform=fig.transFigure, figure=fig, zorder=-1,
        facecolor="#FFF6EA" if highlighted else "white",
        edgecolor=color if highlighted else "#C9D3E0",
        linewidth=2 if highlighted else 1,
    ))

    # Header: title and description on the left, wrapped short enough to
    # clear the change figure on the right.
    top = y + h - 0.020
    title_lines = textwrap.wrap(spec.title, 22)
    desc_lines = textwrap.wrap(spec.description, 40)
    desc_top = top - 0.024 * len(title_lines) - 0.004
    fig.text(x + 0.020, top, "\n".join(title_lines), fontsize=10.5,
             fontweight="bold", color=_PDF_NAVY, va="top", linespacing=1.15)
    fig.text(x + 0.020, desc_top, "\n".join(desc_lines), fontsize=7,
             style="italic", color=_PDF_MUTED, va="top", linespacing=1.3)
    # Accent bar beside the title block, as on the slide.
    bar_bottom = desc_top - 0.0165 * len(desc_lines)
    fig.patches.append(Rectangle(
        (x + 0.010, bar_bottom), 0.004, top + 0.002 - bar_bottom,
        transform=fig.transFigure, figure=fig, facecolor=color, edgecolor="none",
    ))
    if pd.notna(change):
        fig.text(x + w - 0.012, top, _change_text(change), fontsize=12,
                 fontweight="bold", ha="right", va="top",
                 color=_PDF_MUTED if _is_flat(change)
                 else _PDF_POS_COLOR if change > 0 else _PDF_NEG_COLOR)
        fig.text(x + w - 0.012, top - 0.030, f"vs. {baseline_label}", fontsize=7,
                 color=_PDF_MUTED, ha="right", va="top")

    ax = fig.add_axes((x + 0.022, y + 0.028, w - 0.044, h * 0.46))
    xs = list(range(len(series)))
    ax.plot(xs, series.tolist(), color=color, linewidth=2.2, marker="o", markersize=6)
    for i, v in zip(xs, series):
        if pd.notna(v):
            ax.annotate(f"{int(v):,}", (i, v), textcoords="offset points", xytext=(0, 7),
                        ha="center", fontsize=7.5, fontweight="bold", color="#1F2A44")
    y_range = _y_range(series)
    if y_range:
        ax.set_ylim(*y_range)
    ax.set_xticks(xs, [str(yr) for yr in series.index], fontsize=7.5, color=_PDF_MUTED)
    ax.set_xlim(-0.4, len(xs) - 0.6)
    ax.set_yticks([])
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color("#CCCCCC")
    ax.tick_params(axis="x", length=3, color="#CCCCCC")
    ax.set_facecolor("none")


def _generate_pdf(df: pd.DataFrame, highlight: bool = True) -> bytes:
    matplotlib.rcParams.update({
        "figure.facecolor": "white",
        "axes.facecolor": "white",
        "text.color": "black",
        "savefig.facecolor": "white",
    })

    state = _card_state(df, highlight)
    years = state.years

    PAGE_W, PAGE_H = 11.0, 8.5
    card_w = (_PDF_RIGHT - _PDF_LEFT - 2 * _PDF_COL_GAP) / 3
    buf = io.BytesIO()
    with PdfPages(buf) as pdf:
        fig = plt.figure(figsize=(PAGE_W, PAGE_H))
        fig.text(0.50, 0.965, TAB_TITLE, fontsize=16, fontweight="bold", ha="center")
        fig.text(0.50, 0.932,
                 f"Who Is Driving Enrollment?  Headcount by student type, "
                 f"{_fall_range(years)}",
                 fontsize=11, ha="center", color=_PDF_MUTED)

        top = 0.905
        rows = [
            (CREDIT_SECTION, CREDIT_CARDS[:3]),
            (None, CREDIT_CARDS[3:]),
            (NOCE_SECTION, (NOCE_CARD,)),
        ]
        for label, specs in rows:
            if label:
                fig.text(_PDF_LEFT, top - 0.012, label, fontsize=10,
                         fontweight="bold", color=_PDF_NAVY, va="center")
                top -= _PDF_LABEL_H
            card_y = top - _PDF_CARD_H
            for i, spec in enumerate(specs):
                card_x = _PDF_LEFT + i * (card_w + _PDF_COL_GAP)
                _mpl_card(fig, card_x, card_y, card_w, _PDF_CARD_H, spec,
                          _card_series(df, spec), state.changes[spec],
                          spec in state.highlighted, state.baseline_label)
            top = card_y - _PDF_ROW_GAP

        _add_pdf_footer(fig)
        pdf.savefig(fig)
        plt.close(fig)

    return buf.getvalue()


# ---------------------------------------------------------------------------
# Streamlit render
# ---------------------------------------------------------------------------

def _render_card(df: pd.DataFrame, spec: _CardSpec, change: float,
                 highlighted: bool, baseline_label: str | None, dark: bool) -> None:
    # theme.py styles these by key ("Student Headcount by Type cards" there):
    # hl/card picks the card style, up/down the change color. The app's card
    # text rule forces every span black, so markdown :green[] can't be used.
    kind = "hl" if highlighted else "card"
    slug = f"{spec.group}_{spec.styp}"
    with st.container(border=True, height="stretch", key=f"ksh_{kind}_{slug}"):
        with st.container(horizontal=True, key=f"ksh_head_{kind}_{slug}"):
            with st.container(gap=None):
                st.markdown(f"**{spec.title}**")
                st.caption(f"*{spec.description}*")
            if pd.notna(change):
                tone = "flat" if _is_flat(change) else "up" if change > 0 else "down"
                with st.container(width="content", gap=None,
                                  horizontal_alignment="right", key=f"ksh_{tone}_{slug}"):
                    st.markdown(f"**{_change_text(change)}**")
                    st.caption(f"vs. {baseline_label}")
        st.plotly_chart(
            _card_fig(_card_series(df, spec), highlighted, dark),
            config={"displayModeBar": False},
            key=f"ksh_chart_{slug}",
            alt=f"{spec.title} headcount by Fall",
        )


def _render_grid(df: pd.DataFrame, specs: tuple[_CardSpec, ...], state: _CardState,
                 dark: bool, key: str) -> None:
    # Keyed so theme.py can clear the grey Home-card fill from empty slots
    # (the NOCE row fills one of three columns).
    with st.container(key=key):
        for start in range(0, len(specs), 3):
            for col, spec in zip(st.columns(3), specs[start:start + 3]):
                with col:
                    _render_card(df, spec, state.changes[spec],
                                 spec in state.highlighted, state.baseline_label, dark)


def render():
    st.header(TAB_TITLE)

    # --- Sidebar controls ---
    selected_terms = st.sidebar.multiselect(
        "MIS Term IDs",
        options=_DEFAULT_TERMS,
        default=_DEFAULT_TERMS,
        key="ksh_term_ids",
    )
    query_btn = st.sidebar.button("Query", key="ksh_query_btn")
    # Display only, so it needs no re-query; the PDF follows it too.
    highlight = st.sidebar.toggle(
        "Highlight fastest-growing",
        value=True,
        key="ksh_highlight",
        help=f"Give the {HIGHLIGHT_COUNT} credit types with the largest gains "
             "the orange card style.",
    )

    if query_btn:
        if not selected_terms:
            st.warning("Select at least one term.")
            return
        fetch_kpi_styp_headcount.clear()
        df = fetch_kpi_styp_headcount(tuple(sorted(selected_terms)))
        if df.empty:
            # Drop the previous result so the next rerun can't show it (and
            # offer its downloads) under a selection it doesn't match.
            st.session_state.pop("ksh_df", None)
            st.warning("No data returned for the selected terms.")
            return
        st.session_state["ksh_df"] = _prepare_data(df)
        clear_pdf_cache("ksh")
        clear_excel_cache("ksh")

    # --- Downloads in sidebar (after query block) ---
    if "ksh_df" in st.session_state:
        cache_key = (id(st.session_state["ksh_df"]),)
        pdf_bytes = cached_pdf_bytes(
            "ksh",
            (*cache_key, highlight),
            lambda: _generate_pdf(st.session_state["ksh_df"], highlight),
        )
        st.sidebar.download_button(
            "Download PDF",
            data=pdf_bytes,
            file_name="kpi_styp_headcount.pdf",
            mime="application/pdf",
            key="ksh_pdf_btn",
        )
        excel_bytes = cached_excel_bytes(
            "ksh",
            cache_key,
            lambda: _generate_excel(st.session_state["ksh_df"]),
        )
        st.sidebar.download_button(
            "Download Excel",
            data=excel_bytes,
            file_name="kpi_styp_headcount.xlsx",
            mime=EXCEL_MIME,
            key="ksh_excel_btn",
        )

    if "ksh_df" not in st.session_state:
        st.info("Select MIS Term IDs and press **Query** to load data.")
        return

    df = st.session_state["ksh_df"]
    state = _card_state(df, highlight)
    years = state.years
    dark = _is_dark_theme()

    st.subheader("Who is driving enrollment?")
    st.caption(f"Headcount by student type, {_fall_range(years)}.")

    credit_table = _build_table(df, CREDIT_CARDS, total_label=CREDIT_TOTAL_LABEL)
    latest_total = credit_table.iloc[-1][f"Fall {years[-1]}"]
    highlight_note = {
        0: "",
        1: " The fastest-growing type is highlighted.",
    }.get(len(state.highlighted),
          f" The {len(state.highlighted)} fastest-growing types are highlighted.")
    st.markdown(f"#### {CREDIT_SECTION}")
    st.caption(
        "Each student is counted once, even if enrolled at both colleges, and in "
        f"only one type, so the six cards add up to {latest_total:,.0f} students "
        f"in Fall {years[-1]}.{highlight_note}"
    )
    _render_grid(df, CREDIT_CARDS, state, dark, key="ksh_grid_credit")

    st.markdown(f"#### {NOCE_SECTION}")
    st.caption("Noncredit has no student-type split, so NOCE is one headcount.")
    # state.highlighted only ever holds credit cards, so NOCE is never orange.
    _render_grid(df, (NOCE_CARD,), state, dark, key="ksh_grid_noce")

    with st.expander("Headcount table"):
        change_col = _change_col(df)
        fmt: dict[Any, Any] = {f"Fall {y}": "{:,.0f}" for y in years}
        if change_col:
            fmt[change_col] = "{:+.1%}"
        table = pd.concat([credit_table, _build_table(df, (NOCE_CARD,))], ignore_index=True)
        st.dataframe(table.style.format(fmt, na_rep="—"), hide_index=True,
                     alt="Headcount by student type and Fall")
