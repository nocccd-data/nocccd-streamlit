"""Dual-mode data access: Oracle (local) or Tableau Cloud (Streamlit Cloud)."""

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

def _query_oracle(sql_path: Path, terms: tuple[str, ...], db_section: str = "dwhdb") -> pd.DataFrame:
    from src.pipeline.libs.sql import get_engine

    base_sql = sql_path.read_text(encoding="utf-8")
    placeholders = ", ".join(f":t{i}" for i in range(1, len(terms) + 1))
    sql = re.sub(r"IN\s*\(:t1.*?\)", f"IN ({placeholders})", base_sql)
    params = {f"t{i}": t for i, t in enumerate(terms, 1)}

    engine = get_engine(section=db_section)
    with engine.connect() as conn:
        return pd.read_sql(sql, conn, params=params)


# ---------------------------------------------------------------------------
# Cloud mode helpers (Tableau Cloud → Hyper)
# ---------------------------------------------------------------------------

def _download_and_read(dataset_name: str, term_col: str, terms: tuple[str, ...]) -> pd.DataFrame:
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

    # Filter to requested terms
    if term_col in df.columns:
        df = df[df[term_col].astype(str).isin(terms)]
    return df


# ---------------------------------------------------------------------------
# SQL directory (all SQL now lives under src/pipeline/sql/)
# ---------------------------------------------------------------------------

_SQL_DIR = Path(__file__).resolve().parents[1] / "pipeline" / "sql"


# ---------------------------------------------------------------------------
# Public fetch functions
# ---------------------------------------------------------------------------

@st.cache_data(ttl=600, show_spinner="Loading data...")
def fetch_coi_nhrdist(terms: tuple[str, ...]) -> pd.DataFrame:
    if _is_cloud():
        return _download_and_read("coi_nhrdist_val", "mis_term_id", terms)
    return _query_oracle(_SQL_DIR / "coi_nhrdist_val.sql", terms)


@st.cache_data(ttl=600, show_spinner="Loading data...")
def fetch_deg_scff(terms: tuple[str, ...]) -> pd.DataFrame:
    if _is_cloud():
        return _download_and_read("deg_scff", "mis_term_id", terms)
    return _query_oracle(_SQL_DIR / "deg_scff.sql", terms)


@st.cache_data(ttl=600, show_spinner="Loading data...")
def fetch_deg_sp_submitted(terms: tuple[str, ...]) -> pd.DataFrame:
    if _is_cloud():
        return _download_and_read("deg_sp_submitted", "term_id", terms)
    return _query_oracle(_SQL_DIR / "deg_sp_submitted.sql", terms)


# ---------------------------------------------------------------------------
# Single-term Oracle helper (for SQL with :mis_term_id instead of IN(:t1...))
# ---------------------------------------------------------------------------

def _query_oracle_single_term(sql_path: Path, terms: tuple[str, ...], param_name: str, db_section: str = "dwhdb") -> pd.DataFrame:
    from src.pipeline.libs.sql import get_engine

    base_sql = sql_path.read_text(encoding="utf-8")
    engine = get_engine(section=db_section)
    frames = []
    with engine.connect() as conn:
        for t in terms:
            frames.append(pd.read_sql(base_sql, conn, params={param_name: t}))
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


@st.cache_data(ttl=600, show_spinner="Loading data...")
def fetch_deg_fa_scff(terms: tuple[str, ...]) -> pd.DataFrame:
    if _is_cloud():
        return _download_and_read("deg_fa_scff", "mis_term_id", terms)
    return _query_oracle(_SQL_DIR / "deg_fa_scff.sql", terms)


@st.cache_data(ttl=600, show_spinner="Loading data...")
def fetch_deg_fa_submitted(terms: tuple[str, ...]) -> pd.DataFrame:
    if _is_cloud():
        return _download_and_read("deg_fa_submitted", "term_id", terms)
    return _query_oracle(_SQL_DIR / "deg_fa_submitted.sql", terms)


@st.cache_data(ttl=600, show_spinner="Loading data...")
def fetch_deg_sp_current(terms: tuple[str, ...]) -> pd.DataFrame:
    if _is_cloud():
        return _download_and_read("deg_sp_current", "term_id", terms)
    return _query_oracle_single_term(_SQL_DIR / "deg_sp_current.sql", terms, "mis_term_id", db_section="rept")
