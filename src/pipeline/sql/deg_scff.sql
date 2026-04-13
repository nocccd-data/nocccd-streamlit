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

    aaas AS (
        SELECT
            a.student_id,
            a.ccpg,
            a.pell,
            'aaas' AS award_type,
            a.mis_acyr_id,
            COALESCE(s.spriden_pidm, p.spbpers_pidm) AS pidm
        FROM dwh.scff_aaas a
            LEFT JOIN spriden_dedup s
                ON a.student_id = s.spriden_id
            LEFT JOIN spbpers_dedup p
                ON a.student_id = p.spbpers_ssn
    ),

    adt AS (
        SELECT
            a.student_id,
            a.ccpg,
            a.pell,
            'adt' AS award_type,
            a.mis_acyr_id,
            COALESCE(s.spriden_pidm, p.spbpers_pidm) AS pidm
        FROM dwh.scff_adt a
            LEFT JOIN spriden_dedup s
                ON a.student_id = s.spriden_id
            LEFT JOIN spbpers_dedup p
                ON a.student_id = p.spbpers_ssn
    ),

    babs AS (
        SELECT
            a.student_id,
            a.ccpg,
            a.pell,
            'babs' AS award_type,
            a.mis_acyr_id,
            COALESCE(s.spriden_pidm, p.spbpers_pidm) AS pidm
        FROM dwh.scff_babs a
            LEFT JOIN spriden_dedup s
                ON a.student_id = s.spriden_id
            LEFT JOIN spbpers_dedup p
                ON a.student_id = p.spbpers_ssn
    ),

    cert AS (
        SELECT
            a.student_id,
            a.ccpg,
            a.pell,
            'cred_cert' AS award_type,
            a.mis_acyr_id,
            COALESCE(s.spriden_pidm, p.spbpers_pidm) AS pidm
        FROM dwh.scff_cert a
            LEFT JOIN spriden_dedup s
                ON a.student_id = s.spriden_id
            LEFT JOIN spbpers_dedup p
                ON a.student_id = p.spbpers_ssn
    ),

    scff AS (
        SELECT
            mis_acyr_id,
            student_id AS sb00,
            pidm,
            ccpg,
            pell,
            award_type
        FROM aaas
        UNION ALL
        SELECT
            mis_acyr_id,
            student_id,
            pidm,
            ccpg,
            pell,
            award_type
        FROM adt
        UNION ALL
        SELECT
            mis_acyr_id,
            student_id,
            pidm,
            ccpg,
            pell,
            award_type
        FROM babs
        UNION ALL
        SELECT
            mis_acyr_id,
            student_id,
            pidm,
            ccpg,
            pell,
            award_type
        FROM cert
    )

SELECT
    mis_acyr_id,
    award_type,
    sb00,
    ccpg,
    pell
FROM scff
WHERE mis_acyr_id IN (:t1...)
