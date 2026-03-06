WITH
    cte_nhrdist AS (
                   SELECT
                       mis_term_id,
                       nhrdist_pidm AS pidm,
                       nhrdist_posn AS posn,
                       SUM(payamt) AS payamt
                   FROM dwh.mv_nhrdist_terms
                   GROUP BY
                       mis_term_id,
                       nhrdist_pidm,
                       nhrdist_posn
                   ),
    cte_coi AS (
                   SELECT
                       mis_term_id,
                       pidm,
                       posn,
                       SUM(term_salary) AS est_term_sal
                   FROM dwh.mv_cost_of_instruction
                   WHERE posn IS NOT NULL
                     AND fcnt_code IS NOT NULL
                   GROUP BY
                       mis_term_id,
                       pidm,
                       posn
                   )
SELECT
    a.mis_term_id,
    a.pidm,
    a.posn,
    a.est_term_sal,
    b.payamt,
    a.est_term_sal - b.payamt AS diff,
    ROUND((a.est_term_sal - b.payamt) / NULLIF(a.est_term_sal, 0), 2) AS pct_diff
FROM
    cte_coi a
        LEFT JOIN cte_nhrdist b
            ON (a.mis_term_id = b.mis_term_id
            AND a.pidm = b.pidm
            AND a.posn = b.posn)
WHERE a.mis_term_id IN (:t1, :t2, :t3, :t4, :t5)
ORDER BY
    a.mis_term_id,
    a.pidm,
    a.posn
