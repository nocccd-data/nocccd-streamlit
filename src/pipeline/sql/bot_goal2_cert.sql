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
            'Y' as cert_ind
        FROM (
            SELECT
                ROW_NUMBER() OVER (PARTITION BY shrdgmr.shrdgmr_term_code_completed, shrdgmr.shrdgmr_coll_code_1, shrdgmr.shrdgmr_pidm, shrdgmr.shrdgmr_program ORDER BY shrdgmr.shrdgmr_seq_no DESC) AS rnum,
                shrdgmr.shrdgmr_pidm,
                SUBSTR(shrdgmr.shrdgmr_coll_code_1, 1, 1) AS camp_code,
                stvterm.stvterm_acyr_code,
                shrdgmr.shrdgmr_degc_code,
                SUBSTR(baninst1.f_get_desc_fnc('STVDEGS', shrdgmr.shrdgmr_degs_code, 30), 1,
                       30) AS status
            FROM saturn.shrdgmr shrdgmr
                LEFT JOIN saturn.stvterm stvterm
                    ON (shrdgmr.shrdgmr_term_code_completed = stvterm.stvterm_code)
            WHERE shrdgmr.shrdgmr_degc_code IN ('B', 'L', 'N', 'M', 'T', 'F')
        )
        WHERE rnum = 1
          AND status IN ('Awarded', 'Auto-Award')
            AND camp_code in ('1', '2')
        GROUP BY
            stvterm_acyr_code,
            shrdgmr_pidm,
            camp_code
    ),

    base AS (
        SELECT
            t.stvterm_acyr_code AS acyr_code,
            SUBSTR(r.sfrstcr_camp_code, 1, 1) AS camp_code,
            CASE
                WHEN SUBSTR(r.sfrstcr_camp_code, 1, 1) = '1' THEN 'Cypress'
                WHEN SUBSTR(r.sfrstcr_camp_code, 1, 1) = '2' THEN 'Fullerton'
                WHEN SUBSTR(r.sfrstcr_camp_code, 1, 1) = '3' THEN 'NOCE'
            END AS camp_desc,
            CASE
                WHEN SUBSTR(r.sfrstcr_camp_code, 1, 1) IN ('1', '2') THEN 'Credit'
                WHEN SUBSTR(r.sfrstcr_camp_code, 1, 1) = '3' THEN 'Noncredit'
            END AS site,
            n.stvacyr_desc AS academic_year,
            r.sfrstcr_term_code AS term_code,
            r.sfrstcr_pidm AS pidm,
            r.sfrstcr_crn AS crn,
            COALESCE(f.first_gen_ind, 'NULL') AS first_gen_ind,
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
            FLOOR(MONTHS_BETWEEN(stvterm_start_date, spbpers_birth_date) / 12) AS age
        FROM sfrstcr r
            LEFT JOIN first_gen f
                ON (
                r.sfrstcr_pidm = f.svbsgpd_pidm
                    AND r.sfrstcr_term_code >= f.from_term
                    AND r.sfrstcr_term_code < f.to_term
                )
            INNER JOIN stvterm t
                ON (r.sfrstcr_term_code = t.stvterm_code)
            INNER JOIN stvacyr n
                ON (t.stvterm_acyr_code = n.stvacyr_code)
            INNER JOIN stvrsts v
                ON (r.sfrstcr_rsts_code = v.stvrsts_code)
            INNER JOIN spbpers d
                ON (r.sfrstcr_pidm = d.spbpers_pidm)
        WHERE t.stvterm_acyr_code = :acyr_code
          AND (SUBSTR(r.sfrstcr_camp_code, 1, 1) IN ('1', '2')
            AND v.stvrsts_voice_type IN ('R', 'W'))
    )

SELECT
    a.acyr_code,
    a.camp_code,
    a.camp_desc,
    a.site,
    a.academic_year,
    a.term_code,
    a.pidm,
    a.crn,
    CASE MIN(CASE a.first_gen_ind WHEN 'Y' THEN 1 WHEN 'N' THEN 2 ELSE 3 END)
             OVER (PARTITION BY a.acyr_code, a.pidm)
        WHEN 1 THEN 'Y'
        WHEN 2 THEN 'N'
        ELSE 'NULL'
    END AS first_gen_ind,
    a.gender,
    a.race_description,
    a.age
FROM base a
    INNER JOIN cte_shrdgmr b
        ON (a.pidm = b.pidm
        AND a.acyr_code = b.acyr_code
        AND a.camp_code = b.camp_code)
WHERE a.site = 'Credit'