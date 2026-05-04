"""Extract data from Oracle and write to Hyper files."""

import re
from pathlib import Path

import pandas as pd
import pantab

from .config import DATASETS, SQL_DIR, HYPER_DIR
from .libs.sql import get_engine


def _concat_query_frames(frames: list[pd.DataFrame]) -> pd.DataFrame:
    """Concatenate per-parameter query results without pandas dtype warnings."""
    if not frames:
        return pd.DataFrame()

    columns = list(dict.fromkeys(col for frame in frames for col in frame.columns))
    populated_frames = [
        frame.dropna(axis=1, how="all")
        for frame in frames
        if not frame.empty
    ]

    if not populated_frames:
        return frames[0].iloc[0:0].copy()

    df = pd.concat(populated_frames, ignore_index=True)
    for col in columns:
        if col in df.columns:
            continue

        dtype = next(frame[col].dtype for frame in frames if col in frame.columns)
        try:
            df[col] = pd.Series(pd.NA, index=df.index, dtype=dtype)
        except (TypeError, ValueError):
            df[col] = pd.Series(pd.NA, index=df.index)

    return df.reindex(columns=columns)


def extract_dataset(name: str) -> Path:
    """Query Oracle for a dataset and write the result to a .hyper file.

    Returns the path to the generated Hyper file.
    """
    cfg = DATASETS[name]
    sql_path = SQL_DIR / cfg["sql_file"]
    param_name = cfg["param_name"]
    values = cfg[param_name]

    base_sql = sql_path.read_text(encoding="utf-8")
    engine = get_engine(section=cfg.get("db_section", "dwhdb"))

    # Multi-acyr templates have an `IN (:t1)` placeholder we expand to one
    # placeholder per supplied value. `\s*` on both sides of `(` AND before
    # `:t1` accommodates SQL formatted as `IN (\n    :t1\n)`. DOTALL makes
    # `.*?` cross newlines so the closing `)` on a separate line still
    # matches. After substituting, assert the SQL actually changed — silent
    # no-ops would send the literal string `:t1` to Oracle and either fail
    # bind validation or return a partial result.
    in_pattern = r"IN\s*\(\s*:t1.*?\)"
    if re.search(in_pattern, base_sql, re.IGNORECASE | re.DOTALL):
        placeholders = ", ".join(f":t{i}" for i in range(1, len(values) + 1))
        sql = re.sub(
            in_pattern,
            f"IN ({placeholders})",
            base_sql,
            flags=re.IGNORECASE | re.DOTALL,
        )
        if sql == base_sql:
            raise RuntimeError(
                f"IN-clause expansion silently no-op'd in {sql_path.name}; "
                f"placeholder pattern matched but substitution did not. "
                f"Check the SQL template's IN(:t1) formatting."
            )
        params = {f"t{i}": t for i, t in enumerate(values, 1)}
        with engine.connect() as conn:
            df = pd.read_sql(sql, conn, params=params)
    else:
        # Single-acyr: execute once per acyr and concatenate
        frames = []
        with engine.connect() as conn:
            for t in values:
                frames.append(pd.read_sql(base_sql, conn, params={param_name: t}))
        df = _concat_query_frames(frames)

    HYPER_DIR.mkdir(parents=True, exist_ok=True)
    hyper_path = HYPER_DIR / f"{name}.hyper"
    pantab.frame_to_hyper(df, hyper_path, table="Extract")

    print(f"  Wrote {hyper_path} ({len(df):,} rows)")
    return hyper_path
