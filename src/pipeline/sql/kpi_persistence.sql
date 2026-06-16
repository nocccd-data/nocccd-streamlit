SELECT *
FROM dwh.mv_persistence_by_styp
WHERE mis_term_id in (:t1...)
ORDER BY
    mis_term_id,
    camp_code,
    styp_code