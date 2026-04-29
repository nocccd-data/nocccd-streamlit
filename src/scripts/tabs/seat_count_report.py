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

def _resolve_layout_mode(campus: str, term_code: str) -> str:
    """Pick the column-layout mode given the campus filter and the term.

    Banner term codes ending in '0' (e.g. 202310, 202320, 202330) are credit
    colleges only — Cypress and Fullerton — and end in '5' (e.g. 202315,
    202335, 202405) are NOCE only. So when the user picks campus "All",
    the layout follows the term's suffix:

      - term ends in '0' → credit-college layout (13 cols, no Building/C2)
      - term ends in '5' → NOCE layout (16 cols, with Building + C2)

    Specific campus selections always pin to their matching layout.
    """
    if campus in ("Cypress", "Fullerton", "NOCE"):
        return campus
    # "All" or anything unexpected: defer to the term suffix.
    if term_code and term_code[-1] == "5":
        return "NOCE"
    return "Cypress"  # any "credit" sentinel works — both produce the same layout


def _layout_for_campus(campus_mode: str) -> dict:
    """Per-campus column layout.

    Cypress and Fullerton (credit colleges, campus codes 1/2) hide the
    Census 2 count + % columns. NOCE (campus code 3) adds a Building
    column. The "All" view is resolved upstream by ``_resolve_layout_mode``,
    which picks credit vs NOCE based on the term-code suffix, so this
    function only ever sees a concrete campus name.
    """
    is_credit_only = campus_mode in ("Cypress", "Fullerton")
    show_building = not is_credit_only
    show_census_2 = not is_credit_only

    html_labels = ["CRN", "INSM", "Start", "End",
                   "Mtg Days", "Start Time", "End Time"]
    if show_building:
        html_labels.append("Building")
    html_labels.extend(["XList", "Max", "1st Day", "1st Day %",
                        "Census 1", "Census 1 %"])
    if show_census_2:
        html_labels.extend(["Census 2", "Census 2 %"])

    if is_credit_only:
        # 13 columns: distribute removed Building/Census 2 width to INSM
        # and the date columns so descriptions fit comfortably.
        pdf_cols = [
            ("CRN",         0.05),
            ("INSM",        0.27),
            ("Start",       0.12),
            ("End",         0.12),
            ("Mtg\nDays",   0.06),
            ("Start\nTime", 0.06),
            ("End\nTime",   0.06),
            ("XList",       0.05),
            ("Max",         0.05),
            ("1st\nDay",    0.04),
            ("1st Day\n%",  0.04),
            ("Cens 1",      0.04),
            ("Cens 1\n%",   0.04),
        ]
        pdf_rate_indices = (10, 12)         # 1st Day %, Census 1 %
        pdf_center_cols = {0, 2, 3, 4, 5, 6, 7}
        pdf_left_cols = {1}
        subtotal_label_colspan = 8           # CRN..XList
    else:
        # 16 columns: includes Building (after End Time) and Census 2.
        pdf_cols = [
            ("CRN",         0.05),
            ("INSM",        0.14),
            ("Start",       0.07),
            ("End",         0.07),
            ("Mtg\nDays",   0.06),
            ("Start\nTime", 0.05),
            ("End\nTime",   0.05),
            ("Building",    0.19),
            ("XList",       0.04),
            ("Max",         0.04),
            ("1st\nDay",    0.04),
            ("1st Day\n%",  0.04),
            ("Cens 1",      0.04),
            ("Cens 1\n%",   0.04),
            ("Cens 2",      0.04),
            ("Cens 2\n%",   0.04),
        ]
        pdf_rate_indices = (11, 13, 15)      # 1st Day %, Census 1 %, Census 2 %
        pdf_center_cols = {0, 2, 3, 4, 5, 6, 8}
        pdf_left_cols = {1, 7}               # INSM, Building
        subtotal_label_colspan = 9           # CRN..XList (XList shifted right by Building)

    return {
        "html_labels": html_labels,
        "pdf_cols": pdf_cols,
        "pdf_rate_indices": pdf_rate_indices,
        "pdf_center_cols": pdf_center_cols,
        "pdf_left_cols": pdf_left_cols,
        "show_building": show_building,
        "show_census_2": show_census_2,
        "subtotal_label_colspan": subtotal_label_colspan,
    }


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
    if val is None or pd.isna(val):
        return ""
    return escape(str(val))


def _fmt_time(val) -> str:
    """Format a Banner HHMM time string as HH:MM. Blank/NULL → ''."""
    if val is None or pd.isna(val):
        return ""
    s = str(val).strip()
    if not s:
        return ""
    if len(s) == 4 and s.isdigit():
        return f"{s[:2]}:{s[2:]}"
    return escape(s)


def _first_day_combined(row) -> tuple[int, float]:
    """Sum morning + evening + no-hours first-day counts and recompute fill rate."""
    total = 0
    for col in (
        "first_day_morning_enroll_count",
        "first_day_evening_enroll_count",
        "first_day_no_hours_enroll_count",
    ):
        v = row.get(col)
        if v is not None and not pd.isna(v):
            total += int(v)
    max_seats = row.get("enroll_max")
    if max_seats is None or pd.isna(max_seats) or max_seats <= 0:
        return total, 0.0
    return total, total / max_seats


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
    total_census_1 = int(deduped["census_1_enroll_count"].fillna(0).sum())
    total_census_2 = int(deduped["census_2_enroll_count"].fillna(0).sum()) if "census_2_enroll_count" in deduped.columns else 0
    total_wait = int(deduped["wait_count"].fillna(0).sum()) if "wait_count" in deduped.columns else 0
    fd_cols = [
        "first_day_morning_enroll_count",
        "first_day_evening_enroll_count",
        "first_day_no_hours_enroll_count",
    ]
    total_first_day = int(deduped[fd_cols].fillna(0).sum().sum())

    def _rate(num: int) -> float:
        return num / total_max if total_max > 0 else 0.0

    return {
        "sections": df["crn"].nunique(),
        "max": total_max,
        "enrolled": total_enrolled,
        "fill": _rate(total_enrolled),
        "census_1": total_census_1,
        "census_1_fill": _rate(total_census_1),
        "census_2": total_census_2,
        "census_2_fill": _rate(total_census_2),
        "first_day": total_first_day,
        "first_day_fill": _rate(total_first_day),
        "wait": total_wait,
    }


# ---------------------------------------------------------------------------
# Banded HTML builder
# ---------------------------------------------------------------------------

def _build_banded_html(df_division: pd.DataFrame, campus_mode: str = "All") -> str:
    """Build an HTML banded table for a single division.

    The column set varies by campus_mode:
      - Cypress, Fullerton: drop Census 2 count + %
      - NOCE: include Building between End Time and XList
      - All / anything else: union (Building + Census 2 visible)
    """
    layout = _layout_for_campus(campus_mode)
    show_building = layout["show_building"]
    show_census_2 = layout["show_census_2"]
    label_count = len(layout["html_labels"])
    label_colspan = layout["subtotal_label_colspan"]

    rows: list[str] = []

    # Table header
    rows.append('<div style="overflow-x:auto;">')
    rows.append('<table class="sc-banded">')
    rows.append("<thead><tr>")
    for label in layout["html_labels"]:
        rows.append(f"<th>{label}</th>")
    rows.append("</tr></thead>")
    rows.append("<tbody>")

    departments = sorted(df_division["department_desc"].dropna().unique())

    for dept in departments:
        df_dept = df_division[df_division["department_desc"] == dept]

        # Department header band
        rows.append(
            f'<tr class="dept-header"><td colspan="{label_count}">'
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
                f'<tr class="course-header"><td colspan="{label_count}">'
                f"{escape(str(subj))} {display_num} &mdash; "
                f"{escape(str(ctitle))}</td></tr>"
            )

            # CRN detail rows
            for _, r in df_course.iterrows():
                c1_class = _fillrate_css_class(r["census_1_enroll_fillrate"])
                fd_count, fd_rate = _first_day_combined(r)
                fd_class = _fillrate_css_class(fd_rate)

                rows.append("<tr>")
                rows.append(f"<td style='text-align:center'>{_safe(r['crn'])}</td>")
                rows.append(f"<td>{_safe(r.get('insm'))}</td>")
                rows.append(f"<td style='text-align:center'>{_fmt_date(r['start_date'])}</td>")
                rows.append(f"<td style='text-align:center'>{_fmt_date(r['end_date'])}</td>")
                rows.append(f"<td style='text-align:center'>{_safe(r.get('days'))}</td>")
                rows.append(f"<td style='text-align:center'>{_fmt_time(r.get('begin_time'))}</td>")
                rows.append(f"<td style='text-align:center'>{_fmt_time(r.get('end_time'))}</td>")
                if show_building:
                    rows.append(f"<td>{_safe(r.get('building'))}</td>")
                rows.append(f"<td style='text-align:center'>{_safe(r['crosslist_group'])}</td>")
                rows.append(f"<td style='text-align:right'>{_fmt_int(r['enroll_max'])}</td>")
                rows.append(f"<td style='text-align:right'>{_fmt_int(fd_count)}</td>")
                rows.append(f"<td class='{fd_class}' style='text-align:right'>{_fmt_pct(fd_rate)}</td>")
                rows.append(f"<td style='text-align:right'>{_fmt_int(r['census_1_enroll_count'])}</td>")
                rows.append(f"<td class='{c1_class}' style='text-align:right'>{_fmt_pct(r['census_1_enroll_fillrate'])}</td>")
                if show_census_2:
                    c2_class = _fillrate_css_class(r["census_2_enroll_fillrate"])
                    rows.append(f"<td style='text-align:right'>{_fmt_int(r['census_2_enroll_count'])}</td>")
                    rows.append(f"<td class='{c2_class}' style='text-align:right'>{_fmt_pct(r['census_2_enroll_fillrate'])}</td>")
                rows.append("</tr>")

            # Course subtotal
            ct = _compute_totals(df_course)
            ct_c1_class = _fillrate_css_class(ct["census_1_fill"])
            ct_fd_class = _fillrate_css_class(ct["first_day_fill"])
            rows.append('<tr class="subtotal-row">')
            rows.append(f'<td colspan="{label_colspan}" style="text-align:right">Course Total:</td>')
            rows.append(f"<td style='text-align:right'>{ct['max']:,}</td>")
            rows.append(f"<td style='text-align:right'>{ct['first_day']:,}</td>")
            rows.append(f"<td class='{ct_fd_class}' style='text-align:right'>{_fmt_pct(ct['first_day_fill'])}</td>")
            rows.append(f"<td style='text-align:right'>{ct['census_1']:,}</td>")
            rows.append(f"<td class='{ct_c1_class}' style='text-align:right'>{_fmt_pct(ct['census_1_fill'])}</td>")
            if show_census_2:
                ct_c2_class = _fillrate_css_class(ct["census_2_fill"])
                rows.append(f"<td style='text-align:right'>{ct['census_2']:,}</td>")
                rows.append(f"<td class='{ct_c2_class}' style='text-align:right'>{_fmt_pct(ct['census_2_fill'])}</td>")
            rows.append("</tr>")

        # Department subtotal
        dt = _compute_totals(df_dept)
        dt_c1_class = _fillrate_css_class(dt["census_1_fill"])
        dt_fd_class = _fillrate_css_class(dt["first_day_fill"])
        rows.append('<tr class="dept-total">')
        rows.append(
            f'<td colspan="{label_colspan}" style="text-align:right">'
            f"Dept Total &mdash; {escape(dept)}:</td>"
        )
        rows.append(f"<td style='text-align:right'>{dt['max']:,}</td>")
        rows.append(f"<td style='text-align:right'>{dt['first_day']:,}</td>")
        rows.append(f"<td class='{dt_fd_class}' style='text-align:right'>{_fmt_pct(dt['first_day_fill'])}</td>")
        rows.append(f"<td style='text-align:right'>{dt['census_1']:,}</td>")
        rows.append(f"<td class='{dt_c1_class}' style='text-align:right'>{_fmt_pct(dt['census_1_fill'])}</td>")
        if show_census_2:
            dt_c2_class = _fillrate_css_class(dt["census_2_fill"])
            rows.append(f"<td style='text-align:right'>{dt['census_2']:,}</td>")
            rows.append(f"<td class='{dt_c2_class}' style='text-align:right'>{_fmt_pct(dt['census_2_fill'])}</td>")
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


def _generate_pdf(df: pd.DataFrame, term_title: str,
                   filter_scope: str = "", summary: dict | None = None,
                   campus_mode: str = "All") -> bytes:
    """Render a continuous banded report as a multi-page PDF.

    Rows flow continuously across pages (no per-department clipping).
    Uses matplotlib text drawing for precise row-by-row control.

    The column set varies by campus_mode (see _layout_for_campus):
    Cypress/Fullerton drop Census 2; NOCE adds Building; All shows both.
    """
    matplotlib.rcParams.update({
        "figure.facecolor": "white",
        "text.color": "black",
    })

    PAGE_W, PAGE_H = 11.0, 8.5
    ML, MR = 0.50, 0.50  # left/right margins in inches
    MT = 0.70             # top margin
    MB = 0.55             # bottom margin (room for footer)
    ROW_H = 0.16          # row height in inches
    FONT_SZ = 7.0

    layout = _layout_for_campus(campus_mode)
    show_building = layout["show_building"]
    show_census_2 = layout["show_census_2"]
    _cols = layout["pdf_cols"]
    pdf_rate_indices = layout["pdf_rate_indices"]
    pdf_center_cols = layout["pdf_center_cols"]
    pdf_left_cols = layout["pdf_left_cols"]

    # Column geometry — width_fraction is relative to usable width.
    usable = PAGE_W - ML - MR
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
                from matplotlib.patches import FancyBboxPatch

                # Title — left justified
                ax.text(
                    ML, PAGE_H - 0.35,
                    "Seat Count Report",
                    ha="left", va="top", fontsize=14,
                    fontweight="bold", color="black",
                )
                # Filter scope subtitle
                scope_text = filter_scope or term_title
                ax.text(
                    ML, PAGE_H - 0.60,
                    scope_text,
                    ha="left", va="top", fontsize=10,
                    fontweight="bold", color="#003056",
                )
                # Summary metric cards
                if summary:
                    card_y = PAGE_H - 1.25
                    card_h = 0.48
                    card_gap = 0.08
                    card_w = (usable - card_gap * 3) / 4
                    metrics = [
                        ("Total Sections", f"{summary['sections']:,}"),
                        ("Total Seats", f"{summary['max']:,}"),
                        ("Current Enrolled", f"{summary['enrolled']:,}"),
                        ("Overall Fill Rate", _fmt_pct(summary['fill'])),
                    ]
                    for idx, (label, value) in enumerate(metrics):
                        cx = ML + idx * (card_w + card_gap)
                        # Card border
                        ax.add_patch(FancyBboxPatch(
                            (cx, card_y), card_w, card_h,
                            boxstyle="round,pad=0.03",
                            facecolor="white", edgecolor="#AAAAAA",
                            linewidth=0.8, zorder=0,
                        ))
                        # Label
                        ax.text(
                            cx + 0.08, card_y + card_h - 0.06,
                            label, ha="left", va="top",
                            fontsize=7, color="#555555",
                        )
                        # Value
                        ax.text(
                            cx + card_w / 2, card_y + 0.06,
                            value, ha="center", va="bottom",
                            fontsize=12, fontweight="bold", color="black",
                        )
                    cursor = card_y - 0.20
                else:
                    cursor = PAGE_H - MT - 0.50
            else:
                cursor = PAGE_H - MT
            # Column header on every page
            _draw_header_row()

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
            hdr_h = ROW_H * 1.6  # taller for two-line labels
            _ensure_space(hdr_h)
            _draw_row_bg(cursor - hdr_h, "#003056", height=hdr_h)
            for i, label in enumerate(col_labels):
                ax.text(
                    col_x[i] + col_w[i] / 2, cursor - hdr_h / 2,
                    label, ha="center", va="center",
                    fontsize=6, fontweight="bold", color="white",
                    linespacing=1.2,
                )
            cursor -= hdr_h

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
                    fontsize=7.5, fontweight="bold", color="#003056",
                )
                cursor -= ROW_H

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

                        fd_count, fd_rate = _first_day_combined(r)
                        vals = [
                            str(r["crn"]),
                            str(r.get("insm", "")) if pd.notna(r.get("insm")) else "",
                            _fmt_date(r["start_date"]),
                            _fmt_date(r["end_date"]),
                            str(r["days"]) if pd.notna(r.get("days")) else "",
                            _fmt_time(r.get("begin_time")),
                            _fmt_time(r.get("end_time")),
                        ]
                        if show_building:
                            vals.append(str(r["building"]) if pd.notna(r.get("building")) else "")
                        vals.extend([
                            str(r["crosslist_group"]) if pd.notna(r["crosslist_group"]) else "",
                            _fmt_int(r["enroll_max"]),
                            _fmt_int(fd_count),
                            _fmt_pct(fd_rate),
                            _fmt_int(r["census_1_enroll_count"]),
                            _fmt_pct(r["census_1_enroll_fillrate"]),
                        ])
                        if show_census_2:
                            vals.append(_fmt_int(r["census_2_enroll_count"]))
                            vals.append(_fmt_pct(r["census_2_enroll_fillrate"]))

                        # Fill rate cell backgrounds — indices come from layout
                        # (1st Day %, Census 1 %, optional Census 2 %).
                        rate_values = [
                            fd_rate,
                            r["census_1_enroll_fillrate"],
                        ]
                        if show_census_2:
                            rate_values.append(r["census_2_enroll_fillrate"])
                        for ci, rate in zip(pdf_rate_indices, rate_values):
                            from matplotlib.patches import Rectangle as Rect
                            ax.add_patch(Rect(
                                (col_x[ci], y), col_w[ci], ROW_H,
                                facecolor=_fillrate_mpl_color(rate),
                                edgecolor="none", zorder=0,
                            ))

                        for i, val in enumerate(vals):
                            if i in pdf_center_cols:
                                ha = "center"
                                xp = col_x[i] + col_w[i] / 2
                            elif i in pdf_left_cols:
                                ha = "left"
                                xp = col_x[i] + 0.03
                            else:
                                ha = "right"
                                xp = col_x[i] + col_w[i] - 0.03
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
    term_title = params.get("term_title", "")
    filter_scope = params.get("filter_scope", term_title)
    campus_mode = params.get("campus_mode", "All")
    summary = _compute_totals(df)
    return _generate_pdf(df, term_title, filter_scope=filter_scope,
                         summary=summary, campus_mode=campus_mode)


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
        # Force PDF regen on next render in case Hyper refreshed underneath us.
        st.session_state.pop("_sc_pdf_key", None)
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
    # Build filter scope for PDF
    _scope_parts = [term_title]
    if campus != "All":
        _scope_parts.append(campus)
    if division != "All":
        _scope_parts.append(division)
    if department != "All":
        _scope_parts.append(department)
    _filter_scope = " / ".join(_scope_parts)

    # Memoize PDF bytes per filter combination. Matplotlib embeds a creation
    # timestamp in every PDF, so regenerating on each rerun yields different
    # bytes → a different Streamlit media-file hash → the download URL handed
    # to the browser goes stale before the user can fetch it (saved as HTML).
    # When campus="All", resolve to credit-vs-NOCE layout based on the
    # term-code suffix — credit terms end in '0', NOCE terms in '5'.
    _layout_mode = _resolve_layout_mode(campus, selected_term)
    _pdf_key = (selected_term, campus, division, department)
    if st.session_state.get("_sc_pdf_key") != _pdf_key:
        _summary = _compute_totals(filtered)
        st.session_state["_sc_pdf_key"] = _pdf_key
        st.session_state["_sc_pdf_bytes"] = _generate_pdf(
            filtered, term_title,
            filter_scope=_filter_scope, summary=_summary,
            campus_mode=_layout_mode,
        )
    st.sidebar.download_button(
        "Download PDF",
        data=st.session_state["_sc_pdf_bytes"],
        file_name=f"seat_count_{selected_term}.pdf",
        mime="application/pdf",
        key="sc_pdf_btn",
    )

    # --- Main: Term title + filter scope ---
    filter_parts = [term_title]
    if campus != "All":
        filter_parts.append(campus)
    if division != "All":
        filter_parts.append(division)
    if department != "All":
        filter_parts.append(department)
    st.subheader(" / ".join(filter_parts))

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
            html = _build_banded_html(df_div, campus_mode=_layout_mode)
            st.markdown(html, unsafe_allow_html=True)
