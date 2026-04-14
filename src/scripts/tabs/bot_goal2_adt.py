import streamlit as st

from src.pipeline.config import DATASETS
from src.scripts.data_provider import fetch_bot_goal1_students, fetch_bot_goal2_adt
from src.scripts.tabs.bot_helpers import generate_bot_pdf, render_bot_charts

_CFG = DATASETS["bot_goal2_adt"]
_DEFAULT_ACYRS = _CFG[_CFG["param_name"]]

_TITLES = {
    "tab_title": "BOT Goal 2 - ADT",
    "org": "NOCCCD Credit Colleges",
    "headcount_title": "Associate Degrees for Transfer Awarded",
    "headcount_caption": (
        "The unduplicated number of students awarded associate degrees "
        "for transfer at Cypress College and Fullerton College in the "
        "reporting year."
    ),
    "race_title": "Proportion of ADT Recipients by Race/Ethnicity",
    "race_caption": (
        "Among all unduplicated students awarded associate degrees for "
        "transfer in NOCCCD in the reporting year, the proportion by "
        "race/ethnicity."
    ),
    "gender_title": "Proportion of ADT Recipients by Gender",
    "gender_caption": (
        "Among all unduplicated students awarded associate degrees for "
        "transfer in NOCCCD in the reporting year, the proportion by gender."
    ),
    "firstgen_title": "Proportion of ADT Recipients by First-Generation College Status",
    "firstgen_caption": (
        "Among all unduplicated students awarded associate degrees for "
        "transfer in Cypress and Fullerton Colleges in the reporting year, "
        "the proportion who reported neither parent/guardian had ever "
        "attended college."
    ),
    "firstgen_note": None,
}


def render():
    st.header("BOT Goal 2 - ADT")

    selected_acyrs = st.sidebar.multiselect(
        "Academic Years",
        options=_DEFAULT_ACYRS,
        default=_DEFAULT_ACYRS,
        key="bg2t_acyr_codes",
    )
    query_btn = st.sidebar.button("Query", key="bg2t_query_btn")

    if query_btn:
        if not selected_acyrs:
            st.warning("Select at least one academic year.")
            return
        sorted_acyrs = tuple(sorted(selected_acyrs))
        fetch_bot_goal2_adt.clear()
        fetch_bot_goal1_students.clear()
        df = fetch_bot_goal2_adt(sorted_acyrs)
        base = fetch_bot_goal1_students(sorted_acyrs)
        # Credit-only scope: denominator should match (Cypress + Fullerton)
        base = base[base["site"] == "Credit"]
        if df.empty:
            st.warning("No data returned for the selected academic years.")
            return
        st.session_state["bg2t_df"] = df
        st.session_state["bg2t_base"] = base

    if "bg2t_df" in st.session_state:
        pdf_bytes = generate_bot_pdf(
            st.session_state["bg2t_df"], _TITLES,
            base_df=st.session_state.get("bg2t_base"),
        )
        st.sidebar.download_button(
            "Download PDF", data=pdf_bytes,
            file_name="bot_goal2_adt.pdf", mime="application/pdf",
            key="bg2t_pdf_btn",
        )

    if "bg2t_df" not in st.session_state:
        st.info("Select Academic Years and press **Query** to load data.")
        return

    render_bot_charts(
        st.session_state["bg2t_df"], _TITLES,
        base_df=st.session_state.get("bg2t_base"),
    )
