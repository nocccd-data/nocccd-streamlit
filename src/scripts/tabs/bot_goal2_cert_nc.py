import streamlit as st

from src.pipeline.config import DATASETS
from src.scripts.data_provider import (
    fetch_bot_goal2_cert_nc,
    fetch_bot_goal2_cert_nc_denom,
)
from src.scripts.tabs.bot_helpers import generate_bot_pdf, render_bot_charts

_CFG = DATASETS["bot_goal2_cert_nc"]
_DEFAULT_ACYRS = _CFG[_CFG["param_name"]]

_TITLES = {
    "tab_title": "BOT Goal 2 - Noncredit Certificates",
    "org": "NOCE",
    "headcount_title": "Noncredit Certificates Awarded",
    "headcount_caption": (
        "The unduplicated number of students awarded noncredit certificates "
        "at North Orange Continuing Education in the reporting year."
    ),
    "race_title": "Proportion of Certificate Recipients by Race/Ethnicity",
    "race_caption": (
        "Among all NOCE students who enrolled in Basic Skills, CTE, or ESL "
        "courses in the selected year, the proportion who received a "
        "noncredit certificate in the reporting year."
    ),
    "gender_title": "Proportion of Certificate Recipients by Gender",
    "gender_caption": (
        "Among all NOCE students who enrolled in Basic Skills, CTE, or ESL "
        "courses in the selected year, the proportion who received a "
        "noncredit certificate in the reporting year."
    ),
    "firstgen_title": "Proportion of Certificate Recipients by First-Generation College Status",
    "firstgen_caption": (
        "Among all NOCE students who enrolled in Basic Skills, CTE, or ESL "
        "courses in the selected year, the proportion who received a "
        "noncredit certificate in the reporting year."
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
        fetch_bot_goal2_cert_nc_denom.clear()
        df = fetch_bot_goal2_cert_nc(sorted_acyrs)
        base = fetch_bot_goal2_cert_nc_denom(sorted_acyrs)
        if df.empty:
            st.warning("No data returned for the selected academic years.")
            return
        st.session_state["bg2nc_df"] = df
        st.session_state["bg2nc_base"] = base

    if "bg2nc_df" in st.session_state:
        pdf_bytes = generate_bot_pdf(
            st.session_state["bg2nc_df"], _TITLES,
            base_df=st.session_state.get("bg2nc_base"),
        )
        st.sidebar.download_button(
            "Download PDF", data=pdf_bytes,
            file_name="bot_goal2_cert_nc.pdf", mime="application/pdf",
            key="bg2nc_pdf_btn",
        )

    if "bg2nc_df" not in st.session_state:
        st.info("Select Academic Years and press **Query** to load data.")
        return

    render_bot_charts(
        st.session_state["bg2nc_df"], _TITLES,
        base_df=st.session_state.get("bg2nc_base"),
    )
