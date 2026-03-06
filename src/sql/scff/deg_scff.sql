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
                       student_id as sb00,
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
                   )
SELECT
    mis_term_id,
    award_type,
    sb00,
    ccpg,
    pell
FROM
    cte_scff
WHERE
    mis_term_id IN (:t1, :t2, :t3, :t4)
