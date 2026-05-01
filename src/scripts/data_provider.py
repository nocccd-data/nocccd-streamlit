"""Cloud-only data access: reads pre-extracted Hyper files from Tableau Cloud.

Each public ``fetch_*()`` function downloads the dataset's Hyper extract from
Tableau Cloud (published by ``src.pipeline.run``) and returns a Pandas
DataFrame filtered to the requested year/term values.  Results are cached via
``@st.cache_data`` for the lifetime of the Streamlit session.

Oracle access lives only in the pipeline (``src.pipeline.extract``); the app
never queries Oracle directly.
"""

import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st


def _download_and_read(dataset_name: str, filter_col: str, values: tuple[str, ...]) -> pd.DataFrame:
    """Download a dataset's Hyper from Tableau Cloud and filter to ``values``."""
    import pantab
    from src.pipeline.publish import download_hyper

    secrets = st.secrets
    with tempfile.TemporaryDirectory() as tmp:
        hyper_path = download_hyper(
            dataset_name,
            Path(tmp),
            server_url=secrets["SERVER"],
            site_name=secrets["SITE_NAME"],
            pat_name=secrets["PAT_NAME"],
            pat_value=secrets["PAT_VALUE"],
        )
        df = pantab.frame_from_hyper(hyper_path, table="Extract")

    if filter_col not in df.columns:
        available = ", ".join(map(str, df.columns))
        raise KeyError(
            f"Expected filter column {filter_col!r} in {dataset_name!r} Hyper extract. "
            f"Available columns: {available}"
        )
    return df[df[filter_col].astype(str).isin(values)]


# ---------------------------------------------------------------------------
# Public fetch functions — Streamlit-cached, one per dataset
# ---------------------------------------------------------------------------

@st.cache_data(ttl=600, show_spinner="Loading data...")
def fetch_coi_nhrdist(acyrs: tuple[str, ...]) -> pd.DataFrame:
    return _download_and_read("coi_nhrdist_val", "mis_term_id", acyrs)


@st.cache_data(ttl=600, show_spinner="Loading data...")
def fetch_deg_scff(acyrs: tuple[str, ...]) -> pd.DataFrame:
    return _download_and_read("deg_scff", "mis_acyr_id", acyrs)


@st.cache_data(ttl=600, show_spinner="Loading data...")
def fetch_deg_sp_submitted(acyrs: tuple[str, ...]) -> pd.DataFrame:
    return _download_and_read("deg_sp_submitted", "acyr_id", acyrs)


@st.cache_data(ttl=600, show_spinner="Loading data...")
def fetch_deg_fa_scff(acyrs: tuple[str, ...]) -> pd.DataFrame:
    return _download_and_read("deg_fa_scff", "mis_acyr_id", acyrs)


@st.cache_data(ttl=600, show_spinner="Loading data...")
def fetch_deg_fa_submitted(acyrs: tuple[str, ...]) -> pd.DataFrame:
    return _download_and_read("deg_fa_submitted", "acyr_id", acyrs)


@st.cache_data(ttl=600, show_spinner="Loading data...")
def fetch_deg_sp_current(acyrs: tuple[str, ...]) -> pd.DataFrame:
    return _download_and_read("deg_sp_current", "acyr_id", acyrs)


@st.cache_data(ttl=600, show_spinner="Loading data...")
def fetch_fast_facts_stu(acyr_codes: tuple[str, ...]) -> pd.DataFrame:
    return _download_and_read("fast_facts_stu", "acyr_code", acyr_codes)


@st.cache_data(ttl=600, show_spinner="Loading data...")
def fetch_fast_facts_emp(fisc_years: tuple[str, ...]) -> pd.DataFrame:
    return _download_and_read("fast_facts_emp", "fisc_year", fisc_years)


@st.cache_data(ttl=600, show_spinner="Loading data...")
def fetch_cte_scff(acyrs: tuple[str, ...]) -> pd.DataFrame:
    return _download_and_read("cte_scff", "mis_acyr_id", acyrs)


@st.cache_data(ttl=600, show_spinner="Loading data...")
def fetch_cte_sx_submitted(acyrs: tuple[str, ...]) -> pd.DataFrame:
    return _download_and_read("cte_sx_submitted", "mis_acyr_id", acyrs)


@st.cache_data(ttl=600, show_spinner="Loading data...")
def fetch_class_schedule_heatmap(terms: tuple[str, ...]) -> pd.DataFrame:
    return _download_and_read("class_schedule_heatmap", "mis_term_id", terms)


@st.cache_data(ttl=600, show_spinner="Loading data...")
def fetch_persistence_by_styp(terms: tuple[str, ...]) -> pd.DataFrame:
    return _download_and_read("persistence_by_styp", "mis_term_id", terms)


@st.cache_data(ttl=600, show_spinner="Loading data...")
def fetch_seat_count_report(term_codes: tuple[str, ...]) -> pd.DataFrame:
    return _download_and_read("seat_count_report", "term_code", term_codes)


@st.cache_data(ttl=600, show_spinner="Loading data...")
def fetch_bot_goal1_students(acyr_codes: tuple[str, ...]) -> pd.DataFrame:
    return _download_and_read("bot_goal1_students", "acyr_code", acyr_codes)


@st.cache_data(ttl=600, show_spinner="Loading data...")
def fetch_bot_goal2_cert(acyr_codes: tuple[str, ...]) -> pd.DataFrame:
    return _download_and_read("bot_goal2_cert", "acyr_code", acyr_codes)


@st.cache_data(ttl=600, show_spinner="Loading data...")
def fetch_bot_goal2_cert_nc(acyr_codes: tuple[str, ...]) -> pd.DataFrame:
    return _download_and_read("bot_goal2_cert_nc", "acyr_code", acyr_codes)


@st.cache_data(ttl=600, show_spinner="Loading data...")
def fetch_bot_goal2_cert_nc_denom(acyr_codes: tuple[str, ...]) -> pd.DataFrame:
    return _download_and_read("bot_goal2_cert_nc_denom", "acyr_code", acyr_codes)


@st.cache_data(ttl=600, show_spinner="Loading data...")
def fetch_bot_goal2_assoc(acyr_codes: tuple[str, ...]) -> pd.DataFrame:
    return _download_and_read("bot_goal2_assoc", "acyr_code", acyr_codes)


@st.cache_data(ttl=600, show_spinner="Loading data...")
def fetch_bot_goal2_adt(acyr_codes: tuple[str, ...]) -> pd.DataFrame:
    return _download_and_read("bot_goal2_adt", "acyr_code", acyr_codes)


@st.cache_data(ttl=600, show_spinner="Loading data...")
def fetch_bot_goal2_bac(acyr_codes: tuple[str, ...]) -> pd.DataFrame:
    return _download_and_read("bot_goal2_bac", "acyr_code", acyr_codes)


@st.cache_data(ttl=600, show_spinner="Loading data...")
def fetch_bot_goal2_xfer(acyr_codes: tuple[str, ...]) -> pd.DataFrame:
    return _download_and_read("bot_goal2_xfer", "acyr_code", acyr_codes)


@st.cache_data(ttl=600, show_spinner="Loading data...")
def fetch_bot_goal2_wage(acyr_codes: tuple[str, ...]) -> pd.DataFrame:
    return _download_and_read("bot_goal2_wage", "acyr_code", acyr_codes)


@st.cache_data(ttl=600, show_spinner="Loading data...")
def fetch_bot_goal2_wage_denom(acyr_codes: tuple[str, ...]) -> pd.DataFrame:
    return _download_and_read("bot_goal2_wage_denom", "acyr_code", acyr_codes)


@st.cache_data(ttl=600, show_spinner="Loading data...")
def fetch_bot_goal3_finaid(acyr_codes: tuple[str, ...]) -> pd.DataFrame:
    return _download_and_read("bot_goal3_finaid", "acyr_code", acyr_codes)


@st.cache_data(ttl=600, show_spinner="Loading data...")
def fetch_bot_goal3_units(acyr_codes: tuple[str, ...]) -> pd.DataFrame:
    return _download_and_read("bot_goal3_units", "acyr_code", acyr_codes)
