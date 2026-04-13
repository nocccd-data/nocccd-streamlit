WITH
    spriden_dedup AS (
        SELECT
            spriden_id,
            MIN(spriden_pidm) AS spriden_pidm
        FROM spriden
        WHERE spriden_change_ind IS NULL
        GROUP BY
            spriden_id
    ),
    spbpers_dedup AS (
        SELECT
            spbpers_ssn,
            MIN(spbpers_pidm) AS spbpers_pidm
        FROM spbpers
        GROUP BY
            spbpers_ssn
    ),
    aaas AS (
        SELECT
            a.mis_acyr_id,            
            a.student_id,
            NVL(s.spriden_pidm, p.spbpers_pidm) AS pidm,
            a.ccpg,
            a.pell,
            'aaas' AS award_type
        FROM dwh.scff_aaas@dwhdb.nocccd.edu a
            LEFT JOIN spriden_dedup s
                ON a.student_id = s.spriden_id
            LEFT JOIN spbpers_dedup p
                ON a.student_id = p.spbpers_ssn
    ),
    adt AS (
        SELECT
            a.mis_acyr_id,            
            a.student_id,
            NVL(s.spriden_pidm, p.spbpers_pidm) AS pidm,
            a.ccpg,
            a.pell,
            'adt' AS award_type
        FROM dwh.scff_adt@dwhdb.nocccd.edu a
            LEFT JOIN spriden_dedup s
                ON a.student_id = s.spriden_id
            LEFT JOIN spbpers_dedup p
                ON a.student_id = p.spbpers_ssn
    ),
    babs AS (
        SELECT
            a.mis_acyr_id,            
            a.student_id,
            NVL(s.spriden_pidm, p.spbpers_pidm) AS pidm,
            a.ccpg,
            a.pell,
            'babs' AS award_type
        FROM dwh.scff_babs@dwhdb.nocccd.edu a
            LEFT JOIN spriden_dedup s
                ON a.student_id = s.spriden_id
            LEFT JOIN spbpers_dedup p
                ON a.student_id = p.spbpers_ssn
    ),
    cert AS (
        SELECT
            a.mis_acyr_id,            
            a.student_id,
            NVL(s.spriden_pidm, p.spbpers_pidm) AS pidm,
            a.ccpg,
            a.pell,
            'cred_cert' AS award_type
        FROM dwh.scff_cert@dwhdb.nocccd.edu a
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
    ),
    scff_proc AS (
        SELECT *
        FROM scff
        WHERE mis_acyr_id = :mis_acyr_id
    ),
    mis_term AS (
        SELECT
            SUBSTR(
                stvterm.stvterm_acyr_code, 3, 2) + 1 || '0' AS mis_term,
            stvterm.stvterm_code,
            stvterm.stvterm_start_date,
            stvterm.stvterm_end_date
        FROM stvterm stvterm
    ),
    mis_term_proc AS (
        SELECT
            mis_term,
            MIN(
                CASE
                    WHEN SUBSTR(
                        stvterm_code, -1) = '0'
                        THEN stvterm_start_date
                END
            ) AS stvterm_start_date_credit,
            MAX(
                CASE
                    WHEN SUBSTR(
                        stvterm_code, -1) = '0'
                        THEN stvterm_end_date
                END
            ) AS stvterm_end_date_credit,
            MIN(
                CASE
                    WHEN SUBSTR(
                        stvterm_code, -1) = '5'
                        THEN stvterm_start_date
                END
            ) AS stvterm_start_date_noce,
            MAX(
                CASE
                    WHEN SUBSTR(
                        stvterm_code, -1) = '5'
                        THEN stvterm_end_date
                END
            ) AS stvterm_end_date_noce
        FROM mis_term
        GROUP BY
            mis_term
    ),
    smrprle_dedup AS (
        SELECT
            smrprle_co_unique_cde,
            smrprle_program,
            smrprle_program_desc
        FROM (
            SELECT
                smrprle_co_unique_cde,
                smrprle_program,
                smrprle_program_desc,
                ROW_NUMBER(
                ) OVER (
                    PARTITION BY smrprle_co_unique_cde
                    ORDER BY smrprle_program
                    ) AS rn
            FROM smrprle
            WHERE smrprle_co_unique_cde IS NOT NULL
        )
        WHERE rn = 1
    ),
    coci AS (
        SELECT
            control_number,
            CASE
                WHEN award LIKE 'A.A- T%'
                    THEN 'aat'
                WHEN award LIKE 'A.S. T%'
                    THEN 'aas'
            END AS aat_aas_ind,
            'Y' AS adt_ind
        FROM dwh.scff_coci@dwhdb.nocccd.edu
        WHERE goal LIKE 'T%'
          AND (
            award LIKE 'A.%- T%' OR award LIKE 'A.S. T%')
    ),
    sx AS (
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
        FROM dwh.mis_sx@dwhdb.nocccd.edu
        UNION
        SELECT DISTINCT
            sb00,
            gi01,
            gi03 - 5 AS annual_term,
            'Y' AS sx_ind
        FROM dwh.mis_sx@dwhdb.nocccd.edu
        WHERE MOD(gi03, 10) = 5
    ),
    sx_proc AS (
        SELECT DISTINCT
            sb00,
            gi01,
            annual_term,
            sx_ind
        FROM sx
    ),
    sp AS (
        SELECT
            mis_term_proc.mis_term AS gi03,
            gtvdicd.gtvdicd_code AS gi01,
            spriden.spriden_pidm AS pidm,
            spriden.spriden_id AS id,
            gv_mis_global_bp.f_get_identifier(
                spriden.spriden_pidm, spriden.spriden_id, spbpers.spbpers_ssn) AS sb00,
            spriden.spriden_last_name AS last_name,
            spriden.spriden_first_name AS first_name,
            shrdgmr.shrdgmr_grad_date AS sp03,
            shrdgmr.shrdgmr_term_code_completed AS term_comp,
            NVL(
                gv_rept_xml.f_mapvalue(
                    'SP_LOCAL', 'GI92', shrdgmr.shrdgmr_seq_no - 1), shrdgmr.shrdgmr_seq_no - 1
            ) AS gi92,
            shrdgmr.shrdgmr_degs_code AS status,
            sovlcur.sovlcur_degc_code AS degcode,
            stvmajr.stvmajr_tops_code AS topscode,
            sv_mis_sp_local.f_get_program_award(
                sovlcur.sovlcur_degc_code, 'SP_LOCAL') AS sp02,
            sv_mis_sp_local.f_get_program_co_unique_code(
                sovlcur.sovlcur_program) AS sp04,
            sv_mis_sp_local.f_get_program_identifier(
                stvmajr.stvmajr_tops_code) AS sp01,
            sovlcur.sovlcur_program AS sp_progcode,
            aa.smrprle_program_desc AS sp_programname,
            h.adt_ind,
            x.sx_ind
        FROM spriden spriden
            INNER JOIN sgbstdn a
                ON (
                spriden.spriden_pidm = a.sgbstdn_pidm)
            LEFT JOIN spbpers spbpers
                ON (
                spbpers.spbpers_pidm = spriden.spriden_pidm)
            INNER JOIN shrdgmr shrdgmr
                ON (
                shrdgmr.shrdgmr_pidm = spriden.spriden_pidm)
            INNER JOIN stvdegs stvdegs
                ON (
                stvdegs.stvdegs_code = shrdgmr.shrdgmr_degs_code)
            INNER JOIN sovlcur sovlcur
                ON (
                sovlcur.sovlcur_pidm = shrdgmr.shrdgmr_pidm
                    AND sovlcur.sovlcur_lmod_code = 'OUTCOME'
                    AND sovlcur.sovlcur_key_seqno = shrdgmr.shrdgmr_seq_no
                    AND sovlcur.sovlcur_current_ind = 'Y'
                    AND sovlcur.sovlcur_active_ind = 'Y'
                )
            INNER JOIN sovlfos sovlfos
                ON (
                sovlfos.sovlfos_pidm = sovlcur.sovlcur_pidm
                    AND sovlfos.sovlfos_lcur_seqno = sovlcur.sovlcur_seqno
                    AND sovlfos.sovlfos_current_ind = 'Y'
                    AND sovlfos.sovlfos_active_ind = 'Y'
                )
            INNER JOIN stvmajr stvmajr
                ON (
                stvmajr.stvmajr_code = sovlfos.sovlfos_majr_code)
            CROSS JOIN gtvdicd gtvdicd
            INNER JOIN mis_term_proc
                ON mis_term_proc.mis_term = (
                CASE
                    WHEN gtvdicd.gtvdicd_code IN (
                                                  '861', '862')
                        THEN gv_mis_global_bp.f_get_term_id(
                        TO_CHAR(
                            mis_term_proc.stvterm_end_date_credit, 'DD-MON-YYYY'))
                    WHEN gtvdicd.gtvdicd_code = '863'
                        THEN gv_mis_global_bp.f_get_term_id(
                        TO_CHAR(
                            mis_term_proc.stvterm_end_date_noce, 'DD-MON-YYYY'))
                END)
            LEFT JOIN coci h
                ON (
                sv_mis_sp_local.f_get_program_co_unique_code(
                    sovlcur.sovlcur_program) =
                    h.control_number)
            LEFT JOIN smrprle_dedup aa
                ON (
                sovlcur.sovlcur_program = aa.smrprle_program)
            LEFT JOIN sx_proc x
                ON (
                gv_mis_global_bp.f_get_identifier(
                    spriden.spriden_pidm, spriden.spriden_id, spbpers.spbpers_ssn) = x.sb00
                    AND x.annual_term = mis_term_proc.mis_term)
        WHERE spriden.spriden_change_ind IS NULL
          AND spriden.spriden_entity_ind = 'P'
          AND mis_term_proc.mis_term = :mis_acyr_id
          AND shrdgmr.shrdgmr_grad_date BETWEEN CASE
                                                    WHEN gtvdicd.gtvdicd_code IN (
                                                                                  '861', '862')
                                                        THEN mis_term_proc.stvterm_start_date_credit
                                                    WHEN gtvdicd.gtvdicd_code = '863'
                                                        THEN mis_term_proc.stvterm_start_date_noce
                                                END AND CASE
                                                            WHEN gtvdicd.gtvdicd_code IN (
                                                                                          '861', '862')
                                                                THEN mis_term_proc.stvterm_end_date_credit
                                                            WHEN gtvdicd.gtvdicd_code = '863'
                                                                THEN mis_term_proc.stvterm_end_date_noce
                                                        END
          AND (
            (
                shrdgmr.shrdgmr_term_code_grad IS NOT NULL
                    AND a.sgbstdn_term_code_eff = (
                    SELECT
                        MAX(
                            b.sgbstdn_term_code_eff)
                    FROM sgbstdn b
                    WHERE b.sgbstdn_pidm = a.sgbstdn_pidm
                      AND b.sgbstdn_term_code_eff <= shrdgmr.shrdgmr_term_code_grad
                )
                )
                OR (
                shrdgmr.shrdgmr_term_code_grad IS NULL
                    AND shrdgmr.shrdgmr_grad_date IS NOT NULL
                    AND a.sgbstdn_term_code_eff = (
                    SELECT
                        MAX(
                            b.sgbstdn_term_code_eff)
                    FROM sgbstdn b
                    WHERE b.sgbstdn_pidm = a.sgbstdn_pidm
                      AND b.sgbstdn_term_code_eff <= (
                        SELECT
                            MAX(
                                stvterm_code)
                        FROM stvterm
                        WHERE shrdgmr.shrdgmr_grad_date BETWEEN stvterm_start_date AND stvterm_end_date
                    )
                )
                )
                OR (
                shrdgmr.shrdgmr_term_code_grad IS NULL
                    AND shrdgmr.shrdgmr_grad_date IS NOT NULL
                    AND a.sgbstdn_term_code_eff = (
                    SELECT
                        MAX(
                            b.sgbstdn_term_code_eff)
                    FROM sgbstdn b
                    WHERE b.sgbstdn_pidm = a.sgbstdn_pidm
                      AND b.sgbstdn_term_code_eff <=
                        sv_mis_sp_local.f_get_proper_term(
                            shrdgmr.shrdgmr_grad_date)
                )
                )
            )
          AND (
            stvdegs.stvdegs_award_status_ind = 'A'
                OR stvdegs.stvdegs_code = 'SA'
            )
          AND (
            shrdgmr.shrdgmr_camp_code IN (
                SELECT
                    stvcamp_code
                FROM stvcamp
                WHERE stvcamp_dicd_code = gtvdicd.gtvdicd_code
            )
                AND fz_csu_uc_cert(
                NULL, shrdgmr.shrdgmr_degc_code, shrdgmr.shrdgmr_levl_code) = 'N'
            )
        GROUP BY
            mis_term_proc.mis_term,
            gtvdicd.gtvdicd_code,
            spriden.spriden_pidm,
            spriden.spriden_id,
            gv_mis_global_bp.f_get_identifier(
                spriden.spriden_pidm, spriden.spriden_id, spbpers.spbpers_ssn),
            spriden.spriden_last_name,
            spriden.spriden_first_name,
            shrdgmr.shrdgmr_grad_date,
            shrdgmr.shrdgmr_term_code_completed,
            NVL(
                gv_rept_xml.f_mapvalue(
                    'SP_LOCAL', 'GI92', shrdgmr.shrdgmr_seq_no - 1), shrdgmr.shrdgmr_seq_no - 1
            ),
            shrdgmr.shrdgmr_degs_code,
            sovlcur.sovlcur_degc_code,
            stvmajr.stvmajr_tops_code,
            sv_mis_sp_local.f_get_program_award(
                sovlcur.sovlcur_degc_code, 'SP_LOCAL'),
            sv_mis_sp_local.f_get_program_co_unique_code(
                sovlcur.sovlcur_program),
            sv_mis_sp_local.f_get_program_identifier(
                stvmajr.stvmajr_tops_code),
            sovlcur.sovlcur_program,
            aa.smrprle_program_desc,
            h.adt_ind,
            x.sx_ind
    ),
    sp_proc AS (
        SELECT
            a.*,
            CASE
                WHEN a.sp02 IN (
                                'A', 'S') AND a.adt_ind = 'Y'
                    THEN 'adt'
                WHEN (
                    a.sp02 IN (
                               'A', 'S') AND a.adt_ind IS NULL)
                    THEN 'aaas'
                WHEN a.sp02 IN (
                                'Y', 'Z')
                    THEN 'babs'
                WHEN a.sp02 IN (
                                'E', 'M', 'B', 'N', 'L', 'T', 'F', 'O')
                    THEN 'cred_cert'
                ELSE 'noncred_cert'
            END AS award_type,
            ROW_NUMBER(
            ) OVER (
                PARTITION BY a.sb00, a.gi03
                ORDER BY
                    CASE
                        WHEN (
                            a.sp02 IN (
                                       'A', 'S') AND a.adt_ind = 'Y')
                            THEN 1
                        WHEN (
                            a.sp02 IN (
                                       'A', 'S') AND a.adt_ind IS NULL)
                            THEN 2
                        WHEN a.sp02 IN (
                                        'Y', 'Z')
                            THEN 3
                        WHEN a.sp02 IN (
                                        'E', 'M', 'B', 'N', 'L', 'T', 'F', 'O')
                            THEN 4
                        ELSE 5
                    END
                ) AS award_priority
        FROM sp a
    ),
    sp_main AS (
        SELECT
            c.*
        FROM sp_proc c
        WHERE c.award_type <> 'noncred_cert'
          AND c.award_priority = 1
    ),
    main AS (
        SELECT
            COALESCE(
                c.gi03, x.mis_acyr_id) AS acyr_id,
            c.sx_ind AS sp_sx_ind,
            COALESCE(
                c.sb00, x.sb00) AS sb00,
            COALESCE(c.award_type, x.award_type) AS award_type,
            CASE
                WHEN c.sb00 IS NOT NULL AND x.sb00 IS NOT NULL
                    THEN 'Matched'
                WHEN c.sb00 IS NOT NULL AND x.sb00 IS NULL AND c.sx_ind = 'Y'
                    THEN 'SP Only/SX Exists - Not in SCFF'
                WHEN c.sb00 IS NOT NULL AND x.sb00 IS NULL AND c.sx_ind is null
                    THEN 'SP Only/SX Not Exists - Not in SCFF'
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
        FROM sp_main c
            FULL OUTER JOIN scff_proc x
                ON (
                c.sb00 = x.sb00
                    AND c.gi03 = x.mis_acyr_id
                    AND c.award_type = x.award_type)
    )
SELECT *
FROM main
