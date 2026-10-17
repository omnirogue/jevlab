# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 The OmniSI Authors
"""Command line: ``python3 -m jevlab_oss {validate,run,template}``."""

from __future__ import annotations

import argparse
import json
import sys

from . import __version__, bench, fixtures

TEMPLATE = {
    "schema_version": 1,
    "synthetic": True,
    "license": "Apache-2.0",
    "description": "Replace with your own synthetic or self-owned items.",
    "rubric": {
        "id": "my-rubric-v1",
        "questions": [{"id": "q1", "text": "Does the reply answer the question that was asked?"}],
    },
    "items": [
        {
            "id": "item-001",
            "split": "fit",
            "question_id": "q1",
            "text": "Example item text.",
            "truth": True,
            "judgments": {},
        },
        {
            "id": "item-002",
            "split": "holdout",
            "question_id": "q1",
            "text": "Another example item.",
            "truth": False,
            "judgments": {},
        },
    ],
}


def _judge_cmd(value: str) -> tuple[str, str]:
    name, sep, command = value.partition("=")
    if not sep or not name or not command:
        raise argparse.ArgumentTypeError("expected NAME=COMMAND")
    return name, command


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="jevlab_oss", description=__doc__)
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)
    v = sub.add_parser("validate", help="check a fixture against the schema and scrub rules")
    v.add_argument("fixture")
    r = sub.add_parser("run", help="benchmark every judge on a fixture")
    r.add_argument("fixture")
    r.add_argument("--judge-cmd", action="append", type=_judge_cmd, default=[], metavar="N=CMD")
    r.add_argument("--bins", type=int, default=10)
    r.add_argument("--out", help="write the JSON report here instead of stdout")
    sub.add_parser("template", help="print a blank fixture")
    args = parser.parse_args(argv)

    if args.command == "template":
        print(json.dumps(TEMPLATE, indent=2))
        return 0
    try:
        fixture = fixtures.load(args.fixture)
    except (OSError, ValueError) as exc:
        print(f"invalid fixture: {exc}", file=sys.stderr)
        return 2
    if args.command == "validate":
        print(f"ok: {len(fixture['items'])} items, rubric {fixture['rubric']['id']}")
        return 0
    report = bench.run(fixture, dict(args.judge_cmd), args.bins)
    text = json.dumps(report, indent=2)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
