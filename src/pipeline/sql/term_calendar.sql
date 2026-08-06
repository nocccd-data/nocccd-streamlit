-- Banner term calendar: start and end dates per term.
--
-- JOIN KEY IS stvterm_code ONLY.
--
-- stvterm_mis_term_id is deliberately NOT selected. It is 1:many against this table -- one
-- MIS term is one credit term (code suffix '0') plus one NOCE term (suffix '5') -- so a join
-- on it fans every row 2:1 and silently attaches the wrong track's calendar to half of them.
-- Consumers resolve the track upstream and join on the unique term code: mv_persistence_by_styp
-- emits spring_term_code / next_fall_term_code already resolved per campus. Re-add mis_term_id
-- here only with that caveat attached.
--
-- No bind parameters: this is a small dimension pulled whole, registered in config.py without
-- a param_name.
--
-- DELIBERATELY UNFILTERED. The calendar must stay a SUPERSET of every term any consumer can
-- reference, and a floor here duplicates a floor over there: when mv_persistence_by_styp's
-- own floor dropped from 237 to 207, an `acyr_code >= '2023'` filter would have left the new
-- cohorts' spring follow-ups (202020, 202035, ...) with no calendar row -- and the consumer
-- fails SAFE, so they would have been marked "provisional" forever rather than raising.
-- Silently missing dates, not an error. At ~7 rows a year the whole table is free; keep it
-- that way rather than re-deriving the right floor every time a consumer changes.
--
-- Not filtered on stvterm_code: Banner carries a '999999' sentinel term dated 2999, which is
-- outside pandas' nanosecond datetime range. It is kept so the extract mirrors stvterm, and
-- consumers must parse dates defensively (see _attach_completeness in kpi_persistence.py).
--
-- Run against REPT (Banner).
SELECT
    stvterm_code,
    stvterm_start_date,
    stvterm_end_date
FROM stvterm
