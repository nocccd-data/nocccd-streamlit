# Cross-Repo Workflow

How new analyses move from prototype notebooks into the production Streamlit app.

## Workflow: notebooks → nocccd-streamlit

New analyses start as Jupyter notebooks in either **nocccd-scff** (SCFF/funding analyses) or **nocccd-sql** (ad-hoc district queries), where SQL queries and visualization logic are prototyped and validated with stakeholders. Once validated, the analysis is ported here as a production Streamlit tab.

**Source repos:**
- **nocccd-scff**: SCFF degree/award/CTE comparisons — notebooks in `nocccd-scff/notebooks/`, SQL in `nocccd-scff/sql/`
- **nocccd-sql**: Ad-hoc queries (e.g. class schedule heatmap) — notebooks in `nocccd-sql/district/notebooks/`, SQL in `nocccd-sql/district/queries/`

**What gets ported:**
- **SQL queries**: source repo SQL → `src/pipeline/sql/` (adapted for pipeline extraction with acyr/term placeholders)
- **SQL parameterization**: `expand_in_clause()` originated in `nocccd-scff/libs/notebook_utils.py` — the same multi-acyr `IN (:t1...)` regex expansion is used in `extract.py`
- **Crosstab tables**: `build_expandable_crosstab()` in notebook_utils was ported to `_build_expandable_crosstab()` in tab modules for expandable HTML pivot tables
- **Funding status categories**: `derive_funding_status()` (Pell/CCPG/Both/Neither) — same logic in both repos
- **Plotly visualizations**: Interactive charts (e.g. `px.imshow()` heatmaps) are ported directly; PDF export uses matplotlib recreations

When starting a new analysis, prototype in a notebook first, then follow the "Adding a new dataset + tab" checklist in `docs/tabs.md`.
