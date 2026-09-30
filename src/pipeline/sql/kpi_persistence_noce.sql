SELECT *
FROM dwh.mv_noce_persistence_excl_credit
WHERE mis_term_id in (:t1...)
ORDER BY
    mis_term_id