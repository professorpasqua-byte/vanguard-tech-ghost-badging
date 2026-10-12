"""Tests for the SQL that cleans badge taps and pairs them into visits.

Run from the project folder:

    python -m unittest discover -s tests -v

Each test builds a tiny database in memory with a few hand made taps, runs the
real SQL files, and checks the answer.
"""

import sqlite3
import unittest
from pathlib import Path

SQL_DIR = Path(__file__).resolve().parent.parent / "sql"
DAY = "2026-06-02"


def build(taps, desks=2):
    """taps is a list of (employee_id, time of day, direction)."""
    con = sqlite3.connect(":memory:")
    con.executescript((SQL_DIR / "01_schema.sql").read_text())
    people = sorted({t[0].strip() for t in taps})
    con.executemany("INSERT INTO employees (employee_id, team) VALUES (?, 'Test')", [(p,) for p in people])
    con.execute("INSERT INTO building_capacity VALUES (?, ?)", (DAY, desks))
    con.executemany(
        "INSERT INTO badge_events_raw (employee_id, event_time, direction, reader_id) "
        "VALUES (?, ?, ?, 'MAIN_LOBBY')",
        [(who, "%s %s" % (DAY, when), direction) for who, when, direction in taps],
    )
    for name in ["02_pair_taps.sql", "03_occupancy.sql", "04_short_visits.sql"]:
        con.executescript((SQL_DIR / name).read_text())
    return con


def one(con, sql, params=()):
    return con.execute(sql, params).fetchone()


class PairingTests(unittest.TestCase):
    def test_normal_day_is_one_long_visit(self):
        con = build([("E1", "08:00:00", "IN"), ("E1", "17:00:00", "OUT")])
        minutes, known = one(con, "SELECT minutes_inside, exit_known FROM visits")
        self.assertEqual(minutes, 540.0)
        self.assertEqual(known, 1)
        self.assertEqual(one(con, "SELECT is_short FROM day_visits")[0], 0)

    def test_double_tap_and_lowercase_direction_are_cleaned(self):
        con = build(
            [
                ("E2", "09:00:00", "IN"),
                ("E2", "09:00:04", "in"),
                ("E2", "09:40:00", "OUT"),
            ]
        )
        self.assertEqual(one(con, "SELECT COUNT(*) FROM visits")[0], 1)
        self.assertEqual(one(con, "SELECT minutes_inside FROM visits")[0], 40.0)
        self.assertEqual(one(con, "SELECT is_short FROM day_visits")[0], 1)

    def test_stray_space_in_employee_id_is_trimmed(self):
        con = build([("E3 ", "10:00:00", "In"), ("E3", "18:00:00", "OUT")])
        self.assertEqual(one(con, "SELECT COUNT(DISTINCT employee_id) FROM visits")[0], 1)
        self.assertEqual(one(con, "SELECT employee_id FROM visits")[0], "E3")

    def test_missing_exit_tap_leaves_stay_unknown(self):
        con = build([("E4", "09:30:00", "IN")])
        out_time, known = one(con, "SELECT out_time, exit_known FROM visits")
        self.assertIsNone(out_time)
        self.assertEqual(known, 0)
        self.assertIsNone(one(con, "SELECT is_short FROM day_visits")[0])
        self.assertEqual(one(con, "SELECT count_value FROM dq_report WHERE check_name = 'Visits with no exit tap'")[0], 1)

    def test_lunch_break_makes_two_visits_but_one_long_day(self):
        con = build(
            [
                ("E5", "08:10:00", "IN"),
                ("E5", "12:00:00", "OUT"),
                ("E5", "13:00:00", "IN"),
                ("E5", "17:00:00", "OUT"),
            ]
        )
        self.assertEqual(one(con, "SELECT COUNT(*) FROM visits")[0], 2)
        count, minutes, short = one(con, "SELECT visit_count, minutes_inside, is_short FROM day_visits")
        self.assertEqual(count, 2)
        self.assertEqual(minutes, 470.0)
        self.assertEqual(short, 0)

    def test_exit_without_entry_is_counted_not_paired(self):
        con = build([("E6", "17:30:00", "OUT")])
        self.assertEqual(one(con, "SELECT COUNT(*) FROM visits")[0], 0)
        self.assertEqual(
            one(con, "SELECT count_value FROM dq_report WHERE check_name = 'Exit taps with no entry tap'")[0], 1
        )


class CrowdingTests(unittest.TestCase):
    def test_fullness_at_arrival_counts_people_already_inside(self):
        con = build(
            [
                ("E1", "08:00:00", "IN"),
                ("E1", "17:00:00", "OUT"),
                ("E2", "08:30:00", "IN"),
                ("E2", "17:00:00", "OUT"),
                ("E3", "08:45:00", "IN"),
                ("E3", "17:00:00", "OUT"),
            ],
            desks=2,
        )
        rows = {
            r[0]: r[1:]
            for r in con.execute(
                "SELECT employee_id, inside_before, fullness_at_arrival, no_desk_at_arrival FROM day_visits"
            )
        }
        self.assertEqual(rows["E1"], (0, 0.0, 0))
        self.assertEqual(rows["E2"], (1, 0.5, 0))
        self.assertEqual(rows["E3"], (2, 1.0, 1))

    def test_occupancy_slot_counts_people_inside(self):
        con = build([("E1", "08:00:00", "IN"), ("E1", "17:00:00", "OUT")], desks=4)
        inside, fullness = one(
            con,
            "SELECT people_inside, fullness FROM occupancy_15min WHERE slot_start = ?",
            (DAY + " 09:00:00",),
        )
        self.assertEqual(inside, 1)
        self.assertEqual(fullness, 0.25)
        before = one(
            con,
            "SELECT people_inside FROM occupancy_15min WHERE slot_start = ?",
            (DAY + " 07:30:00",),
        )[0]
        self.assertEqual(before, 0)


if __name__ == "__main__":
    unittest.main()
