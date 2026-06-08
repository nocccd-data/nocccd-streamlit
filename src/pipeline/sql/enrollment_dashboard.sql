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