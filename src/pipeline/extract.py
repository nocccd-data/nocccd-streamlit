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
    pantab.frame_to_hyper(df, hyper_path, table="Extract")

    print(f"  Wrote {hyper_path} ({len(df):,} rows)")
    return hyper_path


def _stream_schema(dtypes: pd.Series) -> dict:
    """Stable per-column dtype map used to coerce every chunk before appending.

    Two coercions keep the schema stable across chunks:
    - Plain ``int64`` -> nullable ``Int64`` so a NULL appearing only in a later
      chunk can't break the append (plain int64 cannot hold NaN).
    - ``object`` (text) -> nullable ``string`` so a column that is entirely NULL
      within some chunk still maps to a concrete Hyper TEXT type. A raw all-None
      object column has no inferable Arrow type and pantab rejects it.

    pantab requires every appended chunk to match the table's column types
    exactly; all other dtypes pass through unchanged.
    """
    schema: dict = {}
    for col, dtype in dtypes.items():
        if pd.api.types.is_integer_dtype(dtype) and not pd.api.types.is_extension_array_dtype(dtype):
            schema[col] = "Int64"
        elif pd.api.types.is_object_dtype(dtype):
            schema[col] = "string"
        else:
            schema[col] = dtype
    return schema


def _write_hyper_chunked(name: str, frames) -> Path:
    """Stream query-result chunks into ``hyper/<name>.hyper``, appending each.

    Keeps peak memory bounded for large extracts (millions of rows) instead of
    materializing the whole result in one DataFrame. The first chunk defines the
    table schema and is written with ``table_mode='w'``; every chunk is coerced
    to that schema so pantab's strict column-type matching holds even when a
    chunk is entirely NULL for some column.
    """
    HYPER_DIR.mkdir(parents=True, exist_ok=True)
    hyper_path = HYPER_DIR / f"{name}.hyper"

    schema: dict | None = None
    total = 0
    for chunk in frames:
        if schema is None:
            schema = _stream_schema(chunk.dtypes)
            mode = "w"
        else:
            mode = "a"
        chunk = chunk.reindex(columns=list(schema)).astype(schema)
        pantab.frame_to_hyper(chunk, hyper_path, table="Extract", table_mode=mode)
        total += len(chunk)
        print(f"    ...{total:,} rows written")

    if schema is None:
        # Empty result set: still write an (empty) Extract table so a downstream
        # publish has something to upload rather than failing on a missing file.
        _write_hyper(name, pd.DataFrame())
        return hyper_path

    print(f"  Wrote {hyper_path} ({total:,} rows)")
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

    # Parameterless datasets (e.g. an MV that defines its own window): run the
    # SQL once with no binds. There is no param_name / value list to loop over.
    # Large extracts set "chunksize" so the result streams to Hyper in bounded
    # memory instead of materializing millions of rows in one DataFrame.
    if param_name is None:
        chunksize = cfg.get("chunksize")
        with engine.connect() as conn:
            if chunksize:
                frames = pd.read_sql(base_sql, conn, chunksize=chunksize)
                return _write_hyper_chunked(name, frames)
            df = pd.read_sql(base_sql, conn)
        return _write_hyper(name, df)

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
