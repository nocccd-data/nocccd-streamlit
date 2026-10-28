"""SCFF FA Submitted: the expandable award-description rows count students who got each award.

The tab deduped to one row per student and award type before splitting by
description, so a student holding several awards was counted under whichever
description was read first. In ACYR 220 that showed Cal Grant B as ~1,600 when
4,767 students received it, and moved the CCPG Method B / C split on every
query. Each description row now counts the students who received it (a student
holding Method B and C appears in both rows), and the sub-table Total stays the
unduplicated headcount that matches the award-type row.
"""

import re

import pandas as pd

from src.scripts.tabs import mis_fa_submitted_scff as fa

_B = "CCPG - Method B based on income standards"
_C = "CCPG - Method C based on financial need"


def _fa_rows():
    rows = [
        # student 1 got Method B in fall and Method C in spring
        ("s1", "ccpg", "BB", _B, "215"), ("s1", "ccpg", "BC", _C, "217"),
        ("s2", "ccpg", "BB", _B, "215"),
        ("s3", "ccpg", "BC", _C, "217"),
        # student 1 also stacks two "other" grants
        ("s1", "other", "GB", "Cal Grant B", "215"), ("s1", "other", "GM", "CARES/HEERF federal grants", "215"),
        ("s4", "other", "GB", "Cal Grant B", "217"),
    ]
    df = pd.DataFrame(rows, columns=["student_id", "award_type", "award_type_code", "award_type_desc", "fa_term_aw"])
    df["match_status"] = "Matched"
    # In the SCFF file but not in our FA file: no description; render() fills "N/A".
    scff_only = pd.DataFrame([{"student_id": "s5", "award_type": "ccpg", "award_type_code": None,
                               "award_type_desc": "N/A", "fa_term_aw": None,
                               "match_status": "SCFF Only - Not in FA"}])
    df = pd.concat([df, scff_only], ignore_index=True)
    df["acyr_id"] = "220"
    df["dicd_code"] = "X"
    df["amount"] = 100.0
    return df


def _render(monkeypatch, df2):
    html = []
    monkeypatch.setattr(fa.st, "subheader", lambda *a, **k: None)
    monkeypatch.setattr(fa.st, "info", lambda *a, **k: None)
    monkeypatch.setattr(fa.st, "dataframe", lambda *a, **k: None)
    monkeypatch.setattr(fa.st, "radio", lambda label, options, **k: options[0])
    monkeypatch.setattr(fa.st, "markdown", lambda body, **k: html.append(body))
    fa._render_acyr_tables(pd.DataFrame(), df2, "220")
    return next(h for h in html if "FA Submitted File Match Counts" in h)


def _cells(html, label):
    """The numbers in the sub-table row whose header is `label`."""
    m = re.search(rf"<th>{re.escape(label)}</th>\s*((?:<td>\d+</td>\s*)+)", html)
    assert m, label
    return [int(x) for x in re.findall(r"\d+", m.group(1))]


def test_description_rows_count_every_student_who_received_it(monkeypatch):
    html = _render(monkeypatch, _fa_rows())
    # Columns: Matched, SCFF Only - Not in FA, Total (only statuses present are shown)
    assert _cells(html, _B) == [2, 0, 2]
    assert _cells(html, _C) == [2, 0, 2]
    assert _cells(html, "N/A") == [0, 1, 1]
    assert _cells(html, "Cal Grant B") == [2, 0, 2]
    assert _cells(html, "CARES/HEERF federal grants") == [1, 0, 1]


def test_sub_table_totals_stay_unduplicated(monkeypatch):
    html = _render(monkeypatch, _fa_rows())
    # The first sub-table is ccpg: s1, s2 and s3 matched, s5 SCFF-only, each once.
    assert _cells(html, "Total") == [3, 1, 4]
    # The award-type summary row shows the same headcount, column for column.
    assert "<span>ccpg</span><span>3</span><span>1</span><span>4</span>" in html


def test_description_rows_do_not_depend_on_row_order(monkeypatch):
    first = _render(monkeypatch, _fa_rows())
    for seed in range(5):
        assert _render(monkeypatch, _fa_rows().sample(frac=1, random_state=seed)) == first, seed
