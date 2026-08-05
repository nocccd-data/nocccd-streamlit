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
-- a param_name. The acyr floor is deliberately loose -- the calendar must stay a SUPERSET of
-- every term any consumer can reference, and a floor duplicated in two places turns a lowered
-- consumer floor into silently missing dates rather than an error. ~30 rows a year.
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
WHERE stvterm_acyr_code >= '2023'
