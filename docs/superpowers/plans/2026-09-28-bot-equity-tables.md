# BOT Vision 2030 Equity Tables Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a per-population "Equity Results" table (Baseline | latest-year Benchmark | Actual | Variance | Status by race/ethnicity, gender and first-gen) to 6 BOT target tabs — on the tab, PDF page 1, Excel, and the bulk exporters.

**Architecture:** A new module `src/scripts/tabs/bot_equity.py` (no Streamlit / `bot_helpers` imports) builds one `EquityTable` from per-category aggregates of the plan frame and renders it three ways (HTML, matplotlib, Excel via `bot_excel_helpers`). Count tabs get their table from `bot_helpers.equity_table()`; Units builds its own from average-units aggregates. The existing `render_target_section`, `add_target_page` and Excel section builders gain the table, so the bulk exporters pick it up with no change.

**Tech Stack:** Python 3.13, pandas, Streamlit 1.55 (`st.markdown` HTML), matplotlib (PdfPages, `Rectangle` patches), xlsxwriter via the existing `ExcelSection` writer, pytest.

**Spec:** `docs/superpowers/specs/2026-09-28-bot-equity-tables-design.md`

## Global Constraints

- Reader-facing wording: headers use `BENCHMARK` (`"Benchmark"`, from `bot_targets`); Status is `ON_TRACK = "On Track"` / `PROGRESSING = "Progressing"`; heading `"Equity Results, {short year}"` (e.g. `"Equity Results, 2025-26"`). The word "Target" must never reach a reader.
- Row rule: a group is shown only with **at least 10 students (`CATEGORY_MIN_COUNT`) in both 2022-23 and the equity year**, for all three categories and for Units (students counted, not averaged).
- Equity year: latest academic year in `Targets.frame` after the baseline, capped at the plan end (2029-30). Ignores the sidebar selection.
- Variance = Actual − Benchmark from unrounded values; Status "On Track" when Variance ≥ 0 (Units, rule has `reduce_over`: ≤ 0).
- Tabs: Associate Degrees, ADT, Credit Certificates, Noncredit Certificates, Average Units, Transfer Ready. **Not** Bachelor's (`titles["headcount_only"]` → no table).
- Colours: category band `#004062` with white bold text; Status fill On Track `light-dark(#d6eaf8, #1d4f6e)`, Progressing `light-dark(#f4c3a8, #7a3f22)` (PDF uses the light values).
- `bot_equity.py` must not import Streamlit, `bot_helpers` or `bot_excel_helpers` (import-cycle rule, same as `bot_targets.py`).
- Existing tables, charts and page counts are unchanged (target tabs' PDFs stay 3 pages; Bachelor's 2).
- Test command: `.venv/bin/python -m pytest tests -q -p no:cacheprovider`.
- Lint gate: no NEW diagnostics vs `main` (main is not clean). Binaries are Homebrew: `ruff` and `pyright` (there is no `.venv/bin/ruff`). Compare per file: `git show main:<f> | ruff check --stdin-filename <f> --output-format concise -`. Never run `ruff check --fix` on a directory; only `ruff check --select I001 --fix <changed files>`.
- Commit trailer on every commit:
  ```
  Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01C43MCBdHeNgXj3RtSGCheA
  ```

## Review Focus

1. **An exact hit with float noise** — baseline 210 in 2023-24 gives a benchmark of `219.00000000000003`; a group with 219 students must read Variance `0`, **On Track** (Task 1).
2. **A group with a baseline but no row in the equity year** (every student gone) must be dropped, not raise `KeyError` (Task 1).
3. **A group with 10+ students but a missing average** (Units hours all NaN) must be dropped, not crash (Task 1).
4. **Sidebar narrowed to one year** — the table still comes from the plan frame and shows the latest year (Task 3).
5. **The tallest possible table** (9 race + 4 gender + 3 first-gen groups) must fit on PDF page 1 above the footer (Task 3).

---

### Task 1: `bot_equity.py` — build the table

**Files:**
- Create: `src/scripts/tabs/bot_equity.py`
- Test: `tests/test_bot_equity.py`

**Interfaces:**
- Consumes (from `src/scripts/tabs/bot_targets.py`): `BENCHMARK: str`, `PLAN_LENGTH: int`, `Targets(frame, rule)` with `.is_average`, `group_baselines(agg, *, key_col, value_col) -> dict[str, float]`, `group_target(baselines, key, year_label, rule) -> float`, `plan_years() -> list[str]`, `short_year(label) -> str`, `target_caption(rule) -> str`, `years_from_baseline(label) -> int | None`.
- Produces:
  - constants `ON_TRACK`, `PROGRESSING`, `RACE_CATEGORY = "Race/Ethnicity"`, `GENDER_CATEGORY = "Gender"`, `FIRSTGEN_CATEGORY = "First Generation College Student Status"`, `COLUMNS = ["category", "group", "baseline", "benchmark", "actual", "variance", "status"]`
  - `EquitySource(category: str, agg: pd.DataFrame, key_col: str, value_col: str, order: list[str], labels: dict[str, str])`
  - `EquityTable(year: str, rows: pd.DataFrame, decimals: bool, note: str)` with `.heading -> str` and `.headers() -> dict[str, str]` (keys = `COLUMNS`)
  - `equity_year(targets: Targets) -> str | None`
  - `build_equity_table(targets: Targets, sources: list[EquitySource], *, min_count: int) -> EquityTable | None`
  - `equity_note(rule: dict) -> str`
  - `format_value(value: float, *, decimals: bool) -> str`, `format_variance(value: float, *, decimals: bool) -> str`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_bot_equity.py`:

```python
"""Vision 2030 equity tables (spec docs/superpowers/specs/2026-09-28-bot-equity-tables-design.md).

2025-26 is k=3 years after the 2022-23 baseline: growth factor 1 + 0.3*3/7.
"""

import math

import pandas as pd
import pytest

from src.scripts.tabs.bot_equity import (
    FIRSTGEN_CATEGORY,
    GENDER_CATEGORY,
    ON_TRACK,
    PROGRESSING,
    RACE_CATEGORY,
    EquitySource,
    build_equity_table,
    equity_note,
    equity_year,
    format_value,
    format_variance,
)
from src.scripts.tabs.bot_targets import Targets

GROWTH = {"growth": 0.30}
UNITS = {"growth": 0.20, "reduce_over": 60, "value_col": "sum_hours_earned"}
PLAN = ["2022-2023", "2023-2024", "2024-2025", "2025-2026"]
F3 = 1 + 0.3 * 3 / 7


def _targets(years=PLAN, rule=GROWTH):
    # equity_year() only reads the frame's academic_year column.
    return Targets(frame=pd.DataFrame({"academic_year": list(years)}), rule=rule)


def _counts(values, *, order=None, labels=None, category=RACE_CATEGORY):
    """values: {group: {year: students}} -> a count-tab source."""
    agg = pd.DataFrame([
        {"academic_year": y, "grp": g, "count": n}
        for g, by_year in values.items() for y, n in by_year.items()
    ])
    return EquitySource(category=category, agg=agg, key_col="grp", value_col="count",
                        order=order or list(values), labels=labels or {})


def _averages(values, *, category=RACE_CATEGORY):
    """values: {group: {year: (students, average)}} -> a Units-style source."""
    agg = pd.DataFrame([
        {"academic_year": y, "grp": g, "count": n, "avg_units": v}
        for g, by_year in values.items() for y, (n, v) in by_year.items()
    ])
    return EquitySource(category=category, agg=agg, key_col="grp", value_col="avg_units",
                        order=list(values), labels={})


def test_equity_year_is_the_latest_plan_year():
    assert equity_year(_targets()) == "2025-2026"


def test_equity_year_caps_at_the_plan_end():
    assert equity_year(_targets(["2022-2023", "2029-2030", "2030-2031"])) == "2029-2030"


def test_no_equity_year_or_table_with_only_the_baseline():
    only_base = _targets(["2022-2023"])
    assert equity_year(only_base) is None
    src = _counts({"g": {"2022-2023": 50}})
    assert build_equity_table(only_base, [src], min_count=10) is None


def test_values_and_status_per_group():
    src = _counts({"hisp": {"2022-2023": 100, "2025-2026": 120},
                   "asian": {"2022-2023": 50, "2025-2026": 50}},
                  labels={"hisp": "Latino/Hispanic", "asian": "Asian"})
    t = build_equity_table(_targets(), [src], min_count=10)
    assert t is not None
    assert (t.year, t.decimals) == ("2025-2026", False)
    assert list(t.rows["group"]) == ["Latino/Hispanic", "Asian"]
    assert list(t.rows["category"]) == [RACE_CATEGORY, RACE_CATEGORY]
    rows = t.rows.set_index("group")
    assert rows.loc["Latino/Hispanic", "baseline"] == 100
    assert rows.loc["Latino/Hispanic", "benchmark"] == pytest.approx(100 * F3)
    assert rows.loc["Latino/Hispanic", "actual"] == 120
    assert rows.loc["Latino/Hispanic", "variance"] == pytest.approx(120 - 100 * F3)
    assert rows.loc["Latino/Hispanic", "status"] == ON_TRACK
    assert rows.loc["Asian", "status"] == PROGRESSING


def test_ten_student_floor_in_both_years():
    src = _counts({
        "kept": {"2022-2023": 10, "2025-2026": 10},
        "small_base": {"2022-2023": 9, "2025-2026": 40},   # Noncredit Filipino shape
        "small_now": {"2022-2023": 40, "2025-2026": 9},
        "gone_now": {"2022-2023": 40},                      # no row at all in 2025-26
    })
    t = build_equity_table(_targets(), [src], min_count=10)
    assert t is not None
    assert list(t.rows["group"]) == ["kept"]


def test_rows_follow_the_given_order_and_skip_absent_groups():
    src = _counts({"b": {"2022-2023": 20, "2025-2026": 20},
                   "a": {"2022-2023": 20, "2025-2026": 20}},
                  order=["a", "not_in_data", "b"])
    t = build_equity_table(_targets(), [src], min_count=10)
    assert t is not None
    assert list(t.rows["group"]) == ["a", "b"]


def test_categories_stay_in_source_order():
    race = _counts({"r": {"2022-2023": 20, "2025-2026": 20}}, category=RACE_CATEGORY)
    gender = _counts({"g": {"2022-2023": 20, "2025-2026": 20}}, category=GENDER_CATEGORY)
    fg = _counts({"f": {"2022-2023": 20, "2025-2026": 20}}, category=FIRSTGEN_CATEGORY)
    t = build_equity_table(_targets(), [race, gender, fg], min_count=10)
    assert t is not None
    assert list(t.rows["category"]) == [RACE_CATEGORY, GENDER_CATEGORY, FIRSTGEN_CATEGORY]


def test_exact_hit_is_on_track_despite_float_noise():
    # Baseline 210 in 2023-24 (k=1): 210 * (1 + 0.3/7) == 219.00000000000003.
    src = _counts({"g": {"2022-2023": 210, "2023-2024": 219}})
    t = build_equity_table(_targets(["2022-2023", "2023-2024"]), [src], min_count=10)
    assert t is not None
    row = t.rows.iloc[0]
    assert row["variance"] == 0
    assert row["status"] == ON_TRACK


def test_lower_is_better_flips_status():
    src = _averages({"down": {"2022-2023": (40, 90.0), "2025-2026": (40, 80.0)},
                     "flat": {"2022-2023": (40, 80.0), "2025-2026": (40, 80.0)}})
    t = build_equity_table(_targets(rule=UNITS), [src], min_count=10)
    assert t is not None and t.decimals
    rows = t.rows.set_index("group")
    # 90 - (90 - 60) * 0.2 * 3/7 = 87.43; 80 is below it -> On Track.
    assert rows.loc["down", "benchmark"] == pytest.approx(90 - 30 * 0.2 * 3 / 7)
    assert rows.loc["down", "status"] == ON_TRACK
    assert rows.loc["flat", "status"] == PROGRESSING


def test_floor_counts_students_not_the_average():
    src = _averages({"few": {"2022-2023": (5, 90.0), "2025-2026": (5, 80.0)},
                     "many": {"2022-2023": (40, 90.0), "2025-2026": (40, 80.0)}})
    t = build_equity_table(_targets(rule=UNITS), [src], min_count=10)
    assert t is not None
    assert list(t.rows["group"]) == ["many"]


def test_group_with_a_missing_average_is_skipped():
    src = _averages({"no_hours": {"2022-2023": (40, math.nan), "2025-2026": (40, 80.0)},
                     "ok": {"2022-2023": (40, 90.0), "2025-2026": (40, 80.0)}})
    t = build_equity_table(_targets(rule=UNITS), [src], min_count=10)
    assert t is not None
    assert list(t.rows["group"]) == ["ok"]


def test_no_rows_means_no_table():
    src = _counts({"tiny": {"2022-2023": 3, "2025-2026": 4}})
    assert build_equity_table(_targets(), [src], min_count=10) is None


def test_heading_and_headers():
    src = _counts({"g": {"2022-2023": 20, "2025-2026": 20}})
    t = build_equity_table(_targets(), [src], min_count=10)
    assert t is not None
    assert t.heading == "Equity Results, 2025-26"
    assert t.headers() == {
        "category": "Category",
        "group": "Student Population",
        "baseline": "2022-23 Baseline",
        "benchmark": "2025-26 Benchmark",
        "actual": "2025-26 Actual",
        "variance": "Variance",
        "status": "Status",
    }


def test_note_is_generated_from_the_rule():
    assert equity_note(GROWTH) == (
        "Benchmark: 30% increase over the 2022-23 baseline by 2029-30, in equal "
        "annual steps. Variance = Actual − Benchmark."
    )
    assert equity_note(UNITS).endswith(
        "Lower is better. Variance = Actual − Benchmark. "
        "On Track = at or below the benchmark."
    )


def test_display_formats():
    assert format_value(1047.31, decimals=False) == "1,047"
    assert format_value(82.846, decimals=True) == "82.8"
    assert format_variance(69.69, decimals=False) == "+70"
    assert format_variance(-49.37, decimals=False) == "-49"
    assert format_variance(-0.39, decimals=False) == "0"
    assert format_variance(-0.14, decimals=True) == "-0.1"
    assert format_variance(0.04, decimals=True) == "0"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_bot_equity.py -q -p no:cacheprovider`
Expected: collection ERROR — `ModuleNotFoundError: No module named 'src.scripts.tabs.bot_equity'`.

- [ ] **Step 3: Write the module**

Create `src/scripts/tabs/bot_equity.py`:

```python
"""Vision 2030 equity tables for the BOT tabs (spec 2026-09-28).

For the latest plan year, each student population's actual against its own
benchmark — the group's 2022-23 value run through the tab's Vision 2030 rule
(the same ``group_baselines`` / ``group_target`` path as the Excel Summary
Counts ``{year} Benchmark`` column) — with Variance = Actual − Benchmark and
a Status.

Callers supply each category's aggregate of the plan frame (``bot_helpers``
for the count tabs, ``bot_goal3_units`` for average units). No Streamlit /
``bot_helpers`` imports, so every BOT module can use this one without a cycle.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from src.scripts.tabs.bot_targets import (
    BENCHMARK,
    PLAN_LENGTH,
    Targets,
    group_baselines,
    group_target,
    plan_years,
    short_year,
    target_caption,
    years_from_baseline,
)

ON_TRACK = "On Track"
PROGRESSING = "Progressing"

RACE_CATEGORY = "Race/Ethnicity"
GENDER_CATEGORY = "Gender"
FIRSTGEN_CATEGORY = "First Generation College Student Status"

COLUMNS = ["category", "group", "baseline", "benchmark", "actual", "variance", "status"]


@dataclass(frozen=True, eq=False)
class EquitySource:
    """One category's plan-frame aggregate: ``academic_year``, *key_col*,
    *value_col* and ``count`` (students, for the 10-student floor)."""

    category: str
    agg: pd.DataFrame
    key_col: str
    value_col: str
    order: list[str]
    labels: dict[str, str]


@dataclass(frozen=True, eq=False)
class EquityTable:
    year: str            # the equity year, e.g. "2025-2026"
    rows: pd.DataFrame   # COLUMNS, one row per shown group, in display order
    decimals: bool       # Units: 1 decimal; counts: whole numbers
    note: str

    @property
    def heading(self) -> str:
        return f"Equity Results, {short_year(self.year)}"

    def headers(self) -> dict[str, str]:
        year = short_year(self.year)
        return {
            "category": "Category",
            "group": "Student Population",
            "baseline": f"{short_year(plan_years()[0])} Baseline",
            "benchmark": f"{year} {BENCHMARK}",
            "actual": f"{year} Actual",
            "variance": "Variance",
            "status": "Status",
        }


def equity_year(targets: Targets) -> str | None:
    """Latest year after the baseline in the plan frame, capped at the plan end."""
    years = [
        y for y in targets.frame["academic_year"].dropna().astype(str).unique()
        if (k := years_from_baseline(y)) is not None and 1 <= k <= PLAN_LENGTH
    ]
    return max(years) if years else None


def _by_group(agg: pd.DataFrame, key_col: str, col: str, year: str) -> dict[str, float]:
    sel = agg[agg["academic_year"] == year]
    return {
        str(k): float(v)
        for k, v in zip(sel[key_col].astype(str), sel[col])
        if pd.notna(v)
    }


def build_equity_table(
    targets: Targets, sources: list[EquitySource], *, min_count: int,
) -> EquityTable | None:
    """The equity table, or None when there is no equity year or no group
    has *min_count* students in both the baseline and the equity year."""
    year = equity_year(targets)
    if year is None:
        return None
    base_year = plan_years()[0]
    lower_is_better = targets.rule.get("reduce_over") is not None
    rows = []
    for src in sources:
        base_n = _by_group(src.agg, src.key_col, "count", base_year)
        year_n = _by_group(src.agg, src.key_col, "count", year)
        actuals = _by_group(src.agg, src.key_col, src.value_col, year)
        baselines = group_baselines(src.agg, key_col=src.key_col, value_col=src.value_col)
        for key in src.order:
            if base_n.get(key, 0) < min_count or year_n.get(key, 0) < min_count:
                continue
            if key not in baselines or key not in actuals:
                continue
            benchmark = group_target(baselines, key, year, targets.rule)
            if pd.isna(benchmark):
                continue
            # round() so float noise (219.00000000000003) cannot turn an exact
            # hit into a miss.
            variance = round(actuals[key] - benchmark, 9)
            met = variance <= 0 if lower_is_better else variance >= 0
            rows.append({
                "category": src.category,
                "group": src.labels.get(key, key),
                "baseline": baselines[key],
                "benchmark": benchmark,
                "actual": actuals[key],
                "variance": variance,
                "status": ON_TRACK if met else PROGRESSING,
            })
    if not rows:
        return None
    return EquityTable(
        year=year, rows=pd.DataFrame(rows, columns=COLUMNS),
        decimals=targets.is_average, note=equity_note(targets.rule),
    )


def equity_note(rule: dict) -> str:
    """The note under the table — derived from the rule, like the chart caption."""
    text = f"{target_caption(rule)} Variance = Actual − {BENCHMARK}."
    if rule.get("reduce_over") is not None:
        text += f" {ON_TRACK} = at or below the {BENCHMARK.lower()}."
    return text


def format_value(value: float, *, decimals: bool) -> str:
    return f"{value:,.1f}" if decimals else f"{value:,.0f}"


def format_variance(value: float, *, decimals: bool) -> str:
    """Signed (``+70``, ``-49``, ``-0.1``); a value that rounds to zero is ``0``."""
    shown = round(value, 1) if decimals else round(value)
    if shown == 0:
        return "0"
    return f"{shown:+,.1f}" if decimals else f"{shown:+,.0f}"
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests/test_bot_equity.py -q -p no:cacheprovider`
Expected: all PASS. Then the full suite: `.venv/bin/python -m pytest tests -q -p no:cacheprovider` — all PASS.

- [ ] **Step 5: Lint gate**

Run: `ruff check src/scripts/tabs/bot_equity.py tests/test_bot_equity.py` → `All checks passed!`
Run: `pyright src/scripts/tabs/bot_equity.py tests/test_bot_equity.py` → `0 errors`.

- [ ] **Step 6: Commit**

```bash
git add src/scripts/tabs/bot_equity.py tests/test_bot_equity.py
git commit -m "feat(bot): equity table builder — per-group benchmark, variance, status

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01C43MCBdHeNgXj3RtSGCheA"
```

---

### Task 2: Count-tab tables and the Excel section

**Files:**
- Modify: `src/scripts/tabs/bot_helpers.py` (imports; new `equity_table()` near `headcount_campus_targets`, ~line 910)
- Modify: `src/scripts/tabs/bot_excel_helpers.py` (imports; new `equity_excel_section()` after `actual_vs_target_section`, ~line 122; `standard_bot_excel_sections`, ~line 351)
- Create: `tests/test_bot_equity_outputs.py` (the table as the tabs build and export it; Tasks 3–5 append here)

**Interfaces:**
- Consumes: Task 1's `EquitySource`, `EquityTable`, `build_equity_table`, category constants; existing `aggregate_race(df)`, `aggregate_gender(df)`, `aggregate_firstgen(df, *, credit_only)` (each returns `academic_year`, key, `count`, …), `RACE_ORDER`, `RACE_SHORT`, `GENDER_ORDER`, `GENDER_LABELS`, `FIRSTGEN_ORDER`, `FIRSTGEN_LABELS`, `CATEGORY_MIN_COUNT` (all in `bot_helpers`); `ExcelSection(title, df, percent_cols=(), integer_cols=(), decimal_cols=())`.
- Produces:
  - `bot_helpers.equity_table(targets: Targets | None, titles: dict) -> EquityTable | None` — None without targets or on a `headcount_only` tab.
  - `bot_excel_helpers.equity_excel_section(table: EquityTable) -> ExcelSection`
  - `standard_bot_excel_sections` puts the equity section second (right after the Actual vs Benchmark table) when there is one.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_bot_equity_outputs.py`:

```python
"""The equity table as the tabs build, draw and export it
(spec docs/superpowers/specs/2026-09-28-bot-equity-tables-design.md).

2025-26 is k=3 years after the 2022-23 baseline: growth factor 1 + 0.3*3/7.
"""

import pandas as pd
import pytest

from src.scripts.tabs.bot_equity import (
    FIRSTGEN_CATEGORY,
    GENDER_CATEGORY,
    PROGRESSING,
    RACE_CATEGORY,
)
from src.scripts.tabs.bot_excel_helpers import standard_bot_excel_sections
from src.scripts.tabs.bot_helpers import equity_table
from src.scripts.tabs.bot_targets import Targets

GROWTH = {"growth": 0.30}
UNITS = {"growth": 0.20, "reduce_over": 60, "value_col": "sum_hours_earned"}
F3 = 1 + 0.3 * 3 / 7

TITLES = {
    "tab_title": "BOT Goal 2 - Associate Degrees",
    "target_title": "Associate Degrees: Progress Toward 2029-30 Benchmark",
    "org": "NOCCCD Credit Colleges",
    "headcount_title": "HC", "headcount_caption": "c",
    "race_title": "Race", "race_caption": "c",
    "gender_title": "Gender", "gender_caption": "c",
    "firstgen_title": "FG", "firstgen_caption": "c",
}


def _frame(groups):
    """groups: {(race, gender, first_gen_ind, site): {year: students}} -> student rows."""
    rows, pidm = [], 0
    for (race, gender, fg, site), by_year in groups.items():
        for year, n in by_year.items():
            for _ in range(n):
                rows.append({
                    "pidm": pidm, "academic_year": year, "acyr_code": year[:4],
                    "camp_desc": "NOCE" if site == "Noncredit" else "Cypress",
                    "site": site, "race_description": race, "gender": gender,
                    "first_gen_ind": fg, "sum_hours_earned": 80.0,
                })
                pidm += 1
    return pd.DataFrame(rows)


# Female = Hispanic + Black (110 -> 130); Male = Asian + Filipino + White (85 -> 79);
# first-gen Y = Hispanic + Filipino (105 -> 140); N = Asian + Black + White (90 -> 69).
DISTRICT = {
    ("Hispanic or Latino", "F", "Y", "Credit"): {"2022-2023": 100, "2025-2026": 120},
    ("Asian", "M", "N", "Credit"): {"2022-2023": 50, "2025-2026": 50},
    ("Black or African American", "F", "N", "Credit"): {"2022-2023": 10, "2025-2026": 10},
    ("Filipino", "M", "Y", "Credit"): {"2022-2023": 5, "2025-2026": 20},
    ("White Non-Hispanic", "M", "N", "Credit"): {"2022-2023": 30, "2025-2026": 9},
}


def _district_targets():
    df = _frame(DISTRICT)
    return df, Targets(frame=df, rule=GROWTH)


def test_count_tab_rows_in_tab_order_and_labels():
    _, targets = _district_targets()
    t = equity_table(targets, TITLES)
    assert t is not None
    assert list(zip(t.rows["category"], t.rows["group"])) == [
        (RACE_CATEGORY, "Latino/Hispanic"),
        (RACE_CATEGORY, "Asian"),
        (RACE_CATEGORY, "Black or African American"),   # exactly 10 in both years
        (GENDER_CATEGORY, "Female"),
        (GENDER_CATEGORY, "Male"),
        (FIRSTGEN_CATEGORY, "First Generation Student"),
        (FIRSTGEN_CATEGORY, "Not First Generation Student"),
    ]
    rows = t.rows.set_index("group")
    assert rows.loc["Female", "baseline"] == 110
    assert rows.loc["Male", "actual"] == 79
    assert rows.loc["Male", "status"] == PROGRESSING    # 79 vs 85 * F3 = 95.9


def test_no_table_without_targets_or_on_headcount_only_tabs():
    _, targets = _district_targets()
    assert equity_table(None, TITLES) is None
    assert equity_table(targets, dict(TITLES, headcount_only=True)) is None


def test_first_gen_follows_the_tabs_credit_only_setting():
    df = _frame({
        ("Asian", "F", "Y", "Noncredit"): {"2022-2023": 20, "2025-2026": 30},
        ("Asian", "F", "N", "Credit"): {"2022-2023": 20, "2025-2026": 30},
    })
    targets = Targets(frame=df, rule=GROWTH)

    def first_gen(t):
        return list(t.rows.loc[t.rows["category"] == FIRSTGEN_CATEGORY, "group"])

    assert first_gen(equity_table(targets, TITLES)) == ["Not First Generation Student"]
    assert first_gen(equity_table(targets, dict(TITLES, credit_only_firstgen=False))) == [
        "First Generation Student", "Not First Generation Student",
    ]


def test_benchmark_matches_the_summary_counts_column():
    df, targets = _district_targets()
    sections = standard_bot_excel_sections(df, TITLES, base_df=df, targets=targets)
    summary = next(s for s in sections if s.title == "Race - Summary Counts").df
    expected = dict(zip(summary["Race/Ethnicity"], summary["2025-2026 Benchmark"]))
    t = equity_table(targets, TITLES)
    assert t is not None
    rows = t.rows.set_index("group")
    for group in ("Latino/Hispanic", "Asian"):
        assert rows.loc[group, "benchmark"] == pytest.approx(expected[group])


def test_excel_equity_section_follows_the_actual_vs_benchmark_table():
    df, targets = _district_targets()
    sections = standard_bot_excel_sections(df, TITLES, base_df=df, targets=targets)
    assert sections[0].title == TITLES["target_title"]
    eq = sections[1]
    assert eq.title == "Equity Results, 2025-26"
    assert list(eq.df.columns) == [
        "Category", "Student Population", "2022-23 Baseline", "2025-26 Benchmark",
        "2025-26 Actual", "Variance", "Status",
    ]
    assert eq.integer_cols == (
        "2022-23 Baseline", "2025-26 Benchmark", "2025-26 Actual", "Variance",
    )
    asian = eq.df.set_index("Student Population").loc["Asian"]
    assert asian["2025-26 Benchmark"] == pytest.approx(50 * F3)   # unrounded; Excel formats it
    assert asian["Status"] == PROGRESSING


def test_no_equity_section_on_headcount_only_tabs_or_without_targets():
    df, targets = _district_targets()
    titles = dict(TITLES, headcount_only=True, include_nocccd=False)
    for sections in (standard_bot_excel_sections(df, titles, targets=targets),
                     standard_bot_excel_sections(df, TITLES, base_df=df)):
        assert not any(s.title.startswith("Equity Results") for s in sections)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_bot_equity_outputs.py -q -p no:cacheprovider`
Expected: collection ERROR — `ImportError: cannot import name 'equity_table' from 'src.scripts.tabs.bot_helpers'`.

- [ ] **Step 3: Add `equity_table()` to `bot_helpers.py`**

Add the import next to the existing `bot_targets` import block (keep ruff's isort order: `bot_equity` sorts before `bot_targets`):

```python
from src.scripts.tabs.bot_equity import (
    FIRSTGEN_CATEGORY,
    GENDER_CATEGORY,
    RACE_CATEGORY,
    EquitySource,
    EquityTable,
    build_equity_table,
)
```

Add, right after `headcount_campus_targets()`:

```python
def equity_table(targets: Targets | None, titles: dict) -> EquityTable | None:
    """The tab's equity table (count tabs), or None without targets or on a
    headcount-only tab (Bachelor's has no race/gender/first-gen breakdown).

    Built from the plan frame, so it ignores the sidebar year selection.
    """
    if targets is None or titles.get("headcount_only"):
        return None
    frame = targets.frame
    credit_only = titles.get("credit_only_firstgen", True)
    sources = [
        EquitySource(category=RACE_CATEGORY, agg=aggregate_race(frame),
                     key_col="race_description", value_col="count",
                     order=RACE_ORDER, labels=RACE_SHORT),
        EquitySource(category=GENDER_CATEGORY, agg=aggregate_gender(frame),
                     key_col="gender", value_col="count",
                     order=GENDER_ORDER, labels=GENDER_LABELS),
        EquitySource(category=FIRSTGEN_CATEGORY,
                     agg=aggregate_firstgen(frame, credit_only=credit_only),
                     key_col="fg", value_col="count",
                     order=FIRSTGEN_ORDER, labels=FIRSTGEN_LABELS),
    ]
    return build_equity_table(targets, sources, min_count=CATEGORY_MIN_COUNT)
```

- [ ] **Step 4: Add the Excel section to `bot_excel_helpers.py`**

Add `EquityTable` to the imports (new import line, before the `bot_helpers` import block):

```python
from src.scripts.tabs.bot_equity import EquityTable
```

and add `equity_table` to the existing `from src.scripts.tabs.bot_helpers import (...)` list (alphabetical, after `compute_pct_change`).

Add after `actual_vs_target_section()`:

```python
def equity_excel_section(table: EquityTable) -> ExcelSection:
    """The equity table as one flat Excel table (Category column first), laid
    out like the manager's "Equity Analysis" sheet. Values stay unrounded;
    the number formats round them, like the other Benchmark columns."""
    headers = table.headers()
    df = table.rows.rename(columns=headers)
    nums = tuple(headers[c] for c in ("baseline", "benchmark", "actual", "variance"))
    if table.decimals:
        return ExcelSection(table.heading, df, decimal_cols=nums)
    return ExcelSection(table.heading, df, integer_cols=nums)
```

In `standard_bot_excel_sections`, replace:

```python
    if targets is not None:
        sections.append(actual_vs_target_section(titles, targets))
```

with:

```python
    if targets is not None:
        sections.append(actual_vs_target_section(titles, targets))
        equity = equity_table(targets, titles)
        if equity is not None:
            sections.append(equity_excel_section(equity))
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests -q -p no:cacheprovider`
Expected: all PASS — including the existing `tests/test_bot_target_excel.py::test_no_reader_facing_target_wording_in_the_workbook`, which now also walks the equity section.

- [ ] **Step 6: Lint gate**

Run per changed file (expect identical counts on `main` and branch for `bot_helpers.py`; 0 for the others):
```bash
for f in src/scripts/tabs/bot_helpers.py src/scripts/tabs/bot_excel_helpers.py tests/test_bot_equity_outputs.py; do
  new=$(ruff check --output-format concise "$f" | grep -c ":[0-9]*:[0-9]*:")
  old=$(git show main:"$f" 2>/dev/null | ruff check --stdin-filename "$f" --output-format concise - | grep -c ":[0-9]*:[0-9]*:")
  echo "$f main=$old branch=$new"
done
```
Run: `pyright src/scripts/tabs/bot_helpers.py src/scripts/tabs/bot_excel_helpers.py tests/test_bot_equity_outputs.py` and compare the error total with the same command on `main` (via `git stash`): no increase.

- [ ] **Step 7: Commit**

```bash
git add src/scripts/tabs/bot_helpers.py src/scripts/tabs/bot_excel_helpers.py tests/test_bot_equity_outputs.py
git commit -m "feat(bot): equity table for the count tabs and its Excel section

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01C43MCBdHeNgXj3RtSGCheA"
```

---

### Task 3: PDF page 1

**Files:**
- Modify: `src/scripts/tabs/bot_equity.py` (imports; `mpl_equity_table()` + colour constants)
- Modify: `src/scripts/tabs/bot_helpers.py` (`add_target_page` ~line 1133; its call in `generate_bot_pdf` ~line 1519)
- Test: `tests/test_bot_equity_outputs.py` (append), `tests/test_bot_equity.py` (append the fit test)

**Interfaces:**
- Consumes: Task 1 `EquityTable`, `COLUMNS`, `format_value`, `format_variance`, `ON_TRACK`; Task 2 `bot_helpers.equity_table`.
- Produces:
  - `bot_equity.BAND_COLOR = "#004062"`, `STATUS_FILL = {ON_TRACK: ("#d6eaf8", "#1d4f6e"), PROGRESSING: ("#f4c3a8", "#7a3f22")}` (light, dark)
  - `bot_equity.mpl_equity_table(fig, table: EquityTable, *, top: float, bottom: float) -> None` — heading at paper y *top*; table and note fit above *bottom*.
  - `bot_helpers.add_target_page(pdf, titles, targets, equity: EquityTable | None = None)` — draws the table in page 1's bottom half when given. (Units will pass its own table in Task 5.)

- [ ] **Step 1: Write the failing tests**

In `tests/test_bot_equity_outputs.py`, add `import io` and `from pypdf import PdfReader` to the top import block, change the `bot_helpers` import to `from src.scripts.tabs.bot_helpers import equity_table, generate_bot_pdf`, and append:

```python
# ---------------------------------------------------------------------------
# PDF page 1
# ---------------------------------------------------------------------------


def _pdf_pages(pdf: bytes):
    return PdfReader(io.BytesIO(pdf)).pages


def test_pdf_page_one_carries_the_equity_table():
    df, targets = _district_targets()
    pages = _pdf_pages(generate_bot_pdf(df, TITLES, base_df=df, targets=targets))
    assert len(pages) == 3                      # unchanged: the table uses page 1's free half
    text = pages[0].extract_text()
    assert "Equity Results, 2025-26" in text
    assert "On Track" in text and "Progressing" in text
    assert "Variance = Actual" in text
    assert "Target" not in text


def test_headcount_only_pdf_has_no_equity_table():
    df, targets = _district_targets()
    titles = dict(TITLES, headcount_only=True, include_nocccd=False)
    pages = _pdf_pages(generate_bot_pdf(df, titles, targets=targets))
    assert len(pages) == 2
    assert "Equity Results" not in pages[0].extract_text()


def test_equity_ignores_the_sidebar_year_selection():
    df, targets = _district_targets()
    shown = df[df["academic_year"] == "2022-2023"]          # sidebar narrowed to one year
    pages = _pdf_pages(generate_bot_pdf(shown, TITLES, base_df=shown, targets=targets))
    assert "Equity Results, 2025-26" in pages[0].extract_text()
```

Append to `tests/test_bot_equity.py` (it has the `_counts` / `_targets` helpers):

```python
def test_tallest_table_fits_above_the_footer():
    import matplotlib.pyplot as plt
    from matplotlib.patches import Rectangle

    from src.scripts.tabs.bot_equity import mpl_equity_table

    def every_group(keys, category):
        return _counts({k: {"2022-2023": 40, "2025-2026": 50} for k in keys}, category=category)

    t = build_equity_table(_targets(), [
        every_group([f"race{i}" for i in range(9)], RACE_CATEGORY),
        every_group([f"gender{i}" for i in range(4)], GENDER_CATEGORY),
        every_group([f"fg{i}" for i in range(3)], FIRSTGEN_CATEGORY),
    ], min_count=10)
    assert t is not None and len(t.rows) == 16
    fig = plt.figure(figsize=(8.5, 11.0))
    try:
        mpl_equity_table(fig, t, top=0.505, bottom=0.045)
        ax = fig.axes[0]
        rects = [p for p in ax.patches if isinstance(p, Rectangle)]
        # Every cell sits inside the axes, and the axes sit above *bottom*.
        assert min(r.get_y() for r in rects) >= -1e-9
        assert ax.get_position().y0 >= 0.045
        bands = [r for r in rects if r.get_width() == pytest.approx(1.0)]
        assert len(bands) == 3
        heading, note = fig.texts[0], fig.texts[-1]
        assert heading.get_text() == "Equity Results, 2025-26"
        assert note.get_position()[1] > 0.045       # the note clears the footer area
    finally:
        plt.close(fig)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_bot_equity.py tests/test_bot_equity_outputs.py -q -p no:cacheprovider`
Expected: FAIL — `"Equity Results, 2025-26" in text` is False, and `ImportError: cannot import name 'mpl_equity_table'`.

- [ ] **Step 3: Add the matplotlib renderer to `bot_equity.py`**

Add to the imports:

```python
import textwrap

from matplotlib.patches import Rectangle
```

Add after `COLUMNS`:

```python
BAND_COLOR = "#004062"   # NOCCCD Dark Teal, as in the manager's tables
# Status fill: (light theme / PDF, dark theme).
STATUS_FILL = {ON_TRACK: ("#d6eaf8", "#1d4f6e"), PROGRESSING: ("#f4c3a8", "#7a3f22")}

# Shown columns (Category becomes the band rows) and their x edges on the PDF.
_SHOWN = [c for c in COLUMNS if c != "category"]
_COL_EDGES = (0.0, 0.34, 0.47, 0.60, 0.73, 0.85, 1.0)
_ALIGN = {"group": "left", "status": "center"}   # everything else right
_MAX_ROW_H = 0.021       # paper units; rows shrink below this to fit
_HEADER_ROWS = 1.6       # the header row is 1.6 rows tall (two-line labels)
```

Add at the end of the module:

```python
def _cell_texts(row: dict, decimals: bool) -> list[str]:
    return [
        str(row["group"]),
        format_value(row["baseline"], decimals=decimals),
        format_value(row["benchmark"], decimals=decimals),
        format_value(row["actual"], decimals=decimals),
        format_variance(row["variance"], decimals=decimals),
        str(row["status"]),
    ]


def _two_line(header: str) -> str:
    """``"2025-26 Benchmark"`` -> ``"2025-26\\nBenchmark"``; one-word headers as is."""
    return header.replace(" ", "\n", 1) if header[:1].isdigit() else header


def mpl_equity_table(fig, table: EquityTable, *, top: float, bottom: float) -> None:
    """Heading, table and note between paper y *top* and *bottom* (PDF page 1).

    Drawn with Rectangle patches so each category is one full-width band. Row
    height shrinks to fit, so the tallest table (16 groups + 3 bands) still
    ends above *bottom*.
    """
    fig.text(0.06, top, table.heading, fontsize=10, fontweight="bold", va="top")
    note = textwrap.fill(table.note, width=140)
    note_h = 0.012 * (note.count("\n") + 1)
    ax_top, ax_bottom = top - 0.03, bottom + note_h + 0.01
    ax_h = ax_top - ax_bottom
    ax = fig.add_axes((0.06, ax_bottom, 0.88, ax_h))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")

    records = table.rows.to_dict("records")
    n_bands = table.rows["category"].nunique()
    row_h = min(_MAX_ROW_H / ax_h, 1 / (len(records) + n_bands + _HEADER_ROWS))
    headers = table.headers()

    def draw_row(y: float, h: float, texts: list[str], *, bold: bool,
                 fills: list[str] | None = None, header: bool = False) -> None:
        for i, text in enumerate(texts):
            x0, x1 = _COL_EDGES[i], _COL_EDGES[i + 1]
            fill = fills[i] if fills else "white"
            ax.add_patch(Rectangle((x0, y - h), x1 - x0, h, facecolor=fill,
                                   edgecolor="#444444", linewidth=0.5))
            align = "center" if header else _ALIGN.get(_SHOWN[i], "right")
            tx = {"left": x0 + 0.01, "center": (x0 + x1) / 2, "right": x1 - 0.01}[align]
            # Status is bold, as in the manager's tables.
            weight = "bold" if bold or (not header and _SHOWN[i] == "status") else "normal"
            ax.text(tx, y - h / 2, text, ha=align, va="center", fontsize=7,
                    fontweight=weight)

    y = 1.0
    header_h = row_h * _HEADER_ROWS
    draw_row(y, header_h, [_two_line(headers[c]) for c in _SHOWN], bold=True, header=True)
    y -= header_h
    category = None
    for row in records:
        if row["category"] != category:
            category = row["category"]
            ax.add_patch(Rectangle((0, y - row_h), 1.0, row_h, facecolor=BAND_COLOR,
                                   edgecolor=BAND_COLOR, linewidth=0.5))
            ax.text(0.5, y - row_h / 2, str(category), ha="center", va="center",
                    fontsize=7.5, fontweight="bold", color="white")
            y -= row_h
        fills = ["white"] * 5 + [STATUS_FILL[row["status"]][0]]
        draw_row(y, row_h, _cell_texts(row, table.decimals), bold=False, fills=fills)
        y -= row_h

    table_bottom = ax_bottom + y * ax_h
    fig.text(0.06, table_bottom - 0.008, note, fontsize=6.5, color="#555555", va="top")
```

- [ ] **Step 4: Draw it on page 1 in `bot_helpers.py`**

Add `mpl_equity_table` to the `bot_equity` import block. Change `add_target_page`:

```python
def add_target_page(pdf, titles: dict, targets: Targets,
                    equity: EquityTable | None = None) -> None:
    """PDF page 1 for target tabs. The existing pages follow unchanged.

    *equity* (when given) fills the page's bottom half under the chart.
    The caller has already forced the light-theme rcParams.
    """
```

and, between `_draw_section_source(fig, 0.54, ...)` and `_add_pdf_footer(fig)`, insert:

```python
    if equity is not None:
        mpl_equity_table(fig, equity, top=0.505, bottom=0.045)
```

In `generate_bot_pdf`, change `add_target_page(pdf, titles, targets)` to:

```python
            add_target_page(pdf, titles, targets, equity=equity_table(targets, titles))
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests -q -p no:cacheprovider`
Expected: all PASS (existing page-count tests in `tests/test_bot_target_chart.py` and `tests/test_bot_campus_targets.py` unchanged).

- [ ] **Step 6: Look at the page**

Render page 1 from the synthetic district and check it by eye (heading, three bands, coloured Status cells, note under the table, nothing overlapping the footer):

```bash
PYTHONPATH=. .venv/bin/python - <<'EOF'
import fitz, sys
sys.path.insert(0, "tests")
from test_bot_equity_outputs import TITLES, _district_targets
from src.scripts.tabs.bot_helpers import generate_bot_pdf
df, targets = _district_targets()
pdf = generate_bot_pdf(df, TITLES, base_df=df, targets=targets)
fitz.open(stream=pdf, filetype="pdf")[0].get_pixmap(dpi=110).save(".playwright-mcp/equity_task3_p1.png")
EOF
```

Open `.playwright-mcp/equity_task3_p1.png` and confirm the layout.

- [ ] **Step 7: Lint gate** — as Task 2 Step 6, for `bot_equity.py`, `bot_helpers.py`, `tests/test_bot_equity.py`, `tests/test_bot_equity_outputs.py`.

- [ ] **Step 8: Commit**

```bash
git add src/scripts/tabs/bot_equity.py src/scripts/tabs/bot_helpers.py tests/test_bot_equity.py tests/test_bot_equity_outputs.py
git commit -m "feat(bot): equity table on PDF page 1 under the Actual vs Benchmark chart

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01C43MCBdHeNgXj3RtSGCheA"
```

---

### Task 4: Streamlit tab

**Files:**
- Modify: `src/scripts/tabs/bot_equity.py` (`equity_html()`)
- Modify: `src/scripts/tabs/bot_helpers.py` (`render_equity_table()`; `render_target_section` ~line 888; its call in `render_bot_charts` ~line 978)
- Test: `tests/test_bot_equity_outputs.py` (append)

**Interfaces:**
- Consumes: Task 1 `EquityTable`, formatters; Task 3 `BAND_COLOR`, `STATUS_FILL`, `_SHOWN`, `_ALIGN`; Task 2 `equity_table`.
- Produces:
  - `bot_equity.equity_html(table: EquityTable) -> str`
  - `bot_helpers.render_equity_table(table: EquityTable) -> None` (bold heading, the HTML table, the note as a caption)
  - `bot_helpers.render_target_section(titles, targets, equity: EquityTable | None = None)` — draws the table after the chart's Source line, before the divider. (Units will pass its own table in Task 5.)

- [ ] **Step 1: Write the failing tests**

In `tests/test_bot_equity_outputs.py`, add `equity_html` to the top `from src.scripts.tabs.bot_equity import (...)` block and append:

```python
# ---------------------------------------------------------------------------
# Streamlit tab
# ---------------------------------------------------------------------------


def test_html_has_bands_status_cells_and_both_themes():
    _, targets = _district_targets()
    t = equity_table(targets, TITLES)
    assert t is not None
    html = equity_html(t)
    for band in (RACE_CATEGORY, GENDER_CATEGORY, FIRSTGEN_CATEGORY):
        assert f">{band}</td>" in html
    # On Track: Latino/Hispanic, Female, First Gen. Progressing: Asian, Black, Male, Not First Gen.
    assert html.count(">On Track</td>") == 3
    assert html.count(">Progressing</td>") == 4
    assert "2025-26<br>Benchmark" in html
    assert ">-6</td>" in html                     # Asian: 50 - 56.43
    assert "light-dark(#d6eaf8, #1d4f6e)" in html
    assert "Target" not in html


def test_tab_renders_heading_table_and_note(monkeypatch):
    from src.scripts.tabs import bot_helpers

    calls = []
    monkeypatch.setattr(bot_helpers.st, "markdown",
                        lambda body, **kwargs: calls.append(("markdown", body)))
    monkeypatch.setattr(bot_helpers.st, "caption",
                        lambda body, **kwargs: calls.append(("caption", body)))
    _, targets = _district_targets()
    t = equity_table(targets, TITLES)
    assert t is not None
    bot_helpers.render_equity_table(t)
    assert calls[0] == ("markdown", "**Equity Results, 2025-26**")
    assert calls[1][0] == "markdown" and calls[1][1].startswith("<table")
    assert calls[2] == ("caption", t.note)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_bot_equity_outputs.py -q -p no:cacheprovider`
Expected: collection ERROR — `ImportError: cannot import name 'equity_html'`.

- [ ] **Step 3: Add `equity_html()` to `bot_equity.py`**

```python
_TH = "padding:6px 10px; border-bottom:2px solid #555; text-align:{align};"
_TD = "padding:4px 10px; border-bottom:1px solid #888; text-align:{align};"


def equity_html(table: EquityTable) -> str:
    """The equity table as HTML for ``st.markdown``. Status fills use
    ``light-dark()`` like the tab's other HTML tables, so both themes read."""
    headers = table.headers()
    out = ['<table style="border-collapse:collapse; font-size:13px;">', "<thead><tr>"]
    for col in _SHOWN:
        label = _two_line(headers[col]).replace("\n", "<br>")
        out.append(f"<th style='{_TH.format(align=_ALIGN.get(col, 'right'))}'>{label}</th>")
    out.append("</tr></thead><tbody>")
    category = None
    for row in table.rows.to_dict("records"):
        if row["category"] != category:
            category = row["category"]
            out.append(
                f"<tr><td colspan='{len(_SHOWN)}' style='background:{BAND_COLOR}; "
                "color:#FFFFFF; font-weight:bold; text-align:center; padding:5px;'>"
                f"{category}</td></tr>"
            )
        cells = []
        for col, text in zip(_SHOWN, _cell_texts(row, table.decimals)):
            style = _TD.format(align=_ALIGN.get(col, "right"))
            if col == "status":
                light, dark = STATUS_FILL[row["status"]]
                style += f" background:light-dark({light}, {dark}); font-weight:bold;"
            cells.append(f"<td style='{style}'>{text}</td>")
        out.append("<tr>" + "".join(cells) + "</tr>")
    out.append("</tbody></table>")
    return "\n".join(out)
```

- [ ] **Step 4: Render it on the tab (`bot_helpers.py`)**

Add `equity_html` to the `bot_equity` import block. Add near `render_target_section`:

```python
def render_equity_table(table: EquityTable) -> None:
    st.markdown(f"**{table.heading}**")
    st.markdown(equity_html(table), unsafe_allow_html=True)
    st.caption(table.note)
```

Change `render_target_section`'s signature and tail:

```python
def render_target_section(titles: dict, targets: Targets,
                          equity: EquityTable | None = None) -> None:
    """Chart 0: district Actual vs Benchmark, 2022-23 -> 2029-30, and the
    equity table under it when given.

    Always the full plan — it does not follow the Academic Years selection.
    """
    ...
    st.markdown(_source_html(titles), unsafe_allow_html=True)
    if equity is not None:
        render_equity_table(equity)
    st.divider()
```

In `render_bot_charts`, change `render_target_section(titles, targets)` to:

```python
        render_target_section(titles, targets, equity=equity_table(targets, titles))
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests -q -p no:cacheprovider`
Expected: all PASS.

- [ ] **Step 6: Lint gate** — as Task 2 Step 6, for `bot_equity.py`, `bot_helpers.py`, `tests/test_bot_equity_outputs.py`.

- [ ] **Step 7: Commit**

```bash
git add src/scripts/tabs/bot_equity.py src/scripts/tabs/bot_helpers.py tests/test_bot_equity_outputs.py
git commit -m "feat(bot): equity table on the tab under the Actual vs Benchmark chart

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01C43MCBdHeNgXj3RtSGCheA"
```

---

### Task 5: Average Units tab

**Files:**
- Modify: `src/scripts/tabs/bot_goal3_units.py` (imports; `_aggregate_firstgen` ~line 212; new `_equity_table()` after `_campus_targets` ~line 273; `_generate_pdf` ~line 927; `units_excel_sections` ~line 1046; render ~line 1298)
- Test: `tests/test_bot_equity_outputs.py` (append)

**Interfaces:**
- Consumes: Task 1 `EquitySource`, `build_equity_table`, category constants; Task 2 `equity_excel_section`; Task 3 `add_target_page(..., equity=)`; Task 4 `render_target_section(..., equity=)`; `bot_helpers.CATEGORY_MIN_COUNT`.
- Produces: `bot_goal3_units._equity_table(targets: Targets | None) -> EquityTable | None`; `_aggregate_firstgen` output gains a `count` column (students per group per year). Every existing consumer of `_aggregate_firstgen` names `avg_units` / `fg_label` explicitly (`_build_firstgen_chart`, `_build_firstgen_summary`, `_mpl_firstgen_chart`, `_mpl_firstgen_summary`, `matrix_table(..., value_col="avg_units")`, `value_summary(..., value_col="avg_units")`, the Detail section's explicit column list), so the extra column changes no output.

- [ ] **Step 1: Write the failing tests**

In `tests/test_bot_equity_outputs.py`, add `from src.scripts.tabs import bot_goal3_units` to the top import block, add `ON_TRACK` to the `bot_equity` import, and append:

```python
# ---------------------------------------------------------------------------
# Average Units (lower is better)
# ---------------------------------------------------------------------------


def _units_frame(groups):
    """groups: {(race, gender, first_gen_ind): {year: (students, hours)}}."""
    rows, pidm = [], 0
    for (race, gender, fg), by_year in groups.items():
        for year, (n, hours) in by_year.items():
            for _ in range(n):
                rows.append({
                    "pidm": pidm, "academic_year": year, "acyr_code": year[:4],
                    "camp_desc": "Cypress", "site": "Credit",
                    "race_description": race, "gender": gender,
                    "first_gen_ind": fg, "sum_hours_earned": hours,
                })
                pidm += 1
    return pd.DataFrame(rows)


# Hispanic falls 90 -> 80 (below its 87.4 benchmark: On Track); Asian stays at 80
# (above 78.3: Progressing).
UNITS_DISTRICT = {
    ("Hispanic or Latino", "F", "Y"): {"2022-2023": (40, 90.0), "2025-2026": (40, 80.0)},
    ("Asian", "M", "N"): {"2022-2023": (40, 80.0), "2025-2026": (40, 80.0)},
}


def test_units_equity_uses_averages_and_lower_is_better():
    df = _units_frame(UNITS_DISTRICT)
    t = bot_goal3_units._equity_table(Targets(frame=df, rule=UNITS))
    assert t is not None and t.decimals
    rows = t.rows[t.rows["category"] == RACE_CATEGORY].set_index("group")
    assert rows.loc["Latino/Hispanic", "baseline"] == pytest.approx(90.0)
    assert rows.loc["Latino/Hispanic", "benchmark"] == pytest.approx(90 - 30 * 0.2 * 3 / 7)
    assert rows.loc["Latino/Hispanic", "status"] == ON_TRACK
    assert rows.loc["Asian", "status"] == PROGRESSING
    assert "On Track = at or below the benchmark." in t.note


def test_units_first_gen_aggregate_counts_students():
    agg = bot_goal3_units._aggregate_firstgen(_units_frame(UNITS_DISTRICT))
    by = agg.set_index(["academic_year", "fg"])["count"]
    assert by[("2022-2023", "Y")] == 40


def test_units_excel_and_pdf_carry_the_equity_table():
    df = _units_frame(UNITS_DISTRICT)
    targets = Targets(frame=df, rule=UNITS)
    sections = bot_goal3_units.units_excel_sections(df, targets=targets)
    assert sections[0].title == bot_goal3_units._TITLES["target_title"]
    assert sections[1].title == "Equity Results, 2025-26"
    assert sections[1].decimal_cols == (
        "2022-23 Baseline", "2025-26 Benchmark", "2025-26 Actual", "Variance",
    )
    pages = _pdf_pages(bot_goal3_units.generate_pdf(df, targets=targets))
    assert len(pages) == 3
    assert "Equity Results, 2025-26" in pages[0].extract_text()


def test_units_without_targets_has_no_equity_table():
    df = _units_frame(UNITS_DISTRICT)
    assert bot_goal3_units._equity_table(None) is None
    sections = bot_goal3_units.units_excel_sections(df)
    assert not any(s.title.startswith("Equity Results") for s in sections)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest tests/test_bot_equity_outputs.py -q -p no:cacheprovider`
Expected: FAIL — `AttributeError: module 'src.scripts.tabs.bot_goal3_units' has no attribute '_equity_table'`, and `KeyError: 'count'` in the first-gen test.

- [ ] **Step 3: Count students in `_aggregate_firstgen`**

Replace the body's aggregation in `_aggregate_firstgen`:

```python
    out = (
        stu.groupby(["academic_year", "fg"])["sum_hours_earned"]
        .mean()
        .reset_index(name="avg_units")
    )
```

with (matching `_aggregate_race` / `_aggregate_gender`):

```python
    out = (
        stu.groupby(["academic_year", "fg"])
        .agg(
            avg_units=("sum_hours_earned", "mean"),
            count=("pidm", "nunique"),
        )
        .reset_index()
    )
```

- [ ] **Step 4: Add `_equity_table()` and wire the three outputs**

Imports: add to the `bot_excel_helpers` import list `equity_excel_section`; add to the `bot_helpers` import list `CATEGORY_MIN_COUNT`; add a new import block:

```python
from src.scripts.tabs.bot_equity import (
    FIRSTGEN_CATEGORY,
    GENDER_CATEGORY,
    RACE_CATEGORY,
    EquitySource,
    EquityTable,
    build_equity_table,
)
```

After `_campus_targets()`:

```python
def _equity_table(targets: Targets | None) -> EquityTable | None:
    """Units' equity table: average units per group, where lower is better."""
    if targets is None:
        return None
    frame = targets.frame
    sources = [
        EquitySource(category=RACE_CATEGORY, agg=_aggregate_race(frame),
                     key_col="race_description", value_col="avg_units",
                     order=RACE_ORDER, labels=RACE_SHORT),
        EquitySource(category=GENDER_CATEGORY, agg=_aggregate_gender(frame),
                     key_col="gender", value_col="avg_units",
                     order=GENDER_ORDER, labels=GENDER_LABELS),
        EquitySource(category=FIRSTGEN_CATEGORY, agg=_aggregate_firstgen(frame),
                     key_col="fg", value_col="avg_units",
                     order=FIRSTGEN_ORDER, labels=FIRSTGEN_LABELS),
    ]
    return build_equity_table(targets, sources, min_count=CATEGORY_MIN_COUNT)
```

In `_generate_pdf`, change `add_target_page(pdf, _TITLES, targets)` to:

```python
            add_target_page(pdf, _TITLES, targets, equity=_equity_table(targets))
```

In `units_excel_sections`, replace:

```python
    if targets is not None:
        sections.append(actual_vs_target_section(_TITLES, targets))
```

with:

```python
    if targets is not None:
        sections.append(actual_vs_target_section(_TITLES, targets))
        equity = _equity_table(targets)
        if equity is not None:
            sections.append(equity_excel_section(equity))
```

In the render, change `render_target_section(_TITLES, targets)` to:

```python
        render_target_section(_TITLES, targets, equity=_equity_table(targets))
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest tests -q -p no:cacheprovider`
Expected: all PASS.

- [ ] **Step 6: Lint gate** — as Task 2 Step 6, for `bot_goal3_units.py` and `tests/test_bot_equity_outputs.py`.

- [ ] **Step 7: Commit**

```bash
git add src/scripts/tabs/bot_goal3_units.py tests/test_bot_equity_outputs.py
git commit -m "feat(bot): equity table on the Average Units tab (lower is better)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01C43MCBdHeNgXj3RtSGCheA"
```

---

### Task 6: Docs and real-data verification

**Files:**
- Modify: `docs/bot-tabs.md` (the "Vision 2030 targets (Actual vs Benchmark)" section; the "BOT PDF paper coordinates" list)
- Modify: `docs/exports.md` ("Vision 2030 target data")
- Modify: `docs/deferred.md` (cluster 7, item 1)

**Interfaces:**
- Consumes: everything above. Produces: no code.

- [ ] **Step 1: Document the table**

In `docs/bot-tabs.md`, add after the "Campus Excel table" bullet of the Vision 2030 section:

```markdown
- **Equity table** (`src/scripts/tabs/bot_equity.py`, spec `docs/superpowers/specs/2026-09-28-bot-equity-tables-design.md`): under the Actual vs Benchmark chart on 6 tabs (not Bachelor's, a `headcount_only` tab), "Equity Results, {latest year}" compares each race/ethnicity, gender and first-gen group's latest-year actual with its own benchmark: `Student Population | 2022-23 Baseline | {year} Benchmark | {year} Actual | Variance | Status`. The year is the latest plan year in the extract (capped at 2029-30) and ignores the sidebar. A group is shown only with 10+ students (`CATEGORY_MIN_COUNT`) in both 2022-23 and that year — the two counts the table prints — so e.g. Noncredit Filipino (2 students in 2022-23) is left out even though the race chart shows it. Benchmarks come from the same `group_baselines` / `group_target` path as the Summary Counts `{year} Benchmark` column. Variance = Actual − Benchmark (unrounded; rounded for display); Status is "On Track" when Variance ≥ 0 ("≤ 0" on Units, where lower is better), else "Progressing". The note under the table is generated from the rule. Count tabs build it with `bot_helpers.equity_table()`, Units with `bot_goal3_units._equity_table()` (average units); `render_target_section(..., equity=)` / `add_target_page(..., equity=)` draw it on the tab and in the PDF's page-1 bottom half, and `equity_excel_section()` adds a flat Excel table right after the Actual vs Benchmark table.
```

In the "BOT PDF paper coordinates" list, extend the Actual vs Benchmark page bullet with: `Equity table (when present): heading at y=0.505, table + note between 0.475 and 0.045 (rows shrink to fit, max 0.021).`

In `docs/exports.md`, extend the "Vision 2030 target data" paragraph with: `On the 6 tabs with an equity breakdown (not Bachelor's), PDF page 1 also carries the "Equity Results" table under the chart, and the Excel export adds it as a flat table right after the Actual vs Benchmark table (see docs/bot-tabs.md).`

In `docs/deferred.md` cluster 7 item 1, add after the sentence ending "(or gate once where `target_of` is built, `bot_excel_helpers.py::_target_fn`)." : `The equity table does not have this problem: bot_equity.py::equity_year caps the year at the plan end, so from the 2031 run it keeps showing 2029-30, the plan's final result.`

- [ ] **Step 2: Check live numbers against the manager's workbook**

```bash
PYTHONPATH=. .venv/bin/python - <<'EOF' 2>/dev/null
from src.pipeline.hyper_cache import HyperCache
from src.scripts.tabs import bot_goal2_assoc, bot_goal3_units
from src.scripts.tabs.bot_helpers import equity_table
from src.scripts.tabs.bot_targets import targets_from_cache
cache = HyperCache()
aa = equity_table(targets_from_cache(cache, "bot_goal2_assoc"), bot_goal2_assoc._TITLES)
print(aa.rows.to_string())
units = bot_goal3_units._equity_table(targets_from_cache(cache, "bot_goal3_units"))
print(units.rows.to_string())
EOF
```

Expected (workbook "AA" sheet, rows 28-42): Asian baseline 244, benchmark ≈ 275.37, actual 226, variance ≈ −49.37, Progressing. Latino/Hispanic, Male and First Gen may differ by 1 student (the extract was refreshed after the workbook was built). Units Latino/Hispanic: ≈ 82.4 → 80.5 → 80.3, On Track.

- [ ] **Step 3: Check the running app and the PDFs**

Start the app (`.venv/bin/streamlit run src/scripts/streamlit_app.py --server.headless true --server.port 8599`, background). With Playwright, open "BOT Goal 2 - Associate Degrees", press Query, and confirm: the "Equity Results, 2025-26" heading and table sit under the Actual vs Benchmark chart; no `.stException`; in dark theme the Status cells stay readable. Repeat on "BOT Goal 3 - Average Units" and "BOT Goal 2 - Bachelor's Degrees" (the latter must have no equity table). Screenshots go under `.playwright-mcp/`; Streamlit's main area scrolls in its own container, so use `element.scrollIntoView()`. Stop the server when done.

Render the bulk PDF and Excel into a scratch dir and check page counts are unchanged and each in-scope tab's page 1 shows the table:

```bash
BOT_EXPORT_ROOT_PDF=/private/tmp/claude-501/-Users-hoonywise-GitHub-nocccd-data-nocccd-streamlit/4e4093a6-7086-402d-a9e2-7dbea7b025ab/scratchpad/bulk_pdf PYTHONPATH=. .venv/bin/python -m src.pipeline.bot_export
BOT_EXPORT_ROOT_EXCEL=/private/tmp/claude-501/-Users-hoonywise-GitHub-nocccd-data-nocccd-streamlit/4e4093a6-7086-402d-a9e2-7dbea7b025ab/scratchpad/bulk_xlsx PYTHONPATH=. .venv/bin/python -m src.pipeline.bot_excel_export
```

- [ ] **Step 4: Full test + lint gate**

Run: `.venv/bin/python -m pytest tests -q -p no:cacheprovider` → all PASS.
Run the per-file ruff comparison and the pyright total comparison over every file changed on the branch (`git diff --name-only main -- '*.py'`): no new diagnostics.

- [ ] **Step 5: Commit**

```bash
git add docs/bot-tabs.md docs/exports.md docs/deferred.md
git commit -m "docs(bot): equity tables

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01C43MCBdHeNgXj3RtSGCheA"
```
