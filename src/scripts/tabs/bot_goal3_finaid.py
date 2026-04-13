import streamlit as st

from src.pipeline.config import DATASETS
from src.scripts.data_provider import (
    fetch_bot_goal1_students,
    fetch_bot_goal3_finaid,
)
from src.scripts.tabs.bot_helpers import render_bot_charts

_CFG = DATASETS["bot_goal3_finaid"]
_DEFAULT_ACYRS = _CFG[_CFG["param_name"]]

_TITLES = {
    "org": "NOCCCD Credit Colleges",
    "headcount_title": "Students Receiving Financial Aid",
    "headcount_caption": (
        "The unduplicated number of students receiving financial aid "
        "(Pell Grant or Board of Governors Grant) at Cypress College and "
        "Fullerton College in the reporting year."
    ),
    "race_title": "Proportion of Students Receiving Financial Aid by Race/Ethnicity",
    "race_caption": (
        "Among all unduplicated students enrolled in Cypress and Fullerton "
        "Colleges in the reporting year, the proportion by race/ethnicity "
        "who received financial aid."
    ),
    "gender_title": "Proportion of Students Receiving Financial Aid by Gender",
    "gender_caption": (
        "Among all unduplicated students enrolled in Cypress and Fullerton "
        "Colleges in the reporting year, the proportion by gender who "
        "received financial aid."
    ),
    "firstgen_title": "Proportion of Students Receiving Financial Aid by First-Generation College Status",
    "firstgen_caption": (
        "Among all unduplicated students enrolled in Cypress and Fullerton "
        "Colleges in the reporting year, the proportion who received "
        "financial aid, by first-generation college status."
    ),
    "firstgen_note": None,
}


def render():
    st.header("BOT Goal 3 - Financial Aid")

    selected_acyrs = st.sidebar.multiselect(
        "Academic Years",
        options=_DEFAULT_ACYRS,
        default=_DEFAULT_ACYRS,
        key="bg3f_acyr_codes",
    )
    query_btn = st.sidebar.button("Query", key="bg3f_query_btn")

    if query_btn:
        if not selected_acyrs:
            st.warning("Select at least one academic year.")
            return
        sorted_acyrs = tuple(sorted(selected_acyrs))
        fetch_bot_goal3_finaid.clear()
        fetch_bot_goal1_students.clear()
        df = fetch_bot_goal3_finaid(sorted_acyrs)
        base = fetch_bot_goal1_students(sorted_acyrs)
        if df.empty:
            st.warning("No data returned for the selected academic years.")
            return
        st.session_state["bg3f_df"] = df
        st.session_state["bg3f_base"] = base

    if "bg3f_df" not in st.session_state:
        st.info("Select Academic Years and press **Query** to load data.")
        return

    render_bot_charts(
        st.session_state["bg3f_df"], _TITLES,
        base_df=st.session_state.get("bg3f_base"),
    )
