import streamlit as st

from src.pipeline.config import DATASETS
from src.scripts.data_provider import fetch_bot_goal2_bac
from src.scripts.tabs.bot_helpers import render_bot_charts

_CFG = DATASETS["bot_goal2_bac"]
_DEFAULT_ACYRS = _CFG[_CFG["param_name"]]

_TITLES = {
    "org": "NOCCCD Credit Colleges",
    "headcount_title": "Bachelor's Degrees Awarded",
    "headcount_caption": (
        "The unduplicated number of students awarded bachelor's degrees "
        "at Cypress College and Fullerton College in the reporting year."
    ),
    "race_title": "Proportion of Bachelor's Degree Recipients by Race/Ethnicity",
    "race_caption": (
        "Among all unduplicated students awarded bachelor's degrees in "
        "NOCCCD in the reporting year, the proportion by race/ethnicity."
    ),
    "gender_title": "Proportion of Bachelor's Degree Recipients by Gender",
    "gender_caption": (
        "Among all unduplicated students awarded bachelor's degrees in "
        "NOCCCD in the reporting year, the proportion by gender."
    ),
    "firstgen_title": "Proportion of Bachelor's Degree Recipients by First-Generation College Status",
    "firstgen_caption": (
        "Among all unduplicated students awarded bachelor's degrees in "
        "Cypress and Fullerton Colleges in the reporting year, the proportion "
        "who reported neither parent/guardian had ever attended college."
    ),
    "firstgen_note": None,
    "include_nocccd": False,
    "headcount_only": True,
}


def render():
    st.header("BOT Goal 2 - Bachelor's Degrees")

    selected_acyrs = st.sidebar.multiselect(
        "Academic Years",
        options=_DEFAULT_ACYRS,
        default=_DEFAULT_ACYRS,
        key="bg2b_acyr_codes",
    )
    query_btn = st.sidebar.button("Query", key="bg2b_query_btn")

    if query_btn:
        if not selected_acyrs:
            st.warning("Select at least one academic year.")
            return
        fetch_bot_goal2_bac.clear()
        df = fetch_bot_goal2_bac(tuple(sorted(selected_acyrs)))
        if df.empty:
            st.warning("No data returned for the selected academic years.")
            return
        st.session_state["bg2b_df"] = df

    if "bg2b_df" not in st.session_state:
        st.info("Select Academic Years and press **Query** to load data.")
        return

    render_bot_charts(st.session_state["bg2b_df"], _TITLES)
