"""Read-once-per-run cache for local Tableau Hyper extracts.

Used by both ``bot_export`` (PDF) and ``bot_excel_export`` (Excel). A single
exporter run touches the same Hyper file (notably ``bot_goal1_students``)
from multiple per-tab builders; reading once and reusing the DataFrame
avoids redundant disk I/O on the OneDrive-synced extract directory.
"""

from __future__ import annotations

import pandas as pd
import pantab

from src.pipeline.config import HYPER_DIR


class HyperCache:
    """Read each local Hyper file at most once per export run.

    Callers must treat returned DataFrames as read-only. Mutating in place
    (e.g. ``df.rename(inplace=True)``, ``df['x'] = …``) corrupts the cached
    frame for all subsequent callers — pass through ``.copy()`` or use
    non-mutating operations like ``df[df['col'] == x]`` if you need a
    derived view.
    """

    def __init__(self) -> None:
        self._frames: dict[str, pd.DataFrame] = {}

    def get(self, name: str) -> pd.DataFrame:
        if name not in self._frames:
            path = HYPER_DIR / f"{name}.hyper"
            if not path.exists():
                raise FileNotFoundError(
                    f"Hyper file not found at {path}.\n"
                    f"Run: python -m src.pipeline.run {name}"
                )
            self._frames[name] = pantab.frame_from_hyper(path, table="Extract")
        return self._frames[name]
