"""Vanguard Tech: Ghost Badging. Home page of the dashboard.

Run it with:  streamlit run app.py

The other two pages live in the pages folder and show up in the side menu.
"""

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parent))
from src.common import RESULTS_DIR, load_json, nice_date, percent, read_sql  # noqa: E402

st.set_page_config(page_title="Vanguard Tech: Ghost Badging", layout="centered")


@st.cache_data
def get_tipping():
    return load_json("tipping_point.json")


@st.cache_data
def get_odd_days():
    return pd.read_csv(RESULTS_DIR / "odd_days.csv").fillna("")


@st.cache_data
def get_odd_summary():
    return load_json("odd_days_summary.json")


@st.cache_data
def get_checks():
    return read_sql(
        'SELECT check_name AS "What was checked", count_value AS "Count", note AS "Meaning" FROM dq_report'
    )


@st.cache_data
def get_people_sample():
    return read_sql(
        'SELECT employee_id AS "ID", first_name AS "First name", last_name AS "Last name", team AS "Team" '
        "FROM employees ORDER BY employee_id"
    )


@st.cache_data
def get_messy_taps():
    return read_sql(
        'SELECT event_time AS "Time", \'[\' || employee_id || \']\' AS "Employee ID in the raw data", '
        'direction AS "Direction", reader_id AS "Reader" '
        "FROM badge_events_raw "
        "WHERE direction <> UPPER(direction) OR employee_id <> TRIM(employee_id) "
        "ORDER BY event_id LIMIT 8"
    )


def show_table(frame):
    try:
        st.dataframe(frame, hide_index=True)
    except TypeError:
        st.dataframe(frame)


def link(path, label):
    try:
        st.page_link(path, label=label)
    except Exception:
        st.write(label)


tip = get_tipping()
odd = get_odd_days()
odd_info = get_odd_summary()
periods = {row["period"]: row for row in tip["periods"]}
before = periods["Before the closure"]
during = periods["Floor partly closed"]
after = periods["After the closure"]
grade = tip["grade"]

st.title("Vanguard Tech: The Ghost Badging Problem")
st.subheader("When people badge in and leave within the hour, did they choose to, or did the office run out of desks?")
st.info(
    "Vanguard Tech is a made up company. Ghost badging is the name used inside it. "
    "The real world name is coffee badging. All data here is synthetic."
)

st.write(
    "Vanguard Tech has 500 employees and 300 desks. In June 2026 it asked everyone to come in "
    "five days a week. Over 12 weeks the building recorded every badge tap, every desk booking "
    "and how full the floor was. Managers noticed that many people tapped in and left soon after. "
    "The usual reaction is to blame the workers. This project asks if the crowded floor played a part."
)

st.header("The short version")
c1, c2, c3 = st.columns(3)
c1.metric("Left within 90 minutes", percent(tip["short_visit_rate"]))
c2.metric("Tipping point", percent(tip["tipping_fullness"], 1) + " full")
c3.metric("Pushed out by a full floor", percent(tip["forced_share"]))
st.caption(
    "Tipping point range: %s to %s. Share pushed out range: %s to %s. "
    "The share is the part of all short visits that the model puts down to a crowded floor."
    % (
        percent(tip["tipping_low"], 1),
        percent(tip["tipping_high"], 1),
        percent(tip["forced_share_low"]),
        percent(tip["forced_share_high"]),
    )
)

st.header("Where people start to leave")
st.write(
    "Each point below is a group of people who arrived when the building was about this full. "
    "On calm days around %s of visits are short. That is the base rate, and it is the part people "
    "choose. Close to %s full, the rate climbs fast." % (percent(tip["base_rate"]), percent(tip["tipping_fullness"]))
)
bins = pd.DataFrame(tip["bins"])
chart = pd.DataFrame(
    {
        "Left within 90 minutes (%)": (bins["short_rate"] * 100).round(1).values,
        "Base rate on calm days (%)": round(tip["base_rate"] * 100, 1),
    },
    index=(bins["fullness"] * 100).round(0).astype(int).values,
)
chart.index.name = "How full the building was when they arrived (% of desks)"
st.line_chart(chart)
st.caption("Over 100% means more people were inside than there are desks.")

st.header("The floor closure test")
st.write(
    "For two weeks, part of floor 4 was closed and 60 desks went out of service. The same kind of people "
    "came in, but the short visit rate rose from %s to %s and the share arriving to no free desk went from "
    "%s to %s. After the desks came back, the short visit rate returned to %s."
    % (
        percent(before["short_visit_rate"]),
        percent(during["short_visit_rate"]),
        percent(before["arrived_to_no_desk"]),
        percent(during["arrived_to_no_desk"]),
        percent(after["short_visit_rate"]),
    )
)
table = pd.DataFrame(tip["periods"])
table = table.rename(
    columns={
        "period": "Period",
        "office_days": "Office days",
        "desks": "Desks",
        "person_days": "Person days",
        "short_visit_rate": "Left within 90 min",
        "arrived_to_no_desk": "Arrived to no desk",
    }
)
table["Left within 90 min"] = table["Left within 90 min"].map(percent)
table["Arrived to no desk"] = table["Arrived to no desk"].map(percent)
show_table(table)

st.header("Strange days")
st.write(
    "An Isolation Forest model looked at each office day, not at people, and picked out the days that "
    "did not look like the rest. It flagged %d of %d days. The last column is the building log. "
    "The model never saw it."
    % (odd_info["days_flagged"], odd_info["days_checked"])
)
flagged = odd[odd["flagged"].astype(str) == "True"].copy()
flagged["Day"] = flagged["work_date"].map(nice_date)
flagged = flagged.rename(
    columns={"strangeness": "Score", "reason": "What stood out", "building_log_note": "Building log says"}
)
show_table(flagged[["Day", "Score", "What stood out", "Building log says"]])
st.caption(
    "%d of the %d flagged days have a note in the building log. The model found %d of the %d days that have a note."
    % (
        odd_info["flagged_days_with_a_log_note"],
        odd_info["days_flagged"],
        odd_info["flagged_days_with_a_log_note"],
        odd_info["days_with_a_log_note"],
    )
)

st.header("Explore")
link("pages/1_Replay_a_Day.py", "Replay a Day: watch one day fill up, hour by hour")
link("pages/2_Desk_Planner.py", "Desk Planner: how many desks keep early leaving low")

st.header("How well did it work?")
st.write(
    "Because the data is made up, the real answer is known, so the analysis can be graded. "
    "The model put the tipping point at %s. The real value is %s. It estimated that %s of short visits were "
    "pushed out by a full floor. The real figure is %s."
    % (
        percent(grade["estimated_tipping_fullness"], 1),
        percent(grade["true_tipping_fullness"], 1),
        percent(grade["estimated_forced_share_of_short_visits"]),
        percent(grade["true_forced_share_of_short_visits"]),
    )
)
st.write(
    "The pushed out share comes out a little low. When the floor is full, some people who would have left "
    "anyway are pushed out first, and a method that only sees the base rate cannot separate them. "
    "Treat the figure as a careful minimum."
)

st.header("A peek at the data")
st.write(
    "These are the people in the dataset. The names are fake. They were added only to make the table feel "
    "real, and the analysis never uses them. Everyone is tracked by ID."
)
people = get_people_sample().dropna(axis=1, how="all")
show_table(people)
st.write(
    "And these are some raw badge taps, before cleaning. The square brackets show stray spaces in the ID, "
    "and the direction is sometimes in lower case. The SQL fixes both."
)
show_table(get_messy_taps())

st.header("Data checks")
st.write("The raw badge data was messy on purpose, as real data is. These are the checks the SQL ran.")
show_table(get_checks())

st.header("Limits")
st.write(
    "The data is synthetic, and the pushed out effect was built into it. That means this project shows that the "
    "method works. It does not show that real offices behave this way. Exit taps go missing more often for quick "
    "visits, so the short visit rate is probably a little low. Early arrivals see a calmer floor and late arrivals "
    "see a crowded one, so fullness and arrival time are tied together. This page shows counts only. "
    "No individual person is ever shown."
)
st.caption("Built with Python, SQLite, pandas, numpy, scikit learn, Faker and Streamlit.")
