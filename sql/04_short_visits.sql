/* One row per person per office day.
   A short visit is a day with less than 90 minutes inside the building.
   fullness_at_arrival is the number of people already inside a moment before
   this person walked in, divided by the desks available that day. */

DROP TABLE IF EXISTS day_visits;
CREATE TABLE day_visits AS
WITH per_day AS (
    SELECT employee_id,
           work_date,
           MIN(in_time)        AS first_in,
           MAX(out_time)       AS last_out,
           COUNT(*)            AS visit_count,
           MIN(exit_known)     AS all_exits_known,
           SUM(minutes_inside) AS known_minutes
    FROM visits
    GROUP BY employee_id, work_date
),
with_crowd AS (
    SELECT p.*,
           (SELECT COUNT(*)
              FROM visit_span v
             WHERE v.work_date = p.work_date
               AND v.in_time   < p.first_in
               AND v.out_used  > p.first_in) AS inside_before
    FROM per_day p
)
SELECT w.employee_id,
       e.team,
       w.work_date,
       w.first_in,
       w.last_out,
       CAST(strftime('%H', w.first_in) AS INTEGER) * 60
         + CAST(strftime('%M', w.first_in) AS INTEGER) AS arrival_minute,
       w.visit_count,
       w.all_exits_known,
       CASE WHEN w.all_exits_known = 1 THEN ROUND(w.known_minutes, 1) END AS minutes_inside,
       w.inside_before,
       c.desks_available,
       ROUND(w.inside_before * 1.0 / c.desks_available, 3) AS fullness_at_arrival,
       CASE WHEN w.inside_before >= c.desks_available THEN 1 ELSE 0 END AS no_desk_at_arrival,
       CASE
           WHEN w.all_exits_known = 1
           THEN CASE WHEN w.known_minutes < 90 THEN 1 ELSE 0 END
       END AS is_short
FROM with_crowd w
JOIN building_capacity c ON c.work_date = w.work_date
LEFT JOIN employees e ON e.employee_id = w.employee_id;

CREATE INDEX idx_dayvisits_date ON day_visits (work_date);


DROP VIEW IF EXISTS short_visits;
CREATE VIEW short_visits AS
SELECT * FROM day_visits WHERE is_short = 1;
