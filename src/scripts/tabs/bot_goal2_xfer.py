import pandas as pd
import streamlit as st

from src.pipeline.config import DATASETS
from src.scripts.data_provider import fetch_bot_goal1_students, fetch_bot_goal2_xfer
from src.scripts.tabs.bot_helpers import generate_bot_pdf, render_bot_charts

_CFG = DATASETS["bot_goal2_xfer"]
_DEFAULT_ACYRS = _CFG[_CFG["param_name"]]

_CAMP_DESC_MAP = {"1": "Cypress", "2": "Fullerton", "3": "NOCE"}
_SITE_MAP = {"1": "Credit", "2": "Credit", "3": "Noncredit"}

_TITLES = {
    "tab_title": "BOT Goal 2 - Transfers",
    "org": "NOCCCD Credit Colleges",
    "headcount_title": "Headcount of Students Who Transferred to a Four-year Institution",
    "headcount_caption": (
        "The number of students who completed at least 12 credit units, exited "
        "the community college system, and then enrolled in a four-year "
        "institution in the reporting year."
    ),
    "race_title": "Proportion of Students Who Transferred by Race/Ethnicity",
    "race_caption": (
        "Among all students enrolled in Cypress and Fullerton Colleges in the "
        "year prior to the reporting year, the proportion who completed at "
        "least 12 credit units, exited the community college system, and "
        "enrolled in a four-year institution in the reporting year."
    ),
    "gender_title": "Proportion of Students Who Transferred by Gender",
    "gender_caption": (
        "Among all students enrolled in Cypress and Fullerton Colleges in the "
        "year prior to the reporting year, the proportion who completed at "
        "least 12 credit units, exited the community college system, and "
        "enrolled in a four-year institution in the reporting year."
    ),
    "firstgen_title": "Proportion of Students Who Transferred by First-Generation College Status",
    "firstgen_caption": (
        "Among all students enrolled in Cypress and Fullerton Colleges in the "
        "year prior to the reporting year, the proportion who completed at "
        "least 12 credit units, exited the community college system, and "
        "enrolled in a four-year institution in the reporting year."
    ),
    "race_note": (
        "Note: To maintain confidentiality, groups with fewer than 10 students "
        "are not displayed."
    ),
    "gender_note": (
        "Note: To maintain confidentiality, groups with fewer than 10 students "
        "are not displayed."
    ),
    "firstgen_note": None,
    "source": "CCCCO Supplemental & Success Data for the SCFF files; Banner",
}


def _normalize(df: pd.DataFrame, base_df: pd.DataFrame | None = None) -> pd.DataFrame:
    """Add academic_year, camp_desc, site columns expected by bot_helpers.

    When base_df is provided, academic_year is derived from base_df's
    (acyr_code -> academic_year) mapping so values match exactly for joins.
    """
    out = df.copy()
    out["camp_code"] = out["camp_code"].astype(str)
    out["acyr_code"] = out["acyr_code"].astype(str)

    if base_df is not None and {"acyr_code", "academic_year"}.issubset(base_df.columns):
        base_keys = base_df.copy()
        base_keys["acyr_code"] = base_keys["acyr_code"].astype(str)
        yr_map = (
            base_keys.drop_duplicates("acyr_code")
            .set_index("acyr_code")["academic_year"]
            .to_dict()
        )
        out["academic_year"] = out["acyr_code"].map(yr_map)
    else:
        out["academic_year"] = out["acyr_code"].apply(
            lambda y: f"{y}-{str(int(y) + 1)[-2:]}"
        )

    out["camp_desc"] = out["camp_code"].map(_CAMP_DESC_MAP)
    out["site"] = out["camp_code"].map(_SITE_MAP)
    return out


def render():
    st.header("BOT Goal 2 - Transfers")

    selected_acyrs = st.sidebar.multiselect(
        "Academic Years",
        options=_DEFAULT_ACYRS,
        default=_DEFAULT_ACYRS,
        key="bg2x_acyr_codes",
    )
    query_btn = st.sidebar.button("Query", key="bg2x_query_btn")

    if query_btn:
        if not selected_acyrs:
            st.warning("Select at least one academic year.")
            return
        sorted_acyrs = tuple(sorted(selected_acyrs))
        fetch_bot_goal2_xfer.clear()
        fetch_bot_goal1_students.clear()
        df = fetch_bot_goal2_xfer(sorted_acyrs)
        base = fetch_bot_goal1_students(sorted_acyrs)
        # Credit-only scope: denominator should match (Cypress + Fullerton)
        base = base[base["site"] == "Credit"]
        if df.empty:
            st.warning("No data returned for the selected academic years.")
            return
        st.session_state["bg2x_df"] = _normalize(df, base_df=base)
        st.session_state["bg2x_base"] = base

    if "bg2x_df" in st.session_state:
        pdf_bytes = generate_bot_pdf(
            st.session_state["bg2x_df"], _TITLES,
            base_df=st.session_state.get("bg2x_base"),
        )
        st.sidebar.download_button(
            "Download PDF", data=pdf_bytes,
            file_name="bot_goal2_xfer.pdf", mime="application/pdf",
            key="bg2x_pdf_btn",
        )

    if "bg2x_df" not in st.session_state:
        st.info("Select Academic Years and press **Query** to load data.")
        return

    render_bot_charts(
        st.session_state["bg2x_df"], _TITLES,
        base_df=st.session_state.get("bg2x_base"),
    )
