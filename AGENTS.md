# AGENTS.md

Codex entrypoint for `/Users/hoonywise/GitHub/nocccd-data/nocccd-streamlit`.

This file is intentionally small and does not import `CLAUDE.md`. Do not read `CLAUDE.md` unless the user explicitly asks; it is the Claude Code entrypoint for the same project and exists to avoid cross-tool context duplication.

Shared engineering guidance lives in `docs/` and is loaded on demand only when relevant to the task. Read only the sections you need.

## Topic Index

| When you're working on | Read |
|------------------------|------|
| First-time orientation, architecture, commands, deployment, hard constraints | `docs/agent-guidance.md` |
| Cross-repo workflow (notebooks → streamlit), `nocccd-scff` / `nocccd-sql` ports | `docs/workflow.md` |
| `src/pipeline/`: dataset config, `extract.py`, SQL parameterization, bind-variable + db_section gotchas | `docs/pipeline.md` |
| `src/scripts/tabs/`: tab system, adding-a-tab checklist, cascading filters, Seat Count layout, Persistence projections, Class Schedule Heatmap, admin auth, sidebar download patterns, PDF rendering rules | `docs/tabs.md` |
| `src/scripts/tabs/bot_*`: BOT goal/metric tabs, base population rules, `_TITLES` flags, BOT PDF generator + paper coordinates, Excel helpers | `docs/bot-tabs.md` |
| `src/pipeline/seat_count_export.py`, `bot_export.py`, `bot_excel_export.py`: bulk PDF/Excel exports | `docs/exports.md` |
| `src/pipeline/mail/`: mass mailing, `REPORT_REGISTRY`, `CAMPAIGNS`, sender, GitHub Actions | `docs/mail.md` |
| `src/scripts/theme.py`, CSS, color palettes, Streamlit 1.55 gotchas, NOCCCD brand colors | `docs/theme.md` |
| Known issues deliberately left unfixed, and the decision each one is waiting on | `docs/deferred.md` |

## Quick Defaults

- Use `.venv/` for Python commands unless the user says otherwise.
- Use `ruff` for Python linting.
- The Streamlit app reads Tableau Hyper extracts at runtime; Oracle access belongs in `src/pipeline/`.
- Do not return unfiltered data when required schema/filter columns are missing — fail loudly.
