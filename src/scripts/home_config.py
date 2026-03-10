"""Project card configuration for the Home landing page.

Edit this file to update card descriptions, due dates, and milestones.
Each entry's ``tab_label`` must match the label string in ``tabs.TABS``.
Set ``due_date`` to ``None`` for projects with no due date.
"""

PROJECTS = [
    {
        "tab_label": "COI vs NHRDIST Validation",
        "description": "Validates COI estimated term salaries against NHRDIST actual payments.",
        "due_date": "",
        "milestones": [
            {"label": "Create MV of COI and NHRDIST base queries", "done": True},
            {"label": "Create coi_nhrdist.sql query for calcs", "done": True},
            {"label": "Build metrics and tables via Jupyter", "done": True},
            {"label": "Import metrics and tables to Streamlit", "done": True},
            {"label": "Stakeholder review complete", "done": False},
        ],
    },
    {
        "tab_label": "MIS SP Submitted vs. SCFF",
        "description": "Compares MIS SP Submitted records against SCFF financial-aid awards.",
        "due_date": "",
        "milestones": [
            {"label": "Create deg_scff.sql base SCFF counts", "done": True},
            {"label": "Create deg_sp_submitted.sql comparison query", "done": True},
            {"label": "Metrics and table exploration via Jupyter", "done": True},
            {"label": "Import tables to Streamlit", "done": True},
            {"label": "Stakeholder review complete", "done": False},
        ],
    },
    {
        "tab_label": "MIS SP Current vs. SCFF",
        "description": "Compares MIS SP Current records against SCFF financial-aid awards.",
        "due_date": "",
        "milestones": [
            {"label": "Create deg_sp_current.sql comparison query", "done": True},
            {"label": "Metrics and table exploration via Jupyter", "done": True},
            {"label": "Import tables to Streamlit", "done": True},
            {"label": "Stakeholder review complete", "done": False},
        ],
    },
]
