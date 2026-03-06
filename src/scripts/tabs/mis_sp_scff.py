import hashlib
import re
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

# Add nocccd-sql/district to sys.path so we can import libs.sql
_DISTRICT_DIR = Path(__file__).resolve().parents[4] / "nocccd-sql" / "district"
if str(_DISTRICT_DIR) not in sys.path:
    sys.path.insert(0, str(_DISTRICT_DIR))

from libs.sql import get_engine

_SQL_DIR = Path(__file__).resolve().parents[4] / "nocccd-scff" / "sql"
_AWARD_ORDER = ["adt", "aaas", "babs", "cred_cert", "noncred_cert"]
_DEFAULT_TERMS = ["220", "230", "240", "250"]
_MATCH_ORDER = ["Matched", "SP Only - Not in SCFF", "SCFF Only - Not in SP"]


@st.cache_data(ttl=600, show_spinner="Querying Oracle...")
def _fetch_data(mis_term_ids: tuple[str, ...]) -> tuple[pd.DataFrame, pd.DataFrame]:
    sql1 = (_SQL_DIR / "deg_scff.sql").read_text(encoding="utf-8")
    sql2 = (_SQL_DIR / "deg_sp_submitted.sql").read_text(encoding="utf-8")
    # Rewrite the IN clause to match the number of term IDs
    placeholders = ", ".join(f":t{i+1}" for i in range(len(mis_term_ids)))
    sql1 = re.sub(r"IN\s*\(:t1.*?\)", f"IN ({placeholders})", sql1)
    sql2 = re.sub(r"IN\s*\(:t1.*?\)", f"IN ({placeholders})", sql2)
    params = {f"t{i+1}": v for i, v in enumerate(mis_term_ids)}
    engine = get_engine(section="dwh")
    with engine.connect() as conn:
        df1 = pd.read_sql(sql1, conn, params=params, dtype_backend="numpy_nullable")
        df2 = pd.read_sql(sql2, conn, params=params, dtype_backend="numpy_nullable")
    return df1, df2


def _derive_funding_status(df: pd.DataFrame, ccpg_col: str, pell_col: str) -> pd.DataFrame:
    ccpg = (df[ccpg_col] == "Y").fillna(False)
    pell = (df[pell_col] == "Y").fillna(False)
    df["funding_status"] = "Neither"
    df.loc[ccpg & ~pell, "funding_status"] = "CCPG"
    df.loc[~ccpg & pell, "funding_status"] = "Pell"
    df.loc[ccpg & pell, "funding_status"] = "Both"
    df["funding_status"] = pd.Categorical(
        df["funding_status"],
        categories=["Pell", "CCPG", "Both", "Neither"],
        ordered=True,
    )
    return df


def _ordered_crosstab(df, row_col, col_col, count_col, sort_cols=True, col_order=None):
    ct = pd.crosstab(
        df[row_col], df[col_col],
        values=df[count_col], aggfunc="count",
        margins=True, margins_name="Total",
    ).fillna(0).astype(int)
    ct.columns.name = "award_type"
    ct.index.name = None
    ordered_idx = [x for x in _AWARD_ORDER if x in ct.index] + ["Total"]
    ct = ct.reindex(ordered_idx)
    if sort_cols:
        data_cols = [c for c in col_order if c in ct.columns] if col_order else sorted(c for c in ct.columns if c != "Total")
        ct = ct[data_cols + ["Total"]]
    return ct


def _build_expandable_crosstab(summary_ct, source_df, row_col, col_col, count_col, detail_col, title):
    uid = "xt_" + hashlib.md5(title.encode()).hexdigest()[:8]
    data_cols = [c for c in summary_ct.columns if c != "Total"]
    all_cols = data_cols + (["Total"] if "Total" in summary_ct.columns else [])
    n_cols = len(all_cols)
    grid_tpl = f"minmax(180px, 2fr) repeat({n_cols}, minmax(60px, 1fr))"

    css = f"""
    <style>
    .{uid} {{ font-family: monospace; font-size: 13px; max-width: 900px; }}
    .{uid} .grid-row {{
        display: grid;
        grid-template-columns: {grid_tpl};
        align-items: center;
        padding: 2px 4px;
        border-bottom: 1px solid var(--text-color, #444);
    }}
    .{uid} .grid-row.header {{
        font-weight: bold;
        background: var(--secondary-background-color, #555);
        border-bottom: 2px solid var(--text-color, #888);
    }}
    .{uid} .grid-row.total {{
        font-weight: bold;
        border-top: 2px solid var(--text-color, #888);
    }}
    .{uid} .grid-row span {{ text-align: right; padding-right: 8px; }}
    .{uid} .grid-row span:first-child {{ text-align: left; }}
    .{uid} .grid-row span + span {{ border-left: 1px solid var(--text-color, #444); padding-left: 8px; }}
    .{uid} details {{ border-bottom: 1px solid var(--text-color, #444); }}
    .{uid} details summary {{ cursor: pointer; list-style: disclosure-closed; }}
    .{uid} details[open] summary {{ list-style: disclosure-open; }}
    .{uid} details summary .grid-row {{ border-bottom: none; }}
    .{uid} .sub-table {{
        margin: 2px 0 6px 20px;
        font-size: 12px;
        border-collapse: collapse;
    }}
    .{uid} .sub-table th, .{uid} .sub-table td {{
        padding: 2px 8px;
        border: 1px solid var(--text-color, #444);
        text-align: right;
    }}
    .{uid} .sub-table th:first-child, .{uid} .sub-table td:first-child {{
        text-align: left;
    }}
    .{uid} .sub-table thead th {{ background: var(--secondary-background-color, #555); }}
    </style>
    """

    header_cells = f"<span>{row_col}</span>" + "".join(
        f"<span>{c}</span>" for c in all_cols
    )
    header = f'<div class="grid-row header">{header_cells}</div>'

    body_rows = []
    non_total_idx = [r for r in summary_ct.index if r != "Total"]
    for row_val in non_total_idx:
        cells = f"<span>{row_val}</span>" + "".join(
            f"<span>{int(summary_ct.loc[row_val, c])}</span>" for c in all_cols
        )
        subset = source_df[source_df[row_col] == row_val].copy()
        sub_ct = pd.crosstab(
            subset[detail_col], subset[col_col],
            values=subset[count_col], aggfunc="count",
            margins=True, margins_name="Total",
        ).fillna(0).astype(int)
        for c in all_cols:
            if c not in sub_ct.columns:
                sub_ct[c] = 0
        sub_ct = sub_ct[all_cols]
        sub_html = sub_ct.to_html(classes="sub-table")

        body_rows.append(
            f"<details>"
            f'<summary><div class="grid-row">{cells}</div></summary>'
            f"{sub_html}"
            f"</details>"
        )

    total_row = ""
    if "Total" in summary_ct.index:
        total_cells = "<span><b>Total</b></span>" + "".join(
            f"<span><b>{int(summary_ct.loc['Total', c])}</b></span>" for c in all_cols
        )
        total_row = f'<div class="grid-row total">{total_cells}</div>'

    return (
        f"<details open><summary><b>{title}</b></summary>"
        f'{css}<div class="{uid}">{header}{"".join(body_rows)}{total_row}</div>'
        f"</details>"
    )


def _render_term_tables(df1_term: pd.DataFrame, df2_term: pd.DataFrame, term: str):
    """Render SCFF and SP tables for a single term."""
    st.subheader(f"Term {term}")

    if not df1_term.empty:
        table1 = _ordered_crosstab(df1_term, "award_type", "funding_status", "sb00")
        st.markdown(
            _build_expandable_crosstab(
                table1, df1_term, "award_type", "funding_status", "sb00",
                "funding_status", f"SCFF File Counts — Term {term}",
            ),
            unsafe_allow_html=True,
        )
    else:
        st.info(f"No SCFF data for term {term}.")

    if not df2_term.empty:
        table2 = _ordered_crosstab(df2_term, "award_type", "match_status", "sb00", col_order=_MATCH_ORDER)
        st.markdown(
            _build_expandable_crosstab(
                table2, df2_term, "award_type", "match_status", "sb00",
                "funding_status", f"SP Submitted File Match Counts — Term {term}",
            ),
            unsafe_allow_html=True,
        )

        dicd_filter = st.radio(
            "DICD Filter",
            ["All", "Matched", "SP Only", "SCFF Only"],
            horizontal=True,
            key=f"dicd_filter_{term}",
        )
        filter_map = {
            "Matched": "Matched",
            "SP Only": "SP Only - Not in SCFF",
            "SCFF Only": "SCFF Only - Not in SP",
        }
        df2_dicd = (
            df2_term[df2_term["match_status"] == filter_map[dicd_filter]]
            if dicd_filter != "All"
            else df2_term
        )
        df2_dicd = df2_dicd.copy()
        df2_dicd["dicd_code"] = df2_dicd["dicd_code"].fillna("N/A")
        if df2_dicd.empty:
            st.info(f"No records for filter '{dicd_filter}' - Term {term}.")
        else:
            table3 = pd.crosstab(
                df2_dicd["award_type"], df2_dicd["dicd_code"],
                values=df2_dicd["sb00"], aggfunc="count",
                margins=True, margins_name="Total",
            ).fillna(0).astype(int)
            sorted_cols = sorted(c for c in table3.columns if c != "Total")
            if "Total" in table3.columns:
                sorted_cols += ["Total"]
            table3 = table3[sorted_cols]
            table3.columns.name = "award_type"
            table3.index.name = None
            ordered_idx = [x for x in _AWARD_ORDER if x in table3.index] + ["Total"]
            table3 = table3.reindex(ordered_idx)
            st.markdown(
                _build_expandable_crosstab(
                    table3, df2_dicd, "award_type", "dicd_code", "sb00",
                    "funding_status", f"Counts by Award Type and DICD Code — Term {term}",
                ),
                unsafe_allow_html=True,
            )
    else:
        st.info(f"No SP submitted data for term {term}.")


def render():
    st.header("MIS SP Submitted vs. SCFF Files")

    selected_terms = st.sidebar.multiselect(
        "MIS Term IDs",
        options=_DEFAULT_TERMS,
        default=_DEFAULT_TERMS,
        key="scff_term_ids",
    )
    query_btn = st.sidebar.button("Query", key="scff_query_btn")

    if query_btn:
        if not selected_terms:
            st.warning("Select at least one MIS Term ID.")
            return
        term_ids = tuple(sorted(selected_terms))
        df1, df2 = _fetch_data(term_ids)
        # Derive funding_status
        df1 = _derive_funding_status(df1, "ccpg", "pell")
        df2["sb00"] = df2["sp_sb00"].fillna(df2["scff_sb00"])
        df2 = _derive_funding_status(df2, "scff_ccpg", "scff_pell")
        st.session_state["scff_df1"] = df1
        st.session_state["scff_df2"] = df2
        st.session_state["scff_terms"] = term_ids

    if "scff_df1" not in st.session_state:
        st.info("Enter MIS Term IDs and press **Query** to load data.")
        return

    df1 = st.session_state["scff_df1"]
    df2 = st.session_state["scff_df2"]
    term_ids = st.session_state["scff_terms"]

    for i, term in enumerate(term_ids):
        if i > 0:
            st.divider()
        df1_term = df1[df1["mis_term_id"] == term]
        df2_term = df2[df2["term_id"] == term]
        _render_term_tables(df1_term, df2_term, term)
