"""Seat Count Report tab — banded enrollment report with cascading filters."""

import io
from html import escape

import matplotlib
import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st
from matplotlib.backends.backend_pdf import PdfPages

from src.pipeline.config import DATASETS
from src.scripts.data_provider import fetch_seat_count_report

_CFG = DATASETS["seat_count_report"]
_DEFAULT_TERMS = _CFG[_CFG["param_name"]]

_PDF_FOOTER_LEFT = "https://nocccd.streamlit.app/"
_PDF_FOOTER_RIGHT = "Author: Jihoon Ahn  jahn@nocccd.edu"

# Columns to display in the banded HTML table
_DISPLAY_COLS = [
    "crn",
    "start_date", "end_date", "crosslist_group",
    "enroll_max", "current_enroll_count", "current_enroll_fillrate",
    "census_1_enroll_count", "census_1_enroll_fillrate",
    "first_day_morning_enroll_count", "first_day_morning_enroll_fillrate",
    "first_day_evening_enroll_count", "first_day_evening_enroll_fillrate",
    "first_day_no_hours_enroll_count", "first_day_no_hours_enroll_fillrate",
]

_COL_LABELS = [
    "CRN", "Schedule",
    "Start", "End", "XList",
    "Max", "Enrolled", "Fill %",
    "Census", "Census %",
    "1st AM", "AM %",
    "1st PM", "PM %",
    "1st NoHrs", "NoHrs %",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fillrate_css_class(rate: float) -> str:
    if rate >= 0.80:
        return "sc-fillrate-high"
    if rate >= 0.50:
        return "sc-fillrate-med"
    return "sc-fillrate-low"


def _fmt_pct(rate: float) -> str:
    return f"{rate:.0%}"


def _fmt_int(val) -> str:
    try:
        return f"{int(val):,}"
    except (ValueError, TypeError):
        return ""


def _fmt_date(val) -> str:
    if pd.isna(val):
        return ""
    try:
        return pd.Timestamp(val).strftime("%m/%d/%Y")
    except (ValueError, TypeError):
        return escape(str(val))


def _safe(val) -> str:
    if pd.isna(val):
        return ""
    return escape(str(val))


def _dedup_for_totals(df: pd.DataFrame) -> pd.DataFrame:
    """Deduplicate crosslisted sections for accurate totals.

    For crosslisted CRNs (same crosslist_group), enroll_max and enrollment
    counts are shared. Keep only the first CRN per crosslist_group so sums
    aren't inflated. Non-crosslisted rows pass through unchanged.
    """
    has_xlist = df["crosslist_group"].notna()
    no_xlist = df[~has_xlist]
    with_xlist = df[has_xlist].drop_duplicates(
        subset=["crosslist_group"], keep="first"
    )
    return pd.concat([no_xlist, with_xlist], ignore_index=True)


def _compute_totals(df: pd.DataFrame) -> dict:
    """Compute summary totals from a (possibly pre-deduped) DataFrame."""
    deduped = _dedup_for_totals(df)
    total_max = int(deduped["enroll_max"].sum())
    total_enrolled = int(deduped["current_enroll_count"].sum())
    fill = total_enrolled / total_max if total_max > 0 else 0.0
    return {
        "sections": df["crn"].nunique(),
        "max": total_max,
        "enrolled": total_enrolled,
        "fill": fill,
    }


# ---------------------------------------------------------------------------
# Banded HTML builder
# ---------------------------------------------------------------------------

def _build_banded_html(df_division: pd.DataFrame) -> str:
    """Build an HTML banded table for a single division."""
    rows: list[str] = []

    # Table header
    rows.append('<div style="overflow-x:auto;">')
    rows.append('<table class="sc-banded">')
    rows.append("<thead><tr>")
    for label in _COL_LABELS:
        rows.append(f"<th>{label}</th>")
    rows.append("</tr></thead>")
    rows.append("<tbody>")

    departments = sorted(df_division["department_desc"].dropna().unique())

    for dept in departments:
        df_dept = df_division[df_division["department_desc"] == dept]

        # Department header band
        rows.append(
            f'<tr class="dept-header"><td colspan="{len(_COL_LABELS)}">'
            f"{escape(dept)}</td></tr>"
        )

        # Group by course (subject_code + course_number)
        courses = (
            df_dept.groupby(["subject_code", "course_number"], sort=True)
            .first()
            .reset_index()[["subject_code", "course_number", "course_title", "crse_alias"]]
            .sort_values(["subject_code", "course_number"])
        )

        for _, course_row in courses.iterrows():
            subj = course_row["subject_code"]
            cnum = course_row["course_number"]
            ctitle = course_row["course_title"]
            alias = course_row["crse_alias"]

            df_course = df_dept[
                (df_dept["subject_code"] == subj)
                & (df_dept["course_number"] == cnum)
            ].sort_values("crn")

            # Course header — use crse_alias (already includes course_number or alias)
            display_num = escape(str(alias)) if pd.notna(alias) and str(alias).strip() else escape(str(cnum))
            rows.append(
                f'<tr class="course-header"><td colspan="{len(_COL_LABELS)}">'
                f"{escape(str(subj))} {display_num} &mdash; "
                f"{escape(str(ctitle))}</td></tr>"
            )

            # CRN detail rows
            for _, r in df_course.iterrows():
                fill_class = _fillrate_css_class(r["current_enroll_fillrate"])
                census_class = _fillrate_css_class(r["census_1_enroll_fillrate"])
                am_class = _fillrate_css_class(r["first_day_morning_enroll_fillrate"])
                pm_class = _fillrate_css_class(r["first_day_evening_enroll_fillrate"])
                nohrs_class = _fillrate_css_class(r["first_day_no_hours_enroll_fillrate"])

                rows.append("<tr>")
                rows.append(f"<td>{_safe(r['crn'])}</td>")
                rows.append(f"<td>{_safe(r['scheduling_desc'])}</td>")
                rows.append(f"<td>{_fmt_date(r['start_date'])}</td>")
                rows.append(f"<td>{_fmt_date(r['end_date'])}</td>")
                rows.append(f"<td>{_safe(r['crosslist_group'])}</td>")
                rows.append(f"<td style='text-align:right'>{_fmt_int(r['enroll_max'])}</td>")
                rows.append(f"<td style='text-align:right'>{_fmt_int(r['current_enroll_count'])}</td>")
                rows.append(f"<td class='{fill_class}' style='text-align:right'>{_fmt_pct(r['current_enroll_fillrate'])}</td>")
                rows.append(f"<td style='text-align:right'>{_fmt_int(r['census_1_enroll_count'])}</td>")
                rows.append(f"<td class='{census_class}' style='text-align:right'>{_fmt_pct(r['census_1_enroll_fillrate'])}</td>")
                rows.append(f"<td style='text-align:right'>{_fmt_int(r['first_day_morning_enroll_count'])}</td>")
                rows.append(f"<td class='{am_class}' style='text-align:right'>{_fmt_pct(r['first_day_morning_enroll_fillrate'])}</td>")
                rows.append(f"<td style='text-align:right'>{_fmt_int(r['first_day_evening_enroll_count'])}</td>")
                rows.append(f"<td class='{pm_class}' style='text-align:right'>{_fmt_pct(r['first_day_evening_enroll_fillrate'])}</td>")
                rows.append(f"<td style='text-align:right'>{_fmt_int(r['first_day_no_hours_enroll_count'])}</td>")
                rows.append(f"<td class='{nohrs_class}' style='text-align:right'>{_fmt_pct(r['first_day_no_hours_enroll_fillrate'])}</td>")
                rows.append("</tr>")

            # Course subtotal
            ct = _compute_totals(df_course)
            ct_fill_class = _fillrate_css_class(ct["fill"])
            rows.append('<tr class="subtotal-row">')
            rows.append('<td colspan="5" style="text-align:right">Course Total:</td>')
            rows.append(f"<td style='text-align:right'>{ct['max']:,}</td>")
            rows.append(f"<td style='text-align:right'>{ct['enrolled']:,}</td>")
            rows.append(f"<td class='{ct_fill_class}' style='text-align:right'>{_fmt_pct(ct['fill'])}</td>")
            rows.append('<td colspan="8"></td>')
            rows.append("</tr>")

        # Department subtotal
        dt = _compute_totals(df_dept)
        dt_fill_class = _fillrate_css_class(dt["fill"])
        rows.append('<tr class="dept-total">')
        rows.append(
            f'<td colspan="5" style="text-align:right">'
            f"Dept Total &mdash; {escape(dept)}:</td>"
        )
        rows.append(f"<td style='text-align:right'>{dt['max']:,}</td>")
        rows.append(f"<td style='text-align:right'>{dt['enrolled']:,}</td>")
        rows.append(f"<td class='{dt_fill_class}' style='text-align:right'>{_fmt_pct(dt['fill'])}</td>")
        rows.append('<td colspan="8"></td>')
        rows.append("</tr>")

    rows.append("</tbody></table></div>")
    return "\n".join(rows)


# ---------------------------------------------------------------------------
# PDF export
# ---------------------------------------------------------------------------

def _add_pdf_footer(fig):
    fig.text(0.04, 0.02, _PDF_FOOTER_LEFT, fontsize=7, color="grey", ha="left")
    fig.text(0.96, 0.02, _PDF_FOOTER_RIGHT, fontsize=7, color="grey", ha="right")


def _fillrate_mpl_color(rate: float) -> str:
    if rate >= 0.80:
        return "#D4EDDA"
    if rate >= 0.50:
        return "#FFF3CD"
    return "#F8D7DA"


def _generate_pdf(df: pd.DataFrame, term_title: str) -> bytes:
    """Render a continuous banded report as a multi-page PDF.

    Rows flow continuously across pages (no per-department clipping).
    Uses matplotlib text drawing for precise row-by-row control.
    """
    matplotlib.rcParams.update({
        "figure.facecolor": "white",
        "text.color": "black",
    })

    PAGE_W, PAGE_H = 8.5, 11.0
    ML, MR = 0.50, 0.50  # left/right margins in inches
    MT = 0.70             # top margin
    MB = 0.55             # bottom margin (room for footer)
    ROW_H = 0.16          # row height in inches
    FONT_SZ = 6.0

    # Column definitions: (label, width_fraction, align)
    # width_fraction is relative to usable width (PAGE_W - ML - MR)
    usable = PAGE_W - ML - MR
    _cols = [
        ("CRN",   0.055), ("Sched", 0.065), ("Start", 0.085), ("End", 0.085),
        ("XList", 0.045),
        ("Max",   0.04),  ("Enrl",  0.04),  ("Fill%", 0.05),
        ("Cens",  0.04),  ("Cens%", 0.05),
        ("AM",    0.04),  ("AM%",   0.05),
        ("PM",    0.04),  ("PM%",   0.05),
        ("NoHr",  0.04),  ("NoHr%", 0.05),
    ]
    col_labels = [c[0] for c in _cols]
    col_w = [c[1] * usable for c in _cols]
    col_x = []
    x = ML
    for w in col_w:
        col_x.append(x)
        x += w
    n_cols = len(col_labels)

    buf = io.BytesIO()
    with PdfPages(buf) as pdf:
        fig = None
        ax = None
        cursor = 0.0
        page_num = 0

        def _new_page():
            nonlocal fig, ax, cursor, page_num
            if fig is not None:
                _add_pdf_footer(fig)
                pdf.savefig(fig)
                plt.close(fig)
            fig = plt.figure(figsize=(PAGE_W, PAGE_H))
            ax = fig.add_axes([0, 0, 1, 1])
            ax.set_xlim(0, PAGE_W)
            ax.set_ylim(0, PAGE_H)
            ax.axis("off")
            page_num += 1
            if page_num == 1:
                ax.text(
                    PAGE_W / 2, PAGE_H - 0.35,
                    f"Seat Count Report \u2014 {term_title}",
                    ha="center", va="top", fontsize=12,
                    fontweight="bold", color="black",
                )
            cursor = PAGE_H - MT

        def _ensure_space(needed):
            if cursor - needed < MB:
                _new_page()

        def _draw_row_bg(y, color, height=ROW_H):
            from matplotlib.patches import Rectangle
            ax.add_patch(Rectangle(
                (ML, y), usable, height,
                facecolor=color, edgecolor="none", zorder=0,
            ))

        def _draw_header_row():
            nonlocal cursor
            _ensure_space(ROW_H)
            _draw_row_bg(cursor - ROW_H, "#003056")
            for i, label in enumerate(col_labels):
                ax.text(
                    col_x[i] + col_w[i] / 2, cursor - ROW_H / 2,
                    label, ha="center", va="center",
                    fontsize=5, fontweight="bold", color="white",
                )
            cursor -= ROW_H

        def _draw_gridlines(y):
            for i in range(n_cols + 1):
                xp = col_x[i] if i < n_cols else col_x[-1] + col_w[-1]
                ax.plot([xp, xp], [y, y + ROW_H], color="#CCCCCC",
                        linewidth=0.3, zorder=1)
            ax.plot([ML, ML + usable], [y, y], color="#CCCCCC",
                    linewidth=0.3, zorder=1)

        _new_page()

        divisions = sorted(df["division_desc"].dropna().unique())

        for division in divisions:
            df_div = df[df["division_desc"] == division]
            departments = sorted(df_div["department_desc"].dropna().unique())

            # Division header
            _ensure_space(ROW_H * 2)
            ax.text(
                ML, cursor - ROW_H * 0.6,
                division, ha="left", va="center",
                fontsize=9, fontweight="bold", color="#003056",
            )
            cursor -= ROW_H * 1.2

            for dept in departments:
                df_dept = df_div[df_div["department_desc"] == dept]
                dt = _compute_totals(df_dept)

                # Department header
                _ensure_space(ROW_H * 2.5)
                dept_label = (
                    f"{dept}  ({dt['sections']} sect, "
                    f"{dt['enrolled']:,}/{dt['max']:,}, {_fmt_pct(dt['fill'])})"
                )
                _draw_row_bg(cursor - ROW_H, "#D6E4F0")
                ax.text(
                    ML + 0.05, cursor - ROW_H / 2,
                    dept_label, ha="left", va="center",
                    fontsize=6.5, fontweight="bold", color="#003056",
                )
                cursor -= ROW_H

                # Column header
                _draw_header_row()

                courses = (
                    df_dept.groupby(["subject_code", "course_number"], sort=True)
                    .first()
                    .reset_index()[["subject_code", "course_number", "course_title", "crse_alias"]]
                    .sort_values(["subject_code", "course_number"])
                )

                for _, cr in courses.iterrows():
                    subj = str(cr["subject_code"])
                    alias = cr["crse_alias"]
                    display_num = str(alias) if pd.notna(alias) and str(alias).strip() else str(cr["course_number"])
                    ctitle = str(cr["course_title"])

                    # Course header — merged row
                    _ensure_space(ROW_H)
                    _draw_row_bg(cursor - ROW_H, "#EDF2F7")
                    ax.text(
                        ML + 0.08, cursor - ROW_H / 2,
                        f"{subj} {display_num} \u2014 {ctitle}",
                        ha="left", va="center",
                        fontsize=FONT_SZ, fontweight="bold", fontstyle="italic",
                        color="#003056",
                    )
                    cursor -= ROW_H

                    # CRN data rows
                    df_c = df_dept[
                        (df_dept["subject_code"] == cr["subject_code"])
                        & (df_dept["course_number"] == cr["course_number"])
                    ].sort_values("crn")

                    for _, r in df_c.iterrows():
                        _ensure_space(ROW_H)
                        y = cursor - ROW_H
                        _draw_gridlines(y)

                        vals = [
                            str(r["crn"]),
                            str(r.get("scheduling_desc", "")) if pd.notna(r.get("scheduling_desc")) else "",
                            _fmt_date(r["start_date"]),
                            _fmt_date(r["end_date"]),
                            str(r["crosslist_group"]) if pd.notna(r["crosslist_group"]) else "",
                            _fmt_int(r["enroll_max"]),
                            _fmt_int(r["current_enroll_count"]),
                            _fmt_pct(r["current_enroll_fillrate"]),
                            _fmt_int(r["census_1_enroll_count"]),
                            _fmt_pct(r["census_1_enroll_fillrate"]),
                            _fmt_int(r["first_day_morning_enroll_count"]),
                            _fmt_pct(r["first_day_morning_enroll_fillrate"]),
                            _fmt_int(r["first_day_evening_enroll_count"]),
                            _fmt_pct(r["first_day_evening_enroll_fillrate"]),
                            _fmt_int(r["first_day_no_hours_enroll_count"]),
                            _fmt_pct(r["first_day_no_hours_enroll_fillrate"]),
                        ]

                        # Fill rate cell backgrounds
                        rates = {
                            7: r["current_enroll_fillrate"],
                            9: r["census_1_enroll_fillrate"],
                            11: r["first_day_morning_enroll_fillrate"],
                            13: r["first_day_evening_enroll_fillrate"],
                            15: r["first_day_no_hours_enroll_fillrate"],
                        }
                        for ci, rate in rates.items():
                            from matplotlib.patches import Rectangle as Rect
                            ax.add_patch(Rect(
                                (col_x[ci], y), col_w[ci], ROW_H,
                                facecolor=_fillrate_mpl_color(rate),
                                edgecolor="none", zorder=0,
                            ))

                        for i, val in enumerate(vals):
                            ha = "right" if i >= 5 else "left"
                            xp = col_x[i] + col_w[i] - 0.03 if ha == "right" else col_x[i] + 0.03
                            ax.text(
                                xp, y + ROW_H / 2, val,
                                ha=ha, va="center", fontsize=FONT_SZ, color="black",
                            )

                        cursor -= ROW_H

        # Final page
        if fig is not None:
            _add_pdf_footer(fig)
            pdf.savefig(fig)
            plt.close(fig)

    return buf.getvalue()


def generate_report_pdf(df: pd.DataFrame, params: dict) -> bytes:
    """Public API for the mail system. params must include 'term_title'."""
    return _generate_pdf(df, params.get("term_title", ""))


# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------

def render():
    st.header("Seat Count Report")

    # --- Sidebar: Term Code ---
    selected_term = st.sidebar.selectbox(
        "Term Code",
        options=_DEFAULT_TERMS,
        index=len(_DEFAULT_TERMS) - 1,
        key="sc_term",
    )

    # --- Sidebar: Query button ---
    query_btn = st.sidebar.button("Query", key="sc_query_btn")

    if query_btn:
        fetch_seat_count_report.clear()
        df = fetch_seat_count_report((selected_term,))
        if df.empty:
            st.warning("No data returned for the selected term.")
            return
        st.session_state["sc_df"] = df
        if "term_title" in df.columns and not df["term_title"].empty:
            st.session_state["sc_term_title"] = df["term_title"].iloc[0]
        else:
            st.session_state["sc_term_title"] = selected_term

    # --- No data yet ---
    if "sc_df" not in st.session_state:
        st.info("Select a **Term Code** and press **Query** to load data.")
        return

    raw_df = st.session_state["sc_df"]
    term_title = st.session_state.get("sc_term_title", "")

    # --- Sidebar: Cascading filters ---
    st.sidebar.divider()

    # Campus
    campuses = sorted(raw_df["campus_desc"].dropna().unique())
    campus = st.sidebar.selectbox("Campus", ["All"] + campuses, key="sc_campus")
    filtered = raw_df if campus == "All" else raw_df[raw_df["campus_desc"] == campus]

    # Division
    divisions = sorted(filtered["division_desc"].dropna().unique())
    division = st.sidebar.selectbox("Division", ["All"] + divisions, key="sc_division")
    if division != "All":
        filtered = filtered[filtered["division_desc"] == division]

    # Department
    departments = sorted(filtered["department_desc"].dropna().unique())
    department = st.sidebar.selectbox("Department", ["All"] + departments, key="sc_dept")
    if department != "All":
        filtered = filtered[filtered["department_desc"] == department]

    # --- Sidebar: PDF export (after query block per ordering rule) ---
    pdf_bytes = _generate_pdf(filtered, term_title)
    st.sidebar.download_button(
        "Download PDF",
        data=pdf_bytes,
        file_name=f"seat_count_{selected_term}.pdf",
        mime="application/pdf",
        key="sc_pdf_btn",
    )

    # --- Main: Term title ---
    st.subheader(f"{term_title}")

    # --- Main: Summary metrics ---
    totals = _compute_totals(filtered)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Sections", f"{totals['sections']:,}")
    c2.metric("Total Seats", f"{totals['max']:,}")
    c3.metric("Current Enrolled", f"{totals['enrolled']:,}")
    c4.metric("Overall Fill Rate", _fmt_pct(totals["fill"]))

    st.divider()

    # --- Main: Banded report by division ---
    div_list = sorted(filtered["division_desc"].dropna().unique())

    if not div_list:
        st.warning("No divisions found for the current filter selection.")
        return

    for div_name in div_list:
        df_div = filtered[filtered["division_desc"] == div_name]
        div_totals = _compute_totals(df_div)
        label = (
            f"{div_name}  \u2014  "
            f"{div_totals['sections']} sections, "
            f"{div_totals['enrolled']:,}/{div_totals['max']:,} seats, "
            f"{_fmt_pct(div_totals['fill'])} fill"
        )
        with st.expander(label):
            html = _build_banded_html(df_div)
            st.markdown(html, unsafe_allow_html=True)
