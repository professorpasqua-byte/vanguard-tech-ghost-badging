"""Find how full the office gets before people start leaving early.

Run it from anywhere:

    python src/tipping_point.py

The question: when someone badges in and leaves within 90 minutes, did they
choose to, or did the floor feel too full?

The idea, in plain words:
* On calm days some people leave early by choice. That gives a steady base rate.
* When the floor gets close to full, the early leavers rise sharply.
* The extra early leavers above the base rate are the ones the crowd pushed out.

The script fits a simple shape to the data: a flat base rate that climbs to a
higher level between two fullness values. It repeats the fit 300 times on
resampled days to show how sure it is. At the end it grades itself against the
hidden truth stored in the database. The fit never looks at that truth.
"""

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.common import read_sql, save_json  # noqa: E402

BIN = 0.02
N_BINS = 80                      # fullness from 0.00 to 1.60
START_GRID = np.round(np.arange(0.50, 1.21, 0.01), 2)
WIDTH_GRID = [0.05, 0.10, 0.15, 0.20, 0.30]
BOOTSTRAPS = 300


def ramp(x, start, width):
    """0 below start, 1 above start plus width, and a straight climb between."""
    return np.clip((np.asarray(x, dtype=float) - start) / width, 0.0, 1.0)


def load_visits(db_path=None):
    return read_sql(
        "SELECT employee_id, work_date, fullness_at_arrival, is_short, no_desk_at_arrival "
        "FROM day_visits "
        "WHERE is_short IS NOT NULL AND fullness_at_arrival IS NOT NULL",
        db_path=db_path,
    )


def count_by_day_and_bin(visits):
    """Two tables, days by fullness bins: visits, and short visits."""
    codes, days = pd.factorize(visits["work_date"])
    clipped = np.clip(visits["fullness_at_arrival"].values, 0, N_BINS * BIN - 1e-6)
    bins = (clipped / BIN).astype(int)
    visits_table = np.zeros((len(days), N_BINS))
    short_table = np.zeros((len(days), N_BINS))
    np.add.at(visits_table, (codes, bins), 1)
    np.add.at(short_table, (codes, bins), visits["is_short"].values)
    return visits_table, short_table


def fit_ramp(visit_counts, short_counts):
    """Best base rate, jump, start and width. Returns a dict or None."""
    centers = (np.arange(N_BINS) + 0.5) * BIN
    keep = visit_counts > 0
    x_centers = centers[keep]
    n = visit_counts[keep]
    y = short_counts[keep] / n
    sw = n.sum()
    swy = (n * y).sum()

    best = None
    for width in WIDTH_GRID:
        for start in START_GRID:
            x = ramp(x_centers, start, width)
            swx = (n * x).sum()
            swxx = (n * x * x).sum()
            swxy = (n * x * y).sum()
            det = sw * swxx - swx * swx
            if det <= 1e-9:
                continue
            jump = (sw * swxy - swx * swy) / det
            base = (swy - jump * swx) / sw
            if jump <= 0:
                continue
            error = (n * (y - base - jump * x) ** 2).sum()
            if best is None or error < best["error"]:
                best = {
                    "error": float(error),
                    "base_rate": float(base),
                    "jump": float(jump),
                    "start": float(start),
                    "width": float(width),
                    "tipping_fullness": float(start + width / 2.0),
                }
    return best


def forced_share(fit, visit_counts, short_counts):
    """Estimated share of all short visits that the crowd pushed out."""
    centers = (np.arange(N_BINS) + 0.5) * BIN
    extra = fit["jump"] * ramp(centers, fit["start"], fit["width"])
    pushed_out = float((visit_counts * extra).sum())
    return min(pushed_out / max(float(short_counts.sum()), 1.0), 1.0)


def bootstrap(visits_table, short_table, seed=7):
    rng = np.random.default_rng(seed)
    n_days = visits_table.shape[0]
    tips, shares = [], []
    for _ in range(BOOTSTRAPS):
        pick = rng.integers(0, n_days, n_days)
        v = visits_table[pick].sum(axis=0)
        s = short_table[pick].sum(axis=0)
        fit = fit_ramp(v, s)
        if fit is None:
            continue
        tips.append(fit["tipping_fullness"])
        shares.append(forced_share(fit, v, s))
    return np.array(tips), np.array(shares)


def period_table(visits, db_path=None):
    """Compare the weeks before, during and after the partial floor closure."""
    capacity = read_sql("SELECT work_date, desks_available FROM building_capacity ORDER BY work_date", db_path=db_path)
    normal = capacity["desks_available"].max()
    closed_days = capacity.loc[capacity["desks_available"] < normal, "work_date"]
    first_closed, last_closed = closed_days.min(), closed_days.max()

    def label(day):
        if day < first_closed:
            return "Before the closure"
        if day <= last_closed:
            return "Floor partly closed"
        return "After the closure"

    all_days = read_sql("SELECT work_date, no_desk_at_arrival FROM day_visits", db_path=db_path)
    all_days["period"] = all_days["work_date"].map(label)
    visits = visits.copy()
    visits["period"] = visits["work_date"].map(label)

    rows = []
    for name in ["Before the closure", "Floor partly closed", "After the closure"]:
        subset = visits[visits["period"] == name]
        everyone = all_days[all_days["period"] == name]
        desks = capacity.loc[capacity["work_date"].map(label) == name, "desks_available"]
        rows.append(
            {
                "period": name,
                "office_days": int(len(desks)),
                "desks": int(desks.iloc[0]),
                "person_days": int(len(everyone)),
                "short_visit_rate": round(float(subset["is_short"].mean()), 3),
                "arrived_to_no_desk": round(float(everyone["no_desk_at_arrival"].mean()), 3),
            }
        )
    return rows


def display_bins(visits, width=0.05, minimum=40):
    """Coarser bins, for the chart on the dashboard."""
    frame = visits.copy()
    frame["bin"] = (np.clip(frame["fullness_at_arrival"], 0, 1.5) // width) * width + width / 2
    grouped = frame.groupby("bin").agg(visits=("is_short", "size"), short_rate=("is_short", "mean")).reset_index()
    grouped = grouped[grouped["visits"] >= minimum]
    return [
        {"fullness": round(float(r.bin), 3), "short_rate": round(float(r.short_rate), 3), "visits": int(r.visits)}
        for r in grouped.itertuples()
    ]


def grade(fit, estimated_share, db_path=None):
    """Compare the answer with the hidden truth. Only used for grading."""
    settings = read_sql("SELECT name, value FROM truth_settings", db_path=db_path)
    truth = dict(zip(settings["name"], settings["value"]))
    reasons = read_sql(
        "SELECT g.true_reason AS reason, COUNT(*) AS n "
        "FROM day_visits d JOIN ground_truth g "
        "  ON g.employee_id = d.employee_id AND g.work_date = d.work_date "
        "WHERE d.is_short = 1 GROUP BY g.true_reason",
        db_path=db_path,
    )
    counts = dict(zip(reasons["reason"], reasons["n"]))
    total = max(sum(counts.values()), 1)
    true_share = counts.get("forced", 0) / total
    return {
        "true_tipping_fullness": float(truth["tipping_fullness"]),
        "estimated_tipping_fullness": round(fit["tipping_fullness"], 3),
        "true_forced_share_of_short_visits": round(true_share, 3),
        "estimated_forced_share_of_short_visits": round(estimated_share, 3),
        "short_visits_by_true_reason": {k: int(v) for k, v in counts.items()},
    }


def run(db_path=None, write=True):
    visits = load_visits(db_path)
    visits_table, short_table = count_by_day_and_bin(visits)
    total_visits = visits_table.sum(axis=0)
    total_short = short_table.sum(axis=0)

    fit = fit_ramp(total_visits, total_short)
    if fit is None:
        raise RuntimeError("No tipping point found in this data.")
    share = forced_share(fit, total_visits, total_short)
    tips, shares = bootstrap(visits_table, short_table)

    result = {
        "person_days_used": int(len(visits)),
        "short_visit_rate": round(float(visits["is_short"].mean()), 3),
        "base_rate": round(fit["base_rate"], 3),
        "jump": round(fit["jump"], 3),
        "ramp_start": round(fit["start"], 3),
        "ramp_width": round(fit["width"], 3),
        "tipping_fullness": round(fit["tipping_fullness"], 3),
        "tipping_low": round(float(np.percentile(tips, 5)), 3),
        "tipping_high": round(float(np.percentile(tips, 95)), 3),
        "forced_share": round(share, 3),
        "forced_share_low": round(float(np.percentile(shares, 5)), 3),
        "forced_share_high": round(float(np.percentile(shares, 95)), 3),
        "periods": period_table(visits, db_path),
        "bins": display_bins(visits),
        "grade": grade(fit, share, db_path),
    }
    if write:
        save_json("tipping_point.json", result)
    return result


if __name__ == "__main__":
    out = run()
    print("Person days used:        ", out["person_days_used"])
    print("Short visit rate:        ", out["short_visit_rate"])
    print("Base rate on calm days:  ", out["base_rate"])
    print("Tipping point (fullness):", out["tipping_fullness"], "range", out["tipping_low"], "to", out["tipping_high"])
    print("Pushed out share:        ", out["forced_share"], "range", out["forced_share_low"], "to", out["forced_share_high"])
    print("Grade against the truth: ", out["grade"])
    for row in out["periods"]:
        print(row)
