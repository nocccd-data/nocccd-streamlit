SELECT
    s.stvterm_mis_term_id AS mis_term_id,
    CASE MOD(s.stvterm_mis_term_id, 10)
        WHEN 7 THEN '20' || TRUNC(s.stvterm_mis_term_id / 10)
                     || '-' || (TRUNC(s.stvterm_mis_term_id / 10) + 1) || ' Fall'
        WHEN 3 THEN '20' || (TRUNC(s.stvterm_mis_term_id / 10) - 1)
                     || '-' || TRUNC(s.stvterm_mis_term_id / 10) || ' Spring'
        WHEN 5 THEN '20' || (TRUNC(s.stvterm_mis_term_id / 10) - 1)
                     || '-' || TRUNC(s.stvterm_mis_term_id / 10) || ' Summer'
    END AS academic_term,
    CASE
        WHEN SUBSTR(a.campus_code, 1, 1) = '1' THEN 'Cypress'
        WHEN SUBSTR(a.campus_code, 1, 1) = '2' THEN 'Fullerton'
        WHEN SUBSTR(a.campus_code, 1, 1) = '3' THEN 'NOCE'
    END AS campus_description,
    a.crn,
    b.meeting_category,
    c.course_title,
    a.subject_code,
    a.subject_desc,
    a.course_number,
    a.division_code,
    a.division_desc,
    a.department_code,
    a.department_desc,
    a.instruction_mode_code,
    b.modality_code,
    b.modality_desc,
    b.schedule_code AS meeting_schd_code,
    b.schedule_desc AS meeting_schd_desc,
    b.meeting_type_code,
    b.meeting_type_desc,
    a.current_enrollment,
    b.meeting_start_date,
    b.meeting_end_date,
    b.meeting_begin_time,
    b.meeting_end_time,
    b.meeting_days,
    b.building_code,
    b.building_desc,
    b.room_code
FROM edw_prod.dim_section a
    JOIN edw_prod.dim_section_meeting b
        ON (a.section_key = b.section_key)
    JOIN edw_prod.dim_course c
        ON (a.course_key = c.course_key)
    JOIN stvterm@banner.nocccd.edu s
        ON (a.term_code = s.stvterm_code)
WHERE s.stvterm_mis_term_id in (:t1...)