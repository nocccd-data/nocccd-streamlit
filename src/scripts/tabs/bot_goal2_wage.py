import streamlit as st

from src.pipeline.config import DATASETS
from src.scripts.data_provider import fetch_bot_goal1_students, fetch_bot_goal2_wage
from src.scripts.tabs.bot_helpers import render_bot_charts

_CFG = DATASETS["bot_goal2_wage"]
_DEFAULT_ACYRS = _CFG[_CFG["param_name"]]

_TITLES = {
    "org": "NOCCCD",
    "headcount_title": "Students with Living Wage Employment",
    "headcount_caption": (
        "The unduplicated number of students from Cypress College, "
        "Fullerton College, and North Orange Continuing Education who "
        "achieved a living wage in the reporting year."
    ),
    "race_title": "Proportion of Students Earning a Living Wage by Race/Ethnicity",
    "race_caption": (
        "Among all unduplicated students enrolled in NOCCCD in the reporting "
        "year, the proportion by race/ethnicity who achieved a living wage."
    ),
    "gender_title": "Proportion of Students Earning a Living Wage by Gender",
    "gender_caption": (
        "Among all unduplicated students enrolled in NOCCCD in the reporting "
        "year, the proportion by gender who achieved a living wage."
    ),
    "firstgen_org": "NOCCCD Credit Colleges",
    "firstgen_title": "Proportion of Students Earning a Living Wage by First-Generation College Status",
    "firstgen_caption": (
        "Among all unduplicated students enrolled in Cypress and Fullerton "
        "Colleges in the reporting year, the proportion who achieved a "
        "living wage, by first-generation college status."
    ),
    "firstgen_note": (
        "Note: NOCE data are excluded from the first-generation chart due "
        "to the large number of unknown cases."
    ),
}


def render():
    st.header("BOT Goal 2 - Living Wage")

    selected_acyrs = st.sidebar.multiselect(
        "Academic Years",
        options=_DEFAULT_ACYRS,
        default=_DEFAULT_ACYRS,
        key="bg2w_acyr_codes",
    )
    query_btn = st.sidebar.button("Query", key="bg2w_query_btn")

    if query_btn:
        if not selected_acyrs:
            st.warning("Select at least one academic year.")
            return
        sorted_acyrs = tuple(sorted(selected_acyrs))
        fetch_bot_goal2_wage.clear()
        fetch_bot_goal1_students.clear()
        df = fetch_bot_goal2_wage(sorted_acyrs)
        base = fetch_bot_goal1_students(sorted_acyrs)
        if df.empty:
            st.warning("No data returned for the selected academic years.")
            return
        st.session_state["bg2w_df"] = df
        st.session_state["bg2w_base"] = base

    if "bg2w_df" not in st.session_state:
        st.info("Select Academic Years and press **Query** to load data.")
        return

    render_bot_charts(
        st.session_state["bg2w_df"], _TITLES,
        base_df=st.session_state.get("bg2w_base"),
    )
