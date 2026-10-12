"""Small helpers shared by the scripts and the app.

Nothing in here needs Streamlit, so the scripts and tests can use it too.
"""

import datetime as dt
import json
import sqlite3
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "vanguard.db"
RESULTS_DIR = ROOT / "results"


def read_sql(sql, params=(), db_path=None):
    """Run a query and return a DataFrame."""
    path = Path(db_path) if db_path else DB_PATH
    con = sqlite3.connect(str(path))
    try:
        return pd.read_sql_query(sql, con, params=params)
    finally:
        con.close()


def load_json(name):
    with open(RESULTS_DIR / name) as handle:
        return json.load(handle)


def save_json(name, data):
    RESULTS_DIR.mkdir(exist_ok=True)
    with open(RESULTS_DIR / name, "w") as handle:
        json.dump(data, handle, indent=2)


def nice_date(iso_text):
    """2026-06-01 becomes Mon 1 Jun."""
    day = dt.date.fromisoformat(str(iso_text)[:10])
    return "%s %d %s" % (day.strftime("%a"), day.day, day.strftime("%b"))


def percent(value, digits=0):
    return "%.*f%%" % (digits, float(value) * 100)
