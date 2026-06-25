import streamlit as st

from src.pipeline.config import DATASETS
from src.scripts.data_provider import (
    fetch_bot_goal1_students,
    fetch_bot_goal4_xfer_ready,
)
from src.scripts.pdf_cache import (
    cached_excel_bytes,
    cached_pdf_bytes,
    clear_excel_cache,
    clear_pdf_cache,
)
from src.scripts.tabs.bot_excel_helpers import EXCEL_MIME, generate_bot_excel
from src.scripts.tabs.bot_helpers import generate_bot_pdf, render_bot_charts

_CFG = DATASETS["bot_goal4_xfer_ready"]
_DEFAULT_ACYRS = _CFG[_CFG["param_name"]]

_TITLES = {
    "tab_title": "BOT Goal 4 - Transfer Ready",
    "org": "NOCCCD Credit Colleges",
    # Transfer readiness is measured district-wide (no campus split), so the
    # headcount chart shows a single Credit-college bar — not Cypress/Fullerton.
    "include_nocccd": False,
    "headcount_title": "Headcount of Students who are Transfer Ready",
    "headcount_caption": (
        "The number of students enrolled in Cypress and Fullerton Colleges "
        "who are transfer ready in the reporting year."
    ),
    "headcount_note": "Note: NOCE data not applicable for this metric.",
    "race_title": "Proportion of Students Who are Transfer Ready by Race/Ethnicity",
    "race_caption": (
        "Among all students enrolled in Cypress and Fullerton Colleges in the "
        "selected year, the proportion of students who are transfer ready."
    ),
    "gender_title": "Proportion of Students Who are Transfer Ready by Gender",
    "gender_caption": (
        "Among all students enrolled in Cypress and Fullerton Colleges in the "
        "selected year, the proportion of students who are transfer ready."
    ),
    "firstgen_title": "Proportion of Students Who are Transfer Ready by First-Generation College Status",
    "firstgen_caption": (
        "Among all students enrolled in Cypress and Fullerton Colleges in the "
        "selected year, the proportion of students who are transfer ready."
    ),
    "race_note": (
        "Note: To maintain confidentiality, groups with fewer than 10 students "
        "are not displayed."
    ),
    "firstgen_note": None,
}


def render():
    st.header("BOT Goal 4 - Transfer Ready")

    selected_acyrs = st.sidebar.multiselect(
        "Academic Years",
        options=_DEFAULT_ACYRS,
        default=_DEFAULT_ACYRS,
        key="bg4_acyr_codes",
    )
    query_btn = st.sidebar.button("Query", key="bg4_query_btn")

    if query_btn:
        if not selected_acyrs:
            st.warning("Select at least one academic year.")
            return
        sorted_acyrs = tuple(sorted(selected_acyrs))
        fetch_bot_goal4_xfer_ready.clear()
        fetch_bot_goal1_students.clear()
        df = fetch_bot_goal4_xfer_ready(sorted_acyrs)
        base = fetch_bot_goal1_students(sorted_acyrs)
        # Credit-only scope: denominator should match (Cypress + Fullerton)
        base = base[base["site"] == "Credit"]
        if df.empty:
            st.warning("No data returned for the selected academic years.")
            return
        st.session_state["bg4_df"] = df
        st.session_state["bg4_base"] = base
        clear_excel_cache("bg4")
        clear_pdf_cache("bg4")

    if "bg4_df" in st.session_state:
        cache_key = (
            id(st.session_state["bg4_df"]),
            id(st.session_state.get("bg4_base")),
        )
        pdf_bytes = cached_pdf_bytes(
            "bg4",
            cache_key,
            lambda: generate_bot_pdf(
                st.session_state["bg4_df"],
                _TITLES,
                base_df=st.session_state.get("bg4_base"),
            ),
        )
        st.sidebar.download_button(
            "Download PDF", data=pdf_bytes,
            file_name="bot_goal4_xfer_ready.pdf", mime="application/pdf",
            key="bg4_pdf_btn",
        )
        excel_bytes = cached_excel_bytes(
            "bg4",
            cache_key,
            lambda: generate_bot_excel(
                st.session_state["bg4_df"],
                _TITLES,
                base_df=st.session_state.get("bg4_base"),
            ),
        )
        st.sidebar.download_button(
            "Download Excel", data=excel_bytes,
            file_name="bot_goal4_xfer_ready.xlsx", mime=EXCEL_MIME,
            key="bg4_excel_btn",
        )

    if "bg4_df" not in st.session_state:
        st.info("Select Academic Years and press **Query** to load data.")
        return

    render_bot_charts(
        st.session_state["bg4_df"], _TITLES,
        base_df=st.session_state.get("bg4_base"),
    )
