"""Replay a Day: watch one office day fill up, step by step."""

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.common import RESULTS_DIR, nice_date, read_sql  # noqa: E402

st.set_page_config(page_title="Replay a Day", layout="centered")


@st.cache_data
def load_days():
    summary = read_sql(
        "SELECT work_date, weekday, desks_available, peak_inside, people_badged_in "
        "FROM daily_summary ORDER BY work_date"
    )
    odd = pd.read_csv(RESULTS_DIR / "odd_days.csv").fillna("")
    odd = odd[["work_date", "strangeness", "flagged", "reason", "building_log_note"]]
    return summary.merge(odd, on="work_date", how="left")


@st.cache_data
def load_slots(day):
    return read_sql(
        "SELECT slot_start, people_inside, desks_available FROM occupancy_15min "
        "WHERE work_date = ? ORDER BY slot_start",
        (day,),
    )


@st.cache_data
def load_visits(day):
    return read_sql(
        "SELECT first_in, last_out, is_short, no_desk_at_arrival FROM day_visits WHERE work_date = ?",
        (day,),
    )


days = load_days()

st.title("Replay a Day")
st.write(
    "Pick a day, then move the clock. The line grows as the day goes on, and you can see "
    "when the desks run out. This page shows counts only. No individual person is shown."
)

which = st.radio("Which days?", ["Strange days", "All days"], horizontal=True)
if which == "Strange days":
    options = days[days["flagged"].astype(str) == "True"].sort_values("strangeness", ascending=False)
else:
    options = days
dates = options["work_date"].tolist()
day = st.selectbox("Day", dates, format_func=nice_date)

row = days[days["work_date"] == day].iloc[0]
slots = load_slots(day)
visits = load_visits(day)

labels = [text[11:16] for text in slots["slot_start"]]
start_value = "09:00" if "09:00" in labels else labels[0]
clock = st.select_slider("Time of day", options=labels, value=start_value)
position = labels.index(clock)
now = day + " " + clock + ":00"

inside_now = int(slots.loc[position, "people_inside"])
desks = int(slots.loc[position, "desks_available"])

series = slots["people_inside"].astype(float).to_numpy().copy()
series[position + 1:] = np.nan
chart = pd.DataFrame(
    {"People inside": series, "Desks": float(desks)},
    index=labels,
)
chart.index.name = "Time of day"
st.line_chart(chart)

arrived = visits[visits["first_in"] <= now]
left_early = visits[(visits["is_short"] == 1) & (visits["last_out"].notna()) & (visits["last_out"] <= now)]
no_desk = arrived[arrived["no_desk_at_arrival"] == 1]

if inside_now >= desks:
    status = "There are no free desks."
else:
    status = "%d desks are free." % (desks - inside_now)
st.write("At %s there were %d people inside and %d desks. %s" % (clock, inside_now, desks, status))

left, right = st.columns(2)
left.metric("Arrived so far", len(arrived))
right.metric("Arrived to no free desk", len(no_desk))
left.metric("People inside now", inside_now)
right.metric("Left within 90 minutes so far", len(left_early))

st.subheader(nice_date(day))
if row["flagged"] is True or str(row["flagged"]) == "True":
    st.write("The model flagged this as a strange day. " + str(row["reason"]))
else:
    st.write("The model did not flag this day as strange.")
if str(row["building_log_note"]) != "":
    st.info("Building log: %s The model never saw this note." % row["building_log_note"])
st.caption(
    "Peak headcount %d, people who badged in %d, desks available %d."
    % (row["peak_inside"], row["people_badged_in"], row["desks_available"])
)
