"""Campaign definitions and report registry for mass mailing.

REPORT_REGISTRY maps report type names to the functions needed to fetch data,
filter per-recipient, and generate a PDF.

CAMPAIGNS defines mail jobs: which report, what parameters, and recipient lists
with per-recipient filter overrides.

Data is fetched from Tableau Cloud Hyper files (same source as Streamlit Cloud),
not from Oracle directly. This avoids Oracle dependencies and uses the same
pre-extracted data that the production app serves.
"""

import tempfile
import tomllib
from pathlib import Path


def _load_tableau_secrets() -> dict:
    """Load Tableau Cloud credentials from secrets.toml (CLI-safe, no st.secrets)."""
    secrets_path = Path(__file__).resolve().parents[3] / ".streamlit" / "secrets.toml"
    with open(secrets_path, "rb") as f:
        return tomllib.load(f)


def _fetch_from_hyper(dataset_name: str, filter_col: str, filter_values: tuple[str, ...]) -> "pd.DataFrame":
    """Download a Hyper file from Tableau Cloud and return a filtered DataFrame."""
    import pandas as pd
    import pantab
    from src.pipeline.publish import download_hyper

    secrets = _load_tableau_secrets()
    with tempfile.TemporaryDirectory() as tmp:
        hyper_path = download_hyper(
            dataset_name,
            Path(tmp),
            server_url=secrets["SERVER"],
            site_name=secrets["SITE_NAME"],
            pat_name=secrets["PAT_NAME"],
            pat_value=secrets["PAT_VALUE"],
        )
        df = pantab.frame_from_hyper(hyper_path, table="Extract")

    if filter_col in df.columns:
        df = df[df[filter_col].astype(str).isin(filter_values)]
    return df


# ---------------------------------------------------------------------------
# Report Registry — fetch functions pull from Tableau Cloud Hyper files
# ---------------------------------------------------------------------------

def _fetch_seat_count(params):
    return _fetch_from_hyper("seat_count_report", "term_code", (params["term_code"],))


def _pdf_seat_count(df, params):
    from src.scripts.tabs.seat_count_report import generate_report_pdf
    return generate_report_pdf(df, params)


REPORT_REGISTRY = {
    "seat_count_report": {
        "fetch_fn": _fetch_seat_count,
        "filter_columns": ["campus_desc", "division_desc", "department_desc"],
        "pdf_fn": _pdf_seat_count,
        "title_fn": lambda params: f"Seat Count Report - {params.get('term_title', '')}",
        "filename_fn": lambda params, filters: (
            "seat_count_"
            + "_".join(v.lower().replace(" ", "_") for v in filters.values())
            + ".pdf"
        ) if filters else "seat_count_full.pdf",
    },
}


# ---------------------------------------------------------------------------
# Campaigns
# ---------------------------------------------------------------------------

CAMPAIGNS = {
    # Example campaign — update recipients with real addresses
    "seat_count_fall2025_by_campus": {
        "report_type": "seat_count_report",
        "params": {
            "term_code": "202510",
            "term_title": "Fall 2025",
        },
        "subject_template": "Seat Count Report - {term_title} - {filter_desc}",
        "body_template": (
            "Dear {recipient_name},\n\n"
            "Please find attached the Seat Count Report for {term_title}, "
            "filtered to {filter_desc}.\n\n"
            "This report is also available interactively at "
            "https://nocccd.streamlit.app/\n\n"
            "Best regards,\n"
            "NOCCCD ESIE Data Team"
        ),
        "recipients": [
            {
                "name": "Test Recipient",
                "email": "jahn@nocccd.edu",
                "filters": {"campus_desc": "Cypress"},
            },
        ],
    },
}
