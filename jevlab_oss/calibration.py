# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 The OmniSI Authors
"""Pure-Python calibration, paired bias diagnostics and inter-judge agreement.

Scores are p(positive), not confidence in the chosen class. Fit on a calibration
split and evaluate on a separate holdout; improvements are signed, never promised.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence

from . import fixtures, metrics


def _probabilities(values: Sequence[float]) -> None:
    if not values or any(type(p) not in (int, float) or not math.isfinite(p) or
                         not 0 <= p <= 1 for p in values):
        raise ValueError("scores must be non-empty finite probabilities in [0, 1]")


def _labels(values: Sequence[bool]) -> None:
    if not values or any(type(y) not in (bool, int) or y not in (0, 1) for y in values):
        raise ValueError("labels must be non-empty binary values (boolean or 0/1)")


def _check(ps: Sequence[float], truth: Sequence[bool]) -> None:
    _probabilities(ps)
    _labels(truth)
    if len(ps) != len(truth):
        raise ValueError("scores and labels must have the same length")


def _bins(n_bins: int) -> None:
    if type(n_bins) is not int or not 1 <= n_bins <= 1000:
        raise ValueError("n_bins must be an integer between 1 and 1000")


def calibration_metrics(ps: Sequence[float], truth: Sequence[bool], n_bins: int = 10) -> dict:
    """Equal-width ECE/MCE, Brier and occupied reliability bins."""
    _check(ps, truth)
    _bins(n_bins)
    bins = metrics.reliability_bins(ps, truth, n_bins)
    return {
        "n": len(ps), "ece": metrics.ece(ps, truth, n_bins),
        "mce": max(abs(b["mean_p"] - b["observed"]) for b in bins),
        "brier": metrics.brier(ps, truth), "accuracy": metrics.accuracy(ps, truth),
        "reliability": bins,
    }


class _Calibrator:
    fitted = False

    def apply(self, p: float) -> float:
        raise NotImplementedError

    def predict(self, ps: Sequence[float]) -> list[float]:
        _probabilities(ps)
        return [self.apply(p) for p in ps]

    def evaluate(self, ps: Sequence[float], truth: Sequence[bool], n_bins: int = 10) -> dict:
        before = calibration_metrics(ps, truth, n_bins)
        after = calibration_metrics(self.predict(ps), truth, n_bins)
        return {"before": before, "after": after,
                "improvement": {k: before[k] - after[k] for k in ("ece", "mce", "brier")}}


class PlattCalibrator(_Calibrator):
    """sigmoid(a * logit(p) + b), using gradient descent with backtracking.

    temperature_only=True fixes b=0 and constrains a=1/T > 0. A tiny ridge
    penalty keeps separable fits finite. Endpoints are clipped at 1e-6.
    """

    def __init__(self, *, temperature_only: bool = False) -> None:
        self.temperature_only = temperature_only
        self.a, self.b = 1.0, 0.0
        self.fitted = False

    @staticmethod
    def _logit(p: float) -> float:
        p = min(max(p, 1e-6), 1 - 1e-6)
        return math.log(p / (1 - p))

    @property
    def temperature(self) -> float:
        if not self.temperature_only:
            raise ValueError("temperature is defined only for temperature scaling")
        return 1 / self.a

    def fit(self, ps: Sequence[float], truth: Sequence[bool], *, iters: int = 400) -> PlattCalibrator:
        _check(ps, truth)
        if type(iters) is not int or not 1 <= iters <= 10000:
            raise ValueError("iters must be an integer between 1 and 10000")
        xs = [self._logit(p) for p in ps]
        n, ridge = len(ps), 1e-6

        def loss(a: float, b: float) -> float:
            zs = [a * x + b for x in xs]
            return sum(max(z, 0) + math.log1p(math.exp(-abs(z))) - y * z
                       for z, y in zip(zs, truth)) / n + ridge * (a * a + b * b) / 2

        a, b = 1.0, 0.0
        step_size = 4 / (1 + sum(x * x for x in xs) / n)
        old_loss = loss(a, b)
        for _ in range(iters):
            errors = [metrics._sigmoid(a * x + b) - y for x, y in zip(xs, truth)]
            ga = sum(e * x for e, x in zip(errors, xs)) / n + ridge * a
            gb = 0.0 if self.temperature_only else sum(errors) / n + ridge * b
            step = step_size
            for _ in range(30):
                na, nb = a - step * ga, b - step * gb
                if self.temperature_only:
                    na = max(1e-4, na)
                new_loss = loss(na, nb)
                if new_loss <= old_loss:
                    break
                step /= 2
            else:
                break
            converged = old_loss - new_loss < 1e-12
            a, b, old_loss = na, nb, new_loss
            if converged:
                break
        self.a, self.b, self.fitted = a, b, True
        return self

    def apply(self, p: float) -> float:
        _probabilities([p])
        if not self.fitted:
            raise ValueError("fit the calibrator before prediction")
        return metrics._sigmoid(self.a * self._logit(p) + self.b)


class TemperatureCalibrator(PlattCalibrator):
    """One-parameter positive temperature scaling: sigmoid(logit(p) / T)."""

    def __init__(self) -> None:
        super().__init__(temperature_only=True)


class HistogramCalibrator(_Calibrator):
    """Equal-width bin frequencies with symmetric pseudocounts.

    Empty fit bins retain the input probability. alpha=0 gives empirical rates;
    the default alpha=1 smooths occupied bins with one positive and one negative.
    """

    def __init__(self, n_bins: int = 10, alpha: float = 1.0) -> None:
        _bins(n_bins)
        if type(alpha) not in (int, float) or not math.isfinite(alpha) or alpha < 0:
            raise ValueError("alpha must be finite and non-negative")
        self.n_bins, self.alpha = n_bins, alpha
        self.fitted = False
        self.rates: list[float | None] = [None] * n_bins

    def fit(self, ps: Sequence[float], truth: Sequence[bool]) -> HistogramCalibrator:
        _check(ps, truth)
        counts, positive = [0] * self.n_bins, [0] * self.n_bins
        for p, y in zip(ps, truth):
            i = min(int(p * self.n_bins), self.n_bins - 1)
            counts[i] += 1
            positive[i] += int(y)
        self.rates = [(s + self.alpha) / (n + 2 * self.alpha) if n else None
                      for s, n in zip(positive, counts)]
        self.fitted = True
        return self

    def apply(self, p: float) -> float:
        _probabilities([p])
        if not self.fitted:
            raise ValueError("fit the calibrator before prediction")
        rate = self.rates[min(int(p * self.n_bins), self.n_bins - 1)]
        return p if rate is None else rate


def spearman(x: Sequence[float], y: Sequence[float]) -> float | None:
    """Pearson correlation of average ranks; None for fewer than 2 or constant ranks."""
    if len(x) != len(y) or any(type(v) not in (int, float) or not math.isfinite(v)
                              for v in [*x, *y]):
        raise ValueError("rank inputs must be equally sized finite numeric sequences")
    if len(x) < 2:
        return None

    def ranks(values: Sequence[float]) -> list[float]:
        order = sorted(range(len(values)), key=lambda i: values[i])
        result = [0.0] * len(values)
        start = 0
        while start < len(order):
            end = start + 1
            while end < len(order) and values[order[end]] == values[order[start]]:
                end += 1
            for i in order[start:end]:
                result[i] = (start + end - 1) / 2
            start = end
        return result

    rx, ry = ranks(x), ranks(y)
    mx, my = sum(rx) / len(x), sum(ry) / len(y)
    xx, yy = [v - mx for v in rx], [v - my for v in ry]
    denom = math.sqrt(sum(v * v for v in xx) * sum(v * v for v in yy))
    return max(-1.0, min(1.0, sum(a * b for a, b in zip(xx, yy)) / denom)) if denom else None


def format_density(text: str) -> float:
    """Fraction of nonblank lines containing markdown headings/lists/emphasis/code/links."""
    lines = [line for line in text.splitlines() if line.strip()]
    pattern = r"^\s*(?:#{1,6}\s|[-*+]\s|\d+[.)]\s|>|```)|\*\*|__|`|\[[^]]+\]\("
    return sum(bool(re.search(pattern, line)) for line in lines) / len(lines) if lines else 0.0


class BiasAuditor:
    """Audit matched A/B pairs. Probabilities always refer to the first displayed option.

    forward=p(A wins in A/B); swapped=p(B wins in B/A). Exactly 0.5 is a tie;
    ties are excluded from winner flip rates and counted separately. Correlations
    describe association, not causal bias. Self-preference requires origin IDs.
    """

    def audit(self, pairs: Sequence[dict]) -> dict:
        if not pairs:
            raise ValueError("pairs must be non-empty")
        groups: dict[str, list[dict]] = {}
        for pair in pairs:
            if not isinstance(pair, dict) or not all(isinstance(pair.get(k), str)
                                                   for k in ("a", "b")):
                raise ValueError("each pair needs string a and b responses")
            _probabilities([pair.get("forward"), pair.get("swapped")])
            judge = pair.get("judge", "judge")
            if not isinstance(judge, str) or not judge:
                raise ValueError("judge must be a non-empty string")
            for key in ("judge_model", "a_model", "b_model"):
                if key in pair and not isinstance(pair[key], str):
                    raise ValueError("model identities must be strings")
            groups.setdefault(judge, []).append(pair)
        return {"pairs": len(pairs), "judges": {name: self._group(rows)
                                                for name, rows in sorted(groups.items())},
                "interpretation": "Associations require matched quality controls; undefined correlations are null."}

    @staticmethod
    def _group(pairs: list[dict]) -> dict:
        f, s = [p["forward"] for p in pairs], [p["swapped"] for p in pairs]
        decisive = [(a, b) for a, b in zip(f, s) if a != 0.5 and b != 0.5]
        flips = sum((a > 0.5) == (b > 0.5) for a, b in decisive)
        # Average A preference across both orders, to reduce positional confounding.
        preference = [(a + 1 - b) / 2 for a, b in zip(f, s)]
        first = sum(p > 0.5 for p in [*f, *s])
        second = sum(p < 0.5 for p in [*f, *s])
        own_indicator, own_preference = [], []
        for pair, pref in zip(pairs, preference):
            model = pair.get("judge_model")
            if not model or not pair.get("a_model") or not pair.get("b_model"):
                continue
            own_a, own_b = pair["a_model"] == model, pair["b_model"] == model
            if own_a != own_b:
                own_indicator.append(float(own_a) - float(own_b))
                own_preference.append(pref)
        own_scores = [p if own > 0 else 1 - p
                      for own, p in zip(own_indicator, own_preference)]
        n = len(pairs)
        return {
            "pairs": n,
            "position_swap": {"decisive_pairs": len(decisive), "tie_pairs": n - len(decisive),
                "flips": flips, "flip_rate": flips / len(decisive) if decisive else None,
                "first_win_rate": first / (2 * n), "second_win_rate": second / (2 * n),
                "tie_rate": 1 - (first + second) / (2 * n),
                "directional_bias": (first - second) / (2 * n),
                "probability_bias": sum(a + b - 1 for a, b in zip(f, s)) / n,
                "mean_swap_gap": sum(abs(a + b - 1) for a, b in zip(f, s)) / n},
            "verbosity": {"spearman": spearman([len(p["a"]) - len(p["b"]) for p in pairs], preference),
                          "length_unit": "characters"},
            "format": {"spearman": spearman([format_density(p["a"]) - format_density(p["b"])
                                              for p in pairs], preference)},
            "self_preference": {"eligible_pairs": len(own_scores),
                "mean_own_probability": sum(own_scores) / len(own_scores) if own_scores else None,
                "spearman": spearman(own_indicator, own_preference)},
        }


class AgreementMatrix:
    """Aligned binary ratings on the same items, with no missing-rater imputation."""

    def __init__(self, ratings: Mapping[str, Sequence[bool]]) -> None:
        if not ratings:
            raise ValueError("at least one judge is required")
        for name, values in ratings.items():
            if not isinstance(name, str) or not name:
                raise ValueError("judge names must be non-empty strings")
            _labels(values)
        if len({len(v) for v in ratings.values()}) != 1:
            raise ValueError("judges must rate the same number of aligned items")
        self.ratings = {name: list(values) for name, values in sorted(ratings.items())}

    def pairwise(self) -> dict:
        return {a: {b: metrics.cohen_kappa(av, bv) for b, bv in self.ratings.items()}
                for a, av in self.ratings.items()}

    def fleiss_kappa(self) -> float | None:
        m = len(self.ratings)
        if m < 2:
            return None
        rows = list(zip(*self.ratings.values()))
        positive = [sum(row) for row in rows]
        observed = sum((k * (k - 1) + (m - k) * (m - k - 1)) / (m * (m - 1))
                       for k in positive) / len(rows)
        p = sum(positive) / (len(rows) * m)
        chance = p * p + (1 - p) ** 2
        return (observed - chance) / (1 - chance) if chance < 1 else None

    def pareto_frontier(self, costs: Mapping[str, float], truth: Sequence[bool]) -> list[dict]:
        """Non-dominated cost/accuracy layers; rank 1 is the frontier. Lower cost wins.

        Costs must use the same unit and workload for all judges. Duplicate points
        share a rank. Missing costs are rejected rather than treated as free.
        """
        _labels(truth)
        if set(costs) != set(self.ratings):
            raise ValueError("costs must name every judge exactly once")
        if any(type(c) not in (int, float) or not math.isfinite(c) or c < 0 for c in costs.values()):
            raise ValueError("costs must be finite and non-negative")
        rows = []
        for name, values in self.ratings.items():
            if len(values) != len(truth):
                raise ValueError("truth must align with the ratings")
            rows.append({"judge": name, "cost": costs[name],
                         "accuracy": sum(a == b for a, b in zip(values, truth)) / len(truth)})
        remaining, ranked, rank = rows[:], [], 1
        while remaining:
            front = [r for r in remaining if not any(
                q["cost"] <= r["cost"] and q["accuracy"] >= r["accuracy"] and
                (q["cost"] < r["cost"] or q["accuracy"] > r["accuracy"]) for q in remaining)]
            ranked.extend(dict(r, pareto_rank=rank, frontier=rank == 1)
                          for r in sorted(front, key=lambda r: (r["cost"], r["judge"])))
            remaining = [r for r in remaining if r not in front]
            rank += 1
        return ranked


def optimal_threshold(ps: Sequence[float], truth: Sequence[bool], *,
                      false_positive_cost: float = 1, false_negative_cost: float = 1) -> dict:
    """Minimize empirical weighted errors on the FIT split, including all-negative.

    O(n log n). Ties favor the threshold closest to 0.5, then the lower threshold.
    A threshold just above 1 represents an all-negative decision rule if needed.
    """
    _check(ps, truth)
    if any(type(c) not in (int, float) or not math.isfinite(c) or c <= 0
           for c in (false_positive_cost, false_negative_cost)):
        raise ValueError("error costs must be finite and positive")
    groups: dict[float, list[int]] = {}
    for p, y in zip(ps, truth):
        counts = groups.setdefault(p, [0, 0])
        counts[int(y)] += 1
    candidates = sorted({0.0, 0.5, *ps, math.nextafter(max(ps), math.inf)})
    fp, fn, cursor = len(ps) - sum(truth), 0, 0
    scores = sorted(groups)
    best = None
    for threshold in candidates:
        while cursor < len(scores) and scores[cursor] < threshold:
            neg, pos = groups[scores[cursor]]
            fp, fn, cursor = fp - neg, fn + pos, cursor + 1
        key = (fp * false_positive_cost + fn * false_negative_cost, abs(threshold - 0.5), threshold)
        if best is None or key < best[0]:
            best = (key, {"threshold": threshold, "fit_accuracy": 1 - (fp + fn) / len(ps),
                          "fit_loss": key[0] / len(ps), "false_positives": fp, "false_negatives": fn,
                          "selection_split": "fit", "rule": "positive when p >= threshold"})
    assert best is not None
    return best[1]


def calibrate_fixture(fixture: dict, n_bins: int = 10, pairs: Sequence[dict] | None = None) -> dict:
    """Fit all three methods on fit only; score and plot on the untouched holdout."""
    fixtures.validate(fixture)
    _bins(n_bins)
    fit = [i for i in fixture["items"] if i["split"] == "fit"]
    hold = [i for i in fixture["items"] if i["split"] == "holdout"]
    names = sorted(fit[0].get("judgments", {}))
    if not names:
        raise ValueError("calibration requires recorded judgments")
    fy, hy = [i["truth"] for i in fit], [i["truth"] for i in hold]
    report = {"schema_version": 1, "fixture": {"rubric_id": fixture["rubric"]["id"],
              "fit": len(fit), "holdout": len(hold), "synthetic": fixture["synthetic"]},
              "n_bins": n_bins, "judges": {}}
    ratings = {}
    for name in names:
        fp, hp = [i["judgments"][name] for i in fit], [i["judgments"][name] for i in hold]
        methods = {}
        for key, model in (("platt", PlattCalibrator()), ("temperature", TemperatureCalibrator()),
                           ("histogram", HistogramCalibrator(n_bins))):
            model.fit(fp, fy)
            comparison = model.evaluate(hp, hy, n_bins)
            threshold = optimal_threshold(model.predict(fp), fy)
            threshold["holdout_accuracy"] = metrics.accuracy(model.predict(hp), hy, threshold["threshold"])
            params = {"rates": model.rates, "alpha": model.alpha} if isinstance(model, HistogramCalibrator) else {
                "a": model.a, "b": model.b}
            if key == "temperature":
                params["temperature"] = model.temperature
            methods[key] = {**comparison, "parameters": params, "decision": threshold}
        report["judges"][name] = {"before": calibration_metrics(hp, hy, n_bins), "methods": methods}
        ratings[name] = [p >= 0.5 for p in hp]
    agreement = AgreementMatrix(ratings)
    costs = fixture.get("judge_costs")
    if costs is not None and not isinstance(costs, dict):
        raise ValueError("judge_costs must map judge names to comparable numeric costs")
    report["agreement"] = {"pairwise": agreement.pairwise(), "fleiss_kappa": agreement.fleiss_kappa(),
        "pareto": agreement.pareto_frontier(costs, hy) if costs is not None else [],
        "cost_note": "Costs supplied by fixture, in a common unit." if costs is not None else "No judge_costs supplied; no cost ranking inferred."}
    report["bias"] = BiasAuditor().audit(pairs) if pairs is not None else None
    report["notes"] = ["All calibration and threshold selection uses fit only; metrics use holdout.",
        "Positive improvement means lower error; negative means calibration made it worse.",
        "Thresholds minimize fit error with equal error costs; validate on new data before deployment.",
        "Do not repeatedly select methods against the same holdout. Small samples have high uncertainty."]
    return report
