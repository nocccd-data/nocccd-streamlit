"""CLI entry point for mass mailing.

Usage:
    python -m src.pipeline.mail                                    # list campaigns
    python -m src.pipeline.mail seat_count_fall2025_by_campus      # run campaign
    python -m src.pipeline.mail seat_count_fall2025_by_campus --dry-run
    python -m src.pipeline.mail seat_count_fall2025_by_campus --recipient "Test Recipient"
"""

import argparse
import tomllib
from pathlib import Path

from .mail_config import CAMPAIGNS
from .report_generator import run_campaign


def _load_secrets() -> dict:
    secrets_path = Path(__file__).resolve().parents[3] / ".streamlit" / "secrets.toml"
    with open(secrets_path, "rb") as f:
        return tomllib.load(f)


def main():
    parser = argparse.ArgumentParser(description="Generate and email filtered PDF reports")
    parser.add_argument("campaign", nargs="?", help="Campaign name (omit to list all)")
    parser.add_argument("--dry-run", action="store_true", help="Generate PDFs but don't send emails")
    parser.add_argument("--recipient", help="Send to a single recipient (by name) for testing")
    args = parser.parse_args()

    if not args.campaign:
        print("Available campaigns:")
        for name, cfg in CAMPAIGNS.items():
            n = len(cfg["recipients"])
            print(f"  {name}: {cfg['report_type']} -> {n} recipient(s)")
        return

    if args.campaign not in CAMPAIGNS:
        print(f"Unknown campaign: {args.campaign}")
        print(f"Available: {', '.join(CAMPAIGNS)}")
        return

    secrets = _load_secrets()
    email_config = secrets.get("email", {})

    if not args.dry_run and not email_config.get("smtp_password"):
        print("Error: [email] section in .streamlit/secrets.toml is missing or incomplete.")
        return

    mode = "DRY RUN" if args.dry_run else "SENDING"
    print(f"[{args.campaign}] {mode}")

    def _cli_progress(current, total, name):
        print(f"  [{current}/{total}] {name}")

    results = run_campaign(
        args.campaign,
        email_config,
        dry_run=args.dry_run,
        recipient_filter=args.recipient,
        progress_callback=_cli_progress,
    )

    # Summary
    sent = sum(1 for r in results if r.success)
    failed = sum(1 for r in results if not r.success)
    print(f"\nDone. Success: {sent}, Failed: {failed}")
    for r in results:
        status = "OK" if r.success else f"FAILED: {r.error}"
        print(f"  {r.recipient_name} <{r.recipient_email}> ({r.filter_desc}): {status}")


if __name__ == "__main__":
    main()
