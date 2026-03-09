"""CLI entry point: extract Oracle data to Hyper and publish to Tableau Cloud.

Usage:
    python -m src.pipeline.run                    # all datasets
    python -m src.pipeline.run coi_nhrdist_val    # single dataset
    python -m src.pipeline.run --extract-only     # skip upload
"""

import argparse
import tomllib
from pathlib import Path

from .config import DATASETS
from .extract import extract_dataset
from .publish import publish_hyper


def _load_secrets() -> dict:
    secrets_path = Path(__file__).resolve().parents[2] / ".streamlit" / "secrets.toml"
    with open(secrets_path, "rb") as f:
        return tomllib.load(f)


def main():
    parser = argparse.ArgumentParser(description="Oracle → Hyper → Tableau Cloud pipeline")
    parser.add_argument("datasets", nargs="*", help="Dataset names (default: all)")
    parser.add_argument("--extract-only", action="store_true", help="Only create .hyper files, skip upload")
    args = parser.parse_args()

    names = args.datasets if args.datasets else list(DATASETS.keys())
    for name in names:
        if name not in DATASETS:
            print(f"Unknown dataset: {name}")
            print(f"Available: {', '.join(DATASETS.keys())}")
            return

    secrets = _load_secrets()

    for name in names:
        print(f"[{name}] Extracting from Oracle...")
        hyper_path = extract_dataset(name)

        if not args.extract_only:
            print(f"[{name}] Publishing to Tableau Cloud...")
            publish_hyper(
                name,
                hyper_path,
                server_url=secrets["SERVER"],
                site_name=secrets["SITE_NAME"],
                pat_name=secrets["PAT_NAME"],
                pat_value=secrets["PAT_VALUE"],
            )

    print("Done.")


if __name__ == "__main__":
    main()
