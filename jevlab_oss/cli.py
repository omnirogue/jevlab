# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 The OmniSI Authors
"""Offline benchmark, calibration, bias diagnostics and public rubric tools."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from . import __version__, bench, fixtures, resources
from .calibration import BiasAuditor, calibrate_fixture
from .report import write_report


def _pairs(path: str) -> list[dict]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("synthetic") is not True or data.get("license") != "Apache-2.0":
        raise ValueError("pair fixture must declare synthetic: true and license: Apache-2.0")
    pairs = data.get("pairs")
    if not isinstance(pairs, list):
        raise ValueError("pair fixture needs a pairs array")
    return pairs


def main(argv: list[str] | None = None) -> int:
    args_in = list(sys.argv[1:] if argv is None else argv)
    # Retain the original CLI and its output schema unchanged.
    if args_in and args_in[0] in ("run", "validate", "template"):
        from .legacy_cli import main as legacy_main
        try:
            return legacy_main(args_in)
        except (ValueError, OSError, RuntimeError, subprocess.SubprocessError) as exc:
            print(f"jevlab: {exc}", file=sys.stderr)
            return 2
    parser = argparse.ArgumentParser(prog="jevlab", description=__doc__)
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("bench", "calibrate"):
        command = sub.add_parser(name)
        command.add_argument("--fixture", help="synthetic fixture JSON (default: bundled sample)")
        command.add_argument("--bins", type=int, default=10)
        command.add_argument("--json", action="store_true", help="print machine-readable results")
        if name == "calibrate":
            command.add_argument("--output", default="calibration_report.html")
            command.add_argument("--pairs", help="optional paired bias fixture JSON")
    bias = sub.add_parser("bias-audit")
    bias.add_argument("--pairs", help="paired bias fixture JSON (default: bundled synthetic sample)")
    bias.add_argument("--json", action="store_true")
    rubrics = sub.add_parser("rubrics").add_subparsers(dest="rubric_command", required=True)
    rubrics.add_parser("list")
    rubrics.add_parser("show").add_argument("id")
    sub.add_parser("run", help="legacy benchmark; run --help for options")
    sub.add_parser("validate", help="legacy fixture validator")
    sub.add_parser("template", help="legacy blank fixture")
    args = parser.parse_args(args_in)
    try:
        if args.command == "rubrics":
            if args.rubric_command == "show":
                print(json.dumps(resources.show_rubric(args.id), indent=2))
            else:
                for rubric in resources.list_rubrics():
                    print(f'{rubric["id"]:36} {rubric["title"]}')
            return 0
        if args.command == "bias-audit":
            result = BiasAuditor().audit(_pairs(args.pairs) if args.pairs else resources.default_pairs())
            if args.json:
                print(json.dumps(result, indent=2, allow_nan=False))
            else:
                print(f'JevLab bias audit · {result["pairs"]} synthetic pairs')
                for name, row in result["judges"].items():
                    p = row["position_swap"]
                    flip = "n/a" if p["flip_rate"] is None else f'{p["flip_rate"]:.1%}'
                    print(f'{name}: swap flips {flip}; first − second bias {p["directional_bias"]:+.3f}; length ρ={row["verbosity"]["spearman"]}; format ρ={row["format"]["spearman"]}')
                print(result["interpretation"])
            return 0
        if not 1 <= args.bins <= 1000:
            raise ValueError("bins must be between 1 and 1000")
        fixture = fixtures.load(args.fixture) if args.fixture else resources.default_fixture()
        if args.command == "bench":
            result = bench.run(fixture, n_bins=args.bins)
            if args.json:
                print(json.dumps(result, indent=2, allow_nan=False))
            else:
                print(f'JevLab benchmark · {result["fixture"]["holdout"]} holdout items')
                for name, row in result["judges"].items():
                    m = row["holdout"]
                    print(f'{name}: accuracy {m["accuracy"]:.1%} · ECE {m["ece"]:.4f} · Brier {m["brier"]:.4f}')
            return 0
        pairs = _pairs(args.pairs) if args.pairs else (None if args.fixture else resources.default_pairs())
        result = calibrate_fixture(fixture, args.bins, pairs)
        write_report(result, args.output)
        if args.json:
            print(json.dumps(result, indent=2, allow_nan=False))
        else:
            print(f'Wrote {args.output} · {len(result["judges"])} judges · Platt, temperature, histogram')
            for name, judge in result["judges"].items():
                delta = judge["methods"]["platt"]["improvement"]
                print(f'{name}: Platt holdout improvement · ECE {delta["ece"]:+.4f} · MCE {delta["mce"]:+.4f} · Brier {delta["brier"]:+.4f}')
        return 0
    except (ValueError, OSError, RuntimeError) as exc:
        print(f"jevlab: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
