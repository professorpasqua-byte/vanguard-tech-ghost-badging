/* Raw tables. src/build_database.py fills these.
   Everything the later SQL files make comes from these tables. */

DROP TABLE IF EXISTS employees;
DROP TABLE IF EXISTS building_capacity;
DROP TABLE IF EXISTS building_log;
DROP TABLE IF EXISTS desk_bookings;
DROP TABLE IF EXISTS badge_events_raw;
DROP TABLE IF EXISTS ground_truth;
DROP TABLE IF EXISTS truth_settings;

/* first_name and last_name are fake. src/add_names.py fills them with Faker.
   The analysis never reads them. */
CREATE TABLE employees (
    employee_id TEXT PRIMARY KEY,
    team        TEXT NOT NULL,
    first_name  TEXT,
    last_name   TEXT
);

CREATE TABLE building_capacity (
    work_date       TEXT PRIMARY KEY,
    desks_available INTEGER NOT NULL
);

CREATE TABLE building_log (
    work_date TEXT NOT NULL,
    note      TEXT NOT NULL
);

CREATE TABLE desk_bookings (
    booking_id  INTEGER PRIMARY KEY,
    employee_id TEXT NOT NULL,
    work_date   TEXT NOT NULL,
    booked_at   TEXT NOT NULL,
    status      TEXT NOT NULL
);

/* Messy on purpose: duplicate taps, missing taps, mixed upper and lower case,
   and stray spaces in employee ids. */
CREATE TABLE badge_events_raw (
    event_id    INTEGER PRIMARY KEY,
    employee_id TEXT,
    event_time  TEXT,
    direction   TEXT,
    reader_id   TEXT
);

/* Used only at the very end, to grade the analysis. The analysis never reads it
   while it works out its answers. */
CREATE TABLE ground_truth (
    employee_id TEXT NOT NULL,
    work_date   TEXT NOT NULL,
    true_reason TEXT NOT NULL
);

CREATE TABLE truth_settings (
    name  TEXT PRIMARY KEY,
    value REAL NOT NULL
);

CREATE INDEX idx_bookings_date ON desk_bookings (work_date);
CREATE INDEX idx_events_person_time ON badge_events_raw (employee_id, event_time);
CREATE INDEX idx_truth_person_day ON ground_truth (employee_id, work_date);
