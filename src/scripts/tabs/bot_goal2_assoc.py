import streamlit as st

from src.pipeline.config import DATASETS
from src.scripts.data_provider import fetch_bot_goal1_students, fetch_bot_goal2_assoc
from src.scripts.tabs.bot_helpers import generate_bot_pdf, render_bot_charts

_CFG = DATASETS["bot_goal2_assoc"]
_DEFAULT_ACYRS = _CFG[_CFG["param_name"]]

_TITLES = {
    "tab_title": "BOT Goal 2 - Associate Degrees",
    "org": "NOCCCD Credit Colleges",
    "headcount_title": "Associate Degrees Awarded",
    "headcount_caption": (
        "The unduplicated number of students awarded associate degrees "
        "at Cypress College and Fullerton College in the reporting year."
    ),
    "race_title": "Proportion of Associate Degree Recipients by Race/Ethnicity",
    "race_caption": (
        "Among all unduplicated students awarded associate degrees in "
        "NOCCCD in the reporting year, the proportion by race/ethnicity."
    ),
    "gender_title": "Proportion of Associate Degree Recipients by Gender",
    "gender_caption": (
        "Among all unduplicated students awarded associate degrees in "
        "NOCCCD in the reporting year, the proportion by gender."
    ),
    "firstgen_title": "Proportion of Associate Degree Recipients by First-Generation College Status",
    "firstgen_caption": (
        "Among all unduplicated students awarded associate degrees in "
        "Cypress and Fullerton Colleges in the reporting year, the proportion "
        "who reported neither parent/guardian had ever attended college."
    ),
    "firstgen_note": None,
}


def render():
    st.header("BOT Goal 2 - Associate Degrees")

    selected_acyrs = st.sidebar.multiselect(
        "Academic Years",
        options=_DEFAULT_ACYRS,
        default=_DEFAULT_ACYRS,
        key="bg2a_acyr_codes",
    )
    query_btn = st.sidebar.button("Query", key="bg2a_query_btn")

    if query_btn:
        if not selected_acyrs:
            st.warning("Select at least one academic year.")
            return
        sorted_acyrs = tuple(sorted(selected_acyrs))
        fetch_bot_goal2_assoc.clear()
        fetch_bot_goal1_students.clear()
        df = fetch_bot_goal2_assoc(sorted_acyrs)
        base = fetch_bot_goal1_students(sorted_acyrs)
        # Credit-only scope: denominator should match (Cypress + Fullerton)
        base = base[base["site"] == "Credit"]
        if df.empty:
            st.warning("No data returned for the selected academic years.")
            return
        st.session_state["bg2a_df"] = df
        st.session_state["bg2a_base"] = base

    if "bg2a_df" in st.session_state:
        pdf_bytes = generate_bot_pdf(
            st.session_state["bg2a_df"], _TITLES,
            base_df=st.session_state.get("bg2a_base"),
        )
        st.sidebar.download_button(
            "Download PDF", data=pdf_bytes,
            file_name="bot_goal2_assoc.pdf", mime="application/pdf",
            key="bg2a_pdf_btn",
        )

    if "bg2a_df" not in st.session_state:
        st.info("Select Academic Years and press **Query** to load data.")
        return

    render_bot_charts(
        st.session_state["bg2a_df"], _TITLES,
        base_df=st.session_state.get("bg2a_base"),
    )
