"""Find the strangest office days with an Isolation Forest.

Run it from anywhere:

    python src/odd_days.py

How it works, in plain words:
Each office day becomes one row of numbers, such as how full the building got
and how many people left within 90 minutes. An Isolation Forest then looks for
the rows that are easiest to separate from all the others. Those are the
strange days.

The model looks at days only. It never looks at individual people.

The script uses scikit learn when it is installed. If it is not, for example
on a phone, it uses a small version written with numpy that follows the same
idea. Both give the same kind of score.
"""

import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.common import RESULTS_DIR, read_sql, save_json  # noqa: E402

FEATURES = [
    "peak_fullness",
    "hours_above_90",
    "people_badged_in",
    "declined_bookings",
    "short_visit_rate",
    "no_desk_share",
    "unknown_exit_share",
    "median_stay_minutes",
]

PHRASES = {
    "peak_fullness": ("the building got much fuller", "the building stayed much emptier"),
    "hours_above_90": (
        "the floor stayed above 90 percent full for much longer",
        "the floor was almost never close to full",
    ),
    "people_badged_in": ("far more people came in", "far fewer people came in"),
    "declined_bookings": (
        "many more desk bookings were turned down",
        "almost no desk bookings were turned down",
    ),
    "short_visit_rate": (
        "far more people left within 90 minutes",
        "far fewer people left within 90 minutes",
    ),
    "no_desk_share": (
        "far more people arrived to find no desk free",
        "almost nobody arrived to find no desk free",
    ),
    "unknown_exit_share": (
        "many more exit taps were missing",
        "fewer exit taps were missing",
    ),
    "median_stay_minutes": (
        "people stayed much longer",
        "people stayed for much less time",
    ),
}


def daily_features(db_path=None):
    """One row per office day."""
    days = read_sql("SELECT * FROM daily_summary ORDER BY work_date", db_path=db_path)
    visits = read_sql(
        "SELECT work_date, is_short, no_desk_at_arrival, all_exits_known, minutes_inside "
        "FROM day_visits",
        db_path=db_path,
    )
    grouped = visits.groupby("work_date").agg(
        short_visit_rate=("is_short", "mean"),
        no_desk_share=("no_desk_at_arrival", "mean"),
        exits_known=("all_exits_known", "mean"),
        median_stay_minutes=("minutes_inside", "median"),
    )
    grouped["unknown_exit_share"] = 1 - grouped["exits_known"]
    out = days.merge(grouped.drop(columns="exits_known"), on="work_date")
    return out.fillna(0.0)


def adjust_for_weekday(frame):
    """Subtract the usual value for that weekday, so a busy Wednesday is not
    called strange just because it is a Wednesday."""
    adjusted = frame[FEATURES].copy()
    for name in FEATURES:
        usual = frame.groupby("weekday")[name].transform("median")
        adjusted[name] = frame[name] - usual
    return adjusted


def _average_path(n):
    if n <= 1:
        return 0.0
    if n == 2:
        return 1.0
    return 2.0 * (math.log(n - 1) + 0.5772156649) - 2.0 * (n - 1) / n


class SimpleIsolationForest:
    """A small Isolation Forest in numpy. Used when scikit learn is missing."""

    def __init__(self, n_trees=300, sample_size=256, seed=42):
        self.n_trees = n_trees
        self.sample_size = sample_size
        self.seed = seed
        self.trees = []
        self.psi = 0

    def fit(self, X):
        rng = np.random.default_rng(self.seed)
        n = X.shape[0]
        self.psi = min(self.sample_size, n)
        limit = int(math.ceil(math.log2(max(self.psi, 2))))
        self.trees = []
        for _ in range(self.n_trees):
            rows = rng.choice(n, self.psi, replace=False)
            self.trees.append(self._grow(X[rows], 0, limit, rng))
        return self

    def _grow(self, X, depth, limit, rng):
        n = len(X)
        if depth >= limit or n <= 1:
            return ("leaf", n)
        column = int(rng.integers(X.shape[1]))
        low, high = X[:, column].min(), X[:, column].max()
        if low == high:
            return ("leaf", n)
        cut = rng.uniform(low, high)
        left = X[:, column] < cut
        return (
            "node",
            column,
            cut,
            self._grow(X[left], depth + 1, limit, rng),
            self._grow(X[~left], depth + 1, limit, rng),
        )

    def _path_length(self, row, node, depth=0):
        while node[0] == "node":
            node = node[3] if row[node[1]] < node[2] else node[4]
            depth += 1
        return depth + _average_path(node[1])

    def score(self, X):
        """Between 0 and 1. Higher means stranger."""
        paths = np.zeros(len(X))
        for tree in self.trees:
            for i, row in enumerate(X):
                paths[i] += self._path_length(row, tree)
        paths /= len(self.trees)
        return 2.0 ** (-paths / _average_path(self.psi))


def strangeness_scores(X, use_sklearn=True, seed=42):
    """Return (scores, name of method). Higher score means stranger."""
    if use_sklearn:
        try:
            from sklearn.ensemble import IsolationForest

            model = IsolationForest(n_estimators=500, random_state=seed)
            model.fit(X)
            return -model.score_samples(X), "scikit learn IsolationForest"
        except ImportError:
            pass
    return SimpleIsolationForest(seed=seed).fit(X).score(X), "numpy version of Isolation Forest"


def explain(adjusted, frame):
    """For each day, say in plain words what made it strange."""
    spread = {}
    for name in FEATURES:
        column = adjusted[name]
        mad = float(np.median(np.abs(column - column.median()))) * 1.4826
        spread[name] = mad if mad > 0 else (float(column.std()) or 1.0)

    reasons = []
    for i in range(len(adjusted)):
        weekday = frame.loc[i, "weekday"]
        scored = []
        for name in FEATURES:
            z = (adjusted.loc[i, name] - adjusted[name].median()) / spread[name]
            scored.append((abs(z), z, name))
        scored.sort(reverse=True)
        parts = []
        for size, z, name in scored[:2]:
            if size >= 2.0:
                high, low = PHRASES[name]
                parts.append(high if z > 0 else low)
        if parts:
            text = "Compared with a usual %s, %s." % (weekday, "; ".join(parts))
        else:
            text = "No single measure stands out. The mix of measures is unusual."
        reasons.append(text[0].upper() + text[1:])
    return reasons


def run(db_path=None, use_sklearn=True, flag_share=0.15, write=True):
    frame = daily_features(db_path)
    adjusted = adjust_for_weekday(frame)
    scores, method = strangeness_scores(adjusted.values.astype(float), use_sklearn)

    n_flag = int(math.ceil(flag_share * len(frame)))
    cutoff = np.sort(scores)[::-1][n_flag - 1]
    flagged = scores >= cutoff

    notes = read_sql("SELECT work_date, note FROM building_log", db_path=db_path)
    note_by_day = dict(zip(notes["work_date"], notes["note"]))

    result = pd.DataFrame(
        {
            "work_date": frame["work_date"],
            "weekday": frame["weekday"],
            "strangeness": np.round(scores, 3),
            "flagged": flagged,
            "reason": explain(adjusted, frame),
            "building_log_note": [note_by_day.get(d, "") for d in frame["work_date"]],
        }
    ).sort_values("strangeness", ascending=False)

    logged = int((result["building_log_note"] != "").sum())
    flagged_rows = result[result["flagged"]]
    caught = int((flagged_rows["building_log_note"] != "").sum())
    summary = {
        "method": method,
        "days_checked": int(len(frame)),
        "days_flagged": int(len(flagged_rows)),
        "days_with_a_log_note": logged,
        "flagged_days_with_a_log_note": caught,
        "share_of_flagged_days_explained_by_log": round(caught / max(len(flagged_rows), 1), 3),
        "share_of_logged_days_found": round(caught / max(logged, 1), 3),
    }

    if write:
        RESULTS_DIR.mkdir(exist_ok=True)
        result.to_csv(RESULTS_DIR / "odd_days.csv", index=False)
        save_json("odd_days_summary.json", summary)
    return result, summary


if __name__ == "__main__":
    table, info = run(use_sklearn="--no-sklearn" not in sys.argv)
    print("Method:", info["method"])
    print(
        "Flagged %d of %d days. %d of the flagged days have a building log note."
        % (info["days_flagged"], info["days_checked"], info["flagged_days_with_a_log_note"])
    )
    print(table[table["flagged"]][["work_date", "weekday", "strangeness", "building_log_note"]].to_string(index=False))
