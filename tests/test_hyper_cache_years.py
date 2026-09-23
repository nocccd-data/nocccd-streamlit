"""Bulk exporters read extracts whole. Once a target dataset's extract also
carries the rolled-out baseline year (2028+), the existing charts must not
gain a stray 2022-23 column — only the target chart/columns use it."""

import pandas as pd
import pytest

from src.pipeline import hyper_cache
from src.pipeline.hyper_cache import HyperCache

YEARS = ["2018", "2022", "2023", "2024", "2025", "2026", "2027"]


@pytest.fixture
def cache(tmp_path, monkeypatch):
    for name in ("bot_goal2_assoc", "bot_goal1_students"):
        (tmp_path / f"{name}.hyper").touch()
    monkeypatch.setattr(hyper_cache, "HYPER_DIR", tmp_path)
    monkeypatch.setattr(
        hyper_cache.pantab, "frame_from_hyper",
        lambda *_a, **_k: pd.DataFrame({"acyr_code": YEARS, "pidm": range(7)}),
    )
    return HyperCache()


def test_existing_charts_never_see_the_rolled_out_baseline(cache, window_2028):
    got = sorted(cache.get("bot_goal2_assoc")["acyr_code"])
    assert got == ["2018", "2023", "2024", "2025", "2026", "2027"]


def test_target_frame_keeps_the_baseline(cache, window_2028):
    got = sorted(cache.get_targets_frame("bot_goal2_assoc")["acyr_code"])
    assert got == ["2022", "2023", "2024", "2025", "2026", "2027"]


def test_non_target_dataset_is_returned_whole(cache):
    assert sorted(cache.get("bot_goal1_students")["acyr_code"]) == YEARS


def test_integer_acyr_codes_are_matched(tmp_path, monkeypatch, window_2028):
    (tmp_path / "bot_goal2_assoc.hyper").touch()
    monkeypatch.setattr(hyper_cache, "HYPER_DIR", tmp_path)
    monkeypatch.setattr(
        hyper_cache.pantab, "frame_from_hyper",
        lambda *_a, **_k: pd.DataFrame({"acyr_code": [int(y) for y in YEARS]}),
    )
    assert 2022 not in set(HyperCache().get("bot_goal2_assoc")["acyr_code"])
