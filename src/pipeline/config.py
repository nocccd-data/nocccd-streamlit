from pathlib import Path

DATASETS = {
    "coi_nhrdist_val": {
        "sql_file": "coi_nhrdist_val.sql",
        "terms": ["243", "245", "247", "253", "255", "257"],
    },
    "deg_scff": {
        "sql_file": "deg_scff.sql",
        "terms": ["220", "230", "240", "250"],
    },
    "deg_sp_submitted": {
        "sql_file": "deg_sp_submitted.sql",
        "terms": ["220", "230", "240", "250"],
    },
}

SQL_DIR = Path(__file__).resolve().parent / "sql"
HYPER_DIR = Path(__file__).resolve().parent / "hyper"
