from pathlib import Path

DATASETS = {
    "fast_facts_emp": {
        "sql_file": "fast_facts_emp.sql",
        "fisc_year": ["2024", "2025", "2026"],
        "param_name": "fisc_year",
        "db_section": "rept",
    },
    "fast_facts_stu": {
        "sql_file": "fast_facts_stu.sql",
        "acyr_code": ["2023", "2024", "2025"],
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
    "kpi_persistence": {
        "sql_file": "kpi_persistence.sql",
        "mis_term_id": ["237", "247", "257", "267"],
        "param_name": "mis_term_id",
        "db_section": "dwhdb",
    },
    "kpi_applied_to_enrolled": {
        "sql_file": "kpi_applied_to_enrolled.sql",
        "mis_term_id": ["247", "257", "267"],
        "param_name": "mis_term_id",
        "db_section": "dwhdb",
    },
    "kpi_dual_enrollment": {
        "sql_file": "kpi_dual_enrollment.sql",
        "acyr_code": ["2024", "2025", "2026"],
        "param_name": "acyr_code",
        "db_section": "dwhdb",
    },
    "enrollment_dashboard": {
        # Used by the Tableau hyper pipeline only (no Streamlit tab). Excluded
        # from the bulk/scheduled refresh; run manually when needed:
        #   python -m src.pipeline.run enrollment_dashboard
        "skip_refresh": True,
        # The MV is a rolling 5-year window (by SYSDATE); we filter it down to
        # the two terms being compared so the extract stays small. Change the
        # term list to reslice without touching the SQL.
        "sql_file": "enrollment_dashboard.sql",
        "banner_term_code": ["202510", "202610"],
        "param_name": "banner_term_code",
        "db_section": "dwhdb",
    },
    "seat_count_report": {
        "sql_file": "seat_count_report.sql",
        "banner_term_code": ["202310", "202315", "202320", "202335", "202330", "202405",
                             "202410", "202415", "202420", "202435", "202430", "202505",
                             "202510", "202515", "202520", "202535", "202530", "202605",
                             "202610", "202615"],
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
    },
    "bot_goal4_xfer_ready": {
        "sql_file": "bot_goal4_xfer_ready.sql",
        "acyr_code": ["2020", "2021", "2022", "2023", "2024"],
        "param_name": "acyr_code",
        "db_section": "rept",
    }
}

SQL_DIR = Path(__file__).resolve().parent / "sql"
HYPER_DIR = Path(__file__).resolve().parent / "hyper"


def max_acyr_label() -> str:
    """Academic-year label from the max bot_goal1_students acyr_code.

    Other BOT datasets sometimes cover a different 5-year window (e.g.
    living-wage is shifted by 1), so export organization is anchored on the
    canonical Goal 1 students range. Example: ``2024`` -> ``2024-25``.
    """
    cfg = DATASETS["bot_goal1_students"]
    max_acyr = max(cfg[cfg["param_name"]], key=lambda value: int(value))
    start_year = int(max_acyr)
    return f"{start_year}-{(start_year + 1) % 100:02d}"
