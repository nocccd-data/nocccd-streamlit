WITH
    acyr_term AS (
        SELECT
            :acyr_code AS acyr,
            :acyr_code || '20' AS cutoff_term
        FROM dual
    ),
    cte_first_gen AS (
        SELECT
            svbsgpd_pidm AS pidm,
            svbsgpd_eff_term AS from_term,
            LEAD(svbsgpd_eff_term, 1, '999999') OVER (
                PARTITION BY
                    svbsgpd_pidm
                ORDER BY
                    svbsgpd_eff_term ASC NULLS LAST
                ) AS to_term,
            CASE
                WHEN svbsgpd_guard_1_gedl_code IN ('4', '5', '6', '7') THEN 'N'
                WHEN svbsgpd_guard_2_gedl_code IN ('4', '5', '6', '7') THEN 'N'
                WHEN (
                    svbsgpd_guard_1_gedl_code IN ('X', 'Y', NULL)
                        AND svbsgpd_guard_2_gedl_code IN ('X', 'Y', NULL)
                    ) THEN 'NULL'
                ELSE 'Y'
            END AS first_gen_ind
        FROM svbsgpd
            LEFT JOIN svvgedl gedl1
                ON svbsgpd_guard_1_gedl_code = gedl1.svvgedl_code
            LEFT JOIN svvgedl gedl2
                ON svbsgpd_guard_2_gedl_code = gedl2.svvgedl_code
    ),
    cte_sfrstcr AS (
        SELECT DISTINCT
            CASE MIN(CASE a.first_gen_ind WHEN 'Y' THEN 1 WHEN 'N' THEN 2 ELSE 3 END)
                     OVER (PARTITION BY a.acyr, a.pidm)
                WHEN 1 THEN 'Y'
                WHEN 2 THEN 'N'
                ELSE 'NULL'
            END AS first_gen_ind,
            a.gender,
            a.race_description,
            a.acyr,
            a.pidm
        FROM (
            SELECT
                COALESCE(y.first_gen_ind, 'NULL') AS first_gen_ind,
                (CASE
                     WHEN d.spbpers_gndr_code IN ('0B', '1B', '2B', 'B')
                         THEN 'NB'
                     ELSE COALESCE(d.spbpers_sex, 'N')
                 END) AS gender,
                CASE
                    WHEN baninst1.fz_get_student_ipeds_ethnicity(r.sfrstcr_pidm) = 'A'
                        THEN 'Asian'
                    WHEN baninst1.fz_get_student_ipeds_ethnicity(r.sfrstcr_pidm) = 'B'
                        THEN 'Black or African American'
                    WHEN baninst1.fz_get_student_ipeds_ethnicity(r.sfrstcr_pidm) = 'H'
                        THEN 'Hispanic or Latino'
                    WHEN baninst1.fz_get_student_ipeds_ethnicity(r.sfrstcr_pidm) = 'N'
                        THEN 'American Indian or Alaska Native'
                    WHEN baninst1.fz_get_student_ipeds_ethnicity(r.sfrstcr_pidm) = 'P'
                        THEN 'Pacific Islander or Native Hawaiian'
                    WHEN baninst1.fz_get_student_ipeds_ethnicity(r.sfrstcr_pidm) = 'T'
                        THEN 'Multiethnicity'
                    WHEN baninst1.fz_get_student_ipeds_ethnicity(r.sfrstcr_pidm) = 'W'
                        THEN 'White Non-Hispanic'
                    WHEN baninst1.fz_get_student_ipeds_ethnicity(r.sfrstcr_pidm) = 'F'
                        THEN 'Filipino'
                    WHEN baninst1.fz_get_student_ipeds_ethnicity(r.sfrstcr_pidm) = 'X'
                        THEN 'Unreported'
                    ELSE 'Unreported'
                END AS race_description,
                t.stvterm_acyr_code AS acyr,
                r.sfrstcr_pidm AS pidm
            FROM sfrstcr r
                INNER JOIN stvrsts v
                    ON (r.sfrstcr_rsts_code = v.stvrsts_code)
                INNER JOIN stvterm t
                    ON (r.sfrstcr_term_code = t.stvterm_code)
                LEFT JOIN cte_first_gen y
                    ON (
                    r.sfrstcr_pidm = y.pidm
                        AND r.sfrstcr_term_code >= y.from_term
                        AND r.sfrstcr_term_code < y.to_term
                    )
                INNER JOIN spbpers d
                    ON (r.sfrstcr_pidm = d.spbpers_pidm)
            WHERE t.stvterm_acyr_code = :acyr_code
              AND SUBSTR(r.sfrstcr_camp_code, 1, 1) IN ('1', '2')
              AND v.stvrsts_voice_type IN ('R', 'W')
        ) a
    ),
    cte_scrsbgi AS (
        SELECT
            a.scrsbgi_subj_code,
            a.scrsbgi_crse_numb,
            a.scrsbgi_eff_term AS from_term,
            LEAD(a.scrsbgi_eff_term, 1, '999999') OVER (
                PARTITION BY
                    a.scrsbgi_subj_code,
                    a.scrsbgi_crse_numb
                ORDER BY
                    a.scrsbgi_eff_term ASC NULLS LAST
                ) AS to_term
        FROM scrsbgi a
        WHERE scrsbgi_sbgi_code IN ('UC', 'CSU')
    ),
    cte_latest_attempt AS (
        SELECT
            a.shrtckn_pidm,
            s.first_gen_ind,
            s.gender,
            s.race_description,
            at.acyr,
            at.cutoff_term,
            a.shrtckn_subj_code,
            a.shrtckn_crse_numb,
            a.shrtckn_term_code,
            c.shrtckg_credit_hours,
            c.shrtckg_grde_code_final,
            d.shrgrde_gpa_ind,
            d.shrgrde_quality_points,
            ROW_NUMBER() OVER (
                PARTITION BY
                    a.shrtckn_pidm,
                    at.acyr,
                    a.shrtckn_subj_code,
                    a.shrtckn_crse_numb,
                    a.shrtckn_term_code
                ORDER BY
                    c.shrtckg_seq_no DESC
                ) AS rn
        FROM cte_sfrstcr s
            INNER JOIN acyr_term at
                ON (s.acyr = at.acyr)
            INNER JOIN saturn.shrtckn a
                ON (a.shrtckn_pidm = s.pidm)
            INNER JOIN saturn.shrtckl b
                ON (
                a.shrtckn_pidm = b.shrtckl_pidm
                    AND a.shrtckn_term_code = b.shrtckl_term_code
                    AND a.shrtckn_seq_no = b.shrtckl_tckn_seq_no
                )
            INNER JOIN saturn.shrtckg c
                ON (
                a.shrtckn_pidm = c.shrtckg_pidm
                    AND a.shrtckn_term_code = c.shrtckg_term_code
                    AND a.shrtckn_seq_no = c.shrtckg_tckn_seq_no
                )
            INNER JOIN saturn.shrgrde d
                ON (
                c.shrtckg_grde_code_final = d.shrgrde_code
                    AND SUBSTR(a.shrtckn_camp_code, 1, 1) = SUBSTR(d.shrgrde_levl_code, 1, 1)
                )
            INNER JOIN cte_scrsbgi e
                ON (
                a.shrtckn_crse_numb = e.scrsbgi_crse_numb
                    AND a.shrtckn_subj_code = e.scrsbgi_subj_code
                    AND a.shrtckn_term_code >= e.from_term
                    AND a.shrtckn_term_code < e.to_term
                )
        WHERE b.shrtckl_primary_levl_ind = 'Y'
          AND a.shrtckn_term_code <= at.cutoff_term
          AND SUBSTR(b.shrtckl_levl_code, 1, 1) IN ('1', '2')
          AND c.shrtckg_credit_hours <> 0
          AND NVL(a.shrtckn_repeat_course_ind, 'X') <> 'E'
    ),
    cte_student_agg AS (
        SELECT
            la.acyr,
            la.shrtckn_pidm AS pidm,
            la.first_gen_ind,
            la.gender,
            la.race_description,
            ROUND(
                SUM(
                    CASE
                        WHEN la.shrgrde_gpa_ind = 'Y' THEN (la.shrgrde_quality_points * la.shrtckg_credit_hours)
                        ELSE 0
                    END
                ) / NULLIF(
                    SUM(
                        CASE
                            WHEN la.shrgrde_gpa_ind = 'Y' THEN la.shrtckg_credit_hours
                            ELSE 0
                        END
                    ),
                    0
                    ),
                3
            ) AS gpa,
            SUM(
                CASE
                    WHEN la.shrtckg_grde_code_final IN ('A', 'B', 'C', 'P', 'CR', 'IP', 'INB', 'INC')
                        THEN la.shrtckg_credit_hours
                    ELSE 0
                END
            ) AS units_earn,
            COUNT(
                DISTINCT CASE
                             WHEN la.shrtckn_subj_code = 'MATH'
                                 AND TO_NUMBER(REGEXP_REPLACE(la.shrtckn_crse_numb, '[^0-9]', '')) >= 100
                                 AND la.shrtckg_grde_code_final IN ('A', 'B', 'C', 'P', 'CR', 'IP', 'INB', 'INC')
                                 THEN 'MATH'
                             WHEN la.shrtckn_subj_code = 'ENGL'
                                 AND TO_NUMBER(REGEXP_REPLACE(la.shrtckn_crse_numb, '[^0-9]', '')) >= 100
                                 AND la.shrtckg_grde_code_final IN ('A', 'B', 'C', 'P', 'CR', 'IP', 'INB', 'INC')
                                 THEN 'ENGL'
                         END
            ) AS math_eng_count
        FROM cte_latest_attempt la
        WHERE la.rn = 1
        GROUP BY
            la.acyr,
            la.shrtckn_pidm,
            la.first_gen_ind,
            la.gender,
            la.race_description
    )
SELECT
    agg.acyr AS acyr_code,
    n.stvacyr_desc AS academic_year,
    -- Transfer readiness is a district-level, student-level fact (no single
    -- home campus), so the headcount chart shows one Credit-college bar
    -- rather than a Cypress/Fullerton split. NOCE is excluded upstream.
    'NOCCCD (Unduplicated)' AS camp_desc,
    'Credit' AS site,
    agg.pidm,
    agg.first_gen_ind,
    agg.gender,
    agg.race_description,
    agg.gpa,
    agg.units_earn,
    agg.math_eng_count
FROM cte_student_agg agg
    INNER JOIN stvacyr n
        ON (agg.acyr = n.stvacyr_code)
WHERE agg.gpa >= 2.0
  AND agg.units_earn >= 60
  AND agg.math_eng_count = 2
ORDER BY
    agg.acyr,
    agg.pidm
