"""Build vanguard.db for the Vanguard Tech project.

Run it from anywhere:

    python src/build_database.py

What it does, in plain steps:
1. Creates the raw tables from sql/01_schema.sql.
2. Simulates 60 office days at Vanguard Tech and fills the raw tables.
3. Runs the SQL files that clean the taps and build the summary tables.

Everything here is synthetic. No real person or company is involved.
Inside Vanguard Tech, leaving soon after badging in is called ghost badging.
The real world name for it is coffee badging.
"""

import datetime as dt
import heapq
import sqlite3
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
SQL_DIR = ROOT / "sql"
DB_PATH = ROOT / "vanguard.db"

SEED = 2026
START_DATE = dt.date(2026, 6, 1)  # a Monday, the first day of the five day rule
N_DAYS = 60                        # 12 weeks of office days

TEAM_SIZES = {
    "Engineering": 160,
    "Sales": 90,
    "Support": 100,
    "Finance": 50,
    "Operations": 60,
    "Product": 40,
}
TEAM_ARRIVAL_SHIFT = {  # minutes later (plus) or earlier (minus) than the 8:36 average
    "Engineering": 25,
    "Sales": -15,
    "Support": -30,
    "Finance": 0,
    "Operations": -20,
    "Product": 15,
}

DESKS_NORMAL = 300
DESKS_CLOSED = 240            # while part of one floor is closed
CLOSED_DAYS = range(30, 40)   # weeks 7 and 8
DRILL_DAY = 17                # a fire drill
OFFSITE_DAY = 23              # most people are away at a company event
OUTAGE_DAY = 47               # a badge reader fault loses many exit taps

# The hidden rules the analysis has to discover.
TIPPING = 0.90        # crowding starts to push people out near this fullness
TIP_WIDTH = 0.03      # how sharp the tipping point is
FORCED_MAX = 0.55     # the most people who leave because the floor is too full

WEEKDAY_ATTEND = [0.60, 0.80, 0.82, 0.78, 0.50]  # Monday to Friday
WEEKDAY_CHOSEN = [1.4, 0.9, 0.8, 0.9, 1.5]       # ghost badging is likelier on Mondays and Fridays
SHORT_MIN, SHORT_MAX = 20, 80                    # minutes inside on a short visit


def sigmoid(x):
    return 1.0 / (1.0 + np.exp(-x))


def stamp(day, minutes):
    """Turn a day and minutes after midnight into a text timestamp."""
    base = dt.datetime.combine(day, dt.time(0, 0))
    moment = base + dt.timedelta(seconds=float(minutes) * 60.0)
    return moment.strftime("%Y-%m-%d %H:%M:%S")


def work_dates():
    dates = []
    for i in range(N_DAYS):
        dates.append(START_DATE + dt.timedelta(days=7 * (i // 5) + i % 5))
    return dates


def emit_tap(rng, events, employee_id, day, minute, direction, p_missing):
    """Add one badge tap, with the kinds of mess a real system has."""
    if rng.random() < p_missing:
        return
    repeats = 2 if rng.random() < 0.015 else 1  # a double tap
    for r in range(repeats):
        when = minute + r * rng.uniform(1, 6) / 60.0
        if rng.random() < 0.88:
            label = direction
        else:
            label = str(rng.choice([direction.lower(), direction.capitalize()]))
        who = employee_id + " " if rng.random() < 0.004 else employee_id
        reader = "MAIN_LOBBY" if rng.random() < 0.65 else "GARAGE_B"
        events.append((stamp(day, when), who, label, reader))


def simulate(rng):
    n = sum(TEAM_SIZES.values())
    ids, teams = [], []
    for team, size in TEAM_SIZES.items():
        for _ in range(size):
            ids.append("E%04d" % (len(ids) + 1))
            teams.append(team)
    ids = np.array(ids)

    attend_trait = np.clip(rng.normal(1.0, 0.12, n), 0.5, 1.2)
    regular_ghost = rng.random(n) < 0.08
    ghost_rate = np.where(regular_ghost, 0.5, rng.beta(1.5, 14, n))
    personal_shift = rng.normal(0, 25, n)
    team_shift = np.array([TEAM_ARRIVAL_SHIFT[t] for t in teams], dtype=float)

    dates = work_dates()
    capacity, log, bookings, events, truth = [], [], [], [], []

    for d, day in enumerate(dates):
        wd = d % 5
        desks = DESKS_CLOSED if d in CLOSED_DAYS else DESKS_NORMAL
        capacity.append((day.isoformat(), desks))
        if d in CLOSED_DAYS:
            log.append((day.isoformat(), "Part of floor 4 closed for repairs. 60 desks out of service."))
        if d == DRILL_DAY:
            log.append((day.isoformat(), "Fire drill at 11:20. Many people did not come back inside."))
        if d == OFFSITE_DAY:
            log.append((day.isoformat(), "Company offsite. Most staff were away."))
        if d == OUTAGE_DAY:
            log.append((day.isoformat(), "Badge reader fault. Many exit taps were not recorded."))

        p_attend = np.clip(WEEKDAY_ATTEND[wd] * attend_trait, 0.05, 0.97)
        if d == OFFSITE_DAY:
            p_attend = p_attend * 0.3
        comes = rng.random(n) < p_attend
        attendees = np.flatnonzero(comes)

        arrivals = rng.normal(516, 55, len(attendees))
        arrivals = arrivals + team_shift[attendees] + personal_shift[attendees]
        arrivals = np.clip(arrivals, 390, 690)

        inside = []  # departure times of everyone currently inside
        for pos in np.argsort(arrivals):
            e = attendees[pos]
            t = float(arrivals[pos])
            while inside and inside[0] <= t:
                heapq.heappop(inside)
            before = len(inside)
            fullness = before / desks
            p_forced = FORCED_MAX * float(sigmoid((fullness - TIPPING) / TIP_WIDTH))

            if rng.random() < p_forced:
                reason = "forced"
                stay = rng.uniform(SHORT_MIN, SHORT_MAX)
            elif rng.random() < ghost_rate[e] * WEEKDAY_CHOSEN[wd]:
                reason = "chosen"
                stay = rng.uniform(SHORT_MIN, SHORT_MAX)
            else:
                reason = "normal"
                if before >= desks:
                    stay = float(np.clip(rng.normal(330, 60), 200, 480))
                else:
                    stay = float(np.clip(rng.normal(470, 50), 300, 600))
            depart = min(t + stay, 1140.0)

            if d == DRILL_DAY and t < 680 < depart and rng.random() < 0.65:
                depart = 680 + rng.uniform(0, 10)
                reason = "other"

            heapq.heappush(inside, depart)

            segments = [(t, depart)]
            if reason == "normal" and stay > 400 and rng.random() < 0.06:
                out1 = rng.uniform(720, 810)  # steps out for lunch and comes back
                back = out1 + rng.uniform(40, 70)
                if t + 90 < out1 < back < depart - 30:
                    segments = [(t, out1), (back, depart)]

            short_visit = (depart - t) < 90
            for k, (start, end) in enumerate(segments):
                emit_tap(rng, events, ids[e], day, start, "IN", 0.01)
                if d == OUTAGE_DAY:
                    p_out = 0.70
                elif short_visit:
                    p_out = 0.06
                else:
                    p_out = 0.035
                emit_tap(rng, events, ids[e], day, end, "OUT", p_out)

            truth.append((ids[e], day.isoformat(), reason))

        # Desk bookings made the day before. The system accepts up to 10 percent
        # more bookings than there are desks, because some people never show up.
        wanting = [e for e in attendees if rng.random() < 0.85]
        others = np.flatnonzero(~comes)
        extra = rng.choice(others, size=min(len(others), int(0.13 * len(attendees))), replace=False)
        requests = list(wanting) + list(extra)
        stamps = []
        for e in requests:
            minute = rng.uniform(8 * 60, 18 * 60)
            stamps.append((stamp(day - dt.timedelta(days=1), minute), ids[e]))
        stamps.sort()
        cap = int(1.1 * desks)
        for k, (when, who) in enumerate(stamps):
            status = "confirmed" if k < cap else "declined"
            bookings.append((who, day.isoformat(), when, status))

    employees = list(zip(ids.tolist(), teams))
    events.sort(key=lambda row: row[0])
    return employees, capacity, log, bookings, events, truth


def build():
    if DB_PATH.exists():
        DB_PATH.unlink()
    rng = np.random.default_rng(SEED)
    employees, capacity, log, bookings, events, truth = simulate(rng)

    con = sqlite3.connect(DB_PATH)
    con.executescript((SQL_DIR / "01_schema.sql").read_text())
    con.executemany("INSERT INTO employees (employee_id, team) VALUES (?, ?)", employees)
    con.executemany("INSERT INTO building_capacity VALUES (?, ?)", capacity)
    con.executemany("INSERT INTO building_log VALUES (?, ?)", log)
    con.executemany(
        "INSERT INTO desk_bookings VALUES (?, ?, ?, ?, ?)",
        [(i + 1,) + row for i, row in enumerate(bookings)],
    )
    con.executemany(
        "INSERT INTO badge_events_raw VALUES (?, ?, ?, ?, ?)",
        [(i + 1, who, when, label, reader) for i, (when, who, label, reader) in enumerate(events)],
    )
    con.executemany("INSERT INTO ground_truth VALUES (?, ?, ?)", truth)
    con.executemany(
        "INSERT INTO truth_settings VALUES (?, ?)",
        [("tipping_fullness", TIPPING), ("forced_max", FORCED_MAX), ("tip_width", TIP_WIDTH)],
    )
    con.commit()

    for name in ["02_pair_taps.sql", "03_occupancy.sql", "04_short_visits.sql"]:
        con.executescript((SQL_DIR / name).read_text())
    con.commit()

    print("Built", DB_PATH.name)
    for table in [
        "employees", "desk_bookings", "badge_events_raw", "taps_clean", "visits",
        "occupancy_15min", "daily_summary", "day_visits", "ground_truth",
    ]:
        count = con.execute("SELECT COUNT(*) FROM " + table).fetchone()[0]
        print("  %-18s %7d rows" % (table, count))

    # The app does not need the helper tables or the indexes. Dropping them
    # keeps the file small enough to commit to GitHub.
    con.execute("DROP TABLE IF EXISTS taps_clean")
    con.execute("DROP TABLE IF EXISTS visit_span")
    names = con.execute(
        "SELECT name FROM sqlite_master WHERE type = 'index' AND sql IS NOT NULL"
    ).fetchall()
    for (name,) in names:
        con.execute("DROP INDEX IF EXISTS " + name)
    con.commit()
    con.execute("VACUUM")
    con.close()
    print("File size: %.1f MB" % (DB_PATH.stat().st_size / 1e6))


if __name__ == "__main__":
    build()
