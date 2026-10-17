# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 The OmniSI Authors
"""Known-answer, split isolation and degeneracy checks for the enhanced API."""

import copy
import math
import unittest

from jevlab import calibration as c
from jevlab_oss import resources
from jevlab_oss.report import render_report


class Calibration(unittest.TestCase):
    def test_known_metrics_and_endpoints(self):
        result = c.calibration_metrics([0, 1, .5, .5], [False, True, True, False], 2)
        self.assertAlmostEqual(result['brier'], .125)
        self.assertAlmostEqual(result['ece'], 0)
        self.assertAlmostEqual(result['mce'], 0)
        self.assertEqual(sum(b['count'] for b in result['reliability']), 4)
        self.assertEqual(c.calibration_metrics([.2, .9], [False, False])['mce'], .9)

    def test_overconfidence_reduces_on_independent_repeated_population(self):
        fit_p, fit_y = [.99, .99, .99, .01, .01, .01] * 10, [1, 1, 0, 0, 0, 1] * 10
        hold_p, hold_y = [.98, .98, .98, .02, .02, .02] * 4, [1, 1, 0, 0, 0, 1] * 4
        for model in (c.PlattCalibrator(), c.TemperatureCalibrator(), c.HistogramCalibrator()):
            result = model.fit(fit_p, fit_y).evaluate(hold_p, hold_y)
            for key in ('brier', 'ece', 'mce'):
                self.assertGreater(result['improvement'][key], 0)
        temp = c.TemperatureCalibrator().fit(fit_p, fit_y)
        self.assertGreater(temp.temperature, 1)
        self.assertEqual(temp.b, 0)
        self.assertEqual(temp.predict([0, .5, 1]), sorted(temp.predict([0, .5, 1])))

    def test_invalid_and_unfitted_inputs(self):
        for model in (c.PlattCalibrator(), c.TemperatureCalibrator(), c.HistogramCalibrator()):
            with self.assertRaises(ValueError):
                model.apply(.5)
            for ps, ys in [([], []), ([math.nan], [1]), ([math.inf], [0]), ([True], [1]),
                           ([.5], [2]), ([.5], ['true']), ([.2, .3], [True])]:
                with self.assertRaises(ValueError):
                    model.fit(ps, ys)
        for bins in (0, -1, 1.5, True, 1001):
            with self.assertRaises(ValueError):
                c.HistogramCalibrator(bins)

    def test_histogram_empty_bin_and_refit(self):
        model = c.HistogramCalibrator(n_bins=4, alpha=0).fit([0, 0, 1], [0, 1, 1])
        self.assertEqual(model.predict([0, .4, 1]), [.5, .4, 1])
        model.fit([.4], [0])
        self.assertEqual(model.predict([.4, .9]), [0, .9])

    def test_no_holdout_leakage_into_parameters_or_threshold(self):
        fixture = resources.default_fixture()
        before = c.calibrate_fixture(fixture)
        changed = copy.deepcopy(fixture)
        for item in changed['items']:
            if item['split'] == 'holdout':
                item['truth'] = not item['truth']
                item['judgments'] = {name: 1 - p for name, p in item['judgments'].items()}
        after = c.calibrate_fixture(changed)
        for name in before['judges']:
            for method, original in before['judges'][name]['methods'].items():
                altered = after['judges'][name]['methods'][method]
                self.assertEqual(original['parameters'], altered['parameters'])
                self.assertEqual(original['decision']['threshold'], altered['decision']['threshold'])
        self.assertIsNone(after['bias'])
        self.assertEqual(after['agreement']['pareto'], [])

    def test_threshold_candidates_and_asymmetric_cost(self):
        self.assertGreater(c.optimal_threshold([1, 1], [0, 0])['threshold'], 1)
        self.assertEqual(c.optimal_threshold([0, 0], [1, 1])['threshold'], 0)
        ps, ys = [.2, .3, .4, .8], [False, True, False, True]
        ordinary = c.optimal_threshold(ps, ys)
        expensive_fp = c.optimal_threshold(ps, ys, false_positive_cost=10)
        self.assertGreaterEqual(expensive_fp['threshold'], ordinary['threshold'])
        # Exhaustively compare objective to all possible distinct classifications.
        for threshold in [0, .2, .3, .4, .8, math.nextafter(.8, math.inf)]:
            errors = sum((p >= threshold) != y for p, y in zip(ps, ys))
            self.assertLessEqual(ordinary['fit_loss'], errors / len(ys))

    def test_report_escapes_labels_and_shows_negative_improvement(self):
        fixture = resources.default_fixture()
        fixture['rubric']['id'] = '<script>alert(1)</script>'
        report = c.calibrate_fixture(fixture, pairs=resources.default_pairs())
        html = render_report(report)
        self.assertNotIn('<script>', html)
        self.assertIn('&lt;script&gt;', html)
        self.assertIn('Content-Security-Policy', html)
        self.assertIn('<svg', html)
        self.assertIn('First − second bias', html)
        self.assertIn('class="bad"', html)
        self.assertIn('Holdout accuracy at this threshold', html)


class BiasAndAgreement(unittest.TestCase):
    def test_swap_orientation_direction_and_ties(self):
        audit = c.BiasAuditor()
        base = {'a': 'A', 'b': 'B'}
        consistent = audit.audit([dict(base, forward=.8, swapped=.2)])['judges']['judge']
        self.assertEqual(consistent['position_swap']['flip_rate'], 0)
        self.assertEqual(consistent['position_swap']['directional_bias'], 0)
        for p, direction in [(.8, 1), (.2, -1)]:
            biased = audit.audit([dict(base, forward=p, swapped=p)])['judges']['judge']
            self.assertEqual(biased['position_swap']['flip_rate'], 1)
            self.assertEqual(biased['position_swap']['directional_bias'], direction)
        tie = audit.audit([dict(base, forward=.5, swapped=.5)])['judges']['judge']
        self.assertIsNone(tie['position_swap']['flip_rate'])
        self.assertEqual(tie['position_swap']['tie_pairs'], 1)
        self.assertIsNone(tie['self_preference']['mean_own_probability'])

    def test_spearman_average_ties_and_degenerate(self):
        self.assertAlmostEqual(c.spearman([1, 1, 3], [2, 3, 4]), math.sqrt(3) / 2)
        self.assertEqual(c.spearman([1, 2, 3], [3, 2, 1]), -1)
        self.assertIsNone(c.spearman([1, 1], [2, 3]))
        self.assertIsNone(c.spearman([], []))
        self.assertEqual(c.format_density('# Heading\nplain\n- item\n'), 2 / 3)
        with self.assertRaises(ValueError):
            c.spearman([math.nan], [1])

    def test_self_preference_requires_and_uses_provenance(self):
        pairs = [dict(a='A', b='B', forward=.9, swapped=.1, judge_model='own', a_model='own', b_model='other'),
                 dict(a='A', b='B', forward=.1, swapped=.9, judge_model='own', a_model='other', b_model='own')]
        result = c.BiasAuditor().audit(pairs)['judges']['judge']['self_preference']
        self.assertEqual(result['eligible_pairs'], 2)
        self.assertAlmostEqual(result['mean_own_probability'], .9)
        self.assertAlmostEqual(result['spearman'], 1)

    def test_kappas_known_values(self):
        matrix = c.AgreementMatrix({'a': [1, 1, 0, 0], 'b': [1, 0, 1, 0], 'c': [1, 1, 0, 0]})
        self.assertEqual(matrix.pairwise()['a']['b'], 0)
        self.assertEqual(matrix.pairwise()['a']['c'], 1)
        self.assertAlmostEqual(matrix.fleiss_kappa(), 1 / 3)
        self.assertIsNone(c.AgreementMatrix({'a': [1], 'b': [1]}).fleiss_kappa())
        self.assertIsNone(c.AgreementMatrix({'a': [0]}).pairwise()['a']['a'])
        with self.assertRaises(ValueError):
            c.AgreementMatrix({'a': [1, 0], 'b': [1]})
        with self.assertRaises(ValueError):
            c.AgreementMatrix({'a': [.9]})

    def test_pareto_tradeoff_duplicates_and_dominance(self):
        matrix = c.AgreementMatrix({'cheap': [1, 1], 'best': [1, 0], 'duplicate': [1, 0], 'bad': [0, 1]})
        rows = matrix.pareto_frontier({'cheap': 1, 'best': 2, 'duplicate': 2, 'bad': 3}, [1, 0])
        ranks = {r['judge']: r['pareto_rank'] for r in rows}
        self.assertEqual(ranks, {'cheap': 1, 'best': 1, 'duplicate': 1, 'bad': 2})
        with self.assertRaises(ValueError):
            matrix.pareto_frontier({'cheap': 1}, [1, 0])


if __name__ == '__main__':
    unittest.main()
