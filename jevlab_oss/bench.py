# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 The OmniSI Authors
"""Multi-judge benchmark: per-judge metrics, Platt recalibration, agreement and a mean ensemble.

Calibration is fitted on the ``fit`` split only and reported on ``holdout``, so the calibrated
numbers are not scored on the data they were fitted to.
"""

from __future__ import annotations

from itertools import combinations

from . import metrics
from .judges import CommandJudge, RecordedJudge


def run(fixture: dict, command_judges: dict[str, str] | None = None, n_bins: int = 10) -> dict:
    questions = {q["id"]: q["text"] for q in fixture["rubric"]["questions"]}
    items = fixture["items"]
    judges: list = [RecordedJudge(name) for name in sorted(items[0].get("judgments", {}))]
    for name, command in sorted((command_judges or {}).items()):
        if any(j.name == name for j in judges):
            raise ValueError(f"judge name {name} is already recorded in the fixture")
        judges.append(CommandJudge(name, command))
    if not judges:
        raise ValueError("no judges: record judgments in the fixture or pass --judge-cmd")

    scores = {j.name: [j.score(questions[i["question_id"]], i) for i in items] for j in judges}
    split = {s: [k for k, i in enumerate(items) if i["split"] == s] for s in ("fit", "holdout")}
    truth = [i["truth"] for i in items]

    def pick(values: list, s: str) -> list:
        return [values[k] for k in split[s]]

    report: dict = {
        "fixture": {
            "rubric_id": fixture["rubric"]["id"],
            "items": len(items),
            "fit": len(split["fit"]),
            "holdout": len(split["holdout"]),
            "synthetic": fixture["synthetic"],
        },
        "judges": {},
    }
    hold_truth = pick(truth, "holdout")
    for name, ps in scores.items():
        platt = metrics.PlattCalibrator().fit(pick(ps, "fit"), pick(truth, "fit"))
        calibrated = [platt.apply(p) for p in pick(ps, "holdout")]
        report["judges"][name] = {
            "fit": metrics.summarize(pick(ps, "fit"), pick(truth, "fit"), n_bins),
            "holdout": metrics.summarize(pick(ps, "holdout"), hold_truth, n_bins),
            "holdout_platt": metrics.summarize(calibrated, hold_truth, n_bins),
            "platt": {"a": round(platt.a, 6), "b": round(platt.b, 6)},
            "holdout_reliability": metrics.reliability_bins(
                pick(ps, "holdout"), hold_truth, n_bins
            ),
        }

    names = sorted(scores)
    verdicts = {n: [p >= 0.5 for p in pick(scores[n], "holdout")] for n in names}
    report["agreement_holdout"] = []
    for a, b in combinations(names, 2):
        kappa = metrics.cohen_kappa(verdicts[a], verdicts[b])
        report["agreement_holdout"].append(
            {"judges": [a, b], "cohen_kappa": None if kappa is None else round(kappa, 6)}
        )
    if len(names) > 1:
        mean = [sum(scores[n][k] for n in names) / len(names) for k in range(len(items))]
        report["ensemble_mean_holdout"] = metrics.summarize(
            pick(mean, "holdout"), hold_truth, n_bins
        )
    best = min(names, key=lambda n: report["judges"][n]["holdout"]["brier"])
    report["best_holdout_brier"] = best
    return report
