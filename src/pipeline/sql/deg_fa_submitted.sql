WITH
    spriden_dedup AS (
        SELECT
            spriden_id,
            MIN(spriden_pidm) AS spriden_pidm
        FROM spriden@banner.nocccd.edu
        WHERE spriden_change_ind IS NULL
        GROUP BY
            spriden_id
    ),
    spbpers_dedup AS (
        SELECT
            spbpers_ssn,
            MIN(spbpers_pidm) AS spbpers_pidm
        FROM spbpers@banner.nocccd.edu
        GROUP BY
            spbpers_ssn
    ),
    scff AS (
        SELECT
            a.mis_acyr_id,
            a.student_id AS sb00,
            'ccpg' AS scff_type
        FROM dwh.scff_ccpg a
        UNION ALL
        SELECT
            a.mis_acyr_id,
            a.student_id,
            'pell'
        FROM dwh.scff_pell a
    ),
    fa AS (
        SELECT
            a.gi90,
            a.gi01,
            a.gi03,
            a.gi03_aw,
            a.sb00,
            a.sf21,
            CASE
                WHEN a.sf21 = 'GP' THEN 'pell'
                WHEN a.sf21 IN ('BA', 'B1', 'B2', 'B3', 'BB', 'BC', 'BD') THEN 'ccpg'
                ELSE 'other'
            END AS type,
            a.sf22,
            b.description,
            NVL(s.spriden_pidm, p.spbpers_pidm) AS pidm
        FROM dwh.mis_fa a
            LEFT JOIN dwh.xwk_mis_sf21 b
                ON (a.sf21 = b.code)
            LEFT JOIN spriden_dedup s
                ON (a.sb00 = s.spriden_id)
            LEFT JOIN spbpers_dedup p
                ON (a.sb00 = p.spbpers_ssn)
    ),
    main AS (
        SELECT
            COALESCE(fa.gi03, x.mis_acyr_id) AS acyr_id,
            coalesce(fa.sb00, x.sb00) AS student_id,
            coalesce(fa.type, x.scff_type) AS award_type,
            CASE
                WHEN fa.sb00 IS NOT NULL AND x.sb00 IS NOT NULL
                    THEN 'Matched'
                WHEN fa.sb00 IS NOT NULL AND x.sb00 IS NULL
                    THEN 'FA Only - Not in SCFF'
                WHEN fa.sb00 IS NULL AND x.sb00 IS NOT NULL
                    THEN 'SCFF Only - Not in FA'
            END AS match_status,
            fa.gi03 AS fa_acyr_id,
            fa.gi01 AS dicd_code,
            fa.gi03_aw AS fa_term_aw,
            fa.pidm AS fa_pidm,
            fa.sb00 AS fa_sb00,
            fa.type AS award_category,
            fa.sf21 AS award_type_code,
            fa.description AS award_type_desc,
            fa.sf22 AS amount,
            x.sb00 AS scff_sb00,
            x.scff_type
        FROM fa fa
            FULL OUTER JOIN scff x
                ON (fa.sb00 = x.sb00
                AND fa.gi03 = x.mis_acyr_id
                AND fa.type = x.scff_type)
    )
SELECT *
FROM main
WHERE acyr_id IN (:t1...)
