WITH

    first_day_enroll AS (
        SELECT
            a.section_key,
            t.term_title,
            SUM(a.first_day_morning_enroll_count) AS first_day_morning_enroll_count,
            SUM(a.first_day_evening_enroll_count) AS first_day_evening_enroll_count,
            SUM(a.first_day_no_hours_enroll_count) AS first_day_no_hours_enroll_count
        FROM edw_prod.fact_enroll@dwhdb.nocccd.edu a
            JOIN edw_prod.dim_term@dwhdb.nocccd.edu t
                ON (a.term_key = t.term_key)
        GROUP BY
            a.section_key,
            t.term_title
    ),

    mtg AS (
        SELECT
            a.section_key,
            a.term_code,
            a.crn,
            a.meeting_category,
            a.meeting_begin_time,
            a.meeting_end_time,
            -- Collapse multi-char day tokens (Th, Sa, Su) to single chars so we can
            -- rebuild the canonical union via INSTR without Th colliding with T.
            REPLACE(REPLACE(REPLACE(a.meeting_days, 'Th', 'h'), 'Sa', 'a'), 'Su', 'u') AS days_tok,
            a.building_desc,
            b.pidm,
            b.primary_indicator
        FROM edw_prod.dim_section_meeting@dwhdb.nocccd.edu a
            INNER JOIN edw_prod.dim_section_instruct@dwhdb.nocccd.edu b
                ON (a.section_meeting_key = b.section_meeting_key)
        WHERE a.term_code = :banner_term_code
    ),
    primary_pick AS (
        -- Pick 1 primary instructor per CRN: if multiple sessions have
        -- primary_indicator='Y', keep the one from the lowest meeting_category.
        SELECT
            term_code,
            crn,
            pidm
        FROM (
            SELECT
                term_code,
                crn,
                pidm,
                ROW_NUMBER() OVER (
                    PARTITION BY term_code, crn
                    ORDER BY meeting_category ASC
                    ) AS rn
            FROM mtg
            WHERE primary_indicator = 'Y'
        )
        WHERE rn = 1
    ),
    building_pick AS (
        -- Pick the building from the lowest meeting_category that has a
        -- non-null building_desc. Sessions with NULL building (e.g., online
        -- modes) are skipped, so a CRN whose 01 session is online and 02
        -- session is on-campus reports the on-campus building.
        SELECT
            term_code,
            crn,
            building_desc
        FROM (
            SELECT
                term_code,
                crn,
                building_desc,
                ROW_NUMBER() OVER (
                    PARTITION BY term_code, crn
                    ORDER BY meeting_category ASC
                    ) AS rn
            FROM mtg
            WHERE building_desc IS NOT NULL
        )
        WHERE rn = 1
    ),
    agg AS (
        -- Collapse all sessions of a CRN into one row.
        SELECT
            term_code,
            crn,
            MAX(section_key) AS section_key,
            MIN(meeting_begin_time) AS meeting_begin_time,
            MAX(meeting_end_time) AS meeting_end_time,
            LISTAGG(days_tok, '') WITHIN GROUP (ORDER BY meeting_category) AS days_concat
        FROM mtg
        GROUP BY
            term_code,
            crn
    ),
    section_meeting AS (
        SELECT
            a.section_key,
            a.term_code,
            a.crn,
            a.meeting_begin_time,
            a.meeting_end_time,
            -- Rebuild meeting_days in canonical M T W Th F Sa Su order.
            CASE WHEN INSTR(a.days_concat, 'M') > 0 THEN 'M' END
                || CASE WHEN INSTR(a.days_concat, 'T') > 0 THEN 'T' END
                || CASE WHEN INSTR(a.days_concat, 'W') > 0 THEN 'W' END
                || CASE WHEN INSTR(a.days_concat, 'h') > 0 THEN 'Th' END
                || CASE WHEN INSTR(a.days_concat, 'F') > 0 THEN 'F' END
                || CASE WHEN INSTR(a.days_concat, 'a') > 0 THEN 'Sa' END
                || CASE WHEN INSTR(a.days_concat, 'u') > 0 THEN 'Su' END AS meeting_days,
            bp.building_desc,
            p.pidm,
            s.spriden_first_name || ' ' || s.spriden_last_name AS instructor_name
        FROM agg a
            LEFT JOIN primary_pick p
                ON (a.term_code = p.term_code
                AND a.crn = p.crn)
            LEFT JOIN building_pick bp
                ON (a.term_code = bp.term_code
                AND a.crn = bp.crn)
            LEFT JOIN spriden s
                ON (p.pidm = s.spriden_pidm
                AND s.spriden_change_ind IS NULL)
    ),

    main AS (
        SELECT
            c.section_key,
            c.term_code,
            a.term_title,
            c.crn,
            sckcsin.f_get_course_alias(
                c.subject_code,
                c.course_number,
                c.term_code
            ) AS crse_alias,
            SUBSTR(c.campus_code, 1, 1) AS campus_code,
            CASE
                WHEN SUBSTR(c.campus_code, 1, 1) = '1' THEN 'Cypress'
                WHEN SUBSTR(c.campus_code, 1, 1) = '2' THEN 'Fullerton'
                WHEN SUBSTR(c.campus_code, 1, 1) = '3' THEN 'NOCE'
            END AS campus_desc,
            c.division_code,
            CASE
                WHEN SUBSTR(c.campus_code, 1, 1) = '3' THEN (
                    CASE
                        WHEN c.subject_code LIKE 'IHS%'
                            OR c.subject_code LIKE 'ABE%'
                                AND fz_get_course_division(c.subject_code, c.course_number, c.term_code) != 'EMER'
                            THEN 'Basic Skills'
                        WHEN fz_get_course_division(c.subject_code, c.course_number, c.term_code)
                            IN ('VBMT', 'VMDC', 'CPLB', 'COMP', 'VECE', 'VELE', 'VFSR', 'VMED', 'VPHM', 'VMDA', 'VBOT',
                                'WFPR',
                                'PARN',
                                'VBSK', 'VCIS', 'VBUS', 'VBSO', 'MEDO')
                            THEN 'CTE'
                        WHEN fz_get_course_division(c.subject_code, c.course_number, c.term_code)
                            IN ('DSPS', 'DSPB', 'VBRT')
                            THEN 'DSS'
                        WHEN c.subject_code IN ('ESLA', 'ESLM')
                            THEN 'ESL'
                        WHEN fz_get_course_division(c.subject_code, c.course_number, c.term_code) IN ('EMER', 'LEAP')
                            THEN 'LEAP'
                    END)
                ELSE c.division_desc
            END AS division_desc,
            c.department_code,
            c.department_desc,
            c.subject_code,
            c.course_number,
            d.course_title,
            c.scheduling_desc,
            g.gtvinsm_desc as insm,
            c.start_date,
            c.end_date,
            sm.meeting_begin_time AS begin_time,
            sm.meeting_end_time AS end_time,
            sm.meeting_days AS days,
            sm.building_desc AS building,
            sm.instructor_name AS pri_instructor,
            TRIM(REGEXP_SUBSTR(c.crosslist, '(.*?)\{', 1, 1, NULL, 1)) AS crosslist_group,
            CASE
                WHEN TRIM(REGEXP_SUBSTR(c.crosslist, '(.*?)\{', 1, 1, NULL, 1)) IS NULL THEN c.enroll_max
                ELSE TO_NUMBER(TRIM(REGEXP_SUBSTR(c.crosslist, '(.*?)\{', 1, 3, NULL, 1)))
            END AS enroll_max,
            CASE
                WHEN TRIM(REGEXP_SUBSTR(c.crosslist, '(.*?)\{', 1, 1, NULL, 1)) IS NULL THEN c.available_seats
                ELSE TO_NUMBER(TRIM(REGEXP_SUBSTR(c.crosslist, '(.*?)\{', 1, 4, NULL, 1)))
            END AS available_seats,
            CASE
                WHEN TRIM(REGEXP_SUBSTR(c.crosslist, '(.*?)\{', 1, 1, NULL, 1)) IS NULL THEN c.current_enrollment
                ELSE SUM(c.current_enrollment) OVER (
                    PARTITION BY
                        c.term_code,
                        TRIM(REGEXP_SUBSTR(c.crosslist, '(.*?)\{', 1, 1, NULL, 1))
                    )
            END AS current_enroll_count,
            CASE
                WHEN TRIM(REGEXP_SUBSTR(c.crosslist, '(.*?)\{', 1, 1, NULL, 1)) IS NULL THEN c.wait_count
                ELSE SUM(c.wait_count) OVER (
                    PARTITION BY
                        c.term_code,
                        TRIM(REGEXP_SUBSTR(c.crosslist, '(.*?)\{', 1, 1, NULL, 1))
                    )
            END AS wait_count,
            CASE
                WHEN TRIM(REGEXP_SUBSTR(c.crosslist, '(.*?)\{', 1, 1, NULL, 1)) IS NULL THEN c.census_1_enrollment
                ELSE SUM(c.census_1_enrollment) OVER (
                    PARTITION BY
                        c.term_code,
                        TRIM(REGEXP_SUBSTR(c.crosslist, '(.*?)\{', 1, 1, NULL, 1))
                    )
            END AS census_1_enroll_count,
            CASE
                WHEN TRIM(REGEXP_SUBSTR(c.crosslist, '(.*?)\{', 1, 1, NULL, 1)) IS NULL THEN c.census_2_enrollment
                ELSE SUM(c.census_2_enrollment) OVER (
                    PARTITION BY
                        c.term_code,
                        TRIM(REGEXP_SUBSTR(c.crosslist, '(.*?)\{', 1, 1, NULL, 1))
                    )
            END AS census_2_enroll_count,
            CASE
                WHEN TRIM(REGEXP_SUBSTR(c.crosslist, '(.*?)\{', 1, 1, NULL, 1)) IS NULL
                    THEN a.first_day_morning_enroll_count
                ELSE SUM(a.first_day_morning_enroll_count) OVER (
                    PARTITION BY
                        c.term_code,
                        TRIM(REGEXP_SUBSTR(c.crosslist, '(.*?)\{', 1, 1, NULL, 1))
                    )
            END AS first_day_morning_enroll_count,
            CASE
                WHEN TRIM(REGEXP_SUBSTR(c.crosslist, '(.*?)\{', 1, 1, NULL, 1)) IS NULL
                    THEN a.first_day_evening_enroll_count
                ELSE SUM(a.first_day_evening_enroll_count) OVER (
                    PARTITION BY
                        c.term_code,
                        TRIM(REGEXP_SUBSTR(c.crosslist, '(.*?)\{', 1, 1, NULL, 1))
                    )
            END AS first_day_evening_enroll_count,
            CASE
                WHEN TRIM(REGEXP_SUBSTR(c.crosslist, '(.*?)\{', 1, 1, NULL, 1)) IS NULL
                    THEN a.first_day_no_hours_enroll_count
                ELSE SUM(a.first_day_no_hours_enroll_count) OVER (
                    PARTITION BY
                        c.term_code,
                        TRIM(REGEXP_SUBSTR(c.crosslist, '(.*?)\{', 1, 1, NULL, 1))
                    )
            END AS first_day_no_hours_enroll_count
        FROM edw_prod.dim_section@dwhdb.nocccd.edu c
            JOIN first_day_enroll a
                ON (c.section_key = a.section_key)
            JOIN edw_prod.dim_course@dwhdb.nocccd.edu d
                ON (c.course_key = d.course_key)
            JOIN section_meeting sm
                ON (c.section_key = sm.section_key)
            left join gtvinsm g
        on (c.instruction_mode_code = g.gtvinsm_code)
        WHERE c.term_code = :banner_term_code
    )

SELECT
    a.term_code,
    a.term_title,
    a.crn,
    a.campus_desc,
    a.division_desc,
    a.department_desc,
    a.subject_code,
    a.course_number,
    a.crse_alias,
    a.course_title,
    a.scheduling_desc,
    a.insm,
    a.start_date,
    a.end_date,
    a.begin_time,
    a.end_time,
    a.days,
    a.building,
    a.pri_instructor,
    a.crosslist_group,
    a.enroll_max,
    a.available_seats,
    a.current_enroll_count,
    a.wait_count,
    ROUND(CASE
              WHEN a.current_enroll_count <= 0 OR a.enroll_max <= 0 THEN 0
              ELSE a.current_enroll_count / a.enroll_max
          END, 2) AS current_enroll_fillrate,
    a.census_1_enroll_count,
    ROUND(CASE
              WHEN a.census_1_enroll_count <= 0 OR a.enroll_max <= 0 THEN 0
              ELSE a.census_1_enroll_count / a.enroll_max
          END, 2) AS census_1_enroll_fillrate,
    a.census_2_enroll_count,
    ROUND(CASE
              WHEN a.census_2_enroll_count <= 0 OR a.enroll_max <= 0 THEN 0
              ELSE a.census_2_enroll_count / a.enroll_max
          END, 2) AS census_2_enroll_fillrate,
    a.first_day_morning_enroll_count,
    ROUND(CASE
              WHEN a.first_day_morning_enroll_count <= 0 OR a.enroll_max <= 0 THEN 0
              ELSE a.first_day_morning_enroll_count / a.enroll_max
          END, 2) AS first_day_morning_enroll_fillrate,
    a.first_day_evening_enroll_count,
    ROUND(CASE
              WHEN a.first_day_evening_enroll_count <= 0 OR a.enroll_max <= 0 THEN 0
              ELSE a.first_day_evening_enroll_count / a.enroll_max
          END, 2) AS first_day_evening_enroll_fillrate,
    a.first_day_no_hours_enroll_count,
    ROUND(CASE
              WHEN a.first_day_no_hours_enroll_count <= 0 OR a.enroll_max <= 0 THEN 0
              ELSE a.first_day_no_hours_enroll_count / a.enroll_max
          END, 2) AS first_day_no_hours_enroll_fillrate
FROM main a
ORDER BY
    a.term_code,
    a.crn
