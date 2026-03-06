WITH
    spriden_cte AS (
                   SELECT
                       spriden_id,
                       MIN(spriden_pidm) AS spriden_pidm
                   FROM
                       jahn.stg_banner__spriden
                   WHERE spriden_change_ind IS NULL
                   GROUP BY
                       spriden_id
                   ),
    spbpers_cte AS (
                   SELECT
                       spbpers_ssn,
                       MIN(spbpers_pidm) AS spbpers_pidm
                   FROM
                       jahn.stg_banner__spbpers
                   GROUP BY
                       spbpers_ssn
                   ),
    cte_aaas AS (
                   SELECT
                       SUBSTR(
                               a.fa_proc_yr, 3, 2) || '0' AS mis_term_id,
                       a.fa_proc_yr,
                       a.student_id,
                       NVL(s.spriden_pidm, p.spbpers_pidm) AS pidm,
                       a.ccpg,
                       a.pell,
                       'aaas' AS award_type
                   FROM
                       dwh.scff_aaas a
                           LEFT JOIN spriden_cte s
                               ON a.student_id = s.spriden_id
                           LEFT JOIN spbpers_cte p
                               ON a.student_id = p.spbpers_ssn
                   ),
    cte_adt AS (
                   SELECT
                       SUBSTR(
                               a.fa_proc_yr, 3, 2) || '0' AS mis_term_id,
                       a.fa_proc_yr,
                       a.student_id,
                       NVL(s.spriden_pidm, p.spbpers_pidm) AS pidm,
                       a.ccpg,
                       a.pell,
                       'adt' AS award_type
                   FROM
                       dwh.scff_adt a
                           LEFT JOIN spriden_cte s
                               ON a.student_id = s.spriden_id
                           LEFT JOIN spbpers_cte p
                               ON a.student_id = p.spbpers_ssn
                   ),
    cte_babs AS (
                   SELECT
                       SUBSTR(
                               a.fa_proc_yr, 3, 2) || '0' AS mis_term_id,
                       a.fa_proc_yr,
                       a.student_id,
                       NVL(s.spriden_pidm, p.spbpers_pidm) AS pidm,
                       a.ccpg,
                       a.pell,
                       'babs' AS award_type
                   FROM
                       dwh.scff_babs a
                           LEFT JOIN spriden_cte s
                               ON a.student_id = s.spriden_id
                           LEFT JOIN spbpers_cte p
                               ON a.student_id = p.spbpers_ssn
                   ),
    cte_cert AS (
                   SELECT
                       SUBSTR(
                               a.fa_proc_yr, 3, 2) || '0' AS mis_term_id,
                       a.fa_proc_yr,
                       a.student_id,
                       NVL(s.spriden_pidm, p.spbpers_pidm) AS pidm,
                       a.ccpg,
                       a.pell,
                       'cred_cert' AS award_type
                   FROM
                       dwh.scff_cert a
                           LEFT JOIN spriden_cte s
                               ON a.student_id = s.spriden_id
                           LEFT JOIN spbpers_cte p
                               ON a.student_id = p.spbpers_ssn
                   ),
    cte_scff AS (
                   SELECT
                       mis_term_id,
                       fa_proc_yr,
                       student_id AS sb00,
                       pidm,
                       ccpg,
                       pell,
                       award_type
                   FROM
                       cte_aaas
                   UNION ALL
                   SELECT
                       mis_term_id,
                       fa_proc_yr,
                       student_id,
                       pidm,
                       ccpg,
                       pell,
                       award_type
                   FROM
                       cte_adt
                   UNION ALL
                   SELECT
                       mis_term_id,
                       fa_proc_yr,
                       student_id,
                       pidm,
                       ccpg,
                       pell,
                       award_type
                   FROM
                       cte_babs
                   UNION ALL
                   SELECT
                       mis_term_id,
                       fa_proc_yr,
                       student_id,
                       pidm,
                       ccpg,
                       pell,
                       award_type
                   FROM
                       cte_cert
                   ),
    cte_smrprle AS (
                   SELECT
                       smrprle_co_unique_cde,
                       smrprle_program,
                       smrprle_program_desc
                   FROM
                       (
                       SELECT
                           smrprle_co_unique_cde,
                           smrprle_program,
                           smrprle_program_desc,
                           ROW_NUMBER(
                           ) OVER (
                               PARTITION BY smrprle_co_unique_cde
                               ORDER BY smrprle_program
                               ) AS rn
                       FROM
                           jahn.stg_banner__smrprle
                       WHERE smrprle_co_unique_cde IS NOT NULL
                       )
                   WHERE rn = 1
                   ),
    cte_coci AS (
                   SELECT
                       control_number,
                       CASE
                           WHEN award LIKE 'A.A- T%'
                               THEN 'aat'
                           WHEN award LIKE 'A.S. T%'
                               THEN 'aas'
                       END AS aat_aas_ind,
                       'Y' AS adt_ind
                   FROM
                       dwh.scff_coci
                   WHERE goal LIKE 'T%'
                     AND (
                       award LIKE 'A.%- T%' OR award LIKE 'A.S. T%')
                   ),
    cte_sx AS (
                   SELECT DISTINCT
                       sb00,
                       gi01,
                       CASE MOD(gi03, 10)
                           WHEN 5
                               THEN gi03 + 5
                           WHEN 7
                               THEN gi03 + 3
                           WHEN 3
                               THEN gi03 - 3
                       END AS annual_term,
                       'Y' AS sx_ind
                   FROM
                       dwh.mis_sx
                   UNION
                   SELECT DISTINCT
                       sb00,
                       gi01,
                       gi03 - 5 AS annual_term,
                       'Y' AS sx_ind
                   FROM
                       dwh.mis_sx
                   WHERE MOD(gi03, 10) = 5
                   ),
    cte_sx_proc AS (
                   SELECT DISTINCT
                       sb00,
                       gi01,
                       annual_term,
                       sx_ind
                   FROM cte_sx
                   ),
    cte_sp AS (
                   SELECT
                       a.gi90,
                       a.gi01,
                       a.gi03,
                       a.sb02,
                       a.sb00,
                       a.sp01,
                       a.sp02,
                       a.sp03,
                       a.gi92,
                       a.sp04,
                       NVL(s.spriden_pidm, p.spbpers_pidm) AS pidm,
                       f.aat_aas_ind,
                       r.smrprle_program AS sp_progcode,
                       r.smrprle_program_desc AS sp_programname,
                       f.adt_ind,
                       x.sx_ind
                   FROM
                       dwh.mis_sp a
                           LEFT JOIN cte_sx_proc x
                               ON (a.sb00 = x.sb00
                               AND a.gi01 = x.gi01
                               AND a.gi03 = x.annual_term)
                           LEFT JOIN spriden_cte s
                               ON (a.sb00 = s.spriden_id)
                           LEFT JOIN spbpers_cte p
                               ON (a.sb00 = p.spbpers_ssn)
                           LEFT JOIN cte_coci f
                               ON (a.sp04 = f.control_number)
                           LEFT JOIN cte_smrprle r
                               ON (a.sp04 = r.smrprle_co_unique_cde)
                   ),
    cte_sp_proc AS (
                   SELECT
                       a.*,
                       CASE
                           WHEN a.sp02 IN ('A', 'S') AND a.adt_ind = 'Y'
                               THEN 'adt'
                           WHEN (a.sp02 IN ('A', 'S') AND a.adt_ind IS NULL)
                               THEN 'aaas'
                           WHEN a.sp02 IN ('Y', 'Z')
                               THEN 'babs'
                           WHEN a.sp02 IN ('E', 'M', 'B', 'N', 'L', 'T', 'F', 'O')
                               THEN 'cred_cert'
                           ELSE 'noncred_cert'
                       END AS award_type,
                       ROW_NUMBER() OVER (
                           PARTITION BY a.sb00, a.gi03
                           ORDER BY
                               CASE
                                   WHEN (a.sp02 IN ('A', 'S') AND a.adt_ind = 'Y')
                                       THEN 1
                                   WHEN (a.sp02 IN ('A', 'S') AND a.adt_ind IS NULL)
                                       THEN 2
                                   WHEN a.sp02 IN ('Y', 'Z')
                                       THEN 3
                                   WHEN a.sp02 IN ('E', 'M', 'B', 'N', 'L', 'T', 'F', 'O')
                                       THEN 4
                                   ELSE 5
                               END
                           ) AS award_priority
                   FROM
                       cte_sp a
                   ),
    cte_sp_main AS (
                   SELECT
                       c.*
                   FROM
                       cte_sp_proc c
                   WHERE c.award_priority = 1
                   ),
    cte_main AS (
                   SELECT
                       COALESCE(c.gi03, x.mis_term_id) AS term_id,
                       c.sx_ind AS sp_sx_ind,
                       COALESCE(c.sb00, x.sb00) AS sb00,
                       coalesce(c.award_type, x.award_type) AS award_type,
                       CASE
                           WHEN c.sb00 IS NOT NULL AND x.sb00 IS NOT NULL
                               THEN 'Matched'
                           WHEN c.sb00 IS NOT NULL AND x.sb00 IS NULL
                               THEN 'SP Only - Not in SCFF'
                           WHEN c.sb00 IS NULL AND x.sb00 IS NOT NULL
                               THEN 'SCFF Only - Not in SP'
                       END AS match_status,
                       c.gi01 AS dicd_code,
                       c.pidm AS sp_pidm,
                       c.sb00 AS sp_sb00,
                       c.award_type AS sp_award_type,
                       c.award_priority AS sp_award_priority,
                       c.sp02 AS sp_mis_degcode,
                       c.gi92 AS sp_seq_no,
                       c.sp03 AS sp_date_graduated,
                       c.sp_progcode,
                       c.sp_programname,
                       c.sp04 AS sp_mis_progcode,
                       c.sp01 AS sp_mis_topscode,
                       x.pidm AS scff_pidm,
                       x.sb00 AS scff_sb00,
                       x.ccpg AS scff_ccpg,
                       x.pell AS scff_pell,
                       x.award_type AS scff_award_type
                   FROM
                       cte_sp_main c
                           FULL OUTER JOIN cte_scff x
                               ON (c.sb00 = x.sb00
                               AND c.gi03 = x.mis_term_id
                               AND c.award_type = x.award_type)
                   )
SELECT
    *
FROM
    cte_main
WHERE term_id IN (:t1, :t2, :t3, :t4)
