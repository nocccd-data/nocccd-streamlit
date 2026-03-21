import io

import matplotlib
import matplotlib.pyplot as plt
import pandas as pd
import streamlit as st
from matplotlib.backends.backend_pdf import PdfPages

from src.pipeline.config import DATASETS
from src.scripts.data_provider import fetch_fast_facts_stu, fetch_fast_facts_emp

_DEFAULT_ACYR_CODES = DATASETS["fast_facts_stu"]["acyr_code"]
_DEFAULT_FISC_YEARS = DATASETS["fast_facts_emp"]["fisc_year"]

_ECLS_FILTER = [
    "Administrator/Manager",
    "Confidential/Classified",
    "FT Faculty",
    "PT/Temp Faculty",
    "Executive",
]

_ETHN_MAP = {
    "A": "Asian",
    "B": "Black or African American",
    "H": "Hispanic or Latino",
    "N": "American Indian or Alaska Native",
    "P": "Pacific Islander or Native Hawaiian",
    "T": "Multiethnicity",
    "W": "White Non-Hispanic",
    "F": "Filipino",
    "X": "Unreported",
}


def _process(df_stu: pd.DataFrame, df_emp: pd.DataFrame, fisc_year: str) -> list[tuple[pd.DataFrame, str]]:
    """Build the 9 summary DataFrames from raw student + employee data."""
    acyr = df_stu["academic_year"].iloc[0]
    fy_label = f"FY {fisc_year}"

    # df1 — Headcount (Unduplicated)
    df1 = pd.DataFrame({
        "academic_year": [acyr],
        "enrollments": [len(df_stu)],
        "headcount": [df_stu["pidm"].nunique()],
    })

    # df2 — Race/Ethnicity
    df2 = (
        df_stu.groupby("race_description", as_index=False)["pidm"]
        .nunique()
        .rename(columns={"pidm": "headcount"})
    )
    df2["pct"] = (df2["headcount"] * 100.0 / df2["headcount"].sum()).round(2)
    df2.insert(0, "academic_year", acyr)
    df2 = df2.sort_values("headcount", ascending=False)

    # df3 — Gender
    df3 = (
        df_stu.groupby("gender", as_index=False)["pidm"]
        .nunique()
        .rename(columns={"pidm": "headcount"})
    )
    df3["pct"] = (df3["headcount"] * 100.0 / df3["headcount"].sum()).round(2)
    df3.insert(0, "academic_year", acyr)
    df3 = df3.sort_values("gender")

    # df4 — Avg. Age by site
    df4 = df_stu.groupby("site", as_index=False).agg(
        avg_age=("age", "mean"),
        headcount=("pidm", "nunique"),
    )
    df4["avg_age"] = df4["avg_age"].round(2)
    df4["pct"] = (df4["headcount"] * 100.0 / df4["headcount"].sum()).round(2)
    df4.insert(0, "academic_year", acyr)
    df4 = df4.sort_values("site")

    # df5 — Student Characteristics (Credit only)
    df_credit = df_stu[df_stu["site"] == "Credit"]
    total_credit = df_credit["pidm"].nunique()
    econ_ct = df_credit[df_credit["econ_disa_ind"] == "Y"]["pidm"].nunique()
    fgen_ct = df_credit[df_credit["first_gen_ind"] == "Y"]["pidm"].nunique()
    df5 = pd.DataFrame({
        "academic_year": [acyr, acyr],
        "characteristic": ["Economically Disadvantaged", "First Generation"],
        "pct": [
            round(econ_ct * 100.0 / total_credit, 2) if total_credit else 0,
            round(fgen_ct * 100.0 / total_credit, 2) if total_credit else 0,
        ],
    })

    # --- Employee tables ---
    df_emp = df_emp[df_emp["ecls_desc"].isin(_ECLS_FILTER)]

    # df6 — Employee Classification
    df6 = (
        df_emp.groupby("ecls_desc", as_index=False)["pidm"]
        .nunique()
        .rename(columns={"pidm": "headcount"})
        .sort_values("ecls_desc")
    )

    # df7 — Employee Gender
    df7 = (
        df_emp.groupby("gender", as_index=False)["pidm"]
        .nunique()
        .rename(columns={"pidm": "headcount"})
    )
    df7["pct"] = (df7["headcount"] * 100.0 / df7["headcount"].sum()).round(2)
    df7 = df7.sort_values("gender")

    # df8 — Employee Age Group
    df8 = (
        df_emp.groupby("agegroup", as_index=False)["pidm"]
        .nunique()
        .rename(columns={"pidm": "headcount"})
    )
    df8["pct"] = (df8["headcount"] * 100.0 / df8["headcount"].sum()).round(2)
    df8 = df8.sort_values("agegroup")

    # df9 — Employee Race/Ethnicity
    df_emp["race_description"] = df_emp["ipeds_ethn"].map(_ETHN_MAP).fillna("Unreported")
    df9 = (
        df_emp.groupby("race_description", as_index=False)["pidm"]
        .nunique()
        .rename(columns={"pidm": "headcount"})
    )
    df9["pct"] = (df9["headcount"] * 100.0 / df9["headcount"].sum()).round(2)
    df9 = df9.sort_values("pct", ascending=False)

    return [
        (df1, f"{acyr} Headcount (Unduplicated)"),
        (df2, f"{acyr} Race/Ethnicity"),
        (df3, f"{acyr} Gender"),
        (df4, f"{acyr} Avg. Age"),
        (df5, f"{acyr} Student Characteristics"),
        (df6, f"{fy_label} Employee Classification"),
        (df7, f"{fy_label} Employee Gender"),
        (df8, f"{fy_label} Employee Age Group"),
        (df9, f"{fy_label} Employee Race/Ethnicity"),
    ]


_PDF_FOOTER_LEFT = "https://nocccd.streamlit.app/"
_PDF_FOOTER_RIGHT = "Author: Jihoon Ahn  jahn@nocccd.edu"


def _add_pdf_footer(fig):
    """Add URL (left) and author (right) footer to a matplotlib figure."""
    fig.text(0.06, 0.02, _PDF_FOOTER_LEFT, fontsize=7, color="grey", ha="left")
    fig.text(0.94, 0.02, _PDF_FOOTER_RIGHT, fontsize=7, color="grey", ha="right")


def _generate_pdf(datasets: list[tuple[pd.DataFrame, str]]) -> bytes:
    """Render all tables into an in-memory PDF and return raw bytes."""
    matplotlib.rcParams.update({
        "figure.facecolor": "white",
        "axes.facecolor": "white",
        "text.color": "black",
        "axes.labelcolor": "black",
        "savefig.facecolor": "white",
    })

    PAGE_W, PAGE_H = 8.5, 11.0
    MARGIN_TOP = 0.75
    MARGIN_BOT = 0.5
    ROW_H = 0.30
    TITLE_H = 0.45
    GAP = 0.35

    def table_inches(df: pd.DataFrame) -> float:
        return TITLE_H + ROW_H * (len(df) + 1) + GAP

    buf = io.BytesIO()
    with PdfPages(buf) as pdf:
        fig = plt.figure(figsize=(PAGE_W, PAGE_H))
        fig.suptitle("Fast Facts", fontsize=16, fontweight="bold", color="black", y=0.97)
        cursor = PAGE_H - MARGIN_TOP - 0.35

        for df, label in datasets:
            h = table_inches(df)

            if cursor - h < MARGIN_BOT:
                _add_pdf_footer(fig)
                pdf.savefig(fig)
                plt.close(fig)
                fig = plt.figure(figsize=(PAGE_W, PAGE_H))
                cursor = PAGE_H - MARGIN_TOP

            ax = fig.add_axes([0.06, (cursor - h) / PAGE_H, 0.88, h / PAGE_H])
            ax.axis("off")
            ax.set_title(label, fontsize=13, fontweight="bold", loc="center", color="black")

            tbl = ax.table(
                cellText=df.values,
                colLabels=df.columns,
                cellLoc="center",
                loc="upper center",
            )
            tbl.auto_set_font_size(False)
            tbl.set_fontsize(9)
            tbl.auto_set_column_width(list(range(len(df.columns))))
            tbl.scale(1, 1.5)

            for key, cell in tbl.get_celld().items():
                cell.set_facecolor("white")
                cell.set_text_props(color="black")
                cell.set_edgecolor("black")

            for col_idx in range(len(df.columns)):
                cell = tbl[0, col_idx]
                cell.set_facecolor("black")
                cell.set_text_props(color="white")

            cursor -= h

        _add_pdf_footer(fig)
        pdf.savefig(fig)
        plt.close(fig)

    return buf.getvalue()


def render():
    st.header("Fast Facts")

    # --- Sidebar controls ---
    acyr_code = st.sidebar.selectbox(
        "Student - Academic Year",
        options=_DEFAULT_ACYR_CODES,
        index=len(_DEFAULT_ACYR_CODES) - 1,
        key="ff_acyr",
    )
    fisc_year = st.sidebar.selectbox(
        "Employee - Fiscal Year",
        options=_DEFAULT_FISC_YEARS,
        index=len(_DEFAULT_FISC_YEARS) - 1,
        key="ff_fisc",
    )
    query_btn = st.sidebar.button("Query", key="ff_query_btn")

    if query_btn:
        fetch_fast_facts_stu.clear()
        fetch_fast_facts_emp.clear()
        df_stu = fetch_fast_facts_stu((acyr_code,))
        df_emp = fetch_fast_facts_emp((fisc_year,))

        if df_stu.empty:
            st.warning("No student data returned.")
            return
        if df_emp.empty:
            st.warning("No employee data returned.")
            return

        st.session_state["ff_data"] = _process(df_stu, df_emp, fisc_year)

    # --- PDF download in sidebar (only when data is loaded) ---
    if "ff_data" in st.session_state:
        pdf_bytes = _generate_pdf(st.session_state["ff_data"])
        st.sidebar.download_button(
            "Download PDF",
            data=pdf_bytes,
            file_name="fast_facts.pdf",
            mime="application/pdf",
            key="ff_pdf_btn",
        )

    if "ff_data" not in st.session_state:
        st.info("Select Academic Year / Fiscal Year and press **Query** to load data.")
        return

    datasets = st.session_state["ff_data"]

    # --- Student tables ---
    st.subheader("Students")
    for df, title in datasets[:5]:
        st.caption(title)
        st.dataframe(df, hide_index=True, use_container_width=True)

    # --- Employee tables ---
    st.subheader("Employees")
    for df, title in datasets[5:]:
        st.caption(title)
        st.dataframe(df, hide_index=True, use_container_width=True)

