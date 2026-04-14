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
        FROM svbsgpd@banner.nocccd.edu
    ),

    next_acyr_not_exist AS (
        SELECT DISTINCT
            sfrstcr.sfrstcr_pidm,
            SUBSTR(sfrstcr.sfrstcr_camp_code, 1, 1) AS camp_code
        FROM saturn.sfrstcr@banner.nocccd.edu sfrstcr
            LEFT JOIN saturn.stvrsts@banner.nocccd.edu stvrsts
                ON (sfrstcr.sfrstcr_rsts_code = stvrsts.stvrsts_code)
            LEFT JOIN saturn.stvterm@banner.nocccd.edu stvterm
                ON (sfrstcr.sfrstcr_term_code = stvterm.stvterm_code)
        WHERE ((stvrsts.stvrsts_voice_type IN ('R', 'W')
            AND SUBSTR(sfrstcr.sfrstcr_camp_code, 1, 1) IN ('1', '2'))
            OR (stvrsts.stvrsts_apport_ind = 'Y'
                AND SUBSTR(sfrstcr.sfrstcr_camp_code, 1, 1) = '3'))
          AND stvterm.stvterm_acyr_code = TO_CHAR(TO_NUMBER(:acyr_code) + 1)
    ),

    xfer_not_exist AS (
        SELECT
            b.spbpers_pidm AS pidm
        FROM dwh.scff_xfer a
            LEFT JOIN saturn.spbpers@banner.nocccd.edu b
                ON (a.student_id = b.spbpers_ssn)
        WHERE '20' || SUBSTR(a.mis_acyr_id, 1, 2) - 1 = TO_CHAR(TO_NUMBER(:acyr_code) + 1)

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
                WHEN dwh.fz_get_student_ipeds_ethnicity(r.sfrstcr_pidm) = 'A'
                    THEN 'Asian'
                WHEN dwh.fz_get_student_ipeds_ethnicity(r.sfrstcr_pidm) = 'B'
                    THEN 'Black or African American'
                WHEN dwh.fz_get_student_ipeds_ethnicity(r.sfrstcr_pidm) = 'H'
                    THEN 'Hispanic or Latino'
                WHEN dwh.fz_get_student_ipeds_ethnicity(r.sfrstcr_pidm) = 'N'
                    THEN 'American Indian or Alaska Native'
                WHEN dwh.fz_get_student_ipeds_ethnicity(r.sfrstcr_pidm) = 'P'
                    THEN 'Pacific Islander or Native Hawaiian'
                WHEN dwh.fz_get_student_ipeds_ethnicity(r.sfrstcr_pidm) = 'T'
                    THEN 'Multiethnicity'
                WHEN dwh.fz_get_student_ipeds_ethnicity(r.sfrstcr_pidm) = 'W'
                    THEN 'White Non-Hispanic'
                WHEN dwh.fz_get_student_ipeds_ethnicity(r.sfrstcr_pidm) = 'F'
                    THEN 'Filipino'
                WHEN dwh.fz_get_student_ipeds_ethnicity(r.sfrstcr_pidm) = 'X'
                    THEN 'Unreported'
                ELSE 'Unreported'
            END AS race_description,
            FLOOR(MONTHS_BETWEEN(stvterm_start_date, spbpers_birth_date) / 12) AS age
        FROM sfrstcr@banner.nocccd.edu r
            LEFT JOIN first_gen f
                ON (
                r.sfrstcr_pidm = f.svbsgpd_pidm
                    AND r.sfrstcr_term_code >= f.from_term
                    AND r.sfrstcr_term_code < f.to_term
                )
            INNER JOIN stvterm@banner.nocccd.edu t
                ON (r.sfrstcr_term_code = t.stvterm_code)
            INNER JOIN stvacyr@banner.nocccd.edu n
                ON (t.stvterm_acyr_code = n.stvacyr_code)
            INNER JOIN stvrsts@banner.nocccd.edu v
                ON (r.sfrstcr_rsts_code = v.stvrsts_code)
            INNER JOIN spbpers@banner.nocccd.edu d
                ON (r.sfrstcr_pidm = d.spbpers_pidm)
        WHERE t.stvterm_acyr_code = :acyr_code
          AND SUBSTR(r.sfrstcr_camp_code, 1, 1) IN ('1', '2')
          AND v.stvrsts_voice_type IN ('R', 'W')


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
WHERE NOT EXISTS
(
    SELECT
        z.sfrstcr_pidm
    FROM next_acyr_not_exist z
    WHERE a.pidm = z.sfrstcr_pidm
      AND z.camp_code IN ('1', '2')
)
  AND NOT EXISTS
(
    SELECT
        y.pidm
    FROM xfer_not_exist y
    WHERE a.pidm = y.pidm
)
