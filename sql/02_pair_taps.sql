/* Step 1: clean the raw taps.
   Fix the case of the direction, trim spaces from ids,
   and drop a tap that repeats the same direction within 10 seconds. */

DROP TABLE IF EXISTS taps_clean;
CREATE TABLE taps_clean AS
WITH tidy AS (
    SELECT event_id,
           TRIM(employee_id)      AS employee_id,
           event_time,
           UPPER(TRIM(direction)) AS direction,
           reader_id
    FROM badge_events_raw
    WHERE employee_id IS NOT NULL
      AND UPPER(TRIM(direction)) IN ('IN', 'OUT')
),
spaced AS (
    SELECT *,
           LAG(event_time) OVER (
               PARTITION BY employee_id, direction
               ORDER BY event_time
           ) AS previous_same_tap
    FROM tidy
)
SELECT event_id, employee_id, event_time, direction, reader_id
FROM spaced
WHERE previous_same_tap IS NULL
   OR (julianday(event_time) - julianday(previous_same_tap)) * 86400.0 > 10;

CREATE INDEX idx_taps_person_time ON taps_clean (employee_id, event_time);


/* Step 2: pair every entry tap with the exit tap that follows it on the same day.
   If no exit tap follows, the exit stays empty and exit_known is 0. */

DROP TABLE IF EXISTS visits;
CREATE TABLE visits AS
WITH ordered AS (
    SELECT employee_id,
           event_time,
           direction,
           LEAD(event_time) OVER w AS next_time,
           LEAD(direction)  OVER w AS next_direction
    FROM taps_clean
    WINDOW w AS (PARTITION BY employee_id ORDER BY event_time)
),
entries AS (
    SELECT employee_id,
           date(event_time) AS work_date,
           event_time       AS in_time,
           CASE
               WHEN next_direction = 'OUT' AND date(next_time) = date(event_time)
               THEN next_time
           END AS out_time
    FROM ordered
    WHERE direction = 'IN'
)
SELECT ROW_NUMBER() OVER (ORDER BY employee_id, in_time) AS visit_id,
       employee_id,
       work_date,
       in_time,
       out_time,
       CASE
           WHEN out_time IS NOT NULL
           THEN ROUND((julianday(out_time) - julianday(in_time)) * 1440.0, 1)
       END AS minutes_inside,
       CASE WHEN out_time IS NOT NULL THEN 1 ELSE 0 END AS exit_known
FROM entries;

CREATE INDEX idx_visits_date ON visits (work_date);
CREATE INDEX idx_visits_person ON visits (employee_id, work_date);


/* Step 3: a short report on how messy the raw data was. */

DROP TABLE IF EXISTS dq_report;
CREATE TABLE dq_report (
    check_name  TEXT,
    count_value INTEGER,
    note        TEXT
);

INSERT INTO dq_report
SELECT 'Raw taps', COUNT(*), 'Rows in badge_events_raw'
FROM badge_events_raw;

INSERT INTO dq_report
SELECT 'Taps removed',
       (SELECT COUNT(*) FROM badge_events_raw) - (SELECT COUNT(*) FROM taps_clean),
       'Repeat taps within 10 seconds, or rows with an unusable direction';

INSERT INTO dq_report
SELECT 'Visits found', COUNT(*), 'Entry taps matched into visits'
FROM visits;

INSERT INTO dq_report
SELECT 'Visits with no exit tap', COALESCE(SUM(1 - exit_known), 0),
       'Stay length unknown, so these days are left out of short visit counts'
FROM visits;

WITH ordered AS (
    SELECT direction,
           event_time,
           LAG(direction)  OVER w AS previous_direction,
           LAG(event_time) OVER w AS previous_time
    FROM taps_clean
    WINDOW w AS (PARTITION BY employee_id ORDER BY event_time)
)
INSERT INTO dq_report
SELECT 'Exit taps with no entry tap', COUNT(*),
       'Likely someone who followed a coworker in. These people are missing from headcounts'
FROM ordered
WHERE direction = 'OUT'
  AND (previous_direction IS NULL
       OR previous_direction <> 'IN'
       OR date(previous_time) <> date(event_time));
