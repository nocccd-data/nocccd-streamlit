"""Extract data from Oracle and write to Hyper files."""

import re
from pathlib import Path

import pandas as pd
import pantab

from .config import DATASETS, SQL_DIR, HYPER_DIR
from .libs.sql import get_engine


def extract_dataset(name: str) -> Path:
    """Query Oracle for a dataset and write the result to a .hyper file.

    Returns the path to the generated Hyper file.
    """
    cfg = DATASETS[name]
    sql_path = SQL_DIR / cfg["sql_file"]
    acyrs = cfg["acyrs"]

    base_sql = sql_path.read_text(encoding="utf-8")
    engine = get_engine(section=cfg.get("db_section", "dwhdb"))

    if re.search(r"IN\s*\(:t1", base_sql):
        # Multi-acyr: expand IN clause
        placeholders = ", ".join(f":t{i}" for i in range(1, len(acyrs) + 1))
        sql = re.sub(r"IN\s*\(:t1.*?\)", f"IN ({placeholders})", base_sql)
        params = {f"t{i}": t for i, t in enumerate(acyrs, 1)}
        with engine.connect() as conn:
            df = pd.read_sql(sql, conn, params=params)
    else:
        # Single-acyr: execute once per acyr and concatenate
        frames = []
        with engine.connect() as conn:
            for t in acyrs:
                frames.append(pd.read_sql(base_sql, conn, params={"mis_acyr_id": t}))
        df = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

    HYPER_DIR.mkdir(parents=True, exist_ok=True)
    hyper_path = HYPER_DIR / f"{name}.hyper"
    pantab.frame_to_hyper(df, hyper_path, table="Extract")

    print(f"  Wrote {hyper_path} ({len(df):,} rows)")
    return hyper_path
