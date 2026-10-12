"""Tests for the strange days detector and the tipping point fit.

Run from the project folder:

    python -m unittest discover -s tests -v
"""

import random
import sqlite3
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src import add_names, odd_days, tipping_point  # noqa: E402


class StrangeDaysTests(unittest.TestCase):
    def test_numpy_forest_scores_an_obvious_outlier_highest(self):
        rng = np.random.default_rng(1)
        crowd = rng.normal(0, 1, size=(59, 3))
        data = np.vstack([crowd, [[12.0, 12.0, 12.0]]])
        scores = odd_days.SimpleIsolationForest(seed=3).fit(data).score(data)
        self.assertEqual(int(np.argmax(scores)), 59)
        self.assertTrue(0.0 < scores.min() < scores.max() < 1.0)

    def test_scores_work_with_or_without_scikit_learn(self):
        rng = np.random.default_rng(2)
        data = np.vstack([rng.normal(0, 1, size=(40, 2)), [[9.0, 9.0]]])
        for use_sklearn in (True, False):
            scores, method = odd_days.strangeness_scores(data, use_sklearn=use_sklearn)
            self.assertEqual(int(np.argmax(scores)), 40, method)


class TippingPointTests(unittest.TestCase):
    def make_tables(self):
        """Twenty days. Short visit rate is 10 percent until fullness 0.8,
        then climbs to 55 percent by fullness 1.0."""
        n_days, n_bins = 20, tipping_point.N_BINS
        centers = (np.arange(n_bins) + 0.5) * tipping_point.BIN
        rate = 0.10 + 0.45 * tipping_point.ramp(centers, 0.8, 0.2)
        visits = np.zeros((n_days, n_bins))
        visits[:, :75] = 40
        shorts = np.round(visits * rate)
        return visits, shorts

    def test_ramp_shape(self):
        values = tipping_point.ramp([0.0, 0.8, 0.9, 1.0, 1.4], 0.8, 0.2)
        self.assertEqual(list(np.round(values, 2)), [0.0, 0.0, 0.5, 1.0, 1.0])

    def test_fit_recovers_the_tipping_point(self):
        visits, shorts = self.make_tables()
        fit = tipping_point.fit_ramp(visits.sum(axis=0), shorts.sum(axis=0))
        self.assertIsNotNone(fit)
        self.assertAlmostEqual(fit["tipping_fullness"], 0.9, delta=0.04)
        self.assertAlmostEqual(fit["base_rate"], 0.10, delta=0.02)

    def test_flat_data_has_no_tipping_point_effect(self):
        n_days, n_bins = 20, tipping_point.N_BINS
        visits = np.zeros((n_days, n_bins))
        visits[:, :75] = 40
        shorts = np.round(visits * 0.12)
        fit = tipping_point.fit_ramp(visits.sum(axis=0), shorts.sum(axis=0))
        if fit is not None:
            share = tipping_point.forced_share(fit, visits.sum(axis=0), shorts.sum(axis=0))
            self.assertLess(share, 0.05)


class AddNamesTests(unittest.TestCase):
    def make_db(self, n=50):
        handle = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        handle.close()
        con = sqlite3.connect(handle.name)
        con.executescript((ROOT / "sql" / "01_schema.sql").read_text())
        con.executemany(
            "INSERT INTO employees (employee_id, team) VALUES (?, 'Test')",
            [("E%04d" % i,) for i in range(1, n + 1)],
        )
        con.commit()
        con.close()
        return handle.name

    def test_names_are_added_and_pairs_are_unique(self):
        first = ["Ana", "Ben", "Cleo", "Dev", "Eli", "Fay", "Gus", "Hana", "Ivo", "Jun"] * 3
        last = ["Ames", "Bose", "Cruz", "Dunn", "Egan", "Fox", "Gill", "Hart", "Ito", "Joy"] * 3

        class StandInFaker:
            rnd = random.Random(0)

            def __init__(self, locales=None):
                pass

            @classmethod
            def seed(cls, value):
                cls.rnd.seed(value)

            def first_name(self):
                return StandInFaker.rnd.choice(first)

            def last_name(self):
                return StandInFaker.rnd.choice(last)

        module = types.ModuleType("faker")
        module.Faker = StandInFaker
        path = self.make_db()
        with mock.patch.dict(sys.modules, {"faker": module}):
            count = add_names.add_names(db_path=path)
        self.assertEqual(count, 50)
        rows = sqlite3.connect(path).execute("SELECT first_name, last_name FROM employees").fetchall()
        self.assertTrue(all(a and b for a, b in rows))
        self.assertEqual(len(set(rows)), 50)

    def test_missing_faker_stops_politely(self):
        path = self.make_db()
        with mock.patch.dict(sys.modules, {"faker": None}):
            self.assertEqual(add_names.add_names(db_path=path), 0)


if __name__ == "__main__":
    unittest.main()
