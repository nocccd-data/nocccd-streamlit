"""Project card configuration for the Home landing page.

Edit this file to update card descriptions, due dates, and milestones.
Each entry's ``tab_label`` must match the label string in ``tabs.TABS``.
Set ``due_date`` to ``None`` for projects with no due date.
"""

PROJECTS = [
    {
        "tab_label": "COI vs NHRDIST Validation",
        "description": "Validates COI estimated term salaries against NHRDIST actual payments.",
        "due_date": "2026-04-15",
        "milestones": [
            {"label": "SQL query finalized", "done": True},
            {"label": "Pipeline extraction tested", "done": True},
            {"label": "Streamlit tab built", "done": True},
            {"label": "Cloud mode validated", "done": False},
            {"label": "Stakeholder review complete", "done": False},
        ],
    },
    {
        "tab_label": "MIS SP Submitted vs. SCFF",
        "description": "Compares MIS SP Submitted records against SCFF financial-aid awards.",
        "due_date": "2026-04-30",
        "milestones": [
            {"label": "SQL query finalized", "done": True},
            {"label": "Pipeline extraction tested", "done": True},
            {"label": "Streamlit tab built", "done": True},
            {"label": "Cloud mode validated", "done": False},
            {"label": "Stakeholder review complete", "done": False},
        ],
    },
    {
        "tab_label": "MIS SP Current vs. SCFF",
        "description": "Compares MIS SP Current records against SCFF financial-aid awards.",
        "due_date": "2026-04-30",
        "milestones": [
            {"label": "SQL query finalized", "done": True},
            {"label": "Pipeline extraction tested", "done": True},
            {"label": "Streamlit tab built", "done": True},
            {"label": "Cloud mode validated", "done": False},
            {"label": "Stakeholder review complete", "done": False},
        ],
    },
]
