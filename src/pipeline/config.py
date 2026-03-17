from pathlib import Path

DATASETS = {
    "coi_nhrdist_val": {
        "sql_file": "coi_nhrdist_val.sql",
        "acyrs": ["243", "245", "247", "253", "255", "257"],
        "db_section": "dwhdb",
    },
    "deg_scff": {
        "sql_file": "deg_scff.sql",
        "acyrs": ["220", "230", "240", "250"],
        "db_section": "dwhdb",
    },
    "deg_sp_submitted": {
        "sql_file": "deg_sp_submitted.sql",
        "acyrs": ["220", "230", "240", "250"],
        "db_section": "dwhdb",
    },
    "deg_sp_current": {
        "sql_file": "deg_sp_current.sql",
        "acyrs": ["240", "250"],
        "db_section": "rept",
    },
    "deg_fa_scff": {
        "sql_file": "deg_fa_scff.sql",
        "acyrs": ["220", "230", "240", "250"],
        "db_section": "dwhdb",
    },
    "deg_fa_submitted": {
        "sql_file": "deg_fa_submitted.sql",
        "acyrs": ["220", "230", "240", "250"],
        "db_section": "dwhdb",
    },
}

SQL_DIR = Path(__file__).resolve().parent / "sql"
HYPER_DIR = Path(__file__).resolve().parent / "hyper"
