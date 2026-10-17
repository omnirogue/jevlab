# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 The OmniSI Authors
"""Run from oss/omnisi-jev-lab: ``python3 -m unittest discover -s tests``."""

import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from jevlab_oss import bench, fixtures, metrics  # noqa: E402

sys.path.insert(0, str(ROOT / "fixtures"))
import make_synthetic  # noqa: E402

SAMPLE = ROOT / "fixtures" / "synthetic_sample.json"


class Metrics(unittest.TestCase):
    def test_brier_and_auc_known_values(self):
        self.assertAlmostEqual(metrics.brier([1.0, 0.0], [True, False]), 0.0)
        self.assertAlmostEqual(metrics.brier([0.5, 0.5], [True, False]), 0.25)
        self.assertEqual(metrics.auc([0.9, 0.8, 0.1], [True, True, False]), 1.0)
        self.assertEqual(metrics.auc([0.5, 0.5], [True, False]), 0.5)
        self.assertIsNone(metrics.auc([0.5], [True]))

    def test_ece_is_zero_when_confidence_matches_rate(self):
        ps = [0.25] * 4 + [0.75] * 4
        truth = [True, False, False, False, True, True, True, False]
        self.assertAlmostEqual(metrics.ece(ps, truth), 0.0)

    def test_rejects_out_of_range(self):
        with self.assertRaises(ValueError):
            metrics.brier([1.2], [True])
        with self.assertRaises(ValueError):
            metrics.brier([0.2, 0.3], [True])

    def test_kappa_and_order_consistency(self):
        self.assertAlmostEqual(metrics.cohen_kappa([True, False], [True, False]), 1.0)
        consistent = metrics.order_consistency([0.9, 0.2], [0.1, 0.8])
        self.assertAlmostEqual(consistent["mean_gap"], 0.0)
        self.assertEqual(consistent["verdict_flips"], 0)
        biased = metrics.order_consistency([0.9], [0.9])
        self.assertEqual(biased["verdict_flips"], 1)

    def test_platt_improves_overconfident_scores(self):
        ps = [0.99, 0.99, 0.99, 0.01, 0.01, 0.01] * 5
        truth = [True, True, False, False, False, True] * 5
        platt = metrics.PlattCalibrator().fit(ps, truth)
        calibrated = [platt.apply(p) for p in ps]
        self.assertLess(metrics.brier(calibrated, truth), metrics.brier(ps, truth))


class Fixtures(unittest.TestCase):
    def test_committed_sample_matches_generator(self):
        on_disk = json.loads(SAMPLE.read_text(encoding="utf-8"))
        self.assertEqual(on_disk, json.loads(json.dumps(make_synthetic.build())))

    def test_sample_is_valid_and_benchmarks(self):
        report = bench.run(fixtures.load(SAMPLE))
        self.assertEqual(
            set(report["judges"]), {"judge-calibrated", "judge-noisy", "judge-overconfident"}
        )
        self.assertEqual(report["fixture"]["holdout"], 20)
        self.assertIn("ensemble_mean_holdout", report)

    def test_scrub_rules(self):
        base = json.loads(SAMPLE.read_text(encoding="utf-8"))
        for mutate in (
            lambda f: f.update(synthetic=False),
            lambda f: f.update(license="MIT"),
            lambda f: f["items"][0].update(text="write to someone@" + "realcompany.co"),
            lambda f: f["items"][0].update(split="train"),
            lambda f: f["items"].append(None),
            lambda f: f["items"].insert(0, "not an object"),
            lambda f: f["rubric"]["questions"].append(None),
            lambda f: f["items"][0].update(question_id=[]),
        ):
            bad = copy.deepcopy(base)
            mutate(bad)
            with self.assertRaises(fixtures.FixtureError):
                fixtures.validate(bad)
        ok = copy.deepcopy(base)
        ok["items"][0]["text"] = "write to someone@example.com"
        fixtures.validate(ok)


if __name__ == "__main__":
    unittest.main()
