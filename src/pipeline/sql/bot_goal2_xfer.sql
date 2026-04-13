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
    first_gen_acyr AS (
        SELECT
            b.stvterm_acyr_code AS acyr_code,
            a.svbsgpd_pidm AS pidm,
            CASE MIN(CASE a.first_gen_ind WHEN 'Y' THEN 1 WHEN 'N' THEN 2 ELSE 3 END)
                WHEN 1 THEN 'Y'
                WHEN 2 THEN 'N'
                ELSE 'NULL'
            END AS first_gen_ind
        FROM first_gen a
            JOIN saturn.stvterm b
                ON (b.stvterm_code >= a.from_term
                AND b.stvterm_code < a.to_term)
        GROUP BY
            b.stvterm_acyr_code,
            a.svbsgpd_pidm
    ),

    shrtgpa_acyr AS (
        SELECT
            b.stvterm_acyr_code AS acyr_code,
            a.shrtgpa_pidm AS pidm,
            SUBSTR(a.shrtgpa_levl_code, 1, 1) AS levl_code,
            SUM(a.shrtgpa_hours_earned) AS sum_hrs,
            SUM(a.shrtgpa_hours_attempted) AS sum_hrs_a
        FROM saturn.shrtgpa a
            LEFT JOIN saturn.stvterm b
                ON (a.shrtgpa_term_code = b.stvterm_code)
            LEFT JOIN first_gen c
                ON (a.shrtgpa_pidm = c.svbsgpd_pidm
                AND b.stvterm_acyr_code >= c.from_term
                AND b.stvterm_acyr_code < c.to_term)
        WHERE SUBSTR(a.shrtgpa_levl_code, 1, 1) <> '3'
        GROUP BY
            b.stvterm_acyr_code,
            a.shrtgpa_pidm,
            SUBSTR(a.shrtgpa_levl_code, 1, 1)
    ),

    shrtgpa_sum AS (
        SELECT
            :acyr_code AS acyr_code,
            a.pidm,
            a.levl_code,
            SUM(a.sum_hrs) AS tot_sum_hrs
        FROM shrtgpa_acyr a
        WHERE a.acyr_code <= :acyr_code
        GROUP BY
            :acyr_code,
            a.pidm,
            a.levl_code
        HAVING SUM(a.sum_hrs) >= 12
    ),

    xfer AS (
        SELECT
            b.spbpers_pidm AS pidm,
            a.mis_acyr_id,
            '20' || SUBSTR(a.mis_acyr_id, 1, 2) - 1 AS acyr_code,
            (CASE
                 WHEN b.spbpers_gndr_code IN ('0B', '1B', '2B', 'B')
                     THEN 'NB'
                 ELSE COALESCE(b.spbpers_sex, 'N')
             END) AS gender,
            CASE
                WHEN baninst1.fz_get_student_ipeds_ethnicity(b.spbpers_pidm) = 'A'
                    THEN 'Asian'
                WHEN baninst1.fz_get_student_ipeds_ethnicity(b.spbpers_pidm) = 'B'
                    THEN 'Black or African American'
                WHEN baninst1.fz_get_student_ipeds_ethnicity(b.spbpers_pidm) = 'H'
                    THEN 'Hispanic or Latino'
                WHEN baninst1.fz_get_student_ipeds_ethnicity(b.spbpers_pidm) = 'N'
                    THEN 'American Indian or Alaska Native'
                WHEN baninst1.fz_get_student_ipeds_ethnicity(b.spbpers_pidm) = 'P'
                    THEN 'Pacific Islander or Native Hawaiian'
                WHEN baninst1.fz_get_student_ipeds_ethnicity(b.spbpers_pidm) = 'T'
                    THEN 'Multiethnicity'
                WHEN baninst1.fz_get_student_ipeds_ethnicity(b.spbpers_pidm) = 'W'
                    THEN 'White Non-Hispanic'
                WHEN baninst1.fz_get_student_ipeds_ethnicity(b.spbpers_pidm) = 'F'
                    THEN 'Filipino'
                WHEN baninst1.fz_get_student_ipeds_ethnicity(b.spbpers_pidm) = 'X'
                    THEN 'Unreported'
                ELSE 'Unreported'
            END AS race_description
        FROM dwh.scff_xfer@dwhdb.nocccd.edu a
            INNER JOIN saturn.spbpers b
                ON (a.student_id = b.spbpers_ssn)
    )
SELECT
    b.levl_code AS camp_code,
    a.acyr_code,
    a.pidm,
    a.gender,
    a.race_description,
    COALESCE(c.first_gen_ind, 'NULL') AS first_gen_ind
FROM xfer a
    INNER JOIN shrtgpa_sum b
        ON (a.pidm = b.pidm
        AND a.acyr_code = b.acyr_code)
    LEFT JOIN first_gen_acyr c
        ON (a.pidm = c.pidm
        AND a.acyr_code = c.acyr_code)
