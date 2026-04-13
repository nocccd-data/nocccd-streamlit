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
    )

SELECT
    a.mis_acyr_id,
    a.student_id AS sb00,
    COALESCE(s.spriden_pidm, p.spbpers_pidm) AS pidm,
    a.ccpg,
    a.pell
FROM dwh.scff_cte a
    LEFT JOIN spriden_dedup s
        ON a.student_id = s.spriden_id
    LEFT JOIN spbpers_dedup p
        ON a.student_id = p.spbpers_ssn
WHERE a.mis_acyr_id IN (:t1...)