"""Orchestrator: fetch data once, filter per recipient, generate PDF, send email."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field

import pandas as pd

from .mail_config import CAMPAIGNS, REPORT_REGISTRY
from .sender import send_email


@dataclass
class SendResult:
    recipient_name: str
    recipient_email: str
    filter_desc: str
    success: bool
    error: str | None = None
    pdf_bytes: bytes = field(default=b"", repr=False)


def _build_filter_desc(filters: dict[str, str]) -> str:
    """Build a human-readable description from a filters dict."""
    if not filters:
        return "All"
    return " / ".join(filters.values())


def _apply_filters(df: pd.DataFrame, filters: dict[str, str]) -> pd.DataFrame:
    """Apply equality filters to a DataFrame."""
    filtered = df
    for col, value in filters.items():
        if col in filtered.columns:
            filtered = filtered[filtered[col] == value]
    return filtered


def _safe_filename(text: str) -> str:
    """Convert text to a safe filename fragment."""
    return text.lower().replace(" ", "_").replace("/", "_").replace("&", "and")


def run_campaign(
    campaign_name: str,
    email_config: dict,
    dry_run: bool = False,
    recipient_filter: str | None = None,
    progress_callback: Callable | None = None,
) -> list[SendResult]:
    """Execute a mail campaign.

    Parameters
    ----------
    campaign_name : str
        Key in CAMPAIGNS dict.
    email_config : dict
        SMTP config from secrets.toml [email] section.
    dry_run : bool
        If True, generate PDFs but don't send emails.
    recipient_filter : str or None
        If set, only send to the recipient with this name.
    progress_callback : callable or None
        Called with (current_index, total, recipient_name) for progress updates.

    Returns
    -------
    list[SendResult]
    """
    if campaign_name not in CAMPAIGNS:
        raise ValueError(f"Unknown campaign: {campaign_name}. Available: {', '.join(CAMPAIGNS)}")

    campaign = CAMPAIGNS[campaign_name]
    report_type = campaign["report_type"]

    if report_type not in REPORT_REGISTRY:
        raise ValueError(f"Unknown report type: {report_type}. Available: {', '.join(REPORT_REGISTRY)}")

    registry = REPORT_REGISTRY[report_type]
    params = campaign["params"]

    # Fetch full dataset once
    df = registry["fetch_fn"](params)
    if df.empty:
        raise ValueError(f"No data returned for params: {params}")

    # Derive term_title from data if not in params
    if "term_title" not in params and "term_title" in df.columns:
        params = {**params, "term_title": df["term_title"].iloc[0]}

    recipients = campaign["recipients"]
    if recipient_filter:
        recipients = [r for r in recipients if r["name"] == recipient_filter]
        if not recipients:
            raise ValueError(f"No recipient named '{recipient_filter}' in campaign '{campaign_name}'")

    results: list[SendResult] = []
    total = len(recipients)

    for i, recipient in enumerate(recipients):
        name = recipient["name"]
        email = recipient["email"]
        filters = recipient.get("filters", {})
        filter_desc = _build_filter_desc(filters)

        if progress_callback:
            progress_callback(i + 1, total, name)

        try:
            # Filter data for this recipient
            filtered_df = _apply_filters(df, filters)

            if filtered_df.empty:
                results.append(SendResult(
                    recipient_name=name,
                    recipient_email=email,
                    filter_desc=filter_desc,
                    success=False,
                    error="No data after filtering",
                ))
                continue

            # Generate PDF
            pdf_bytes = registry["pdf_fn"](filtered_df, params)

            # Build email content
            template_vars = {
                **params,
                "recipient_name": name,
                "filter_desc": filter_desc,
            }
            subject = campaign["subject_template"].format(**template_vars)
            body = campaign["body_template"].format(**template_vars)

            # Build filename
            filename_fn = registry.get("filename_fn")
            if filename_fn:
                pdf_filename = filename_fn(params, filters)
            else:
                pdf_filename = f"report_{_safe_filename(filter_desc)}.pdf"

            if not dry_run:
                send_email(
                    smtp_config=email_config,
                    to_email=email,
                    subject=subject,
                    body=body,
                    pdf_bytes=pdf_bytes,
                    pdf_filename=pdf_filename,
                )
                # Rate limit — Gmail allows ~500/day, be conservative
                if i < total - 1:
                    time.sleep(2)

            results.append(SendResult(
                recipient_name=name,
                recipient_email=email,
                filter_desc=filter_desc,
                success=True,
                pdf_bytes=pdf_bytes if dry_run else b"",
            ))

        except Exception as exc:
            results.append(SendResult(
                recipient_name=name,
                recipient_email=email,
                filter_desc=filter_desc,
                success=False,
                error=str(exc),
            ))

    return results
