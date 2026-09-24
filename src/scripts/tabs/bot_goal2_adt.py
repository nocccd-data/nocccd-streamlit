import streamlit as st

from src.pipeline.config import DATASETS
from src.scripts.data_provider import (
    fetch_bot_goal1_students,
    fetch_bot_goal2_adt,
    fetch_bot_target_frame,
)
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

_CFG = DATASETS["bot_goal2_adt"]
_DEFAULT_ACYRS = _CFG[_CFG["param_name"]]
_DATASET = "bot_goal2_adt"


def _targets() -> Targets | None:
    frame = st.session_state.get("bg2t_targets")
    return None if frame is None else Targets.for_dataset(_DATASET, frame)


_TITLES = {
    "tab_title": "BOT Goal 2 - ADT",
    "target_title": "Associate Degrees for Transfer: Progress Toward 2029-30 Target",
    "org": "NOCCCD Credit Colleges",
    "headcount_title": "Headcount of Students who Earned an Associate Degree for Transfer",
    "headcount_caption": (
        "The unduplicated number of students enrolled in Cypress and Fullerton "
        "Colleges who earned an Associate Degree for Transfer in the reporting year."
    ),
    "race_title": "Proportion of Students Who Earned an Associate Degree for Transfer by Race/Ethnicity",
    "race_caption": (
        "Among all students enrolled in Cypress and Fullerton Colleges in the "
        "selected year, the proportion of students who earned an Associate "
        "Degree for Transfer."
    ),
    "gender_title": "Proportion of Students Who Earned an Associate Degree for Transfer by Gender",
    "gender_caption": (
        "Among all students enrolled in Cypress and Fullerton Colleges in the "
        "selected year, the proportion of students who earned an Associate "
        "Degree for Transfer."
    ),
    "firstgen_title": "Proportion of Students Who Earned an Associate Degree for Transfer by First-Generation College Status",
    "firstgen_caption": (
        "Among all students enrolled in Cypress and Fullerton Colleges in the "
        "selected year, the proportion of students who earned an Associate "
        "Degree for Transfer."
    ),
    "race_note": (
        "Note: To maintain confidentiality, groups with fewer than 10 students "
        "are not displayed."
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
        fetch_bot_target_frame.clear()
        df = fetch_bot_goal2_adt(sorted_acyrs)
        base = fetch_bot_goal1_students(sorted_acyrs)
        # Credit-only scope: denominator should match (Cypress + Fullerton)
        base = base[base["site"] == "Credit"]
        if df.empty:
            st.warning("No data returned for the selected academic years.")
            return
        st.session_state["bg2t_df"] = df
        st.session_state["bg2t_base"] = base
        st.session_state["bg2t_targets"] = fetch_bot_target_frame(_DATASET)
        clear_excel_cache("bg2t")
        clear_pdf_cache("bg2t")

    show_ct = False
    if "bg2t_df" in st.session_state:
        # Campus target ticks: the switch sits right above the campus chart
        # (drawn by render_bot_charts); the tab PDF follows its saved state.
        show_ct = _targets() is not None and campus_targets_on("bg2t")
        cache_key = (
            id(st.session_state["bg2t_df"]),
            id(st.session_state.get("bg2t_base")),
            id(st.session_state.get("bg2t_targets")),
        )
        pdf_bytes = cached_pdf_bytes(
            "bg2t",
            (*cache_key, show_ct),
            lambda: generate_bot_pdf(
                st.session_state["bg2t_df"],
                _TITLES,
                base_df=st.session_state.get("bg2t_base"),
                targets=_targets(),
                show_campus_targets=show_ct,
            ),
        )
        st.sidebar.download_button(
            "Download PDF", data=pdf_bytes,
            file_name="bot_goal2_adt.pdf", mime="application/pdf",
            key="bg2t_pdf_btn",
        )
        excel_bytes = cached_excel_bytes(
            "bg2t",
            cache_key,
            lambda: generate_bot_excel(
                st.session_state["bg2t_df"],
                _TITLES,
                base_df=st.session_state.get("bg2t_base"),
                targets=_targets(),
            ),
        )
        st.sidebar.download_button(
            "Download Excel", data=excel_bytes,
            file_name="bot_goal2_adt.xlsx", mime=EXCEL_MIME,
            key="bg2t_excel_btn",
        )

    if "bg2t_df" not in st.session_state:
        st.info("Select Academic Years and press **Query** to load data.")
        return

    render_bot_charts(
        st.session_state["bg2t_df"], _TITLES,
        base_df=st.session_state.get("bg2t_base"),
        targets=_targets(),
        campus_toggle_prefix="bg2t",
    )
