"""Add fake names to the employees table, using Faker.

Run it from anywhere, after building the database:

    python src/add_names.py

The names are only there so the table feels like real people. The analysis
never reads them, and the dashboard results show counts only.

Faker is not needed for anything else in this project. If it is not installed,
this script tells you how to install it and stops.
"""

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.common import DB_PATH  # noqa: E402

# A mix of locales, so the names do not look like a plain US list.
LOCALES = [
    "en_GB", "en_IN", "en_CA", "en_AU", "en_IE",
    "de_DE", "es_ES", "fr_FR", "it_IT", "pt_BR", "pl_PL", "nl_NL",
]
SEED = 20261012


def add_names(db_path=None, seed=SEED):
    """Fill first_name and last_name for every employee. Returns how many."""
    try:
        from faker import Faker
    except ImportError:
        print("Faker is not installed. Run this first:  pip install faker")
        return 0

    fake = Faker(LOCALES)
    Faker.seed(seed)

    con = sqlite3.connect(str(db_path or DB_PATH))
    ids = [row[0] for row in con.execute("SELECT employee_id FROM employees ORDER BY employee_id")]

    used = set()
    rows = []
    for employee_id in ids:
        for _ in range(100):
            first, last = fake.first_name(), fake.last_name()
            if (first, last) not in used:
                break
        used.add((first, last))
        rows.append((first, last, employee_id))

    con.executemany("UPDATE employees SET first_name = ?, last_name = ? WHERE employee_id = ?", rows)
    con.commit()
    con.close()
    return len(rows)


if __name__ == "__main__":
    count = add_names()
    if count:
        con = sqlite3.connect(str(DB_PATH))
        print("Added names for %d employees. A few of them:" % count)
        for row in con.execute(
            "SELECT employee_id, first_name, last_name, team FROM employees WHERE rowid % 100 = 1"
        ):
            print("  %s  %s %s  (%s)" % row)
        con.close()
