import streamlit as st
import pandas as pd

from src.pipeline.config import DATASETS
from src.scripts.data_provider import fetch_coi_nhrdist

_DEFAULT_TERMS = DATASETS["coi_nhrdist_val"]["acyrs"]


def _process(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Filter, aggregate, and summarize — mirrors notebook Cell 2 logic."""
    df["payamt"] = df["payamt"].fillna(0)
    df["diff"] = df["est_term_sal"] - df["payamt"]

    agg = (
        df.groupby(["mis_term_id", "pidm", "posn", "match_status"])
        .agg(
            est_term_sal=("est_term_sal", "sum"),
            payamt=("payamt", "sum"),
            diff=("diff", "sum"),
        )
        .reset_index()
    )
    agg["pct_diff"] = agg["diff"] / agg["est_term_sal"]
    agg["pct_diff"] = agg["pct_diff"].replace([float("inf"), float("-inf")], -1.0)

    summary = (
        agg.groupby("mis_term_id")
        .agg(
            total_est=("est_term_sal", "sum"),
            total_pay=("payamt", "sum"),
            total_diff=("diff", "sum"),
        )
        .reset_index()
        .set_index("mis_term_id")
    )
    summary["total_diff"] = (summary["total_est"] - summary["total_pay"]).round(2)
    summary["pct_diff"] = summary["total_diff"] / summary["total_est"]

    grand_est = round(agg["est_term_sal"].sum(), 2)
    grand_pay = round(agg["payamt"].sum(), 2)
    grand = {
        "total_est": grand_est,
        "total_pay": grand_pay,
        "total_diff": round(grand_est - grand_pay, 2),
        "pct_diff": (grand_est - grand_pay) / grand_est if grand_est != 0 else 0,
    }

    return agg, summary, grand


def _fmt_currency(x):
    return f"${x:,.2f}"


def _fmt_diff(x):
    return f"{x:+,.2f}"


def _fmt_pct(x):
    return f"{x * 100:+.1f}%"


def render():
    st.header("COI vs Paid Validation")

    # --- Sidebar controls ---
    selected_terms = st.sidebar.multiselect(
        "Term IDs",
        options=_DEFAULT_TERMS,
        default=_DEFAULT_TERMS,
        key="coi_terms",
    )
    query_btn = st.sidebar.button("Query", key="coi_query_btn")

    if query_btn:
        if not selected_terms:
            st.warning("Select at least one term.")
            return
        fetch_coi_nhrdist.clear()
        df = fetch_coi_nhrdist(tuple(sorted(selected_terms)))
        if df.empty:
            st.warning("No data returned for the selected terms.")
            return
        agg, _, _ = _process(df)
        st.session_state["coi_agg"] = agg

    if "coi_agg" not in st.session_state:
        st.info("Select Term IDs and press **Query** to load data.")
        return

    agg = st.session_state["coi_agg"]

    # --- Legend ---
    st.caption(
        "(+) diff = Estimated term salary **overstated** vs payment amount  \n"
        "(-) diff = Estimated term salary **understated** vs payment amount"
    )

    # --- Match status filter ---
    match_filter = st.radio(
        "Match Status",
        options=["All COI", "Matched", "Not Matched"],
        horizontal=True,
        key="coi_match_filter",
    )
    if match_filter != "All COI":
        agg = agg[agg["match_status"] == match_filter]

    # Re-derive summary and grand from filtered agg
    summary = (
        agg.groupby("mis_term_id")
        .agg(
            total_est=("est_term_sal", "sum"),
            total_pay=("payamt", "sum"),
            total_diff=("diff", "sum"),
        )
        .reset_index()
        .set_index("mis_term_id")
    )
    summary["total_diff"] = (summary["total_est"] - summary["total_pay"]).round(2)
    summary["pct_diff"] = summary["total_diff"] / summary["total_est"]

    grand_est = round(agg["est_term_sal"].sum(), 2)
    grand_pay = round(agg["payamt"].sum(), 2)
    grand = {
        "total_est": grand_est,
        "total_pay": grand_pay,
        "total_diff": round(grand_est - grand_pay, 2),
        "pct_diff": (grand_est - grand_pay) / grand_est if grand_est != 0 else 0,
    }

    # --- Summary table ---
    summary_display = summary.copy()
    summary_display.index = summary_display.index.astype(str)

    grand_row = pd.DataFrame(
        {
            "total_est": [grand["total_est"]],
            "total_pay": [grand["total_pay"]],
            "total_diff": [grand["total_diff"]],
            "pct_diff": [grand["pct_diff"]],
        },
        index=["Grand Total"],
    )
    summary_display = pd.concat([summary_display, grand_row])
    summary_display.index.name = "mis_term_id"

    st.subheader("Summary by Term")
    st.dataframe(
        summary_display.style.format(
            {
                "total_est": "${:,.2f}",
                "total_pay": "${:,.2f}",
                "total_diff": "{:+,.2f}",
                "pct_diff": "{:+.1%}",
            }
        ),
        width="stretch",
    )

    # --- Metrics ---
    cols = st.columns(3)
    cols[0].metric("Total Estimated", _fmt_currency(grand["total_est"]))
    cols[1].metric("Total Payment", _fmt_currency(grand["total_pay"]))
    cols[2].metric("Total Diff", _fmt_diff(grand["total_diff"]), delta=_fmt_pct(grand["pct_diff"]))

    # --- Expandable detail per term ---
    st.subheader("Top 10 Outliers by Term")
    for term_id in summary.index:
        term_agg = agg[agg["mis_term_id"] == term_id].copy()
        term_agg["abs_diff"] = term_agg["diff"].abs()
        top10 = term_agg.nlargest(10, "abs_diff")[
            ["pidm", "posn", "est_term_sal", "payamt", "diff", "pct_diff"]
        ]
        term_row = summary.loc[term_id]
        label = (
            f"Term {term_id} -- "
            f"Est: {_fmt_currency(term_row['total_est'])}  |  "
            f"Pay: {_fmt_currency(term_row['total_pay'])}  |  "
            f"Diff: {_fmt_diff(term_row['total_diff'])}  ({_fmt_pct(term_row['pct_diff'])})"
        )
        with st.expander(label):
            st.dataframe(
                top10.style.format(
                    {
                        "est_term_sal": "${:,.2f}",
                        "payamt": "${:,.2f}",
                        "diff": "{:+,.2f}",
                        "pct_diff": "{:+.1%}",
                    }
                ),
                width="stretch",
                hide_index=True,
            )
