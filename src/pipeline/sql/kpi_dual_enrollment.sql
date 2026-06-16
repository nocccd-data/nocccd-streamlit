SELECT *
FROM dwh.mv_dual_enrollment
WHERE acyr_code in (:t1...)
ORDER BY
    acyr_code,
    camp_code