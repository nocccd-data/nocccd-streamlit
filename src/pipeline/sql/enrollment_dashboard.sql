WITH

    cte_scbcrse AS (
        SELECT
            SUBSTR(scbcrse.scbcrse_coll_code, 1, 1) AS scbcrse_coll_code,
            scbcrse.scbcrse_subj_code,
            scbcrse.scbcrse_crse_numb,
            scbcrse.scbcrse_eff_term AS scbcrse_from_term,
            LEAD(scbcrse_eff_term, 1, '999999')
                 OVER ( PARTITION BY SUBSTR(scbcrse.scbcrse_coll_code, 1, 1), scbcrse_subj_code, scbcrse_crse_numb
                     ORDER BY scbcrse_eff_term NULLS LAST) AS scbcrse_to_term,
            scbcrse.scbcrse_divs_code,
            stvdivs.stvdivs_desc,
            scbcrse.scbcrse_dept_code,
            stvdept.stvdept_desc,
            CASE
                WHEN scbcrse.scbcrse_credit_hr_ind IS NOT NULL
                    THEN (CASE
                              WHEN scbcrse.scbcrse_credit_hr_low < 1
                                  THEN NVL(TO_CHAR(scbcrse.scbcrse_credit_hr_low, '90.9'), '0')
                              ELSE NVL(TO_CHAR(scbcrse.scbcrse_credit_hr_low, '90'), '0')
                          END) || ' ' || LOWER(scbcrse.scbcrse_credit_hr_ind) || ' ' ||
                    (CASE
                         WHEN scbcrse.scbcrse_credit_hr_high < 1
                             THEN LTRIM(TO_CHAR(scbcrse.scbcrse_credit_hr_high, '90.9'))
                         ELSE LTRIM(TO_CHAR(scbcrse.scbcrse_credit_hr_high, '90'))
                     END)
                ELSE (CASE
                          WHEN scbcrse.scbcrse_credit_hr_low < 1 THEN TO_CHAR(scbcrse.scbcrse_credit_hr_low, '90.9')
                          ELSE TO_CHAR(scbcrse.scbcrse_credit_hr_low, '90')
                      END)
            END AS scbcrse_units,
            TRIM(scbcrse.scbcrse_lec_hr_low || ' ' || LOWER(scbcrse.scbcrse_lec_hr_ind) || ' '
                || scbcrse.scbcrse_lec_hr_high) AS scbcrse_lec_hrs,
            TRIM(scbcrse.scbcrse_lab_hr_low || ' ' || LOWER(scbcrse.scbcrse_lab_hr_ind) || ' '
                || scbcrse.scbcrse_lab_hr_high) AS scbcrse_lab_hrs,
            scbcrse.scbcrse_lab_hr_low,
            TRIM(scbcrse.scbcrse_cont_hr_low || ' ' || LOWER(scbcrse.scbcrse_cont_hr_ind) || ' '
                || scbcrse.scbcrse_cont_hr_high) AS scbcrse_cont_hrs,
            scbcrse.scbcrse_title,
            scbcrse.scbcrse_cipc_code
        FROM saturn.scbcrse@banner.nocccd.edu scbcrse
            LEFT JOIN saturn.stvdivs@banner.nocccd.edu stvdivs
                ON (scbcrse.scbcrse_divs_code = stvdivs.stvdivs_code)
            LEFT JOIN saturn.stvdept@banner.nocccd.edu stvdept
                ON (scbcrse.scbcrse_dept_code = stvdept.stvdept_code)
    ),

    cte_ssbsect AS (
        SELECT
            ssbsect_ssts_code,
            ssbsect_camp_code,
            ssbsect_term_code,
            ssbsect_crn,
            ssbsect_crse_numb,
            ssbsect_subj_code,
            ssrmeet_catagory,
            ssbsect_acct_code,
            ssbsect_schd_code,
            ssrmeet_schd_code,
            ssrmeet_mtyp_code,
            ssbsect_insm_code,
            ssbsect_ptrm_start_date,
            ssbsect_ptrm_code,
            ssrmeet_bldg_code,
            ssrmeet_room_code,
            session_code,
            session_number,
            lab_ind,
            scbcrse_divs_code,
            stvdivs_desc,
            scbcrse_dept_code,
            stvdept_desc,
            ssbsect_credit_hrs,
            ssrmeet_credit_hr_sess,
            ssbsect_cont_hr,
            ssbsect_lab_hr,
            ssbsect_max_enrl,
            units,
            scbcrse_units,
            scbcrse_lec_hrs,
            scbcrse_lab_hrs,
            scbcrse_cont_hrs,
            scbcrse_title,
            scbcrse_cipc_code,
            ssbsect_census_enrl,
            ssrmeet_hrs_week,
            ssrmeet_hrs_total,
            ssrmeet_meet_no,
            MAX(
                CASE
                    WHEN session_number = '1' THEN 1
                    ELSE 0
                END) OVER (PARTITION BY SUBSTR(ssbsect_camp_code, 1, 1),ssbsect_term_code,ssbsect_crn) AS async,
            MAX(
                CASE
                    WHEN session_number = '2' THEN 1
                    ELSE 0
                END) OVER (PARTITION BY SUBSTR(ssbsect_camp_code, 1, 1),ssbsect_term_code,ssbsect_crn) AS sync,
            MAX(
                CASE
                    WHEN session_number = '3' THEN 1
                    ELSE 0
                END) OVER (PARTITION BY SUBSTR(ssbsect_camp_code, 1, 1),ssbsect_term_code,ssbsect_crn) AS ip,
            MAX(
                CASE
                    WHEN session_number = '0' THEN 1
                    ELSE 0
                END) OVER (PARTITION BY SUBSTR(ssbsect_camp_code, 1, 1),ssbsect_term_code,ssbsect_crn) AS blank
        FROM (
            SELECT
                ssbsect.ssbsect_ssts_code,
                SUBSTR(ssbsect.ssbsect_camp_code, 1, 1) AS ssbsect_camp_code,
                ssbsect.ssbsect_term_code,
                ssbsect.ssbsect_crn,
                ssbsect.ssbsect_crse_numb,
                ssbsect.ssbsect_subj_code,
                ssrmeet.ssrmeet_catagory,
                ssbsect.ssbsect_acct_code,
                ssbsect.ssbsect_schd_code,
                ssrmeet.ssrmeet_schd_code,
                ssrmeet.ssrmeet_mtyp_code,
                ssbsect.ssbsect_insm_code,
                ssbsect.ssbsect_ptrm_start_date,
                ssbsect.ssbsect_ptrm_code,
                ssrmeet.ssrmeet_bldg_code,
                ssrmeet.ssrmeet_room_code,
                ssbsect.ssbsect_credit_hrs,
                ssbsect.ssbsect_census_enrl,
                ssrmeet.ssrmeet_credit_hr_sess,
                ssbsect.ssbsect_cont_hr,
                ssbsect.ssbsect_lab_hr,
                ssbsect.ssbsect_max_enrl,
                ssrmeet.ssrmeet_hrs_week,
                ssrmeet.ssrmeet_hrs_total,
                ssrmeet.ssrmeet_meet_no,
                g.scbcrse_divs_code,
                g.stvdivs_desc,
                g.scbcrse_dept_code,
                g.stvdept_desc,
                g.scbcrse_units,
                g.scbcrse_lec_hrs,
                g.scbcrse_lab_hrs,
                g.scbcrse_cont_hrs,
                g.scbcrse_title,
                g.scbcrse_cipc_code,
                CASE
                    WHEN ssbsect.ssbsect_schd_code = '04' OR (NVL(ssbsect.ssbsect_lab_hr, g.scbcrse_lab_hr_low) > 0
                        AND NVL(ssbsect.ssbsect_lab_hr, g.scbcrse_lab_hr_low) IS NOT NULL) THEN 'Y'
                END AS lab_ind,
                TRIM(CASE
                         WHEN ssbsect.ssbsect_credit_hrs IS NOT NULL
                             THEN (CASE
                                       WHEN ssbsect.ssbsect_credit_hrs < 1
                                           THEN TO_CHAR(ssbsect.ssbsect_credit_hrs, '90.9')
                                       ELSE TO_CHAR(ssbsect.ssbsect_credit_hrs, '90')
                                   END)
                         ELSE g.scbcrse_units
                     END) "UNITS",
                CASE
                    WHEN ssrmeet_schd_code IN ('72', '72L', 'HY', 'HYL') THEN 'Async'
                    WHEN ssrmeet_schd_code IN ('20', '40', '90') AND ssrmeet_mtyp_code IN ('ALT', 'ONL') THEN 'Async'
                    WHEN SUBSTR(ssrmeet_term_code, 6, 1) = '5' AND ssrmeet_schd_code = 'EMO' THEN 'Async'
                    WHEN ssrmeet_bldg_code IN ('Zoom', UPPER('Zoom'), LOWER('Zoom')) THEN 'Sync'
                    WHEN ssrmeet_bldg_code IN ('Online', UPPER('Online'), LOWER('Online'))
                        AND (ssrmeet_schd_code NOT LIKE '72%' OR ssrmeet_schd_code NOT LIKE 'HY%') THEN 'Sync'
                    WHEN ssrmeet_term_code >= '202310' AND ssrmeet_schd_code LIKE '71%' THEN 'Sync'
                    WHEN ssrmeet_bldg_code NOT IN ('Zoom', UPPER('Zoom'), LOWER('Zoom'), 'Online', UPPER('Online'),
                                                   LOWER('Online')) THEN 'In_Person'
                    WHEN ssrmeet_mtyp_code = 'ARN' THEN 'In_Person'
                    WHEN ssrmeet_bldg_code IS NULL THEN 'No_BLDG'
                END AS session_code,
                CASE
                    WHEN ssrmeet_schd_code IN ('72', '72L', 'HY', 'HYL') THEN 1
                    WHEN ssrmeet_schd_code IN ('20', '40', '90') AND ssrmeet_mtyp_code IN ('ALT', 'ONL') THEN 1
                    WHEN SUBSTR(ssrmeet_term_code, 6, 1) = '5' AND ssrmeet_schd_code = 'EMO' THEN 1
                    WHEN ssrmeet_bldg_code IN ('Zoom', UPPER('Zoom'), LOWER('Zoom')) THEN 2
                    WHEN ssrmeet_bldg_code IN ('Online', UPPER('Online'), LOWER('Online'))
                        AND (ssrmeet_schd_code NOT LIKE '72%' OR ssrmeet_schd_code NOT LIKE 'HY%') THEN 2
                    WHEN ssrmeet_term_code >= '202310' AND ssrmeet_schd_code LIKE '71%' THEN 2
                    WHEN ssrmeet_bldg_code NOT IN ('Zoom', UPPER('Zoom'), LOWER('Zoom'), 'Online', UPPER('Online'),
                                                   LOWER('Online')) THEN 3
                    WHEN ssrmeet_mtyp_code = 'ARN' THEN 3
                    WHEN ssrmeet_bldg_code IS NULL THEN 0
                END session_number
            FROM saturn.ssbsect@banner.nocccd.edu ssbsect
                LEFT JOIN saturn.ssrmeet@banner.nocccd.edu ssrmeet
                    ON (ssbsect.ssbsect_term_code = ssrmeet.ssrmeet_term_code
                    AND ssbsect.ssbsect_crn = ssrmeet.ssrmeet_crn)
                LEFT JOIN cte_scbcrse g
                    ON (ssbsect.ssbsect_subj_code = g.scbcrse_subj_code
                    AND ssbsect.ssbsect_crse_numb = g.scbcrse_crse_numb
                    AND SUBSTR(ssbsect.ssbsect_camp_code, 1, 1) = g.scbcrse_coll_code
                    AND ssbsect.ssbsect_term_code >= g.scbcrse_from_term
                    AND ssbsect.ssbsect_term_code < g.scbcrse_to_term)
            WHERE (ssrmeet.ssrmeet_mtyp_code IS NULL OR ssrmeet.ssrmeet_mtyp_code <> 'PAY')
              AND (g.scbcrse_divs_code IS NULL OR g.scbcrse_divs_code <> '2ZZ')

        )
    ),

    cte_ssbxlst_ssrxlst AS (
        SELECT
            ssbxlst.ssbxlst_term_code,
            ssbxlst.ssbxlst_xlst_group,
            ssbxlst.ssbxlst_desc,
            ssrxlst.ssrxlst_crn,
            ssbxlst.ssbxlst_max_enrl,
            ssbxlst.ssbxlst_seats_avail
        FROM saturn.ssbxlst@banner.nocccd.edu ssbxlst
            LEFT JOIN saturn.ssrxlst@banner.nocccd.edu ssrxlst
                ON (ssbxlst.ssbxlst_term_code = ssrxlst.ssrxlst_term_code
                AND ssbxlst.ssbxlst_xlst_group = ssrxlst.ssrxlst_xlst_group)
    ),

    insm AS (
        SELECT DISTINCT
            ssbsect_term_code,
            ssbsect_crn,
            c.ssbxlst_xlst_group AS xlist_import,
            ssbsect_camp_code,
            CASE
                WHEN ssbsect.ssbsect_camp_code LIKE '1%' THEN 'Cypress'
                WHEN ssbsect.ssbsect_camp_code LIKE '2%' THEN 'Fullerton'
                WHEN ssbsect.ssbsect_camp_code LIKE '3%' THEN 'NOCE'
            END "COLLEGE",
            stvdivs_desc,
            stvdept_desc,
            ssbsect_ptrm_start_date,
            ssbsect_ptrm_code,
            NVL(
                ssbsect_max_enrl, 0) AS ssbsect_max_enrl,
            ssbsect_ssts_code,
            ssbsect_acct_code,
            ssbsect_lab_hr,
            ssbsect_schd_code,
            ssbsect_subj_code,
            ssbsect_crse_numb,
            SUBSTR(
                fz_get_course_division@banner.nocccd.edu(
                    ssbsect_subj_code, ssbsect_crse_numb, ssbsect_term_code), 0, 6) AS div,
            lab_ind,
            CASE
                WHEN async = 1 AND (
                    sync + ip + blank) = 0 THEN 'ASN'
                WHEN sync = 1 AND (
                    async + ip + blank) = 0 THEN 'SYN'
                WHEN async = 1 AND ip = 1 THEN 'HYA'
                WHEN sync = 1 AND ip = 1 THEN 'HYS'
                WHEN sync = 1 AND async = 1 AND (
                    ip + blank) = 0 THEN 'OLZ'
                WHEN sync = 1 AND async = 1 AND ip = 1 THEN 'HYO'
                WHEN (
                    async + sync + blank) = 0 AND ip = 1 THEN 'INP'
                WHEN (
                    ip + blank) >= 1 THEN 'INP'
            END AS insm_mode,
            ssbsect_insm_code
        FROM cte_ssbsect ssbsect
            LEFT JOIN (
            SELECT
                s1.*,
                MAX(
                    s1.svrcaln_activity_date) OVER (
                    PARTITION BY s1.svrcaln_crn, s1.svrcaln_term_code, SUBSTR(
                        s1.svrcaln_camp_code, 1, 1)) AS max_date
            FROM saturn.svrcaln@banner.nocccd.edu s1
        ) s
                ON (
                ssbsect.ssbsect_crn = s.svrcaln_crn
                    AND ssbsect.ssbsect_term_code = s.svrcaln_term_code
                    AND SUBSTR(
                    ssbsect.ssbsect_camp_code, 1, 1) = SUBSTR(
                    s.svrcaln_camp_code, 1, 1)
                    AND s.svrcaln_activity_date = s.max_date)
            LEFT JOIN cte_ssbxlst_ssrxlst c
                ON (
                ssbsect.ssbsect_crn = c.ssrxlst_crn
                    AND ssbsect.ssbsect_term_code = c.ssbxlst_term_code)
    ),

    demog AS (
        SELECT
            pidm,
            baninst1.fz_get_student_ipeds_ethnicity@banner.nocccd.edu(pidm) AS ipeds_ethn,
            term_code,
            enrollment_status_code,
            student_term_age,
            college_code,
            high_school_code,
            residency_code,
            gender_code,
            goal_code
        FROM szwstda@banner.nocccd.edu
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
WHERE a.term_code IN (:t1...)