"""Dual-mode data access: Oracle (local) or Tableau Cloud (Streamlit Cloud).

Each public fetch_*() function is cached for Streamlit use.  The corresponding
_fetch_*_raw() helper is un-decorated so it can be called from CLI scripts
(e.g. the mail pipeline) without a Streamlit runtime.
"""

import os
import re
import tempfile
from pathlib import Path

import pandas as pd
import streamlit as st

_CONFIG_INI = Path(__file__).resolve().parents[1] / "pipeline" / "libs" / "config.ini"


def _is_cloud() -> bool:
    """Return True when running on Streamlit Cloud (no Oracle access)."""
    if os.environ.get("FORCE_CLOUD", "").lower() in ("1", "true"):
        return True
    return not _CONFIG_INI.exists()


# ---------------------------------------------------------------------------
# Local mode helpers (Oracle)
# ---------------------------------------------------------------------------

def _query_oracle(sql_path: Path, acyrs: tuple[str, ...], db_section: str = "dwhdb") -> pd.DataFrame:
    from src.pipeline.libs.sql import get_engine

    base_sql = sql_path.read_text(encoding="utf-8")
    placeholders = ", ".join(f":t{i}" for i in range(1, len(acyrs) + 1))
    sql = re.sub(r"IN\s*\(:t1.*?\)", f"IN ({placeholders})", base_sql, flags=re.IGNORECASE)
    params = {f"t{i}": t for i, t in enumerate(acyrs, 1)}

    engine = get_engine(section=db_section)
    with engine.connect() as conn:
        return pd.read_sql(sql, conn, params=params)


# ---------------------------------------------------------------------------
# Cloud mode helpers (Tableau Cloud → Hyper)
# ---------------------------------------------------------------------------

def _download_and_read(dataset_name: str, acyr_col: str, acyrs: tuple[str, ...]) -> pd.DataFrame:
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

    # Filter to requested acyrs
    if acyr_col in df.columns:
        df = df[df[acyr_col].astype(str).isin(acyrs)]
    return df


# ---------------------------------------------------------------------------
# SQL directory (all SQL now lives under src/pipeline/sql/)
# ---------------------------------------------------------------------------

_SQL_DIR = Path(__file__).resolve().parents[1] / "pipeline" / "sql"


# ---------------------------------------------------------------------------
# Single-acyr Oracle helper (for SQL with :mis_acyr_id instead of IN(:t1...))
# ---------------------------------------------------------------------------

def _query_oracle_single_acyr(sql_path: Path, acyrs: tuple[str, ...], param_name: str, db_section: str = "dwhdb") -> pd.DataFrame:
    from src.pipeline.libs.sql import get_engine

    base_sql = sql_path.read_text(encoding="utf-8")
    engine = get_engine(section=db_section)
    frames = []
    with engine.connect() as conn:
        for t in acyrs:
            frames.append(pd.read_sql(base_sql, conn, params={param_name: t}))
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


# ---------------------------------------------------------------------------
# Raw (un-decorated) fetch helpers — usable from both Streamlit and CLI
# ---------------------------------------------------------------------------

def _fetch_coi_nhrdist_raw(acyrs: tuple[str, ...]) -> pd.DataFrame:
    if _is_cloud():
        return _download_and_read("coi_nhrdist_val", "mis_term_id", acyrs)
    return _query_oracle(_SQL_DIR / "coi_nhrdist_val.sql", acyrs)


def _fetch_deg_scff_raw(acyrs: tuple[str, ...]) -> pd.DataFrame:
    if _is_cloud():
        return _download_and_read("deg_scff", "mis_acyr_id", acyrs)
    return _query_oracle(_SQL_DIR / "deg_scff.sql", acyrs)


def _fetch_deg_sp_submitted_raw(acyrs: tuple[str, ...]) -> pd.DataFrame:
    if _is_cloud():
        return _download_and_read("deg_sp_submitted", "acyr_id", acyrs)
    return _query_oracle(_SQL_DIR / "deg_sp_submitted.sql", acyrs)


def _fetch_deg_fa_scff_raw(acyrs: tuple[str, ...]) -> pd.DataFrame:
    if _is_cloud():
        return _download_and_read("deg_fa_scff", "mis_acyr_id", acyrs)
    return _query_oracle(_SQL_DIR / "deg_fa_scff.sql", acyrs)


def _fetch_deg_fa_submitted_raw(acyrs: tuple[str, ...]) -> pd.DataFrame:
    if _is_cloud():
        return _download_and_read("deg_fa_submitted", "acyr_id", acyrs)
    return _query_oracle(_SQL_DIR / "deg_fa_submitted.sql", acyrs)


def _fetch_deg_sp_current_raw(acyrs: tuple[str, ...]) -> pd.DataFrame:
    if _is_cloud():
        return _download_and_read("deg_sp_current", "acyr_id", acyrs)
    return _query_oracle_single_acyr(_SQL_DIR / "deg_sp_current.sql", acyrs, "mis_acyr_id", db_section="rept")


def _fetch_fast_facts_stu_raw(acyr_codes: tuple[str, ...]) -> pd.DataFrame:
    if _is_cloud():
        return _download_and_read("fast_facts_stu", "acyr_code", acyr_codes)
    return _query_oracle_single_acyr(
        _SQL_DIR / "fast_facts_stu.sql", acyr_codes, "acyr_code", db_section="rept")


def _fetch_fast_facts_emp_raw(fisc_years: tuple[str, ...]) -> pd.DataFrame:
    if _is_cloud():
        return _download_and_read("fast_facts_emp", "fisc_year", fisc_years)
    return _query_oracle_single_acyr(
        _SQL_DIR / "fast_facts_emp.sql", fisc_years, "fisc_year", db_section="rept")


def _fetch_cte_scff_raw(acyrs: tuple[str, ...]) -> pd.DataFrame:
    if _is_cloud():
        return _download_and_read("cte_scff", "mis_acyr_id", acyrs)
    return _query_oracle(_SQL_DIR / "cte_scff.sql", acyrs)


def _fetch_cte_sx_submitted_raw(acyrs: tuple[str, ...]) -> pd.DataFrame:
    if _is_cloud():
        return _download_and_read("cte_sx_submitted", "mis_acyr_id", acyrs)
    return _query_oracle(_SQL_DIR / "cte_sx_submitted.sql", acyrs)


def _fetch_class_schedule_heatmap_raw(terms: tuple[str, ...]) -> pd.DataFrame:
    if _is_cloud():
        return _download_and_read("class_schedule_heatmap", "mis_term_id", terms)
    return _query_oracle(_SQL_DIR / "class_schedule_heatmap.sql", terms)


def _fetch_persistence_by_styp_raw(terms: tuple[str, ...]) -> pd.DataFrame:
    if _is_cloud():
        return _download_and_read("persistence_by_styp", "mis_term_id", terms)
    return _query_oracle(_SQL_DIR / "persistence_by_styp.sql", terms)


def _fetch_seat_count_report_raw(term_codes: tuple[str, ...]) -> pd.DataFrame:
    if _is_cloud():
        return _download_and_read("seat_count_report", "term_code", term_codes)
    return _query_oracle_single_acyr(
        _SQL_DIR / "seat_count_report.sql", term_codes, "banner_term_code", db_section="dwhdb")


# ---------------------------------------------------------------------------
# Public fetch functions (Streamlit-cached wrappers)
# ---------------------------------------------------------------------------

@st.cache_data(ttl=600, show_spinner="Loading data...")
def fetch_coi_nhrdist(acyrs: tuple[str, ...]) -> pd.DataFrame:
    return _fetch_coi_nhrdist_raw(acyrs)


@st.cache_data(ttl=600, show_spinner="Loading data...")
def fetch_deg_scff(acyrs: tuple[str, ...]) -> pd.DataFrame:
    return _fetch_deg_scff_raw(acyrs)


@st.cache_data(ttl=600, show_spinner="Loading data...")
def fetch_deg_sp_submitted(acyrs: tuple[str, ...]) -> pd.DataFrame:
    return _fetch_deg_sp_submitted_raw(acyrs)


@st.cache_data(ttl=600, show_spinner="Loading data...")
def fetch_deg_fa_scff(acyrs: tuple[str, ...]) -> pd.DataFrame:
    return _fetch_deg_fa_scff_raw(acyrs)


@st.cache_data(ttl=600, show_spinner="Loading data...")
def fetch_deg_fa_submitted(acyrs: tuple[str, ...]) -> pd.DataFrame:
    return _fetch_deg_fa_submitted_raw(acyrs)


@st.cache_data(ttl=600, show_spinner="Loading data...")
def fetch_deg_sp_current(acyrs: tuple[str, ...]) -> pd.DataFrame:
    return _fetch_deg_sp_current_raw(acyrs)


@st.cache_data(ttl=600, show_spinner="Loading data...")
def fetch_fast_facts_stu(acyr_codes: tuple[str, ...]) -> pd.DataFrame:
    return _fetch_fast_facts_stu_raw(acyr_codes)


@st.cache_data(ttl=600, show_spinner="Loading data...")
def fetch_fast_facts_emp(fisc_years: tuple[str, ...]) -> pd.DataFrame:
    return _fetch_fast_facts_emp_raw(fisc_years)


@st.cache_data(ttl=600, show_spinner="Loading data...")
def fetch_cte_scff(acyrs: tuple[str, ...]) -> pd.DataFrame:
    return _fetch_cte_scff_raw(acyrs)


@st.cache_data(ttl=600, show_spinner="Loading data...")
def fetch_cte_sx_submitted(acyrs: tuple[str, ...]) -> pd.DataFrame:
    return _fetch_cte_sx_submitted_raw(acyrs)


@st.cache_data(ttl=600, show_spinner="Loading data...")
def fetch_class_schedule_heatmap(terms: tuple[str, ...]) -> pd.DataFrame:
    return _fetch_class_schedule_heatmap_raw(terms)


@st.cache_data(ttl=600, show_spinner="Loading data...")
def fetch_persistence_by_styp(terms: tuple[str, ...]) -> pd.DataFrame:
    return _fetch_persistence_by_styp_raw(terms)


@st.cache_data(ttl=600, show_spinner="Loading data...")
def fetch_seat_count_report(term_codes: tuple[str, ...]) -> pd.DataFrame:
    return _fetch_seat_count_report_raw(term_codes)


def _fetch_bot_goal1_students_raw(acyr_codes: tuple[str, ...]) -> pd.DataFrame:
    if _is_cloud():
        return _download_and_read("bot_goal1_students", "acyr_code", acyr_codes)
    return _query_oracle_single_acyr(
        _SQL_DIR / "bot_goal1_students.sql", acyr_codes, "acyr_code",
        db_section="rept")


@st.cache_data(ttl=600, show_spinner="Loading data...")
def fetch_bot_goal1_students(acyr_codes: tuple[str, ...]) -> pd.DataFrame:
    return _fetch_bot_goal1_students_raw(acyr_codes)


def _fetch_bot_goal2_cert_raw(acyr_codes: tuple[str, ...]) -> pd.DataFrame:
    if _is_cloud():
        return _download_and_read("bot_goal2_cert", "acyr_code", acyr_codes)
    return _query_oracle_single_acyr(
        _SQL_DIR / "bot_goal2_cert.sql", acyr_codes, "acyr_code",
        db_section="rept")


@st.cache_data(ttl=600, show_spinner="Loading data...")
def fetch_bot_goal2_cert(acyr_codes: tuple[str, ...]) -> pd.DataFrame:
    return _fetch_bot_goal2_cert_raw(acyr_codes)


def _fetch_bot_goal2_cert_nc_raw(acyr_codes: tuple[str, ...]) -> pd.DataFrame:
    if _is_cloud():
        return _download_and_read("bot_goal2_cert_nc", "acyr_code", acyr_codes)
    return _query_oracle_single_acyr(
        _SQL_DIR / "bot_goal2_cert_nc.sql", acyr_codes, "acyr_code",
        db_section="rept")


@st.cache_data(ttl=600, show_spinner="Loading data...")
def fetch_bot_goal2_cert_nc(acyr_codes: tuple[str, ...]) -> pd.DataFrame:
    return _fetch_bot_goal2_cert_nc_raw(acyr_codes)
