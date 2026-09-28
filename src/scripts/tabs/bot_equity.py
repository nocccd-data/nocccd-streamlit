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

import math
import textwrap
from dataclasses import dataclass

import pandas as pd
from matplotlib.patches import Rectangle

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

BAND_COLOR = "#004062"   # NOCCCD Dark Teal, as in the manager's tables
# Status fill: (light theme / PDF, dark theme).
STATUS_FILL = {ON_TRACK: ("#d6eaf8", "#1d4f6e"), PROGRESSING: ("#f4c3a8", "#7a3f22")}

# Shown columns (Category becomes the band rows) and their x edges on the PDF.
_SHOWN = [c for c in COLUMNS if c != "category"]
_COL_EDGES = (0.0, 0.34, 0.47, 0.60, 0.73, 0.85, 1.0)
_ALIGN = {"group": "left", "status": "center"}   # everything else right
_MAX_ROW_H = 0.021       # paper units; rows shrink below this to fit
_HEADER_ROWS = 1.6       # the header row is 1.6 rows tall (two-line labels)


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


def _whole(value: float) -> int:
    """Round a non-negative count/benchmark to the nearest whole number, ties
    rounding HALF UP — Excel's ``#,##0`` (and the manager's workbook), not
    Python's round-half-even: ``38.5`` -> ``39``, not ``38``. ``round(value, 9)``
    first so float noise (e.g. ``219.00000000000003``) cannot move a tie."""
    return math.floor(round(value, 9) + 0.5)


def format_value(value: float, *, decimals: bool) -> str:
    return f"{value:,.1f}" if decimals else f"{_whole(value):,}"


def format_variance(value: float, *, decimals: bool) -> str:
    """Signed (``+70``, ``-49``, ``-0.1``); a value that rounds to zero is ``0``."""
    shown = round(value, 1) if decimals else round(value)
    if shown == 0:
        return "0"
    return f"{shown:+,.1f}" if decimals else f"{shown:+,.0f}"


def _cell_texts(row: dict, decimals: bool) -> list[str]:
    """Cell text for one row, shared by the PDF and HTML renderers.

    On count tabs (``decimals=False``) the printed Variance is the printed
    Actual minus the printed Benchmark (both whole numbers, rounded half up),
    so a benchmark landing exactly on ``.5`` can never make Actual, Benchmark
    and Variance disagree on the page. Status is unaffected — it is computed
    upstream from the true, unrounded variance. Units (``decimals=True``)
    keeps the true variance rounded to 1 decimal.
    """
    if decimals:
        variance_text = format_variance(row["variance"], decimals=True)
    else:
        printed_variance = int(row["actual"]) - _whole(row["benchmark"])
        variance_text = format_variance(printed_variance, decimals=False)
    return [
        str(row["group"]),
        format_value(row["baseline"], decimals=decimals),
        format_value(row["benchmark"], decimals=decimals),
        format_value(row["actual"], decimals=decimals),
        variance_text,
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
