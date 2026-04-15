from pathlib import Path

DATASETS = {
    "fast_facts_emp": {
        "sql_file": "fast_facts_emp.sql",
        "fisc_year": ["2023", "2024", "2025"],
        "param_name": "fisc_year",
        "db_section": "rept",
    },
    "fast_facts_stu": {
        "sql_file": "fast_facts_stu.sql",
        "acyr_code": ["2022", "2023", "2024"],
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
        "mis_term_id": ["257", "263", "265"],
        "param_name": "mis_term_id",
        "db_section": "dwhdb",
    },
    "persistence_by_styp": {
        "sql_file": "persistence_by_styp.sql",
        "mis_term_id": ["207", "217", "227", "237", "247", "257"],
        "param_name": "mis_term_id",
        "db_section": "dwhdb",
    },
    "seat_count_report": {
        "sql_file": "seat_count_report.sql",
        "banner_term_code": ["202510", "202515", "202520", "202535", "202530", "202605"],
        "param_name": "banner_term_code",
        "db_section": "rept",
    },
    "bot_goal1_students": {
        "sql_file": "bot_goal1_students.sql",
        "acyr_code": ["2020", "2021", "2022", "2023", "2024"],
        "param_name": "acyr_code",
        "db_section": "rept",
    },
    "bot_goal2_cert": {
        "sql_file": "bot_goal2_cert.sql",
        "acyr_code": ["2020", "2021", "2022", "2023", "2024"],
        "param_name": "acyr_code",
        "db_section": "rept",
    },
    "bot_goal2_cert_nc": {
        "sql_file": "bot_goal2_cert_nc.sql",
        "acyr_code": ["2020", "2021", "2022", "2023", "2024"],
        "param_name": "acyr_code",
        "db_section": "rept",
    },
    "bot_goal2_cert_nc_denom": {
        "sql_file": "bot_goal2_cert_nc_denom.sql",
        "acyr_code": ["2020", "2021", "2022", "2023", "2024"],
        "param_name": "acyr_code",
        "db_section": "rept",
    },
    "bot_goal2_assoc": {
        "sql_file": "bot_goal2_assoc.sql",
        "acyr_code": ["2020", "2021", "2022", "2023", "2024"],
        "param_name": "acyr_code",
        "db_section": "rept",
    },
    "bot_goal2_adt": {
        "sql_file": "bot_goal2_adt.sql",
        "acyr_code": ["2020", "2021", "2022", "2023", "2024"],
        "param_name": "acyr_code",
        "db_section": "rept",
    },
    "bot_goal2_bac": {
        "sql_file": "bot_goal2_bac.sql",
        "acyr_code": ["2020", "2021", "2022", "2023", "2024"],
        "param_name": "acyr_code",
        "db_section": "rept",
    },
    "bot_goal2_xfer": {
        "sql_file": "bot_goal2_xfer.sql",
        "acyr_code": ["2020", "2021", "2022", "2023", "2024"],
        "param_name": "acyr_code",
        "db_section": "rept",
    },
    "bot_goal2_wage": {
        "sql_file": "bot_goal2_wage.sql",
        "acyr_code": ["2019", "2020", "2021", "2022", "2023"],
        "param_name": "acyr_code",
        "db_section": "rept",
    },
    "bot_goal2_wage_denom": {
        "sql_file": "bot_goal2_wage_denom.sql",
        "acyr_code": ["2019", "2020", "2021", "2022", "2023"],
        "param_name": "acyr_code",
        "db_section": "dwhdb",
    },
    "bot_goal3_finaid": {
        "sql_file": "bot_goal3_finaid.sql",
        "acyr_code": ["2020", "2021", "2022", "2023", "2024"],
        "param_name": "acyr_code",
        "db_section": "rept",
    },
    "bot_goal3_units": {
        "sql_file": "bot_goal3_units.sql",
        "acyr_code": ["2020", "2021", "2022", "2023", "2024"],
        "param_name": "acyr_code",
        "db_section": "rept",
    }
}

SQL_DIR = Path(__file__).resolve().parent / "sql"
HYPER_DIR = Path(__file__).resolve().parent / "hyper"
