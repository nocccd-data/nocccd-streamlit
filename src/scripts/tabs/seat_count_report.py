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
    matplotlib.rcParams.update({
        "figure.facecolor": "white",
        "axes.facecolor": "white",
        "text.color": "black",
        "axes.labelcolor": "black",
        "savefig.facecolor": "white",
    })

    PAGE_W, PAGE_H = 11.0, 8.5  # landscape
    MARGIN_TOP = 0.70
    MARGIN_BOT = 0.50
    ROW_H = 0.22
    HEADER_H = 0.35

    buf = io.BytesIO()
    with PdfPages(buf) as pdf:
        divisions = sorted(df["division_desc"].dropna().unique())

        for div_idx, division in enumerate(divisions):
            df_div = df[df["division_desc"] == division]
            departments = sorted(df_div["department_desc"].dropna().unique())

            fig = plt.figure(figsize=(PAGE_W, PAGE_H))
            if div_idx == 0:
                fig.suptitle(
                    f"Seat Count Report \u2014 {term_title}",
                    fontsize=14, fontweight="bold", color="black", y=0.96,
                )
            fig.text(
                0.04, PAGE_H - 0.35,
                division, fontsize=12, fontweight="bold", color="#003056",
                transform=fig.dpi_scale_trans,
            )
            cursor = PAGE_H - MARGIN_TOP

            for dept in departments:
                df_dept = df_div[df_div["department_desc"] == dept]
                dt = _compute_totals(df_dept)

                # Build table data for this department
                table_data = []
                col_labels = ["CRN", "Subject", "Crs#", "Title", "Max", "Enrl", "Fill%"]

                courses = (
                    df_dept.groupby(["subject_code", "course_number"], sort=True)
                    .first()
                    .reset_index()[["subject_code", "course_number"]]
                    .sort_values(["subject_code", "course_number"])
                )
                for _, cr in courses.iterrows():
                    df_c = df_dept[
                        (df_dept["subject_code"] == cr["subject_code"])
                        & (df_dept["course_number"] == cr["course_number"])
                    ].sort_values("crn")
                    for _, r in df_c.iterrows():
                        table_data.append([
                            str(r["crn"]),
                            str(r["subject_code"]),
                            str(r["course_number"]),
                            str(r["course_title"])[:30],
                            f"{int(r['enroll_max']):,}",
                            f"{int(r['current_enroll_count']):,}",
                            _fmt_pct(r["current_enroll_fillrate"]),
                        ])

                n_rows = len(table_data) + 1  # +1 for header
                table_h = HEADER_H + ROW_H * n_rows + 0.15

                # Page break if needed
                if cursor - table_h < MARGIN_BOT:
                    _add_pdf_footer(fig)
                    pdf.savefig(fig)
                    plt.close(fig)
                    fig = plt.figure(figsize=(PAGE_W, PAGE_H))
                    cursor = PAGE_H - MARGIN_TOP

                ax = fig.add_axes([
                    0.04, (cursor - table_h) / PAGE_H,
                    0.92, table_h / PAGE_H,
                ])
                ax.axis("off")
                ax.set_title(
                    f"{dept}  ({dt['sections']} sections, "
                    f"{dt['enrolled']:,}/{dt['max']:,}, {_fmt_pct(dt['fill'])} fill)",
                    fontsize=9, fontweight="bold", loc="left", color="black",
                )

                if table_data:
                    tbl = ax.table(
                        cellText=table_data,
                        colLabels=col_labels,
                        cellLoc="center",
                        loc="upper center",
                    )
                    tbl.auto_set_font_size(False)
                    tbl.set_fontsize(7)
                    tbl.auto_set_column_width(list(range(len(col_labels))))
                    tbl.scale(1, 1.3)

                    for key, cell in tbl.get_celld().items():
                        cell.set_facecolor("white")
                        cell.set_text_props(color="black")
                        cell.set_edgecolor("#CCCCCC")

                    # Header row styling
                    for col_idx in range(len(col_labels)):
                        cell = tbl[0, col_idx]
                        cell.set_facecolor("#003056")
                        cell.set_text_props(color="white")

                    # Fill rate column coloring
                    fill_col = len(col_labels) - 1
                    for row_idx in range(1, len(table_data) + 1):
                        try:
                            pct_str = table_data[row_idx - 1][fill_col].rstrip("%")
                            rate = float(pct_str) / 100.0
                            tbl[row_idx, fill_col].set_facecolor(
                                _fillrate_mpl_color(rate)
                            )
                        except (ValueError, IndexError):
                            pass

                cursor -= table_h

            _add_pdf_footer(fig)
            pdf.savefig(fig)
            plt.close(fig)

    return buf.getvalue()


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
