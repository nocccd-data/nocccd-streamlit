-- KPI - Student Headcount by Type: Fall headcount by student type.
--
-- Grain: one row per mis_term_id x college_group x styp_code.
--   college_group 'credit' = Cypress + Fullerton COMBINED (six student types).
--   college_group 'noce'   = NOCE, a single 'adult' count (noncredit has no styp split).
-- pidm_count is a distinct headcount within the group: a student registered at both
-- credit colleges counts once (1,758 in Fall 2022, 2,500 in Fall 2026). Adding
-- per-college counts would count them twice, which is why there is no camp_code column.
--
-- Credit student types, tested in this order:
--   special_admit_dual -- dual enrollment OR special admit, combined into one type:
--       dual enrollment (district/views/mv_dual_enrollment.sql): svbccap_ccap_ind = 'Y',
--         or an SG07 Middle/Early College record svbmchs_mchs_code IN ('1','4'), each
--         matched on pidm + term + college (SUBSTR(dicd_code, 3, 1) = camp digit);
--       special admit (district/queries/special_admit.sql): on the effective SGBSTDN
--         record, styp 'Y' OR edlv '100' OR program_1 IN ('1SPADMIT','2SPADMIT') OR
--         majr_code_1 IN ('1111','2222') OR rate_code 'HS'.
--     Tested FIRST: these students often carry a real styp ('1', '5', ...) that would
--     otherwise put them in first_time / continuing.
--   first_time        -- styp '1', under 25 at term start
--   first_time_trans  -- styp '2', under 25
--   returning         -- styp '3' / '4'
--   continuing        -- styp '5'
--   adult             -- styp '1' / '2', 25 or older
-- Anything else -- another styp code ('X', '0', ...), no SGBSTDN record, or a
-- styp '1'/'2' student with no birth date -- has no type and is dropped.
--
-- CCAP is recorded per college, so one credit student can be dual enrollment at one
-- college and not the other. cte_student takes the flag from EITHER college, keeping
-- every credit student in at most one type, so the six credit counts add up without
-- double-counting anyone. Credit students with no type are in none: 1 each in Fall 2025
-- and Fall 2026, 0 in 2022-2024 (checked 2026-10-28 against distinct credit enrollment).
-- A student in both credit and NOCE is in both groups.
--
-- Enrollment: credit = stvrsts_voice_type IN ('R','W'); NOCE = stvrsts_apport_ind = 'Y'.
-- Each MIS Fall id holds exactly one credit term (YYYY10) and one NOCE term (YYYY15).
-- Run on REPT.
WITH
    cte_terms AS (
        SELECT
            stvterm_code,
            stvterm_mis_term_id,
            stvterm_start_date
        FROM stvterm
        WHERE stvterm_mis_term_id IN (:t1)
    ),
    cte_svbmchs AS (
        SELECT DISTINCT
            svbmchs_pidm,
            svbmchs_term_code,
            SUBSTR(svbmchs_dicd_code, 3, 1) AS camp_code,
            'Y' AS early_college_ind
        FROM saturn.svbmchs
        WHERE svbmchs_mchs_code IN ('1', '4')
    ),
    cte_sgbstdn AS (
        SELECT
            pidm,
            sgbstdn_from_term,
            sgbstdn_to_term,
            sgbstdn_styp_code,
            sgbstdn_edlv_code,
            sgbstdn_program_1,
            sgbstdn_majr_code_1,
            sgbstdn_rate_code
        FROM (
            SELECT
                a.sgbstdn_pidm AS pidm,
                a.sgbstdn_term_code_eff AS sgbstdn_from_term,
                LEAD(a.sgbstdn_term_code_eff, 1, '999999') OVER (
                    PARTITION BY
                        a.sgbstdn_pidm
                    ORDER BY
                        a.sgbstdn_term_code_eff
                    ) AS sgbstdn_to_term,
                a.sgbstdn_styp_code,
                a.sgbstdn_edlv_code,
                a.sgbstdn_program_1,
                a.sgbstdn_majr_code_1,
                a.sgbstdn_rate_code
            FROM sgbstdn a
            -- Only students registered in a target term. LEAD partitions by pidm, so
            -- leaving out other students' records cannot change these windows.
            WHERE a.sgbstdn_pidm IN (
                SELECT r.sfrstcr_pidm
                FROM sfrstcr r
                    INNER JOIN cte_terms rt
                        ON (r.sfrstcr_term_code = rt.stvterm_code)
            )
        )
        -- SGBSTDN is unique on (pidm, term_code_eff), so the windows are disjoint.
        -- No styp filter here (dual_enrl_count.sql drops 'X'/'0'): special_admit.sql
        -- reads the special-admit flags off the effective record whatever its styp,
        -- and an 'X'/'0' record still gets no base type below.
    ),
    cte_sfrstcr AS (
        SELECT
            h.stvterm_mis_term_id AS mis_term_id,
            b.sfrstcr_pidm AS pidm,
            CASE
                WHEN SUBSTR(b.sfrstcr_camp_code, 1, 1) = '3' THEN 'noce'
                ELSE 'credit'
            END AS college_group,
            -- Credit colleges only: the explicit camp guard keeps a future NOCE CCAP or
            -- early-college record from pulling NOCE students out of 'adult'.
            CASE
                WHEN SUBSTR(b.sfrstcr_camp_code, 1, 1) IN ('1', '2')
                    AND (
                    p.svbccap_ccap_ind = 'Y'
                        OR m.early_college_ind = 'Y'
                        OR e.sgbstdn_styp_code = 'Y'
                        OR e.sgbstdn_edlv_code = '100'
                        OR e.sgbstdn_program_1 IN ('1SPADMIT', '2SPADMIT')
                        OR e.sgbstdn_majr_code_1 IN ('1111', '2222')
                        OR e.sgbstdn_rate_code = 'HS'
                    ) THEN 1
                ELSE 0
            END AS special_admit_dual_ind,
            CASE
                WHEN SUBSTR(b.sfrstcr_camp_code, 1, 1) = '3' THEN 'adult'
                WHEN e.sgbstdn_styp_code = '1'
                    AND ROUND(
                        MONTHS_BETWEEN(h.stvterm_start_date, g.spbpers_birth_date) / 12,
                        3
                        ) < 25 THEN 'first_time'
                WHEN e.sgbstdn_styp_code = '2'
                    AND ROUND(
                        MONTHS_BETWEEN(h.stvterm_start_date, g.spbpers_birth_date) / 12,
                        3
                        ) < 25 THEN 'first_time_trans'
                WHEN e.sgbstdn_styp_code IN ('3', '4') THEN 'returning'
                WHEN e.sgbstdn_styp_code = '5' THEN 'continuing'
                WHEN e.sgbstdn_styp_code IN ('1', '2')
                    AND ROUND(
                        MONTHS_BETWEEN(h.stvterm_start_date, g.spbpers_birth_date) / 12,
                        3
                        ) >= 25 THEN 'adult'
            END AS base_styp_code
        FROM sfrstcr b
            INNER JOIN cte_terms h
                ON (b.sfrstcr_term_code = h.stvterm_code)
            LEFT JOIN saturn.stvrsts c
                ON (b.sfrstcr_rsts_code = c.stvrsts_code)
            LEFT JOIN cte_sgbstdn e
                ON (
                b.sfrstcr_pidm = e.pidm
                    AND b.sfrstcr_term_code >= e.sgbstdn_from_term
                    AND b.sfrstcr_term_code < e.sgbstdn_to_term
                )
            LEFT JOIN saturn.svbccap p
                ON (b.sfrstcr_pidm = p.svbccap_pidm
                AND b.sfrstcr_term_code = p.svbccap_term_code
                AND SUBSTR(b.sfrstcr_camp_code, 1, 1) = SUBSTR(p.svbccap_dicd_code, 3, 1))
            LEFT JOIN cte_svbmchs m
                ON (b.sfrstcr_pidm = m.svbmchs_pidm
                AND b.sfrstcr_term_code = m.svbmchs_term_code
                AND SUBSTR(b.sfrstcr_camp_code, 1, 1) = m.camp_code)
            -- LEFT: only the credit age tests need a birth date; an inner join would
            -- also drop NOCE students with no SPBPERS row (about one per Fall).
            LEFT JOIN spbpers g
                ON (b.sfrstcr_pidm = g.spbpers_pidm)
        WHERE (
            c.stvrsts_voice_type IN ('R', 'W')
                AND SUBSTR(b.sfrstcr_camp_code, 1, 1) IN ('1', '2')
            )
           OR (
            c.stvrsts_apport_ind = 'Y'
                AND SUBSTR(b.sfrstcr_camp_code, 1, 1) = '3'
            )
    ),
    cte_student AS (
        -- One row per student per Fall per college group. A credit student's base type
        -- is the same on every credit row (one credit term, one effective SGBSTDN
        -- record), so MAX only collapses the per-CRN grain; the special-admit/dual flag
        -- can differ by college, and a flag at either college wins.
        SELECT
            mis_term_id,
            college_group,
            pidm,
            CASE
                WHEN MAX(special_admit_dual_ind) = 1 THEN 'special_admit_dual'
                ELSE MAX(base_styp_code)
            END AS styp_code
        FROM cte_sfrstcr
        GROUP BY
            mis_term_id,
            college_group,
            pidm
    )
SELECT
    a.mis_term_id,
    a.college_group,
    a.styp_code,
    COUNT(*) AS pidm_count
FROM cte_student a
WHERE a.styp_code IS NOT NULL
GROUP BY
    a.mis_term_id,
    a.college_group,
    a.styp_code
ORDER BY
    a.mis_term_id,
    a.college_group,
    a.styp_code
