import sys
from pathlib import Path

import streamlit as st
import pandas as pd

# Add nocccd-sql/district to sys.path so we can import libs.sql
_DISTRICT_DIR = Path(__file__).resolve().parents[4] / "nocccd-sql" / "district"
if str(_DISTRICT_DIR) not in sys.path:
    sys.path.insert(0, str(_DISTRICT_DIR))

from libs.sql import get_engine

_QUERIES_DIR = _DISTRICT_DIR / "queries"
_DEFAULT_TERMS = ["245", "247", "253", "255", "257"]

_SQL_FILE = "coi_nhrdist_val.sql"


def _build_sql(base_sql: str, n_terms: int) -> str:
    """Replace the fixed IN (:t1, :t2, :t3, :t4, :t5) with the right number of bind params."""
    placeholders = ", ".join(f":t{i}" for i in range(1, n_terms + 1))
    return base_sql.replace(
        "IN (:t1, :t2, :t3, :t4, :t5)",
        f"IN ({placeholders})",
    )


@st.cache_data(ttl=600, show_spinner="Querying Oracle...")
def _fetch_data(sql_filename: str, terms: tuple[str, ...]) -> pd.DataFrame:
    sql_path = _QUERIES_DIR / sql_filename
    base_sql = sql_path.read_text(encoding="utf-8")
    sql = _build_sql(base_sql, len(terms))
    params = {f"t{i}": t for i, t in enumerate(terms, 1)}
    engine = get_engine(section="dwh")
    with engine.connect() as conn:
        return pd.read_sql(sql, conn, params=params)


def _process(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
    """Filter, aggregate, and summarize — mirrors notebook Cell 2 logic."""
    agg = (
        df.groupby(["mis_term_id", "pidm", "posn"])
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
    summary["total_diff"] = summary["total_diff"].round(2)
    summary["pct_diff"] = summary["total_diff"] / summary["total_est"]

    grand = {
        "total_est": round(agg["est_term_sal"].sum(), 2),
        "total_pay": round(agg["payamt"].sum(), 2),
        "total_diff": round(agg["diff"].sum(), 2),
        "pct_diff": agg["diff"].sum() / agg["est_term_sal"].sum() if agg["est_term_sal"].sum() != 0 else 0,
    }

    return agg, summary, grand


def _fmt_currency(x):
    return f"${x:,.2f}"


def _fmt_diff(x):
    return f"{x:+,.2f}"


def _fmt_pct(x):
    return f"{x * 100:+.1f}%"


def render():
    st.header("COI vs NHRDIST Validation")

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
        df = _fetch_data(_SQL_FILE, tuple(sorted(selected_terms)))
        if df.empty:
            st.warning("No data returned for the selected terms.")
            return
        agg, summary, grand = _process(df)
        st.session_state["coi_agg"] = agg
        st.session_state["coi_summary"] = summary
        st.session_state["coi_grand"] = grand

    if "coi_agg" not in st.session_state:
        st.info("Select Term IDs and press **Query** to load data.")
        return

    agg = st.session_state["coi_agg"]
    summary = st.session_state["coi_summary"]
    grand = st.session_state["coi_grand"]

    # --- Legend ---
    st.caption(
        "(+) diff = Estimated term salary **overstated** vs payment amount  \n"
        "(-) diff = Estimated term salary **understated** vs payment amount"
    )

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
