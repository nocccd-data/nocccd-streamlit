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
            COALESCE(s.spriden_pidm, p.spbpers_pidm) AS pidm,
            'ccpg' AS scff_type
        FROM dwh.scff_ccpg a
            LEFT JOIN spriden_dedup s
                ON a.student_id = s.spriden_id
            LEFT JOIN spbpers_dedup p
                ON a.student_id = p.spbpers_ssn
        UNION ALL
        SELECT
            a.mis_acyr_id,
            a.student_id,
            COALESCE(s.spriden_pidm, p.spbpers_pidm),
            'pell' AS scff_type
        FROM dwh.scff_pell a
            LEFT JOIN spriden_dedup s
                ON a.student_id = s.spriden_id
            LEFT JOIN spbpers_dedup p
                ON a.student_id = p.spbpers_ssn
    )

SELECT
    mis_acyr_id,
    sb00,
    pidm,
    scff_type
FROM scff
WHERE mis_acyr_id IN (:t1...)
