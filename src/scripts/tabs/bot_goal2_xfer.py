import pandas as pd
import streamlit as st

from src.pipeline.config import DATASETS
from src.scripts.data_provider import fetch_bot_goal1_students, fetch_bot_goal2_xfer
from src.scripts.tabs.bot_helpers import render_bot_charts

_CFG = DATASETS["bot_goal2_xfer"]
_DEFAULT_ACYRS = _CFG[_CFG["param_name"]]

_CAMP_DESC_MAP = {"1": "Cypress", "2": "Fullerton", "3": "NOCE"}
_SITE_MAP = {"1": "Credit", "2": "Credit", "3": "Noncredit"}

_TITLES = {
    "org": "NOCCCD Credit Colleges",
    "headcount_title": "Transfers to 4-Year Institutions",
    "headcount_caption": (
        "The unduplicated number of students from Cypress College and "
        "Fullerton College who transferred to 4-year institutions in "
        "the reporting year."
    ),
    "race_title": "Proportion of Transfers by Race/Ethnicity",
    "race_caption": (
        "Among all unduplicated students from NOCCCD who transferred to "
        "4-year institutions in the reporting year, the proportion by "
        "race/ethnicity."
    ),
    "gender_title": "Proportion of Transfers by Gender",
    "gender_caption": (
        "Among all unduplicated students from NOCCCD who transferred to "
        "4-year institutions in the reporting year, the proportion by gender."
    ),
    "firstgen_title": "Proportion of Transfers by First-Generation College Status",
    "firstgen_caption": (
        "Among all unduplicated students from Cypress and Fullerton "
        "Colleges who transferred to 4-year institutions in the reporting "
        "year, the proportion who reported neither parent/guardian had "
        "ever attended college."
    ),
    "firstgen_note": None,
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
        if df.empty:
            st.warning("No data returned for the selected academic years.")
            return
        st.session_state["bg2x_df"] = _normalize(df, base_df=base)
        st.session_state["bg2x_base"] = base

    if "bg2x_df" not in st.session_state:
        st.info("Select Academic Years and press **Query** to load data.")
        return

    render_bot_charts(
        st.session_state["bg2x_df"], _TITLES,
        base_df=st.session_state.get("bg2x_base"),
    )
