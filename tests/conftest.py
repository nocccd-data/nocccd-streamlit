"""Make the repo root importable so ``src.pipeline`` resolves under pytest."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest


@pytest.fixture
def window_2028(monkeypatch):
    """Simulate the 2028 run: the 5-year window has rolled past acyr 2022."""
    from src.pipeline.config import DATASETS

    cfg = dict(DATASETS["bot_goal2_assoc"])
    cfg["acyr_code"] = ["2023", "2024", "2025", "2026", "2027"]
    monkeypatch.setitem(DATASETS, "bot_goal2_assoc", cfg)
    return cfg
