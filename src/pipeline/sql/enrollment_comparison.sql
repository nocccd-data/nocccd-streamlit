SELECT *
FROM dwh.mv_enrollment_by_date_5yrs
where term_code in (:t1,:t2)