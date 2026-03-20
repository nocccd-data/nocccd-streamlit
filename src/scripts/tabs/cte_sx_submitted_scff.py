import pandas as pd
import streamlit as st

from src.pipeline.config import DATASETS
from src.scripts.data_provider import fetch_cte_scff, fetch_cte_sx_submitted

_FUNDING_ORDER = ["Pell", "CCPG", "Both", "Neither"]
_cfg = DATASETS["cte_sx_submitted"]
_DEFAULT_ACYRS = _cfg[_cfg["param_name"]]
_MATCH_ORDER = ["Matched", "SX Only - Not in SCFF", "SCFF Only - Not in SX"]


def _derive_funding_status(df: pd.DataFrame, ccpg_col: str, pell_col: str) -> pd.DataFrame:
    ccpg = (df[ccpg_col] == "Y").fillna(False)
    pell = (df[pell_col] == "Y").fillna(False)
    df["funding_status"] = "Neither"
    df.loc[ccpg & ~pell, "funding_status"] = "CCPG"
    df.loc[~ccpg & pell, "funding_status"] = "Pell"
    df.loc[ccpg & pell, "funding_status"] = "Both"
    df["funding_status"] = pd.Categorical(
        df["funding_status"],
        categories=_FUNDING_ORDER,
        ordered=True,
    )
    return df


def _render_acyr_tables(df1_acyr: pd.DataFrame, df2_acyr: pd.DataFrame, acyr: str):
    """Render SCFF CTE and SX tables for a single acyr."""
    st.subheader(f"ACYR {acyr}")

    # Table 1 — SCFF CTE File Counts by funding_status
    if not df1_acyr.empty:
        counts = df1_acyr.groupby("funding_status")["sb00"].count()
        table1 = counts.reindex(_FUNDING_ORDER).to_frame("count").fillna(0).astype(int)
        table1.loc["Total"] = table1["count"].sum()
        table1.index.name = None
        st.markdown(f"**SCFF CTE File Counts — ACYR {acyr}**")
        st.dataframe(table1, use_container_width=False)
    else:
        st.info(f"No SCFF CTE data for ACYR {acyr}.")

    # Table 2 — SX Submitted Match Counts: funding_status × match_status
    if not df2_acyr.empty:
        table2 = pd.crosstab(
            df2_acyr["funding_status"], df2_acyr["match_status"],
            values=df2_acyr["student_id"], aggfunc="count",
            margins=True, margins_name="Total",
        ).fillna(0).astype(int)
        table2.index.name = None
        ordered_idx = [x for x in _FUNDING_ORDER if x in table2.index] + ["Total"]
        table2 = table2.reindex(ordered_idx)
        data_cols = [c for c in _MATCH_ORDER if c in table2.columns]
        if "Total" in table2.columns:
            data_cols += ["Total"]
        table2 = table2[data_cols]
        st.markdown(f"**SX Submitted Match Counts — ACYR {acyr}**")
        st.dataframe(table2, use_container_width=True)

        # Table 3 — SX Count of Students and Sum of Units by DICD Code
        match_filter = st.radio(
            "Match Status Filter",
            ["All", "Matched", "SX Only", "SCFF Only"],
            horizontal=True,
            key=f"cte_sx_match_filter_{acyr}",
        )
        filter_map = {
            "Matched": "Matched",
            "SX Only": "SX Only - Not in SCFF",
            "SCFF Only": "SCFF Only - Not in SX",
        }
        df2_filtered = (
            df2_acyr[df2_acyr["match_status"] == filter_map[match_filter]]
            if match_filter != "All"
            else df2_acyr
        )
        if df2_filtered.empty:
            st.info(f"No records for filter '{match_filter}' — ACYR {acyr}.")
        else:
            rows = []
            for fs in _FUNDING_ORDER:
                grp = df2_filtered[df2_filtered["funding_status"] == fs]
                if grp.empty:
                    rows.append({
                        "funding_status": fs,
                        "861_count": 0, "862_count": 0,
                        "861_units": 0.0, "862_units": 0.0,
                        "861_units_per_student": pd.NA, "862_units_per_student": pd.NA,
                    })
                    continue
                s861 = grp["sum_sx03_861"].fillna(0)
                s862 = grp["sum_sx03_862"].fillna(0)
                cnt_861 = int((s861 > 0).sum())
                cnt_862 = int((s862 > 0).sum())
                units_861 = s861.sum() / 100
                units_862 = s862.sum() / 100
                rows.append({
                    "funding_status": fs,
                    "861_count": cnt_861,
                    "862_count": cnt_862,
                    "861_units": units_861,
                    "862_units": units_862,
                    "861_units_per_student": units_861 / cnt_861 if cnt_861 else pd.NA,
                    "862_units_per_student": units_862 / cnt_862 if cnt_862 else pd.NA,
                })
            table3 = pd.DataFrame(rows).set_index("funding_status")
            # Append Total row
            total_861_count = table3["861_count"].sum()
            total_862_count = table3["862_count"].sum()
            total_861_units = table3["861_units"].sum()
            total_862_units = table3["862_units"].sum()
            table3.loc["Total"] = {
                "861_count": total_861_count,
                "862_count": total_862_count,
                "861_units": total_861_units,
                "862_units": total_862_units,
                "861_units_per_student": total_861_units / total_861_count if total_861_count else pd.NA,
                "862_units_per_student": total_862_units / total_862_count if total_862_count else pd.NA,
            }
            table3.index.name = None
            # Format int columns
            for col in ["861_count", "862_count"]:
                table3[col] = table3[col].astype(int)
            st.markdown(f"**SX Count of Students and Sum of Units by DICD Code — ACYR {acyr}**")
            st.dataframe(table3, use_container_width=True)
    else:
        st.info(f"No SX submitted data for ACYR {acyr}.")


def render():
    st.header("MIS SX Submitted vs. SCFF CTE Files")

    selected_acyrs = st.sidebar.multiselect(
        "MIS ACYR IDs",
        options=_DEFAULT_ACYRS,
        default=_DEFAULT_ACYRS,
        key="cte_sx_acyr_ids",
    )
    query_btn = st.sidebar.button("Query", key="cte_sx_query_btn")

    if query_btn:
        if not selected_acyrs:
            st.warning("Select at least one MIS ACYR ID.")
            return
        fetch_cte_scff.clear()
        fetch_cte_sx_submitted.clear()
        acyr_ids = tuple(sorted(selected_acyrs))
        df1 = _derive_funding_status(fetch_cte_scff(acyr_ids), "ccpg", "pell")
        df2 = _derive_funding_status(fetch_cte_sx_submitted(acyr_ids), "ccpg", "pell")
        df1["mis_acyr_id"] = df1["mis_acyr_id"].astype(str)
        df2["mis_acyr_id"] = df2["mis_acyr_id"].astype(str)
        st.session_state["cte_sx_df1"] = df1
        st.session_state["cte_sx_df2"] = df2
        st.session_state["cte_sx_acyrs"] = acyr_ids

    if "cte_sx_df1" not in st.session_state:
        st.info("Enter MIS ACYR IDs and press **Query** to load data.")
        return

    df1 = st.session_state["cte_sx_df1"]
    df2 = st.session_state["cte_sx_df2"]
    acyr_ids = st.session_state["cte_sx_acyrs"]

    for i, acyr in enumerate(acyr_ids):
        if i > 0:
            st.divider()
        df1_acyr = df1[df1["mis_acyr_id"] == acyr]
        df2_acyr = df2[df2["mis_acyr_id"] == acyr]
        _render_acyr_tables(df1_acyr, df2_acyr, acyr)
