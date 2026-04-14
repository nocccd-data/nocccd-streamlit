import streamlit as st

from src.pipeline.config import DATASETS
from src.scripts.data_provider import fetch_bot_goal1_students
from src.scripts.tabs.bot_helpers import generate_bot_pdf, render_bot_charts

_CFG = DATASETS["bot_goal1_students"]
_DEFAULT_ACYRS = _CFG[_CFG["param_name"]]

_TITLES = {
    "tab_title": "BOT Goal 1 - Students",
    "org": "NOCCCD",
    "headcount_title": "Headcount of Students",
    "headcount_caption": (
        "The unduplicated number of students enrolled as of census in "
        "Cypress College, Fullerton College, and North Orange Continuing "
        "Education in the reporting year."
    ),
    "race_title": "Proportion of Enrolled Students by Race/Ethnicity",
    "race_caption": (
        "Among all unduplicated students enrolled as of census in NOCCCD "
        "in the reporting year, the proportion of students by race/ethnicity."
    ),
    "gender_title": "Proportion of Enrolled Students by Gender",
    "gender_caption": (
        "Among all unduplicated students enrolled as of census in NOCCCD "
        "in the reporting year, the proportion of students by gender."
    ),
    "firstgen_org": "NOCCCD Credit Colleges",
    "firstgen_title": "Proportion of Enrolled Students by First-Generation College Status",
    "firstgen_caption": (
        "Among all unduplicated students enrolled in Cypress and Fullerton "
        "Colleges as of census in the reporting year, the proportion of "
        "students who reported neither parent/guardian had ever attended college."
    ),
    "firstgen_note": (
        "Note: NOCE data are excluded due to the large number of unknown "
        "cases. Because these data are collected through an online survey "
        "and many NOCE students register in person/on paper, their "
        "information are not collected."
    ),
}


def render():
    st.header("BOT Goal 1 - Students")

    selected_acyrs = st.sidebar.multiselect(
        "Academic Years",
        options=_DEFAULT_ACYRS,
        default=_DEFAULT_ACYRS,
        key="bg1_acyr_codes",
    )
    query_btn = st.sidebar.button("Query", key="bg1_query_btn")

    if query_btn:
        if not selected_acyrs:
            st.warning("Select at least one academic year.")
            return
        fetch_bot_goal1_students.clear()
        df = fetch_bot_goal1_students(tuple(sorted(selected_acyrs)))
        if df.empty:
            st.warning("No data returned for the selected academic years.")
            return
        st.session_state["bg1_df"] = df

    if "bg1_df" in st.session_state:
        pdf_bytes = generate_bot_pdf(st.session_state["bg1_df"], _TITLES)
        st.sidebar.download_button(
            "Download PDF", data=pdf_bytes,
            file_name="bot_goal1_students.pdf", mime="application/pdf",
            key="bg1_pdf_btn",
        )

    if "bg1_df" not in st.session_state:
        st.info("Select Academic Years and press **Query** to load data.")
        return

    render_bot_charts(st.session_state["bg1_df"], _TITLES)
