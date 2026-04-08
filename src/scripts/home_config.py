"""Project card configuration for the Home landing page.

Edit this file to update card descriptions and metrics.
Each entry's ``tab_label`` must match the label string in ``tabs.TABS``.
``metrics`` lists the types of metrics/data available in each dashboard.
"""

PROJECTS = [
    {
        "tab_label": "Fast Facts",
        "description": "Student and employee demographics snapshot for the current academic year.",
        "metrics": [
            "Student headcount by ethnicity, gender, age",
            "Student enrollment status breakdown",
            "Employee headcount by classification, ethnicity, gender",
            "Employee full-time/part-time ratios",
        ],
    },
    {
        "tab_label": "Seat Count Report",
        "description": "Section-level seat counts and fill rates by campus, division, and department.",
        "metrics": [
            "Current enrollment and fill rates",
            "Census enrollment and fill rates",
            "First day morning/evening/no-hours enrollment",
            "Crosslist-adjusted seat counts",
            "Department and division totals",
        ],
    },
    {
        "tab_label": "Class Schedule Heatmap",
        "description": "Heatmap visualization of class schedule enrollment by day of week and time of day.",
        "metrics": [
            "Section counts by day and time slot",
            "Enrollment density heatmap",
            "Campus-level comparisons",
        ],
    },
    {
        "tab_label": "Persistence by Student Type",
        "description": "Fall-to-spring and fall-to-fall persistence rates by campus and student type.",
        "metrics": [
            "Fall-to-spring persistence rates",
            "Fall-to-fall persistence rates",
            "Breakdown by student type",
            "Multi-term trend lines by campus",
        ],
    },
    {
        "tab_label": "COI vs NHRDIST Validation",
        "description": "Validates COI estimated term salaries against NHRDIST actual payments.",
        "metrics": [
            "Total estimated vs actual payments",
            "Payment difference by term",
            "Top outlier employees",
            "Match status breakdown",
        ],
    },
    {
        "tab_label": "SCFF Degrees - MIS SP Submitted",
        "description": "Compares MIS SP Submitted records against SCFF financial-aid awards.",
        "metrics": [
            "SCFF degree counts by DICD",
            "MIS SP submitted vs SCFF match rates",
            "Unmatched record detail",
        ],
    },
    {
        "tab_label": "SCFF Degrees - MIS SP Current",
        "description": "Compares MIS SP Current records against SCFF financial-aid awards.",
        "metrics": [
            "SCFF degree counts by DICD",
            "MIS SP current vs SCFF match rates",
            "Unmatched record detail",
        ],
    },
    {
        "tab_label": "SCFF Awards - MIS FA Submitted",
        "description": "Compares MIS FA Submitted records against SCFF financial-aid awards.",
        "metrics": [
            "SCFF award counts by DICD",
            "MIS FA submitted vs SCFF match rates",
            "Unmatched record detail",
        ],
    },
    {
        "tab_label": "SCFF CTE - MIS SX Submitted",
        "description": "Compares MIS SX Submitted records against SCFF CTE awards.",
        "metrics": [
            "SCFF CTE counts by DICD",
            "MIS SX submitted vs SCFF match rates",
            "Unmatched record detail",
        ],
    },
    {
        "tab_label": "BOT Goal 1 - Students",
        "description": "Board of Trustees Goal 1 — Student enrollment headcount trends by campus.",
        "metrics": [
            "Distinct student headcount by campus",
            "NOCCCD unduplicated total",
            "5-year percentage change",
        ],
    },
    {
        "tab_label": "BOT Goal 2 - Certificates",
        "description": "Board of Trustees Goal 2 — Credit certificate awards by campus.",
        "metrics": [
            "Certificate headcount by campus",
            "NOCCCD unduplicated total",
            "5-year percentage change",
        ],
    },
    {
        "tab_label": "BOT Goal 2 - Noncredit Certificates",
        "description": "Board of Trustees Goal 2 — Noncredit certificate awards at NOCE.",
        "metrics": [
            "Noncredit certificate headcount",
            "Race/ethnicity and gender breakdowns",
            "5-year percentage change",
        ],
    },
    {
        "tab_label": "BOT Goal 2 - Associate Degrees",
        "description": "Board of Trustees Goal 2 — Associate degree awards by campus.",
        "metrics": [
            "Associate degree headcount by campus",
            "NOCCCD unduplicated total",
            "5-year percentage change",
        ],
    },
    {
        "tab_label": "BOT Goal 2 - ADT",
        "description": "Board of Trustees Goal 2 — Associate degrees for transfer by campus.",
        "metrics": [
            "ADT headcount by campus",
            "NOCCCD unduplicated total",
            "5-year percentage change",
        ],
    },
    {
        "tab_label": "BOT Goal 2 - Bachelor's Degrees",
        "description": "Board of Trustees Goal 2 — Bachelor's degree awards by campus.",
        "metrics": [
            "Bachelor's degree headcount by campus",
            "NOCCCD unduplicated total",
            "5-year percentage change",
        ],
    },
]
