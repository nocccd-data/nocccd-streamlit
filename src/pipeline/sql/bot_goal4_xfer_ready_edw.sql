-- BOT Goal 4 -- Transfer Ready, rebuilt on dim models only (no Banner tables).
--
-- Replaces bot_goal4_xfer_ready.sql. Two CTEs from the original disappear
-- entirely: cte_first_gen is already dim_student_term.first_gen_flag (same GEDL
-- logic, same effective-term windowing) and cte_scrsbgi is already
-- dim_course.csu_uc_transferable_flag (SCRSBGI effective-term windows resolved
-- upstream in int_course).
--
-- ============================================================================
-- !! CURRENTLY POINTED AT THE DEV SCHEMA (jahn.) FOR VALIDATION !!
--
-- Before pasting into nocccd-streamlit/src/pipeline/sql/bot_goal4_xfer_ready.sql,
-- replace every "jahn." with "edw_prod." -- 6 occurrences. Shipping this file
-- as-is would point a production dashboard at a personal dev schema.
--
-- Prod also needs PR #84 merged and a prod refresh first: dim_academic_history
-- and dim_term.cutoff_term do not exist in EDW_PROD yet.
-- ============================================================================
WITH
    acyr AS (
        -- One row. cutoff_term is per-track, so restricting to a credit term
        -- ('0' suffix) yields the credit Spring that closes the academic year.
        -- This is the analysis-year boundary: transcript history below reaches
        -- back across PRIOR years up to it, so it must come from :acyr_code and
        -- never from the transcript row's own term (which would be a tautology).
        SELECT DISTINCT
            academic_year_code AS acyr_code,
            academic_year_title,
            cutoff_term
        FROM jahn.dim_term
        WHERE academic_year_code = :acyr_code
          AND SUBSTR(term_code, -1) = '0'
    ),

    enrolled AS (
        -- Exactly one row per student. dim_student_term is student-TERM grain,
        -- so without the DISTINCT a student enrolled in three terms would
        -- triple every transcript row joined below and inflate units_earn.
        SELECT DISTINCT
            a.student_key,
            a.student_id AS pidm,
            -- first_gen_flag varies by term (a student can be Y in one term and
            -- NULL in another). Collapse to one value per student on a
            -- Y > N > unknown priority, matching the original.
            CASE
                MIN(CASE a.first_gen_flag WHEN 'Y' THEN 1 WHEN 'N' THEN 2 ELSE 3 END)
                    OVER (PARTITION BY a.student_id)
                WHEN 1 THEN 'Y'
                WHEN 2 THEN 'N'
                ELSE 'NULL'
            END AS first_gen_ind,
            -- dim_student.gender_code is now the derived NB/M/F/N value, which
            -- is the same logic the original applied inline to SPBPERS.
            b.gender_code AS gender,
            -- int_ethnicity now emits the same labels this pipeline hard-codes
            -- ('Black or African American', 'Multiethnicity', 'Unreported', ...),
            -- so the warehouse column can be used directly.
            b.ipeds_ethnicity_description AS race_description
        FROM jahn.dim_student_term a
            JOIN jahn.dim_student b
                ON (a.student_key = b.student_key)
            JOIN jahn.dim_term c
                ON (a.term_key = c.term_key)
        WHERE c.academic_year_code = :acyr_code
          -- Census enrollment at a credit college, i.e. the original's
          -- stvrsts_voice_type IN ('R','W') plus campus 1/2 filter.
          AND (a.cypress_rw_flag = 'Y'
            OR a.fullerton_rw_flag = 'Y')
    ),

    latest_attempt AS (
        SELECT
            e.pidm,
            e.first_gen_ind,
            e.gender,
            e.race_description,
            h.subject_code,
            h.course_number,
            h.term_code,
            h.credit_hours,
            h.grade_code_final,
            h.gpa_ind,
            h.quality_points,
            -- One row per course per term. acyr is fixed by the filter above, so
            -- it drops out of the original's partition. shrtckn_seq_no replaces
            -- shrtckg_seq_no: the latest-grade pick already happened upstream,
            -- so what remains to break is repeat attempts, and the transcript
            -- sequence orders those correctly.
            ROW_NUMBER() OVER (
                PARTITION BY
                    h.student_id,
                    h.subject_code,
                    h.course_number,
                    h.term_code
                ORDER BY
                    h.shrtckn_seq_no DESC
                ) AS rn
        FROM enrolled e
            JOIN jahn.dim_academic_history h
                ON (h.student_key = e.student_key)
            -- course_key is hash(term_code, subject_code, course_number), so the
            -- term is already baked in -- no separate term predicate needed.
            JOIN jahn.dim_course d
                ON (h.course_key = d.course_key)
            CROSS JOIN acyr t
        WHERE d.csu_uc_transferable_flag = 'Y'
          -- campus_code, not SUBSTR(level_code,1,1): it prefers the transcript's
          -- own camp_code, which audits as the more reliable of the two signals.
          AND h.campus_code IN ('1', '2')
          AND h.term_code <= t.cutoff_term
          AND h.credit_hours <> 0
          AND NVL(h.repeat_course_ind, 'X') <> 'E'
    ),

    student_agg AS (
        SELECT
            lat.pidm,
            lat.first_gen_ind,
            lat.gender,
            lat.race_description,
            ROUND(
                SUM(
                    CASE
                        WHEN lat.gpa_ind = 'Y' THEN (lat.quality_points * lat.credit_hours)
                        ELSE 0
                    END
                ) / NULLIF(
                    SUM(CASE WHEN lat.gpa_ind = 'Y' THEN lat.credit_hours ELSE 0 END),
                    0
                    ),
                3
            ) AS gpa,
            SUM(
                CASE
                    WHEN lat.grade_code_final IN ('A', 'B', 'C', 'P', 'CR', 'IP', 'INB', 'INC')
                        THEN lat.credit_hours
                    ELSE 0
                END
            ) AS units_earn,
            COUNT(
                DISTINCT CASE
                             WHEN lat.subject_code IN ('MATH', 'ENGL')
                                 AND TO_NUMBER(REGEXP_REPLACE(lat.course_number, '[^0-9]', '')) >= 100
                                 AND lat.grade_code_final IN ('A', 'B', 'C', 'P', 'CR', 'IP', 'INB', 'INC')
                                 THEN lat.subject_code
                         END
            ) AS math_eng_count
        FROM latest_attempt lat
        WHERE lat.rn = 1
        GROUP BY
            lat.pidm,
            lat.first_gen_ind,
            lat.gender,
            lat.race_description
    )

SELECT
    t.acyr_code,
    -- dim_term.academic_year_title is '2023-24'; the original used
    -- STVACYR.STVACYR_DESC, which is '2023-2024'.
    t.academic_year_title AS academic_year,
    -- Transfer readiness is a district-level, student-level fact (no single
    -- home campus), so the headcount chart shows one Credit-college bar
    -- rather than a Cypress/Fullerton split. NOCE is excluded upstream.
    'NOCCCD (Unduplicated)' AS camp_desc,
    'Credit' AS site,
    agg.pidm,
    agg.first_gen_ind,
    agg.gender,
    agg.race_description,
    agg.gpa,
    agg.units_earn,
    agg.math_eng_count
FROM student_agg agg
    CROSS JOIN acyr t
WHERE agg.gpa >= 2.0
  AND agg.units_earn >= 60
  AND agg.math_eng_count = 2
ORDER BY
    t.acyr_code,
    agg.pidm
