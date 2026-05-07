"""Streamlit tab: NOCCCD Equity Analysis (PPG-1).

Single-page tab that explains the PPG-1 methodology and offers a download
button for the equity workbook. The button calls
``src.pipeline.equity_export.generate_equity_excel()`` so the same code path
that produces the CLI export feeds the Streamlit download — byte-identical
output for the same data snapshot.
"""

from __future__ import annotations

import streamlit as st


# equity_export is deferred-imported inside the helpers below: importing it at
# module load creates a circular dependency through src.scripts.tabs.__init__
# (equity_export imports bot_goal2_wage / bot_goal2_xfer, which triggers the
# tabs package init, which then re-imports this module before equity_export
# has finished defining its public symbols).


def _build_bytes() -> bytes:
    """Adapt the CLI exporter to the Streamlit context.

    The CLI uses a local-disk ``HyperCache``; in Streamlit we wrap the
    Tableau-Cloud fetch functions so they look the same to the exporter.
    Each call returns a DataFrame; the exporter is allowed to mutate copies
    but never the cached frame, mirroring ``HyperCache.get`` semantics.
    """
    from src.pipeline.config import DATASETS
    from src.pipeline.equity_export import generate_equity_excel
    from src.scripts.data_provider import (
        fetch_bot_goal1_students,
        fetch_bot_goal2_adt,
        fetch_bot_goal2_assoc,
        fetch_bot_goal2_bac,
        fetch_bot_goal2_cert,
        fetch_bot_goal2_cert_nc,
        fetch_bot_goal2_cert_nc_denom,
        fetch_bot_goal2_wage,
        fetch_bot_goal2_wage_denom,
        fetch_bot_goal2_xfer,
        fetch_bot_goal3_finaid,
        fetch_bot_goal3_units,
    )

    fetchers = {
        "bot_goal1_students": fetch_bot_goal1_students,
        "bot_goal2_adt": fetch_bot_goal2_adt,
        "bot_goal2_assoc": fetch_bot_goal2_assoc,
        "bot_goal2_bac": fetch_bot_goal2_bac,
        "bot_goal2_cert": fetch_bot_goal2_cert,
        "bot_goal2_cert_nc": fetch_bot_goal2_cert_nc,
        "bot_goal2_cert_nc_denom": fetch_bot_goal2_cert_nc_denom,
        "bot_goal2_wage": fetch_bot_goal2_wage,
        "bot_goal2_wage_denom": fetch_bot_goal2_wage_denom,
        "bot_goal2_xfer": fetch_bot_goal2_xfer,
        "bot_goal3_finaid": fetch_bot_goal3_finaid,
        "bot_goal3_units": fetch_bot_goal3_units,
    }

    class _StreamlitCache:
        def __init__(self) -> None:
            self._frames: dict = {}

        def get(self, name: str):
            if name not in self._frames:
                fetcher = fetchers[name]
                cfg = DATASETS[name]
                acyrs = tuple(cfg[cfg["param_name"]])
                self._frames[name] = fetcher(acyrs)
            return self._frames[name]

    return generate_equity_excel(_StreamlitCache())


def render() -> None:
    from src.pipeline.equity_export import (
        METRICS,
        SUBGROUPS,
        SUPPRESSED_RACE_LABELS,
        _baseline_and_current_labels,
    )
    from src.scripts.pdf_cache import cached_excel_bytes
    from src.scripts.tabs.bot_excel_helpers import EXCEL_MIME

    st.header("Equity Analysis (PPG-1)")

    (_, _, baseline_display, current_display) = _baseline_and_current_labels()

    st.markdown(
        f"""
**Reporting cycle**: Baseline = **{baseline_display}**, Current = **{current_display}**

This workbook applies the California Community Colleges Chancellor's Office
**Percentage Point Gap Minus One (PPG-1)** methodology to the same metrics
shown in the BOT report. For each subgroup, the workbook computes:

- Numerator and denominator from the BOT data pipeline
- Subgroup rate vs. all-other-students rate
- PPG-1 adjusted gap (1-percentage-point penalty per CCCCO 2022)
- 95% margin of error using the two-proportion z-test (floored at 2%)
- Disproportionate-impact flag

Subgroups with cohort N ≤ 10 are flagged as insufficient data to maintain
confidentiality. American Indian/AK Native and Pacific Islander/HI Native
typically fall in this range and are listed in the Summary as "--".
        """
    )

    n_metrics = len(METRICS)
    n_subgroups = len(SUBGROUPS) + len(SUPPRESSED_RACE_LABELS)
    st.caption(
        f"Workbook covers {n_metrics} BOT metrics \xd7 "
        f"{n_subgroups} subgroup rows (Race/Ethnicity, Gender, "
        f"First-Generation Status). Numerator/denominator values refresh on "
        f"every export run; PPG-1, gap, and DI flag formulas recompute on "
        f"open."
    )

    st.divider()

    if st.button("Generate Equity Workbook", key="equity_generate_btn"):
        # Cache key is the current acyr range so a config change invalidates
        # the cached bytes automatically.
        cache_key = (baseline_display, current_display)
        with st.spinner("Querying BOT extracts and building workbook..."):
            try:
                excel_bytes = cached_excel_bytes(
                    "equity",
                    cache_key,
                    _build_bytes,
                )
            except Exception as exc:  # noqa: BLE001
                st.error(f"Equity export failed: {exc}")
                return

        from datetime import date
        filename = f"equity_{date.today().strftime('%Y%m%d')}.xlsx"
        st.success(
            f"Workbook ready ({len(excel_bytes) / 1024:.0f} KB). Click below "
            f"to download."
        )
        st.download_button(
            label="Download Equity Workbook",
            data=excel_bytes,
            file_name=filename,
            mime=EXCEL_MIME,
            key="equity_download_btn",
        )
    else:
        st.info(
            "Click **Generate Equity Workbook** to query the BOT extracts "
            "and build the workbook for download."
        )
