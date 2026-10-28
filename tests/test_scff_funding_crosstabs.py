"""Empty funding_status categories in the SCFF crosstab tabs.

``funding_status`` is a Categorical (Pell / CCPG / Both / Neither). pandas 2's
crosstab kept a category with no students as a row or column of zeros; pandas 3
drops it. On the 2026-10 data that removed the ``Pell 0 …`` / ``CCPG 0 …`` rows
from the expandable sub-tables of SP Current ACYR 240 and SP Submitted ACYR 220.
These tests pin the zero rows/columns back in.
"""

import pandas as pd
import pytest

from src.scripts.tabs import (
    cte_sx_submitted_scff,
    mis_sp_current_scff,
    mis_sp_submitted_scff,
)

_FUNDING = ["Pell", "CCPG", "Both", "Neither"]


def _df():
    # Nobody is "Both" or "Pell"; every award type is adt or aaas.
    return pd.DataFrame({
        "award_type": ["adt", "adt", "aaas"],
        "match_status": ["Matched", "Matched", "SCFF Only - Not in SP"],
        "sb00": ["a", "b", "c"],
        "ccpg": ["Y", "N", "N"],
        "pell": ["N", "N", "N"],
    })


@pytest.mark.parametrize("mod", [mis_sp_current_scff, mis_sp_submitted_scff])
def test_funding_columns_keep_empty_categories(mod):
    df = mod._derive_funding_status(_df(), "ccpg", "pell")
    ct = mod._ordered_crosstab(df, "award_type", "funding_status", "sb00")
    assert set(_FUNDING) <= set(ct.columns)
    assert ct.loc["Total", "Both"] == 0
    assert ct.loc["Total", "Total"] == 3


@pytest.mark.parametrize("mod", [mis_sp_current_scff, mis_sp_submitted_scff])
def test_expandable_sub_tables_keep_empty_categories(mod):
    df = mod._derive_funding_status(_df(), "ccpg", "pell")
    summary = mod._ordered_crosstab(df, "award_type", "match_status", "sb00", col_order=mod._MATCH_ORDER)
    html = mod._build_expandable_crosstab(
        summary, df, "award_type", "match_status", "sb00", "funding_status", "t",
    )
    # One sub-table per award type, each listing all four categories + Total.
    for label in _FUNDING:
        assert html.count(f"<th>{label}</th>") == 2, label


def test_cte_match_table_keeps_empty_categories(monkeypatch):
    shown = []
    monkeypatch.setattr(cte_sx_submitted_scff.st, "subheader", lambda *a, **k: None)
    monkeypatch.setattr(cte_sx_submitted_scff.st, "markdown", lambda *a, **k: None)
    monkeypatch.setattr(cte_sx_submitted_scff.st, "info", lambda *a, **k: None)
    monkeypatch.setattr(cte_sx_submitted_scff.st, "radio", lambda label, options, **k: options[0])
    monkeypatch.setattr(cte_sx_submitted_scff.st, "dataframe", lambda df, **k: shown.append(df))
    df = _df().rename(columns={"sb00": "student_id"})
    df["sb00"] = df["student_id"]
    df["match_status"] = ["Matched", "Matched", "SX Only - Not in SCFF"]
    df["dicd_code"] = ["X", "X", "Y"]
    df["sum_sx03_861"] = [1.0, 2.0, 3.0]
    df["sum_sx03_862"] = [0.0, 0.0, 0.0]
    df["total_sx03"] = [1.0, 2.0, 3.0]
    df = cte_sx_submitted_scff._derive_funding_status(df, "ccpg", "pell")
    cte_sx_submitted_scff._render_acyr_tables(df, df, "250")
    match_table = shown[1]
    assert list(match_table.index) == _FUNDING + ["Total"]
    assert match_table.loc["Both"].sum() == 0
