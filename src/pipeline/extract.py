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


def _write_hyper(name: str, df: pd.DataFrame) -> Path:
    """Write a query result to ``hyper/<name>.hyper`` and return the path."""
    HYPER_DIR.mkdir(parents=True, exist_ok=True)
    hyper_path = HYPER_DIR / f"{name}.hyper"

    # A column that is entirely NULL comes back as an object column of None,
    # which has no inferable Arrow type (pantab raises "Unsupported Arrow type:
    # na"). Coerce those to nullable ``string`` so they map to a concrete Hyper
    # TEXT column. Object columns that hold any data are left for pantab to type.
    for col in df.columns:
        if pd.api.types.is_object_dtype(df[col].dtype) and df[col].isna().all():
            df[col] = df[col].astype("string")

    pantab.frame_to_hyper(df, hyper_path, table="Extract")

    # flush: launchd sends stdout and stderr to the same log, and block-buffered
    # stdout otherwise lands minutes after the unbuffered logging lines it
    # belongs between, which makes the log hard to read after a failure.
    print(f"  Wrote {hyper_path} ({len(df):,} rows)", flush=True)
    return hyper_path


def extract_dataset(name: str) -> Path:
    """Query Oracle for a dataset and write the result to a .hyper file.

    Returns the path to the generated Hyper file.
    """
    cfg = DATASETS[name]
    sql_path = SQL_DIR / cfg["sql_file"]
    param_name = cfg.get("param_name")

    base_sql = sql_path.read_text(encoding="utf-8")
    engine = get_engine(section=cfg.get("db_section", "dwhdb"))

    # Pulling a whole table is an EXPLICIT opt-in, never inferred from a missing
    # `param_name`. Inferring it would mean a config that merely *forgot* its
    # param_name — a line dropped while copy-pasting an existing entry — quietly
    # ships every row of every term to the app instead of failing, which is
    # exactly the unfiltered-data case this repo's conventions forbid. Absence
    # of param_name is a config error; `unparameterized` is the deliberate flag.
    unparameterized = cfg.get("unparameterized", False)
    if unparameterized and param_name is not None:
        raise RuntimeError(
            f"Dataset {name!r} sets both 'unparameterized' and "
            f"'param_name'; they are mutually exclusive."
        )
    if not unparameterized and param_name is None:
        raise RuntimeError(
            f"Dataset {name!r} has no 'param_name'. Add one, or set "
            f"'unparameterized': True to pull the whole table deliberately."
        )

    if unparameterized:
        # A SQL file that *should* have been parameterized would otherwise ship
        # a literal `:t1` to Oracle. Comments and string literals are stripped
        # first so prose like "1:many" in a header, or an Oracle format mask
        # like 'HH24:MI:SS', is not mistaken for a bind. The lookbehind then
        # excludes a colon preceded by a word character or another colon.
        sql_body = re.sub(r"--[^\n]*", "", base_sql)
        sql_body = re.sub(r"/\*.*?\*/", "", sql_body, flags=re.DOTALL)
        sql_body = re.sub(r"'[^']*'", "", sql_body)
        stray = re.search(r"(?<![\w:]):(\w+)", sql_body)
        if stray:
            raise RuntimeError(
                f"{sql_path.name} contains bind placeholder ':{stray.group(1)}' "
                f"but dataset {name!r} is marked 'unparameterized'."
            )
        with engine.connect() as conn:
            df = pd.read_sql(base_sql, conn)
        return _write_hyper(name, df)

    # Guaranteed by the guards above; restated so the type checker narrows it.
    assert param_name is not None
    values = cfg[param_name]

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

    return _write_hyper(name, df)
