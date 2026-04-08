import streamlit as st

from src.pipeline.config import DATASETS
from src.scripts.data_provider import fetch_bot_goal1_students, fetch_bot_goal2_cert_nc
from src.scripts.tabs.bot_helpers import render_bot_charts

_CFG = DATASETS["bot_goal2_cert_nc"]
_DEFAULT_ACYRS = _CFG[_CFG["param_name"]]

_TITLES = {
    "org": "NOCE",
    "headcount_title": "Noncredit Certificates Awarded",
    "headcount_caption": (
        "The unduplicated number of students awarded noncredit certificates "
        "at North Orange Continuing Education in the reporting year."
    ),
    "race_title": "Proportion of Certificate Recipients by Race/Ethnicity",
    "race_caption": (
        "Among all unduplicated students awarded noncredit certificates at "
        "NOCE in the reporting year, the proportion by race/ethnicity."
    ),
    "gender_title": "Proportion of Certificate Recipients by Gender",
    "gender_caption": (
        "Among all unduplicated students awarded noncredit certificates at "
        "NOCE in the reporting year, the proportion by gender."
    ),
    "firstgen_title": "Proportion of Certificate Recipients by First-Generation College Status",
    "firstgen_caption": (
        "Among all unduplicated students awarded noncredit certificates at "
        "NOCE in the reporting year, the proportion who reported neither "
        "parent/guardian had ever attended college."
    ),
    "firstgen_note": None,
    "include_nocccd": False,
    "credit_only_firstgen": False,
}


def render():
    st.header("BOT Goal 2 - Noncredit Certificates")

    selected_acyrs = st.sidebar.multiselect(
        "Academic Years",
        options=_DEFAULT_ACYRS,
        default=_DEFAULT_ACYRS,
        key="bg2nc_acyr_codes",
    )
    query_btn = st.sidebar.button("Query", key="bg2nc_query_btn")

    if query_btn:
        if not selected_acyrs:
            st.warning("Select at least one academic year.")
            return
        sorted_acyrs = tuple(sorted(selected_acyrs))
        fetch_bot_goal2_cert_nc.clear()
        fetch_bot_goal1_students.clear()
        df = fetch_bot_goal2_cert_nc(sorted_acyrs)
        base = fetch_bot_goal1_students(sorted_acyrs)
        if df.empty:
            st.warning("No data returned for the selected academic years.")
            return
        st.session_state["bg2nc_df"] = df
        st.session_state["bg2nc_base"] = base

    if "bg2nc_df" not in st.session_state:
        st.info("Select Academic Years and press **Query** to load data.")
        return

    render_bot_charts(
        st.session_state["bg2nc_df"], _TITLES,
        base_df=st.session_state.get("bg2nc_base"),
    )
