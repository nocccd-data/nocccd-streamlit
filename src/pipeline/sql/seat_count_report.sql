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
            c.division_desc,
            c.department_code,
            c.department_desc,
            c.subject_code,
            c.course_number,
            d.course_title,
            c.scheduling_desc,
            c.start_date,
            c.end_date,
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
                WHEN TRIM(REGEXP_SUBSTR(c.crosslist, '(.*?)\{', 1, 1, NULL, 1)) IS NULL THEN c.census_1_enrollment
                ELSE SUM(c.census_1_enrollment) OVER (
                    PARTITION BY
                        c.term_code,
                        TRIM(REGEXP_SUBSTR(c.crosslist, '(.*?)\{', 1, 1, NULL, 1))
                    )
            END AS census_1_enroll_count,
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
    a.start_date,
    a.end_date,
    a.crosslist_group,
    a.enroll_max,
    a.available_seats,
    a.current_enroll_count,
    ROUND(CASE
              WHEN a.current_enroll_count <= 0 OR a.enroll_max <= 0 THEN 0
              ELSE a.current_enroll_count / a.enroll_max
          END, 2) AS current_enroll_fillrate,
    a.census_1_enroll_count,
    ROUND(CASE
              WHEN a.census_1_enroll_count <= 0 OR a.enroll_max <= 0 THEN 0
              ELSE a.census_1_enroll_count / a.enroll_max
          END, 2) AS census_1_enroll_fillrate,
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
