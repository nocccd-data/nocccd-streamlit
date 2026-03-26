from pathlib import Path

DATASETS = {
    "fast_facts_emp": {
        "sql_file": "fast_facts_emp.sql",
        "fisc_year": ["2020", "2021", "2022", "2023", "2024", "2025"],
        "param_name": "fisc_year",
        "db_section": "rept",
    },
    "fast_facts_stu": {
        "sql_file": "fast_facts_stu.sql",
        "acyr_code": ["2019", "2020", "2021", "2022", "2023", "2024"],
        "param_name": "acyr_code",
        "db_section": "rept",
    },
    "coi_nhrdist_val": {
        "sql_file": "coi_nhrdist_val.sql",
        "mis_term_id": ["243", "245", "247", "253", "255", "257"],
        "param_name": "mis_term_id",
        "db_section": "dwhdb",
    },
    "deg_scff": {
        "sql_file": "deg_scff.sql",
        "mis_acyr_id": ["220", "230", "240", "250"],
        "param_name": "mis_acyr_id",
        "db_section": "dwhdb",
    },
    "deg_sp_submitted": {
        "sql_file": "deg_sp_submitted.sql",
        "mis_acyr_id": ["220", "230", "240", "250"],
        "param_name": "mis_acyr_id",
        "db_section": "dwhdb",
    },
    "deg_sp_current": {
        "sql_file": "deg_sp_current.sql",
        "mis_acyr_id": ["240", "250"],
        "param_name": "mis_acyr_id",
        "db_section": "rept",
    },
    "deg_fa_scff": {
        "sql_file": "deg_fa_scff.sql",
        "mis_acyr_id": ["220", "230", "240", "250"],
        "param_name": "mis_acyr_id",
        "db_section": "dwhdb",
    },
    "deg_fa_submitted": {
        "sql_file": "deg_fa_submitted.sql",
        "mis_acyr_id": ["220", "230", "240", "250"],
        "param_name": "mis_acyr_id",
        "db_section": "dwhdb",
    },
    "cte_scff": {
        "sql_file": "cte_scff.sql",
        "mis_acyr_id": ["230", "240", "250"],
        "param_name": "mis_acyr_id",
        "db_section": "dwhdb",
    },
    "cte_sx_submitted": {
        "sql_file": "cte_sx_submitted.sql",
        "mis_acyr_id": ["230", "240", "250"],
        "param_name": "mis_acyr_id",
        "db_section": "dwhdb",
    },
    "class_schedule_heatmap": {
        "sql_file": "class_schedule_heatmap.sql",
        "mis_term_id": ["207", "213", "215", "217", "223", "225", "227", "233", "235", "237", "243", "243", "247",
                        "253", "255", "257", "263", "265"],
        "param_name": "mis_term_id",
        "db_section": "dwhdb",
    },
    "persistence_by_styp": {
        "sql_file": "persistence_by_styp.sql",
        "mis_term_id": ["107", "117", "127", "137", "147", "157", "167", "177", "187", "197", "207", "217", "227",
                        "237", "247", "257"],
        "param_name": "mis_term_id",
        "db_section": "dwhdb",
    },
    "seat_count_report": {
        "sql_file": "seat_count_report.sql",
        "banner_term_code": ["202010", "202020", "202030", "202110", "202120", "202130", "202210", "202220", "202230",
                             "202310", "202320", "202330", "202410", "202420", "202430", "202510", "202515", "202520",
                             "202535", "202530", "202605"],
        "param_name": "banner_term_code",
        "db_section": "rept",
    },
}

SQL_DIR = Path(__file__).resolve().parent / "sql"
HYPER_DIR = Path(__file__).resolve().parent / "hyper"
