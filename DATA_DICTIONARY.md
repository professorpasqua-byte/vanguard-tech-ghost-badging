# Data Dictionary

Everything is stored in one SQLite file, `vanguard.db`. All of it is synthetic. Vanguard Tech is a made up company.

There are two kinds of tables. Raw tables are loaded by `src/build_database.py`. Built tables are made by the SQL files in the `sql` folder.

## Raw tables

**employees** (500 rows)
* `employee_id`: a simple ID such as E0001. Everything else in the database uses this ID.
* `team`: Engineering, Sales, Support, Finance, Operations or Product.
* `first_name`, `last_name`: fake names added by `src/add_names.py` using Faker. They are empty until that script is run. The analysis never reads them.

**building_capacity** (60 rows)
* `work_date`: the office day, as text in the form 2026-06-01.
* `desks_available`: 300 on most days, 240 in weeks 7 and 8 while part of floor 4 is closed.

**building_log** (13 rows)
* `work_date`: the day the note is about.
* `note`: a plain note from the facilities team, for example a fire drill or a badge reader fault. The analysis never reads it. It is only used to check the strange days model afterward.

**desk_bookings** (about 20,000 rows)
* `booking_id`: a number for each booking.
* `employee_id`: who booked.
* `work_date`: the day the desk was for.
* `booked_at`: when the booking was made, usually the day before.
* `status`: confirmed, or declined when the system was full.

**badge_events_raw** (about 42,000 rows). This table is messy on purpose.
* `event_id`: a number for each tap.
* `employee_id`: may have a stray space at the end.
* `event_time`: when the tap happened.
* `direction`: IN or OUT, sometimes in lower case or mixed case.
* `reader_id`: MAIN_LOBBY or GARAGE_B.

Known problems in this table: double taps, missing exit taps, missing entry taps, and a badge reader fault on one day.

**ground_truth** (about 20,700 rows). Used only for grading.
* `employee_id`, `work_date`: one row per person who came in on a day.
* `true_reason`: normal, chosen (left early by choice), forced (pushed out by a full floor) or other (for example the fire drill).

**truth_settings** (3 rows). Used only for grading.
* `name`, `value`: the real tipping point, the highest chance of being pushed out, and how sharp the tipping point is.

## Built tables

**visits** (about 21,000 rows). Made by `02_pair_taps.sql`.
* `visit_id`: a number for each visit.
* `employee_id`, `work_date`: who and when.
* `in_time`: when the person tapped in.
* `out_time`: when the person tapped out. Empty if the exit tap is missing.
* `minutes_inside`: stay length in minutes. Empty if the exit tap is missing.
* `exit_known`: 1 if an exit tap was found, otherwise 0.

**dq_report** (5 rows). Made by `02_pair_taps.sql`.
* `check_name`, `count_value`, `note`: how many taps were removed, how many visits had no exit tap, and so on.

**occupancy_15min** (2,880 rows). Made by `03_occupancy.sql`.
* `work_date`, `slot_start`: the day and the start of each 15 minute slot from 07:00 to 18:45.
* `desks_available`: desks that day.
* `people_inside`: how many people were inside. A visit with no exit tap is assumed to last 8 hours, up to 19:00.
* `fullness`: `people_inside` divided by `desks_available`. Above 1 means more people than desks.

**daily_summary** (60 rows). Made by `03_occupancy.sql`.
* `work_date`, `weekday`, `desks_available`.
* `peak_inside`, `peak_fullness`: the busiest moment of the day.
* `hours_above_90`: hours the floor was at least 90% full.
* `people_badged_in`: how many different people came in.
* `confirmed_bookings`, `declined_bookings`: desk bookings accepted and turned down.

**day_visits** (about 20,500 rows). Made by `04_short_visits.sql`. One row per person per office day.
* `employee_id`, `team`, `work_date`.
* `first_in`, `last_out`: first entry and last exit of the day.
* `arrival_minute`: minutes after midnight when the person first came in.
* `visit_count`: how many times they came in that day. A lunch break makes two.
* `all_exits_known`: 1 if every visit that day has an exit tap.
* `minutes_inside`: total minutes inside. Empty if any exit tap is missing.
* `inside_before`: how many people were already inside just before this person arrived.
* `desks_available`: desks that day.
* `fullness_at_arrival`: `inside_before` divided by `desks_available`.
* `no_desk_at_arrival`: 1 if `inside_before` was at least the number of desks.
* `is_short`: 1 if the person was inside for less than 90 minutes that day, 0 if not, empty if the stay is unknown.

**short_visits** (a view). The rows of `day_visits` where `is_short` is 1.

## Files in the results folder

* `odd_days.csv`: every office day with a strangeness score, whether it was flagged, a plain English reason, and the building log note.
* `odd_days_summary.json`: how many days were flagged and how many have a building log note.
* `tipping_point.json`: the tipping point, the base rate, the pushed out share, the closure comparison, the chart data and the grade against the truth.
