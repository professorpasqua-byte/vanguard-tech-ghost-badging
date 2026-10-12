/* How many people were inside, every 15 minutes, from 07:00 to 19:00.
   A visit with no exit tap is assumed to last 8 hours, up to 19:00.
   That is a guess, and the project says so. */

DROP TABLE IF EXISTS visit_span;
CREATE TABLE visit_span AS
SELECT work_date,
       employee_id,
       in_time,
       COALESCE(out_time, MIN(datetime(in_time, '+8 hours'), work_date || ' 19:00:00')) AS out_used
FROM visits;

CREATE INDEX idx_span_date ON visit_span (work_date, in_time);


DROP TABLE IF EXISTS occupancy_15min;
CREATE TABLE occupancy_15min AS
WITH RECURSIVE slot_numbers(n) AS (
    SELECT 0
    UNION ALL
    SELECT n + 1 FROM slot_numbers WHERE n < 47
),
slots AS (
    SELECT c.work_date,
           c.desks_available,
           datetime(c.work_date || ' 07:00:00', '+' || (n * 15) || ' minutes') AS slot_start
    FROM building_capacity c
    CROSS JOIN slot_numbers
)
SELECT s.work_date,
       s.slot_start,
       s.desks_available,
       COUNT(v.in_time) AS people_inside,
       ROUND(COUNT(v.in_time) * 1.0 / s.desks_available, 3) AS fullness
FROM slots s
LEFT JOIN visit_span v
       ON v.work_date = s.work_date
      AND v.in_time <= s.slot_start
      AND v.out_used > s.slot_start
GROUP BY s.work_date, s.slot_start, s.desks_available;

CREATE INDEX idx_occ_date ON occupancy_15min (work_date);


/* One row per office day. */

DROP TABLE IF EXISTS daily_summary;
CREATE TABLE daily_summary AS
SELECT o.work_date,
       CASE strftime('%w', o.work_date)
           WHEN '1' THEN 'Monday'
           WHEN '2' THEN 'Tuesday'
           WHEN '3' THEN 'Wednesday'
           WHEN '4' THEN 'Thursday'
           WHEN '5' THEN 'Friday'
       END AS weekday,
       MAX(o.desks_available) AS desks_available,
       MAX(o.people_inside)   AS peak_inside,
       ROUND(MAX(o.fullness), 3) AS peak_fullness,
       SUM(CASE WHEN o.fullness >= 0.9 THEN 1 ELSE 0 END) * 0.25 AS hours_above_90,
       (SELECT COUNT(DISTINCT v.employee_id)
          FROM visits v WHERE v.work_date = o.work_date) AS people_badged_in,
       (SELECT COUNT(*) FROM desk_bookings b
         WHERE b.work_date = o.work_date AND b.status = 'confirmed') AS confirmed_bookings,
       (SELECT COUNT(*) FROM desk_bookings b
         WHERE b.work_date = o.work_date AND b.status = 'declined')  AS declined_bookings
FROM occupancy_15min o
GROUP BY o.work_date;
