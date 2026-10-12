# Vanguard Tech: The Ghost Badging Problem

**When people badge in and leave within the hour, did they choose to, or did the office run out of desks?**


## What happened in the real world

Companies that ordered people back to the office found that many workers had a trick. They tapped their badge, grabbed a coffee, said hello, and went home to do the real work. The trick is called coffee badging. Owl Labs, which surveys hybrid workers, reported in 2023 that 58% of them admitted to it. Source: [CFO.com](https://www.cfo.com/news/workplace-trend-58-of-hybrid-employees-are-coffee-badging/696635/).

Some companies answered with tracking. In August 2025, Samsung began tracking office attendance for some US staff in its semiconductor business, and the move was reported as a way to stop coffee badging. Sources: [Fast Company](https://www.fastcompany.com/91381406/samsung-is-tracking-employee-office-attendance) and [HR Grapevine](https://www.hrgrapevine.com/us/content/article/2025-08-07-samsung-orders-five-day-rto-for-some-us-staff-has-a-plan-to-stop-them-coffee-badging).

But there is another side to the story. Some companies did not have space for everyone they called back. In January 2025, some Amazon workers found there were not enough desks and no parking after the company's return to office rule began ([Slashdot, citing the New York Post](https://tech.slashdot.org/story/25/01/20/0516216/)). The problem is still going on. In September 2026, Money.ca reported that Canada's federal government could not yet fit about 34,000 employees in the office four days a week, because there was not enough space. The rule had started on July 6, 2026. Source: [Money.ca](https://money.ca/employment/federal-return-to-office-desk-space-shortage).

So when someone taps in and leaves early, there are two very different explanations. They chose to leave, or there was nowhere to sit. The badge data looks the same either way. This project builds a made up company to see if the data can tell the two apart.

## The made up company

Vanguard Tech has 500 employees and 300 desks. Inside the company, leaving soon after badging in is called ghost badging. The real world name is coffee badging. On Monday, June 1, 2026, it started a five day office rule. This project follows the next 12 weeks.

Three things make the story more realistic:

* The desk booking system accepts about 10% more bookings than there are desks, because some people never show up.
* In weeks 7 and 8, part of floor 4 is closed and 60 desks go out of service.
* Three one off days happen: a fire drill, a company offsite, and a day when the badge reader fault loses many exit taps.

All of it is synthetic. Nobody in it is real.

## The idea behind the analysis

Some people leave early by choice. That gives a steady base rate on calm days. If a crowded floor pushes more people out, the early leavers should rise sharply once the building gets close to full. The extra early leavers above the base rate are the ones the crowd pushed out.

The psychology that guided the design:

* **Person environment fit.** People stay engaged when the workplace gives them what they need to work. A missing desk is a gap in a very basic need.
* **Job Demands Resources model** (Arnold Bakker and Evangelia Demerouti). A rule that demands presence, without the resources to do the work, leads people to pull back. A desk is a basic resource.
* **Psychological reactance** (Jack Brehm). When a rule takes away freedom, people often look for small ways to take some of it back. Coffee badging can be one of those small ways.

These ideas shaped what was measured. They are not proven by this data.

## How it is built

Most data projects are a few CSV files and a notebook. This one is different. All the data lives in one SQLite database, `vanguard.db`, and the cleaning is done in SQL.

* `src/build_database.py` simulates the 12 weeks and loads the raw tables. About 42,000 badge taps, 20,000 desk bookings and 500 employees go in.
* `src/add_names.py` adds fake names to the employees table with Faker. The names are only for realism. The analysis never reads them.
* `sql/01_schema.sql` creates the raw tables.
* `sql/02_pair_taps.sql` cleans the taps and matches each tap in to its tap out. It fixes upper and lower case, trims stray spaces, removes double taps, and handles missing taps.
* `sql/03_occupancy.sql` counts how many people are inside every 15 minutes and builds a summary for each day.
* `sql/04_short_visits.sql` builds one row per person per day. It marks a short visit (under 90 minutes) and records how full the building was when the person arrived.
* `src/odd_days.py` uses an Isolation Forest to find the strangest office days.
* `src/tipping_point.py` finds how full the floor gets before people start leaving early, and grades itself.
* `tests/` has 15 tests that check the SQL matching and the models.
* `app.py` and the `pages` folder make up the dashboard.

The analysis never picks out or lists a person. The strange days model works on days, not people, and the dashboard shows counts only.

## What the analysis found

About 23% of person days were short visits. On calm days the rate stays near 13%. That is the part people choose. When the floor reaches about 89.5% full, the rate climbs fast, and above 100% full more than half of arrivals leave within 90 minutes. The tipping point range is 89.0% to 90.5%.

The model estimates that about 43% of all short visits were pushed out by a full floor, with a range of 37% to 47%.

The closure weeks give a second check. The same kind of people came in, but for two weeks the building had 60 fewer desks. The short visit rate rose from 22% to 29%, and the share of people arriving to no free desk went from 12% to 25%. When the desks came back, the short visit rate went back to 22%.

The Isolation Forest flagged 9 of the 60 days. All 9 have a note in the building log, such as the offsite, the fire drill, the reader fault or the floor closure. The model never saw the log. It found 9 of the 13 days that have a note.

## How the project grades itself

The data is made up, so the true answer is known. It sits in a separate table that the analysis never reads while it works. At the end, the script compares its answers with the truth.

* The true tipping point is 90.0% full. The model found 89.5%.
* The true share of short visits pushed out is 50%. The model estimated 43%.

The estimate is a little low. When the floor is full, some people who would have left anyway are pushed out first, and the method cannot tell those apart. So read the 43% as a careful minimum.

## Limits

* The data is synthetic and the crowd effect was built in. This shows that the method works. It does not show that real offices behave this way.
* Exit taps go missing more often for quick visits, so the short visit rate is probably a little low.
* The floor is calm early in the day and crowded later, so fullness and arrival time are tied together.
* A visit with no exit tap is assumed to last 8 hours when counting people inside. That is a guess.
* The psychology ideas guided the design. They are not tested here.

## Run it yourself

```bash
pip install -r requirements.txt
streamlit run app.py
```

To rebuild everything from scratch:

```bash
python src/build_database.py
python src/add_names.py
python src/odd_days.py
python src/tipping_point.py
python -m unittest discover -s tests -v
```

`add_names.py` needs Faker (`pip install faker`). The dashboard only needs streamlit, pandas and numpy. The strange days script uses scikit learn if it is installed (`pip install scikit-learn`). If not, it uses a small numpy version of the same idea, so it also runs on a phone.

## Repo map

```
vanguard_tech/
├── app.py                      home page of the dashboard
├── pages/
│   ├── 1_Replay_a_Day.py       watch one day fill up
│   └── 2_Desk_Planner.py       desks needed to keep early leaving low
├── sql/                        schema, cleaning, fullness, short visits
├── src/
│   ├── build_database.py       simulate the data and build vanguard.db
│   ├── add_names.py            adds fake names with Faker
│   ├── odd_days.py             Isolation Forest on office days
│   ├── tipping_point.py        how full before people leave
│   └── common.py               small shared helpers
├── tests/                      15 tests
├── results/                    small result files the app reads
├── vanguard.db                 the SQLite database
├── DATA_DICTIONARY.md
├── requirements.txt
└── README.md
```

## What is real and what is not

Vanguard Tech, its employees (the names come from Faker), and every figure from the analysis are synthetic. The real parts are the events in the first section. No real person's data, badge logs or employment history appears anywhere in this project.

---

**Nwafor Martins**, People Analytics Engineer & I-O Psychology Consultant
[Email](mailto:nwaforchubby@gmail.com)
