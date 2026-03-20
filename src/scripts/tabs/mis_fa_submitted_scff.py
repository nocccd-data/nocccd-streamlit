import hashlib

import pandas as pd
import streamlit as st

from src.pipeline.config import DATASETS
from src.scripts.data_provider import fetch_deg_fa_scff, fetch_deg_fa_submitted

_AWARD_ORDER = ["ccpg", "pell", "other"]
_DEFAULT_ACYRS = DATASETS["deg_fa_submitted"]["mis_acyr_id"]
_MATCH_ORDER = ["Matched", "FA Only - Not in SCFF", "SCFF Only - Not in FA"]


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


def _render_acyr_tables(df1_acyr: pd.DataFrame, df2_acyr: pd.DataFrame, acyr: str):
    """Render SCFF and FA tables for a single acyr."""
    st.subheader(f"ACYR {acyr}")

    # Table 1 — SCFF file counts by scff_type
    if not df1_acyr.empty:
        counts = df1_acyr.groupby("scff_type")["sb00"].count()
        ordered = [t for t in ["ccpg", "pell"] if t in counts.index]
        table1 = counts.reindex(ordered).to_frame("count")
        table1.loc["Total"] = table1["count"].sum()
        table1.index.name = None
        st.markdown(f"**SCFF File Counts — ACYR {acyr}**")
        st.dataframe(table1, use_container_width=False)
    else:
        st.info(f"No SCFF data for ACYR {acyr}.")

    # Table 2 — FA match status crosstab
    if not df2_acyr.empty:
        df2_dedup = df2_acyr.drop_duplicates(subset=["student_id", "award_type", "match_status"])
        table2 = _ordered_crosstab(df2_dedup, "award_type", "match_status", "student_id", col_order=_MATCH_ORDER)
        st.markdown(
            _build_expandable_crosstab(
                table2, df2_dedup, "award_type", "match_status", "student_id",
                "award_type_desc", f"FA Submitted File Match Counts — ACYR {acyr}",
            ),
            unsafe_allow_html=True,
        )

        # DICD filter radio
        dicd_filter = st.radio(
            "DICD Filter",
            ["All", "Matched", "FA Only", "SCFF Only"],
            horizontal=True,
            key=f"fa_dicd_filter_{acyr}",
        )
        filter_map = {
            "Matched": "Matched",
            "FA Only": "FA Only - Not in SCFF",
            "SCFF Only": "SCFF Only - Not in FA",
        }
        df2_dicd = (
            df2_acyr[df2_acyr["match_status"] == filter_map[dicd_filter]]
            if dicd_filter != "All"
            else df2_acyr
        )
        df2_dicd = df2_dicd.copy()
        df2_dicd["dicd_code"] = df2_dicd["dicd_code"].fillna("N/A")
        if df2_dicd.empty:
            st.info(f"No records for filter '{dicd_filter}' — ACYR {acyr}.")
        else:
            # Table 3 — award_type x dicd_code
            table3 = pd.crosstab(
                df2_dicd["award_type"], df2_dicd["dicd_code"],
                values=df2_dicd["student_id"], aggfunc="count",
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
                    table3, df2_dicd, "award_type", "dicd_code", "student_id",
                    "award_type_desc", f"Counts by Award Type and DICD Code — ACYR {acyr}",
                ),
                unsafe_allow_html=True,
            )
    else:
        st.info(f"No FA submitted data for ACYR {acyr}.")


def render():
    st.header("MIS FA Submitted vs. SCFF Files")

    selected_acyrs = st.sidebar.multiselect(
        "MIS ACYR IDs",
        options=_DEFAULT_ACYRS,
        default=_DEFAULT_ACYRS,
        key="fa_acyr_ids",
    )
    query_btn = st.sidebar.button("Query", key="fa_query_btn")

    if query_btn:
        if not selected_acyrs:
            st.warning("Select at least one MIS ACYR ID.")
            return
        fetch_deg_fa_scff.clear()
        fetch_deg_fa_submitted.clear()
        acyr_ids = tuple(sorted(selected_acyrs))
        df1 = fetch_deg_fa_scff(acyr_ids)
        df2 = fetch_deg_fa_submitted(acyr_ids)
        # Filter amount > 0 (keep SCFF-only rows where amount is NA)
        amount_num = pd.to_numeric(df2["amount"], errors="coerce")
        df2 = df2[(amount_num > 0) | amount_num.isna()]
        # Fill NaN in award_type_desc for SCFF-only rows
        df2["award_type_desc"] = df2["award_type_desc"].fillna("N/A")
        st.session_state["fa_df1"] = df1
        st.session_state["fa_df2"] = df2
        st.session_state["fa_acyrs"] = acyr_ids

    if "fa_df1" not in st.session_state:
        st.info("Enter MIS ACYR IDs and press **Query** to load data.")
        return

    df1 = st.session_state["fa_df1"]
    df2 = st.session_state["fa_df2"]
    acyr_ids = st.session_state["fa_acyrs"]

    for i, acyr in enumerate(acyr_ids):
        if i > 0:
            st.divider()
        df1_acyr = df1[df1["mis_acyr_id"] == acyr]
        df2_acyr = df2[df2["acyr_id"] == acyr]
        _render_acyr_tables(df1_acyr, df2_acyr, acyr)
