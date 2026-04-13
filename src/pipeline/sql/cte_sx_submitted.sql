WITH
    cb_cte AS (
        SELECT
            a.gi90,
            a.gi01,
            a.gi03,
            a.cb00,
            a.cb01,
            a.cb02,
            a.cb03,
            a.cb09,
            'Y' AS cte_ind
        FROM dwh.mv_mis_cb a
        WHERE (
                  a.cb09 IN ('A', 'B', 'C')
                      OR EXISTS
                  (
                      SELECT
                          1
                      FROM dwh.xwk_scff_top6 b
                      WHERE b.top_code = a.cb03
                        AND b.top_cte_flag = 'CTE'
                        AND b.cip_cte_flag <> 'Noncredit CIP'
                  )
                  )
    ),

    sx_enrl AS (
        SELECT
            a.pidm,
            a.gi90,
            a.gi01,
            a.gi03,
            a.sb02,
            a.sb00,
            a.cb01,
            a.xb00,
            a.sx01,
            a.sx02,
            a.sx03,
            a.sx04,
            a.sx05,
            a.sx06,
            a.sx07,
            a.cb00,
            TO_CHAR(CASE
                        WHEN MOD(
                            a.gi03, 10
                             ) = 5 THEN a.gi03 + 5
                        WHEN MOD(
                            a.gi03, 10
                             ) = 7 THEN a.gi03 + 3
                        WHEN MOD(
                            a.gi03, 10
                             ) = 3 THEN a.gi03 - 3
                    END) AS mis_acyr_id
        FROM dwh.mv_mis_sx a
            INNER JOIN cb_cte b
                ON (
                a.gi01 = b.gi01
                    AND a.gi03 = b.gi03
                    AND a.cb00 = b.cb00
                )
        WHERE (
            a.sx04 IN (
                       'A', 'B', 'C', 'P'
                )
                OR SUBSTR(
                a.sx04, 1, 2) IN (
                                  'IA', 'IB', 'IC'
                )
                OR SUBSTR(a.sx04, 1, 3) = 'IPP'
            )
          AND a.gi01 IN ('861', '862')
    ),

    scff AS (
        SELECT
            a.mis_acyr_id,
            a.student_id AS sb00,
            a.ccpg,
            a.pell
        FROM dwh.scff_cte a
    ),

    sx_proc AS (
        SELECT
            a.mis_acyr_id,
            a.sb00,
            SUM(DECODE(a.gi01, '861', a.sx03)) AS sum_sx03_861,
            SUM(DECODE(a.gi01, '862', a.sx03)) AS sum_sx03_862,
            SUM(a.sx03) AS total_sx03
        FROM sx_enrl a
        GROUP BY
            a.mis_acyr_id,
            a.sb00
        HAVING SUM(a.sx03) >= 900
    ),

    cte_main AS (
        SELECT
            COALESCE(a.mis_acyr_id, b.mis_acyr_id) AS mis_acyr_id,
            COALESCE(a.sb00, b.sb00) AS student_id,
            CASE
                WHEN a.sb00 IS NOT NULL AND b.sb00 IS NOT NULL
                    THEN 'Matched'
                WHEN a.sb00 IS NOT NULL AND b.sb00 IS NULL
                    THEN 'SX Only - Not in SCFF'
                WHEN a.sb00 IS NULL AND b.sb00 IS NOT NULL
                    THEN 'SCFF Only - Not in SX'
            END AS match_status,
            a.sum_sx03_861,
            a.sum_sx03_862,
            a.total_sx03,
            b.ccpg,
            b.pell
        FROM sx_proc a
            FULL OUTER JOIN scff b
                ON (
                a.mis_acyr_id = b.mis_acyr_id
                    AND a.sb00 = b.sb00
                )
    )

SELECT *
FROM cte_main
WHERE mis_acyr_id IN (:t1...)
