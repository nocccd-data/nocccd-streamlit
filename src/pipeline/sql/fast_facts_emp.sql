WITH

    orgn AS (
        SELECT
            ftvorgn_orgn_code,
            ftvorgn_title
        FROM ftvorgn
        WHERE ftvorgn_status_ind = 'A'
          AND ftvorgn_eff_date = (
            SELECT
                MAX(ftvorgn_eff_date)
            FROM ftvorgn f2
            WHERE f2.ftvorgn_orgn_code = ftvorgn.ftvorgn_orgn_code
        )
    ),

    emp AS (
        SELECT DISTINCT
            a.perjtot_year AS fisc_year,
            a.perjtot_pidm AS pidm,
            a.perjtot_posn AS posn,
            a.perjtot_suff AS suff,
            p.spriden_id AS id,
            p.spriden_last_name AS last_name,
            p.spriden_first_name AS first_name,
            b.pebempl_ecls_code AS ecls_code,
            CASE
                WHEN b.pebempl_ecls_code IN ('AM', 'CM') THEN 'Administrator/Manager'
                WHEN b.pebempl_ecls_code IN ('CF', 'CP', 'CS') THEN 'Confidential/Classified'
                WHEN b.pebempl_ecls_code IN ('F1', 'F2', 'F3', 'F4') THEN 'FT Faculty'
                WHEN b.pebempl_ecls_code IN ('F5', 'F6', 'F7', 'SS') THEN 'PT/Temp Faculty'
                WHEN b.pebempl_ecls_code = 'TA' THEN 'Temp Admin'
                WHEN b.pebempl_ecls_code IN ('XC', 'XO') THEN 'Executive'
                WHEN b.pebempl_ecls_code = 'HE' THEN 'Hourly/Prof Expert/Stud Worker'
                ELSE 'Other'
            END AS ecls_desc,
            baninst1.fz_get_student_ipeds_ethnicity(a.perjtot_pidm) AS ipeds_ethn,
            ROUND(MONTHS_BETWEEN(SYSDATE, s.spbpers_birth_date) / 12) AS age,
            CASE
                WHEN ROUND(MONTHS_BETWEEN(SYSDATE, s.spbpers_birth_date) / 12) BETWEEN 0 AND 17 THEN 'under 18'
                WHEN ROUND(MONTHS_BETWEEN(SYSDATE, s.spbpers_birth_date) / 12) BETWEEN 18 AND 34 THEN '18 to 34'
                WHEN ROUND(MONTHS_BETWEEN(SYSDATE, s.spbpers_birth_date) / 12) BETWEEN 35 AND 39 THEN '35 to 39'
                WHEN ROUND(MONTHS_BETWEEN(SYSDATE, s.spbpers_birth_date) / 12) BETWEEN 40 AND 44 THEN '40 to 44'
                WHEN ROUND(MONTHS_BETWEEN(SYSDATE, s.spbpers_birth_date) / 12) BETWEEN 45 AND 49 THEN '45 to 49'
                WHEN ROUND(MONTHS_BETWEEN(SYSDATE, s.spbpers_birth_date) / 12) BETWEEN 50 AND 54 THEN '50 to 54'
                WHEN ROUND(MONTHS_BETWEEN(SYSDATE, s.spbpers_birth_date) / 12) BETWEEN 55 AND 59 THEN '55 to 59'
                WHEN ROUND(MONTHS_BETWEEN(SYSDATE, s.spbpers_birth_date) / 12) BETWEEN 60 AND 64 THEN '60 to 64'
                ELSE '65+'
            END AS agegroup,
            CASE
                WHEN s.spbpers_gndr_code IN ('0B', '1B', '2B', 'B') THEN 'NB'
                ELSE COALESCE(s.spbpers_sex, 'NULL')
            END AS gender,
            CASE
                WHEN b.pebempl_orgn_code_home >= 1000 AND b.pebempl_orgn_code_home <= 1999 THEN 'District'
                WHEN b.pebempl_orgn_code_home >= 2000 AND b.pebempl_orgn_code_home <= 4999 THEN 'Cypress'
                WHEN b.pebempl_orgn_code_home >= 5000 AND b.pebempl_orgn_code_home <= 7999 THEN 'Fullerton'
                WHEN b.pebempl_orgn_code_home >= 8000 AND b.pebempl_orgn_code_home <= 9999 THEN 'NOCE'
            END AS site,
            o.ftvorgn_title AS dept_from_org
        FROM perjtot a
            INNER JOIN pebempl b
                ON (a.perjtot_pidm = b.pebempl_pidm)
            INNER JOIN spbpers s
                ON (a.perjtot_pidm = s.spbpers_pidm)
            LEFT JOIN orgn o
                ON (b.pebempl_orgn_code_home = o.ftvorgn_orgn_code)
            JOIN spriden p
                ON (a.perjtot_pidm = p.spriden_pidm
                AND p.spriden_change_ind IS NULL)
        WHERE a.perjtot_earn_code <> 'REG'
          AND a.perjtot_year = :fisc_year
          AND a.perjtot_month BETWEEN '01' AND '12'
          AND b.pebempl_ecls_code NOT LIKE 'R%' -- excludes retirees
    )
SELECT *
FROM emp
WHERE ecls_desc IN ('Administrator/Manager', 'Confidential/Classified', 'FT Faculty', 'PT/Temp Faculty', 'Temp Admin',
                    'Executive')