WITH
    nhrdist AS (
        SELECT
            mis_term_id,
            pidm,
            posn,
            SUM(payamt) AS payamt
        FROM
            dwh.mv_nhrdist_terms
        WHERE posn IS NOT NULL
        GROUP BY
            mis_term_id,
            pidm,
            posn
                   ),
    coi AS (
        SELECT
            mis_term_id,
            pidm,
            posn,
            SUM(term_salary) AS est_term_sal
        FROM
            dwh.mv_cost_of_instruction
        WHERE posn IS NOT NULL
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
    ROUND((a.est_term_sal - b.payamt) / NULLIF(a.est_term_sal, 0), 2) AS pct_diff,
    CASE
        WHEN b.pidm IS NOT NULL THEN 'Matched'
        ELSE 'Not Matched'
        END AS match_status
FROM
    coi a
        LEFT JOIN nhrdist b
            ON (a.mis_term_id = b.mis_term_id
            AND a.pidm = b.pidm
            AND a.posn = b.posn)
WHERE a.mis_term_id IN (:t1...)
ORDER BY
    a.mis_term_id,
    a.pidm,
    a.posn