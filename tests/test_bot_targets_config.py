"""The Vision 2030 target plan is fixed and independent of the rolling window.

The manager's plan runs 2022-23 (baseline) -> 2029-30. The 5-year metrics
window rolls forward every year and drops acyr 2022 on the 2028 run, so the
extract must keep pulling baseline -> latest for target datasets, while the
existing charts keep seeing only reference + window.
"""

from src.pipeline.config import (
    BOT_TARGET_BASELINE_ACYR,
    BOT_TARGET_END_ACYR,
    DATASETS,
    display_acyrs,
    extract_values,
    target_acyrs,
)

TARGET_DATASETS = {
    "bot_goal2_assoc",
    "bot_goal2_adt",
    "bot_goal2_cert",
    "bot_goal2_cert_nc",
    "bot_goal2_bac",
    "bot_goal3_units",
    "bot_goal4_xfer_ready",
}


def test_exactly_the_seven_manager_tabs_have_targets():
    assert {n for n, c in DATASETS.items() if "target" in c} == TARGET_DATASETS


def test_plan_is_2022_23_to_2029_30():
    assert (BOT_TARGET_BASELINE_ACYR, BOT_TARGET_END_ACYR) == ("2022", "2029")


def test_rules_match_the_manager_workbook():
    for name in TARGET_DATASETS - {"bot_goal3_units"}:
        assert DATASETS[name]["target"]["growth"] == 0.30, name
    assert DATASETS["bot_goal2_bac"]["target"].get("round_up") is True
    assert DATASETS["bot_goal3_units"]["target"] == {
        "growth": 0.20,
        "reduce_over": 60,
        "value_col": "sum_hours_earned",
    }


def test_extract_values_unchanged_today():
    # Window 2021..2025 already contains 2022..2025 — nothing is added.
    assert extract_values("bot_goal2_assoc") == [
        "2018", "2021", "2022", "2023", "2024", "2025",
    ]


def test_non_target_dataset_extracts_ref_plus_window():
    cfg = DATASETS["bot_goal1_students"]
    assert extract_values("bot_goal1_students") == (
        cfg["ref_acyr_code"] + cfg["acyr_code"]
    )
    assert target_acyrs("bot_goal1_students") == []


def test_2028_run_still_pulls_the_baseline(window_2028):
    assert target_acyrs("bot_goal2_assoc") == [
        "2022", "2023", "2024", "2025", "2026", "2027",
    ]
    assert extract_values("bot_goal2_assoc") == [
        "2018", "2023", "2024", "2025", "2026", "2027", "2022",
    ]
    # Existing charts never see the rolled-out baseline year.
    assert display_acyrs("bot_goal2_assoc") == [
        "2018", "2023", "2024", "2025", "2026", "2027",
    ]


def test_target_years_stop_at_plan_end(monkeypatch):
    cfg = dict(DATASETS["bot_goal2_assoc"])
    cfg["acyr_code"] = ["2027", "2028", "2029", "2030", "2031"]
    monkeypatch.setitem(DATASETS, "bot_goal2_assoc", cfg)
    assert target_acyrs("bot_goal2_assoc") == [
        "2022", "2023", "2024", "2025", "2026", "2027", "2028", "2029",
    ]
