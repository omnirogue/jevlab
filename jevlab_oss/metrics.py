# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 The OmniSI Authors
"""Calibration and agreement metrics over probabilities of "yes" and boolean truth.

Every function takes plain lists and is deterministic. Inputs are validated: probabilities must lie
in [0, 1] and lists must have equal, non-zero length.
"""

from __future__ import annotations

import math
from collections.abc import Sequence


def _check(ps: Sequence[float], truth: Sequence[bool]) -> None:
    if not ps or len(ps) != len(truth):
        raise ValueError("probabilities and truth must be non-empty and the same length")
    for p in ps:
        if not (isinstance(p, (int, float)) and 0.0 <= p <= 1.0 and math.isfinite(p)):
            raise ValueError(f"probability out of range: {p!r}")


def brier(ps: Sequence[float], truth: Sequence[bool]) -> float:
    """Mean squared error between p(yes) and the 0/1 outcome. Lower is better; 0.25 is a coin."""
    _check(ps, truth)
    return sum((p - float(t)) ** 2 for p, t in zip(ps, truth)) / len(ps)


def reliability_bins(ps: Sequence[float], truth: Sequence[bool], n_bins: int = 10) -> list[dict]:
    """Equal-width bins with mean confidence, observed rate and count; empty bins are omitted."""
    _check(ps, truth)
    if n_bins < 1:
        raise ValueError("n_bins must be at least 1")
    bins: list[list[tuple[float, bool]]] = [[] for _ in range(n_bins)]
    for p, t in zip(ps, truth):
        bins[min(int(p * n_bins), n_bins - 1)].append((p, t))
    out = []
    for i, rows in enumerate(bins):
        if rows:
            out.append(
                {
                    "lower": i / n_bins,
                    "upper": (i + 1) / n_bins,
                    "count": len(rows),
                    "mean_p": sum(p for p, _ in rows) / len(rows),
                    "observed": sum(1 for _, t in rows if t) / len(rows),
                }
            )
    return out


def ece(ps: Sequence[float], truth: Sequence[bool], n_bins: int = 10) -> float:
    """Expected calibration error: count-weighted gap between confidence and observed rate."""
    rows = reliability_bins(ps, truth, n_bins)
    return sum(b["count"] * abs(b["mean_p"] - b["observed"]) for b in rows) / len(ps)


def auc(ps: Sequence[float], truth: Sequence[bool]) -> float | None:
    """Area under the ROC curve (Mann-Whitney, ties count half). None when one class is absent."""
    _check(ps, truth)
    pos = [p for p, t in zip(ps, truth) if t]
    neg = [p for p, t in zip(ps, truth) if not t]
    if not pos or not neg:
        return None
    wins = sum(1.0 if a > b else 0.5 if a == b else 0.0 for a in pos for b in neg)
    return wins / (len(pos) * len(neg))


def accuracy(ps: Sequence[float], truth: Sequence[bool], threshold: float = 0.5) -> float:
    _check(ps, truth)
    return sum(1 for p, t in zip(ps, truth) if (p >= threshold) == t) / len(ps)


def wilson_interval(k: int, n: int, z: float = 1.96) -> tuple[float, float] | None:
    """Wilson score interval for k successes in n trials."""
    if n <= 0 or not 0 <= k <= n:
        return None
    phat = k / n
    denom = 1 + z * z / n
    centre = (phat + z * z / (2 * n)) / denom
    half = z * math.sqrt(phat * (1 - phat) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def cohen_kappa(a: Sequence[bool], b: Sequence[bool]) -> float | None:
    """Chance-corrected agreement between two yes/no raters. None when chance agreement is 1."""
    if not a or len(a) != len(b):
        raise ValueError("ratings must be non-empty and the same length")
    n = len(a)
    observed = sum(1 for x, y in zip(a, b) if x == y) / n
    pa, pb = sum(a) / n, sum(b) / n
    chance = pa * pb + (1 - pa) * (1 - pb)
    if chance >= 1.0:
        return None
    return (observed - chance) / (1 - chance)


def order_consistency(forward: Sequence[float], swapped: Sequence[float]) -> dict:
    """Position-bias check for a pairwise judge asked A-vs-B and then B-vs-A.

    ``forward[i]`` is p(first option wins) in A/B order; ``swapped[i]`` the same question in B/A
    order. A consistent judge has forward[i] close to 1 - swapped[i].
    """
    if not forward or len(forward) != len(swapped):
        raise ValueError("forward and swapped must be non-empty and the same length")
    gaps = [abs(f - (1.0 - s)) for f, s in zip(forward, swapped)]
    flips = sum(1 for f, s in zip(forward, swapped) if (f >= 0.5) == (s >= 0.5))
    return {"mean_gap": sum(gaps) / len(gaps), "verdict_flips": flips, "pairs": len(gaps)}


def _sigmoid(z: float) -> float:
    if z >= 0:
        return 1.0 / (1.0 + math.exp(-z))
    e = math.exp(z)
    return e / (1.0 + e)


class PlattCalibrator:
    """Logistic recalibration p' = sigmoid(a * logit(p) + b), fitted by damped Newton's method.

    Targets use Platt's smoothing ((n+ + 1) / (n+ + 2) and 1 / (n- + 2)), which keeps the optimum
    finite when the judge perfectly separates the fit split.
    """

    def __init__(self, a: float = 1.0, b: float = 0.0) -> None:
        self.a, self.b = a, b

    @staticmethod
    def _logit(p: float) -> float:
        p = min(max(p, 1e-6), 1 - 1e-6)
        return math.log(p / (1 - p))

    @staticmethod
    def _loss(a: float, b: float, xs: list[float], ys: list[float]) -> float:
        total = 0.0
        for x, y in zip(xs, ys):
            q = min(max(_sigmoid(a * x + b), 1e-12), 1 - 1e-12)
            total -= y * math.log(q) + (1 - y) * math.log(1 - q)
        return total

    def fit(self, ps: Sequence[float], truth: Sequence[bool], iters: int = 100) -> PlattCalibrator:
        _check(ps, truth)
        n_pos = sum(1 for t in truth if t)
        hi, lo = (n_pos + 1) / (n_pos + 2), 1 / (len(truth) - n_pos + 2)
        xs = [self._logit(p) for p in ps]
        ys = [hi if t else lo for t in truth]
        a, b = 1.0, 0.0
        loss = self._loss(a, b, xs, ys)
        for _ in range(iters):
            ga = gb = haa = hab = hbb = 0.0
            for x, y in zip(xs, ys):
                q = _sigmoid(a * x + b)
                ga += (q - y) * x
                gb += q - y
                w = q * (1 - q)
                haa += w * x * x
                hab += w * x
                hbb += w
            haa, hbb = haa + 1e-9, hbb + 1e-9
            det = haa * hbb - hab * hab
            if det <= 0:
                break
            da = (hbb * ga - hab * gb) / det
            db = (haa * gb - hab * ga) / det
            step = 1.0
            while step > 1e-8:
                na, nb = a - step * da, b - step * db
                new_loss = self._loss(na, nb, xs, ys)
                if new_loss <= loss:
                    break
                step /= 2
            else:
                break
            converged = loss - new_loss < 1e-12
            a, b, loss = na, nb, new_loss
            if converged:
                break
        self.a, self.b = a, b
        return self

    def apply(self, p: float) -> float:
        return _sigmoid(self.a * self._logit(p) + self.b)


def summarize(ps: Sequence[float], truth: Sequence[bool], n_bins: int = 10) -> dict:
    """Every scalar metric for one judge on one split."""
    correct = sum(1 for p, t in zip(ps, truth) if (p >= 0.5) == t)
    interval = wilson_interval(correct, len(ps))
    return {
        "n": len(ps),
        "brier": round(brier(ps, truth), 6),
        "ece": round(ece(ps, truth, n_bins), 6),
        "auc": None if (v := auc(ps, truth)) is None else round(v, 6),
        "accuracy": round(accuracy(ps, truth), 6),
        "accuracy_wilson95": None if interval is None else [round(x, 6) for x in interval],
    }
