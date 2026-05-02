"""Tests for src.pipeline.config."""

import re

from src.pipeline.config import DATASETS, max_acyr_label


def test_max_acyr_label_format():
    label = max_acyr_label()
    assert re.fullmatch(r"\d{4}-\d{2}", label), label


def test_max_acyr_label_uses_max_of_goal1_acyrs():
    """Anchors on the canonical Goal 1 students range, not other BOT datasets
    that may use a shifted window (e.g. living-wage is 1-year arrears).
    """
    cfg = DATASETS["bot_goal1_students"]
    expected_start = max(int(y) for y in cfg["acyr_code"])
    assert max_acyr_label() == f"{expected_start}-{(expected_start + 1) % 100:02d}"
