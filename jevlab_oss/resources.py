# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 The OmniSI Authors
"""Bundled synthetic examples and public rubrics, available from wheels and source."""

import json
from importlib.resources import files

from . import fixtures


def default_fixture() -> dict:
    fixture = json.loads(files("jevlab_oss").joinpath("data/fixtures/synthetic_sample.json").read_text(encoding="utf-8"))
    fixtures.validate(fixture)
    return fixture


def default_pairs() -> list[dict]:
    return json.loads(files("jevlab_oss").joinpath("data/fixtures/bias_pairs.json").read_text(encoding="utf-8"))["pairs"]


def list_rubrics() -> list[dict]:
    # JSON is a YAML 1.2 subset: no YAML dependency or unsafe object loading.
    root = files("jevlab_oss").joinpath("data/rubrics")
    return sorted((json.loads(p.read_text(encoding="utf-8")) for p in root.iterdir()
                   if p.name.endswith(".yaml")), key=lambda r: r["id"])


def show_rubric(rubric_id: str) -> dict:
    for rubric in list_rubrics():
        if rubric["id"] == rubric_id:
            return rubric
    raise ValueError("unknown rubric id; use 'jevlab rubrics list'")
