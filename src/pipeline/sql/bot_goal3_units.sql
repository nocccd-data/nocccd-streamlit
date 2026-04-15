WITH
    first_gen AS (
        SELECT
            svbsgpd_pidm,
            svbsgpd_eff_term AS from_term,
            LEAD(svbsgpd_eff_term, 1, '999999')
                 OVER (
                     PARTITION BY svbsgpd_pidm
                     ORDER BY svbsgpd_eff_term NULLS LAST
                     ) AS to_term,
            CASE
                WHEN svbsgpd_guard_1_gedl_code IN ('4', '5', '6', '7') THEN 'N'
                WHEN svbsgpd_guard_2_gedl_code IN ('4', '5', '6', '7') THEN 'N'
                WHEN (
                    (svbsgpd_guard_1_gedl_code IN ('X', 'Y') OR svbsgpd_guard_1_gedl_code IS NULL)
                        AND (svbsgpd_guard_2_gedl_code IN ('X', 'Y') OR svbsgpd_guard_2_gedl_code IS NULL)
                    ) THEN NULL
                ELSE 'Y'
            END AS first_gen_ind
        FROM svbsgpd
            LEFT JOIN svvgedl gedl1
                ON (svbsgpd_guard_1_gedl_code = gedl1.svvgedl_code)
            LEFT JOIN svvgedl gedl2
                ON (svbsgpd_guard_2_gedl_code = gedl2.svvgedl_code)
    ),
    cte_shrdgmr AS (
        SELECT
            stvterm_acyr_code AS acyr_code,
            shrdgmr_pidm AS pidm,
            camp_code,
            first_gen_ind
        FROM (
            SELECT
                ROW_NUMBER() OVER (PARTITION BY shrdgmr.shrdgmr_term_code_completed, shrdgmr.shrdgmr_coll_code_1, shrdgmr.shrdgmr_pidm, shrdgmr.shrdgmr_program ORDER BY shrdgmr.shrdgmr_seq_no DESC) AS rnum,
                shrdgmr.shrdgmr_pidm,
                SUBSTR(shrdgmr.shrdgmr_coll_code_1, 1, 1) AS camp_code,
                stvterm.stvterm_acyr_code,
                shrdgmr.shrdgmr_degc_code,
                SUBSTR(baninst1.f_get_desc_fnc('STVDEGS', shrdgmr.shrdgmr_degs_code, 30), 1,
                       30) AS status,
                COALESCE(f.first_gen_ind, 'NULL') AS first_gen_ind
            FROM saturn.shrdgmr shrdgmr
                LEFT JOIN saturn.stvterm stvterm
                    ON (shrdgmr.shrdgmr_term_code_completed = stvterm.stvterm_code)
                LEFT JOIN first_gen f
                    ON (
                    shrdgmr.shrdgmr_pidm = f.svbsgpd_pidm
                        AND shrdgmr.shrdgmr_term_code_completed >= f.from_term
                        AND shrdgmr.shrdgmr_term_code_completed < f.to_term
                    )
            WHERE shrdgmr.shrdgmr_degc_code IN ('AA-T', 'AS-T', 'AT')
        )
        WHERE rnum = 1
          AND status IN ('Awarded', 'Auto-Award')
          AND camp_code IN ('1', '2')
        GROUP BY
            stvterm_acyr_code,
            shrdgmr_pidm,
            camp_code,
            first_gen_ind
    ),
    sum_shrtgpa AS (
        SELECT
            SUBSTR(r.shrtgpa_levl_code, 1, 1) AS camp_code,
            r.shrtgpa_pidm AS pidm,
            SUM(r.shrtgpa_hours_earned) AS sum_hours_earned
        FROM shrtgpa r
            INNER JOIN stvterm t
                ON (r.shrtgpa_term_code = t.stvterm_code)
        WHERE stvterm_acyr_code <= :acyr_code
        GROUP BY
            SUBSTR(r.shrtgpa_levl_code, 1, 1),
            r.shrtgpa_pidm
        HAVING SUM(r.shrtgpa_hours_earned) > 0
    )
SELECT
    a.acyr_code,
    a.camp_code,
    CASE
        WHEN a.camp_code = '1' THEN 'Cypress'
        WHEN a.camp_code = '2' THEN 'Fullerton'
        WHEN a.camp_code = '3' THEN 'NOCE'
    END AS camp_desc,
    CASE
        WHEN a.camp_code IN ('1', '2') THEN 'Credit'
        WHEN a.camp_code = '3' THEN 'Noncredit'
    END AS site,
    n.stvacyr_desc AS academic_year,
    a.pidm,
    CASE MIN(CASE a.first_gen_ind WHEN 'Y' THEN 1 WHEN 'N' THEN 2 ELSE 3 END)
             OVER (PARTITION BY a.acyr_code, a.pidm)
        WHEN 1 THEN 'Y'
        WHEN 2 THEN 'N'
        ELSE 'NULL'
    END AS first_gen_ind,
    (CASE
         WHEN d.spbpers_gndr_code IN ('0B', '1B', '2B', 'B')
             THEN 'NB'
         ELSE COALESCE(d.spbpers_sex, 'N')
     END) AS gender,
    CASE
        WHEN baninst1.fz_get_student_ipeds_ethnicity(a.pidm) = 'A'
            THEN 'Asian'
        WHEN baninst1.fz_get_student_ipeds_ethnicity(a.pidm) = 'B'
            THEN 'Black or African American'
        WHEN baninst1.fz_get_student_ipeds_ethnicity(a.pidm) = 'H'
            THEN 'Hispanic or Latino'
        WHEN baninst1.fz_get_student_ipeds_ethnicity(a.pidm) = 'N'
            THEN 'American Indian or Alaska Native'
        WHEN baninst1.fz_get_student_ipeds_ethnicity(a.pidm) = 'P'
            THEN 'Pacific Islander or Native Hawaiian'
        WHEN baninst1.fz_get_student_ipeds_ethnicity(a.pidm) = 'T'
            THEN 'Multiethnicity'
        WHEN baninst1.fz_get_student_ipeds_ethnicity(a.pidm) = 'W'
            THEN 'White Non-Hispanic'
        WHEN baninst1.fz_get_student_ipeds_ethnicity(a.pidm) = 'F'
            THEN 'Filipino'
        WHEN baninst1.fz_get_student_ipeds_ethnicity(a.pidm) = 'X'
            THEN 'Unreported'
        ELSE 'Unreported'
    END AS race_description,
    c.sum_hours_earned
FROM cte_shrdgmr a
    INNER JOIN stvacyr n
        ON (a.acyr_code = n.stvacyr_code)
    INNER JOIN spbpers d
        ON (a.pidm = d.spbpers_pidm)
    INNER JOIN sum_shrtgpa c
        ON (a.pidm = c.pidm
        AND a.camp_code = c.camp_code)
WHERE a.acyr_code = :acyr_code