-- ============================================================================
-- INOPERABLE AS WRITTEN -- dwh.mv_enrollment_by_date_5yrs NO LONGER EXISTS.
--
-- The MV was dropped from DWHDB on 2026-07-22, along with its PUBLIC synonym.
-- Its refresh job had already been dropped on 2026-06-23 after recurring
-- ORA-01555 (snapshot too old) failures -- the daily COMPLETE refresh rebuilt
-- all 5 years / 3.77M rows over the Banner dblink and routinely outlived
-- Banner's undo retention. It is not being rebuilt.
--
-- Impact: the MV is the DRIVING TABLE of the final SELECT below (FROM ... a),
-- so this query now fails outright with ORA-00942 -- it does not degrade. The
-- `enrollment_dashboard` pipeline job (python -m src.pipeline.run
-- enrollment_dashboard) will fail, and its Tableau Cloud publish will not
-- refresh.
--
-- Note also that the MV had been frozen at 2026-06-20 ever since its refresh
-- job was dropped, so anything this job published between then and now was a
-- static snapshot rather than current data.
--
-- To revive this, the 5-year enrollment-by-date grain has to come from
-- somewhere else (e.g. a dbt incremental model in edw_prod keyed on term_code;
-- closed terms never change, so ~3.4M of the 3.77M rows are static).
--
-- The ad-hoc twin of this query, nocccd-sql/district/queries/
-- enrollment_dashboard.sql, carries the same FROM clause and the same note.
-- ============================================================================

WITH

    insm AS (
        SELECT *
        FROM dwh.mv_instructional_method
        where ssbsect_term_code in (:t1...)
    ),

    demog AS (
        SELECT
            pidm,
            dwh.fz_get_student_ipeds_ethnicity(pidm) AS ipeds_ethn,
            term_code,
            enrollment_status_code,
            student_term_age,
            college_code,
            high_school_code,
            residency_code,
            gender_code,
            goal_code
        FROM szwstda@banner.nocccd.edu
        where term_code in (:t1...)
    )

SELECT
    a.*,
    b.xlist_import,
    b.stvdivs_desc,
    b.stvdept_desc,
    b.ssbsect_ptrm_start_date,
    b.ssbsect_max_enrl,
    b.ssbsect_ssts_code,
    b.ssbsect_acct_code,
    b.ssbsect_lab_hr,
    b.ssbsect_schd_code,
    b.ssbsect_subj_code,
    b.ssbsect_crse_numb,
    b.div,
    b.lab_ind,
    b.insm_mode,
    c.ipeds_ethn,
    c.enrollment_status_code,
    c.student_term_age,
    c.college_code,
    c.high_school_code,
    c.residency_code,
    c.gender_code,
    c.goal_code
FROM dwh.mv_enrollment_by_date_5yrs a
    LEFT JOIN insm b
        ON (a.term_code = b.ssbsect_term_code
        AND a.crn = b.ssbsect_crn)
    LEFT JOIN demog c
        ON (a.pidm = c.pidm
        AND a.term_code = c.term_code)
WHERE a.term_code in (:t1...)