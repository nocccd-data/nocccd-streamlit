import hashlib
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


@st.cache_data(ttl=600, show_spinner="Querying Oracle...")
def _fetch_data(mis_term_id: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    sql1 = (_SQL_DIR / "deg_scff.sql").read_text(encoding="utf-8")
    sql2 = (_SQL_DIR / "deg_sp_submitted.sql").read_text(encoding="utf-8")
    params = {"mis_term_id": mis_term_id}
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


def _ordered_crosstab(df, row_col, col_col, count_col, sort_cols=True):
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
        data_cols = [c for c in ct.columns if c != "Total"]
        ct = ct[sorted(data_cols) + ["Total"]] if sort_cols == "sort" else ct
    return ct


def _build_expandable_crosstab(summary_ct, source_df, row_col, col_col, count_col, detail_col, title):
    uid = "xt_" + hashlib.md5(title.encode()).hexdigest()[:8]
    data_cols = [c for c in summary_ct.columns if c != "Total"]
    all_cols = data_cols + ["Total"]
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
    .{uid} .grid-row span {{ text-align: right; }}
    .{uid} .grid-row span:first-child {{ text-align: left; }}
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


def render():
    st.header("MIS SP Submitted vs. SCFF Files")

    mis_term_id = st.sidebar.text_input("MIS Term ID", value="240", key="scff_term_id")
    if not mis_term_id.strip():
        st.warning("Enter a MIS Term ID.")
        return

    df1, df2 = _fetch_data(mis_term_id.strip())
    if df1.empty and df2.empty:
        st.info("No data returned for the given term.")
        return

    # Derive funding_status
    df1 = _derive_funding_status(df1, "ccpg", "pell")
    df2["sb00"] = df2["sp_sb00"].fillna(df2["scff_sb00"])
    df2 = _derive_funding_status(df2, "scff_ccpg", "scff_pell")

    # Table 1: SCFF File Counts
    table1 = _ordered_crosstab(df1, "award_type", "funding_status", "sb00")
    st.markdown(
        _build_expandable_crosstab(
            table1, df1, "award_type", "funding_status", "sb00",
            "funding_status", "SCFF File Counts",
        ),
        unsafe_allow_html=True,
    )

    st.divider()

    # Radio toggle for Table 2 / Table 3
    view = st.radio("View", ["Match Status", "DICD Code"], horizontal=True)

    if view == "Match Status":
        table2 = _ordered_crosstab(df2, "award_type", "match_status", "sb00")
        st.markdown(
            _build_expandable_crosstab(
                table2, df2, "award_type", "match_status", "sb00",
                "funding_status", "SP Submitted File Match Counts - Award Prioritized",
            ),
            unsafe_allow_html=True,
        )
    else:
        table3 = pd.crosstab(
            df2["award_type"], df2["dicd_code"],
            values=df2["sb00"], aggfunc="count",
            margins=True, margins_name="Total",
        ).fillna(0).astype(int)
        table3 = table3[sorted(c for c in table3.columns if c != "Total") + ["Total"]]
        table3.columns.name = "award_type"
        table3.index.name = None
        ordered_idx = [x for x in _AWARD_ORDER if x in table3.index] + ["Total"]
        table3 = table3.reindex(ordered_idx)
        st.markdown(
            _build_expandable_crosstab(
                table3, df2, "award_type", "dicd_code", "sb00",
                "funding_status", "Counts by Award Type and DICD Code - Award Prioritized",
            ),
            unsafe_allow_html=True,
        )
