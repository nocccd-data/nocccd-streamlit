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


def test_bot_fetch_drops_reference_when_user_narrows_the_window(stub_hyper):
    # A reference column only makes sense against the full 5-year window.
    # With a partial selection the frame would be [ref + sliver], which is
    # exactly the shape that let 2018-19 leak into the "5-Yr" metrics and
    # past small-n suppression. Narrowed selections behave as on main.
    out = data_provider._download_and_read("bot_goal1_students", "acyr_code", ("2025",))
    assert sorted(out["acyr_code"]) == ["2025"]
    out = data_provider._download_and_read(
        "bot_goal1_students", "acyr_code", ("2021", "2022", "2023", "2024"),
    )
    assert "2018" not in set(out["acyr_code"])


def test_bot_fetch_full_window_in_any_order_still_gets_reference(stub_hyper):
    out = data_provider._download_and_read(
        "bot_goal1_students", "acyr_code", ("2025", "2023", "2021", "2024", "2022"),
    )
    assert "2018" in set(out["acyr_code"])


def test_non_bot_fetch_is_unchanged(stub_hyper):
    # A dataset with no ref_* key filters to exactly what was asked.
    out = data_provider._download_and_read("kpi_persistence", "acyr_code", ("2024",))
    assert list(out["acyr_code"]) == ["2024"]


def test_unknown_dataset_name_does_not_raise_on_ref_lookup(stub_hyper):
    out = data_provider._download_and_read("not_a_dataset", "acyr_code", ("2021",))
    assert list(out["acyr_code"]) == ["2021"]


def test_target_frame_is_baseline_onward_ignoring_the_sidebar(stub_hyper):
    out = data_provider._read_target_frame("bot_goal2_assoc")
    assert sorted(out["acyr_code"]) == ["2022", "2023", "2024", "2025"]


def test_target_frame_never_carries_the_reference_year(stub_hyper, monkeypatch):
    # 2027 run: window 2022..2026 == target years, which makes
    # _download_and_read add the 2018 reference (Review Focus 5).
    from src.pipeline.config import DATASETS

    cfg = dict(DATASETS["bot_goal2_assoc"])
    cfg["acyr_code"] = ["2022", "2023", "2024", "2025", "2026"]
    monkeypatch.setitem(DATASETS, "bot_goal2_assoc", cfg)
    out = data_provider._read_target_frame("bot_goal2_assoc")
    assert "2018" not in set(out["acyr_code"])
