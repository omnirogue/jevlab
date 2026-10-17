# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 The OmniSI Authors
"""Fixture schema validation.

A fixture is one JSON file: a public rubric of yes/no questions and items with known truth. Only
synthetic or self-owned data belongs in a fixture; ``validate`` refuses files that do not declare
``"synthetic": true`` or that contain an email address outside the reserved example domains.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

SCHEMA_VERSION = 1
SPLITS = ("fit", "holdout")
_EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@([A-Za-z0-9.-]+\.[A-Za-z]{2,})")
_RESERVED = re.compile(r"(^|\.)example\.(com|org|net)$|\.(example|test|invalid)$", re.IGNORECASE)


class FixtureError(ValueError):
    pass


def load(path: str | Path) -> dict:
    with open(path, encoding="utf-8") as fh:
        fixture = json.load(fh)
    validate(fixture)
    return fixture


def validate(fixture: dict) -> None:
    def need(cond: bool, msg: str) -> None:
        if not cond:
            raise FixtureError(msg)

    need(isinstance(fixture, dict), "fixture must be a JSON object")
    need(fixture.get("schema_version") == SCHEMA_VERSION, "schema_version must be 1")
    need(fixture.get("synthetic") is True, 'fixture must declare "synthetic": true')
    need(fixture.get("license") == "Apache-2.0", 'fixture license must be "Apache-2.0"')
    for domain in _EMAIL.findall(json.dumps(fixture)):
        need(bool(_RESERVED.search(domain)), f"non-example email domain in fixture: {domain}")

    rubric = fixture.get("rubric")
    need(isinstance(rubric, dict) and isinstance(rubric.get("id"), str), "rubric.id is required")
    questions = rubric.get("questions")
    need(isinstance(questions, list) and questions, "rubric.questions must be a non-empty list")
    qids = set()
    for q in questions:
        need(isinstance(q, dict), "each rubric question must be an object")
        need(isinstance(q.get("id"), str) and isinstance(q.get("text"), str), "bad question")
        need(q["id"] not in qids, f"duplicate question id {q['id']}")
        qids.add(q["id"])

    items = fixture.get("items")
    need(isinstance(items, list) and items, "items must be a non-empty list")
    ids = set()
    judges: set[str] | None = None
    for item in items:
        need(isinstance(item, dict), "each item must be an object")
        iid = item.get("id")
        need(isinstance(iid, str) and iid not in ids, f"missing or duplicate item id {iid!r}")
        ids.add(iid)
        qid = item.get("question_id")
        need(isinstance(qid, str) and qid in qids, f"{iid}: unknown question_id")
        need(item.get("split") in SPLITS, f"{iid}: split must be one of {SPLITS}")
        need(isinstance(item.get("truth"), bool), f"{iid}: truth must be true or false")
        need(isinstance(item.get("text"), str) and item["text"].strip(), f"{iid}: text required")
        recorded = item.get("judgments", {})
        need(isinstance(recorded, dict), f"{iid}: judgments must be an object")
        for name, p in recorded.items():
            ok = isinstance(p, (int, float)) and not isinstance(p, bool) and 0 <= p <= 1
            need(ok, f"{iid}: judgment {name} must be a probability")
        if judges is None:
            judges = set(recorded)
        need(set(recorded) == judges, f"{iid}: every item must record the same judges")
    for split in SPLITS:
        need(any(i["split"] == split for i in items), f"no items in split {split}")
