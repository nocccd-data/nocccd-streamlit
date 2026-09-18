"""The in-app fetch must return the same years the bulk exporters see.

`_download_and_read` filters a Hyper to the years a tab selected. BOT
datasets also carry `ref_acyr_code` (config.py); those rows must ride along
with any selection so the Streamlit charts and the bulk PDF/Excel exporters
(which read the extract whole) never disagree on the year count.
"""

from types import SimpleNamespace

import pandas as pd
import pytest

from src.scripts import data_provider


@pytest.fixture
def stub_hyper(monkeypatch):
    """Route _download_and_read at an in-memory frame instead of Tableau."""
    frame = pd.DataFrame({
        "acyr_code": ["2018", "2021", "2022", "2023", "2024", "2025"],
        "pidm": range(6),
    })
    monkeypatch.setattr(data_provider, "st", SimpleNamespace(secrets={
        "SERVER": "x", "SITE_NAME": "x", "PAT_NAME": "x", "PAT_VALUE": "x",
    }))
    import pantab

    from src.pipeline import publish
    monkeypatch.setattr(publish, "download_hyper", lambda *_a, **_k: "unused.hyper")
    monkeypatch.setattr(pantab, "frame_from_hyper", lambda *_a, **_k: frame.copy())
    return frame


def test_bot_fetch_always_includes_reference_years(stub_hyper):
    out = data_provider._download_and_read(
        "bot_goal1_students", "acyr_code", ("2021", "2022", "2023", "2024", "2025"),
    )
    assert sorted(out["acyr_code"]) == ["2018", "2021", "2022", "2023", "2024", "2025"]


def test_bot_fetch_keeps_reference_even_when_user_deselects_window_years(stub_hyper):
    out = data_provider._download_and_read("bot_goal1_students", "acyr_code", ("2025",))
    assert sorted(out["acyr_code"]) == ["2018", "2025"]


def test_non_bot_fetch_is_unchanged(stub_hyper):
    # A dataset with no ref_* key filters to exactly what was asked.
    out = data_provider._download_and_read("kpi_persistence", "acyr_code", ("2024",))
    assert list(out["acyr_code"]) == ["2024"]


def test_unknown_dataset_name_does_not_raise_on_ref_lookup(stub_hyper):
    out = data_provider._download_and_read("not_a_dataset", "acyr_code", ("2021",))
    assert list(out["acyr_code"]) == ["2021"]
