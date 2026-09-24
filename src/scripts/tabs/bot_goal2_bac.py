import streamlit as st

from src.pipeline.config import DATASETS
from src.scripts.data_provider import fetch_bot_goal2_bac, fetch_bot_target_frame
from src.scripts.pdf_cache import (
    cached_excel_bytes,
    cached_pdf_bytes,
    clear_excel_cache,
    clear_pdf_cache,
)
from src.scripts.tabs.bot_excel_helpers import EXCEL_MIME, generate_bot_excel
from src.scripts.tabs.bot_helpers import (
    campus_targets_on,
    generate_bot_pdf,
    render_bot_charts,
)
from src.scripts.tabs.bot_targets import Targets

_CFG = DATASETS["bot_goal2_bac"]
_DEFAULT_ACYRS = _CFG[_CFG["param_name"]]
_DATASET = "bot_goal2_bac"


def _targets() -> Targets | None:
    frame = st.session_state.get("bg2b_targets")
    return None if frame is None else Targets.for_dataset(_DATASET, frame)


_TITLES = {
    "tab_title": "BOT Goal 2 - Bachelor's Degrees",
    "target_title": "Baccalaureate Degrees: Progress Toward 2029-30 Target",
    "org": "NOCCCD Credit Colleges",
    "headcount_title": "Headcount of Students who Earned a Baccalaureate Degree",
    "headcount_caption": (
        "The number of students enrolled in Cypress College who earned a "
        "baccalaureate degree in the reporting year."
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
        fetch_bot_target_frame.clear()
        df = fetch_bot_goal2_bac(tuple(sorted(selected_acyrs)))
        if df.empty:
            st.warning("No data returned for the selected academic years.")
            return
        st.session_state["bg2b_df"] = df
        st.session_state["bg2b_targets"] = fetch_bot_target_frame(_DATASET)
        clear_excel_cache("bg2b")
        clear_pdf_cache("bg2b")

    show_ct = False
    if "bg2b_df" in st.session_state:
        # Campus target ticks: the switch sits right above the campus chart
        # (drawn by render_bot_charts); the tab PDF follows its saved state.
        show_ct = _targets() is not None and campus_targets_on("bg2b")
        cache_key = (
            id(st.session_state["bg2b_df"]),
            id(st.session_state.get("bg2b_targets")),
        )
        pdf_bytes = cached_pdf_bytes(
            "bg2b",
            (*cache_key, show_ct),
            lambda: generate_bot_pdf(
                st.session_state["bg2b_df"], _TITLES, targets=_targets(),
                show_campus_targets=show_ct,
            ),
        )
        st.sidebar.download_button(
            "Download PDF", data=pdf_bytes,
            file_name="bot_goal2_bac.pdf", mime="application/pdf",
            key="bg2b_pdf_btn",
        )
        excel_bytes = cached_excel_bytes(
            "bg2b",
            cache_key,
            lambda: generate_bot_excel(
                st.session_state["bg2b_df"], _TITLES, targets=_targets()
            ),
        )
        st.sidebar.download_button(
            "Download Excel", data=excel_bytes,
            file_name="bot_goal2_bac.xlsx", mime=EXCEL_MIME,
            key="bg2b_excel_btn",
        )

    if "bg2b_df" not in st.session_state:
        st.info("Select Academic Years and press **Query** to load data.")
        return

    render_bot_charts(st.session_state["bg2b_df"], _TITLES, targets=_targets(),
                      campus_toggle_prefix="bg2b")
