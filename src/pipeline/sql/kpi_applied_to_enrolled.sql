SELECT *
FROM dwh.mv_applied_to_enrolled
WHERE mis_term_id in (:t1...)
ORDER BY
    mis_term_id,
    camp_code,
    styp_code