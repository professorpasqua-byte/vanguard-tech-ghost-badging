"""Desk Planner: how many desks keep early leaving low."""

import math
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.common import load_json, percent, read_sql  # noqa: E402

st.set_page_config(page_title="Desk Planner", layout="centered")

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]


@st.cache_data
def load_tipping():
    return load_json("tipping_point.json")


@st.cache_data
def load_days():
    return read_sql(
        "SELECT work_date, weekday, desks_available, peak_inside, peak_fullness, people_badged_in "
        "FROM daily_summary"
    )


def show_table(frame):
    try:
        st.dataframe(frame, hide_index=True)
    except TypeError:
        st.dataframe(frame)


tip = load_tipping()
days = load_days()
normal_desks = int(days["desks_available"].max())
normal = days[days["desks_available"] == normal_desks]

st.title("Desk Planner")
st.write(
    "The Replay page shows what happened. This page asks what to do about it. "
    "Pick how many extra early leavers you can accept because of a crowded floor, "
    "and the planner works out how many desks that needs."
)

extra_points = st.radio(
    "Extra early leavers you can accept, caused by crowding",
    [1, 2, 3, 5],
    format_func=lambda n: "%d out of every 100 visits" % n,
    horizontal=True,
)
target = extra_points / 100.0

# The fitted curve says extra early leavers = jump * ramp(fullness).
# Solve for the fullness where the extra reaches the target.
safe_fullness = tip["ramp_start"] + tip["ramp_width"] * target / tip["jump"]

# On calm days, this share of the day's visitors is inside at the busiest moment.
calm = normal[(normal["peak_fullness"] < 0.85) & (normal["people_badged_in"] > 150)]
if len(calm) > 0:
    busiest_share = float((calm["peak_inside"] / calm["people_badged_in"]).mean())
else:
    busiest_share = 0.9

rows = []
for name in WEEKDAYS:
    part = normal[normal["weekday"] == name]
    if part.empty:
        continue
    visitors = float(part["people_badged_in"].mean())
    busiest = visitors * busiest_share
    needed = int(math.ceil(busiest / safe_fullness))
    rows.append(
        {
            "Weekday": name,
            "Typical visitors": int(round(visitors)),
            "Inside at the busiest moment": int(round(busiest)),
            "Desks needed": needed,
            "Desks today": normal_desks,
            "Gap": needed - normal_desks,
        }
    )
plan = pd.DataFrame(rows)

booking_cap = int(math.floor(normal_desks * safe_fullness / busiest_share))

a, b = st.columns(2)
a.metric("Safe fullness at arrival", percent(safe_fullness, 1))
b.metric("Visitors per day the current desks can take", booking_cap)

st.subheader("Desks needed by weekday")
show_table(plan)
st.caption("A positive gap means more desks are needed than the building has today.")

st.subheader("Another way to read it")
st.write(
    "If you cannot add desks, cap daily bookings near %d, or spread visitors across more days. "
    "Based on the typical days above, the busiest days (%s) bring more people than that."
    % (
        booking_cap,
        ", ".join(plan.loc[plan["Typical visitors"] > booking_cap, "Weekday"].tolist()) or "none",
    )
)

st.subheader("How this is worked out")
st.write(
    "1. The tipping point analysis gives a curve: a base rate of early leavers on calm days, "
    "and an extra amount that climbs as the floor fills.  \n"
    "2. Your chosen target sets the fullness where that extra amount reaches the target.  \n"
    "3. On calm days about %s of a day's visitors are inside at the busiest moment. "
    "That share turns typical visitors into a busiest headcount.  \n"
    "4. Desks needed is that headcount divided by the safe fullness." % percent(busiest_share)
)
st.caption(
    "This is an estimate from synthetic data. If more desks were added, the people who now leave "
    "would stay, so real demand at the busiest moment may be a little higher than shown."
)
