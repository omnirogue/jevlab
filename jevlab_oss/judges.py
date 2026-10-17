# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 The OmniSI Authors
"""Judges turn (question, item text) into p(yes).

``RecordedJudge`` replays probabilities stored in the fixture, so a benchmark is reproducible and
offline. ``CommandJudge`` runs a command you supply once per item, writing
``{"question": ..., "text": ...}`` to its stdin and reading ``{"p_yes": float}`` from its stdout:
that is how JEV, an LLM or a human-review queue plugs in. The harness itself opens no network
connection and reads no credentials; a command judge inherits only the environment you give it.
"""

from __future__ import annotations

import json
import shlex
import subprocess


class RecordedJudge:
    def __init__(self, name: str) -> None:
        self.name = name

    def score(self, question: str, item: dict) -> float:
        return float(item["judgments"][self.name])


class CommandJudge:
    def __init__(self, name: str, command: str, timeout: float = 60.0) -> None:
        self.name = name
        self.argv = shlex.split(command)
        if not self.argv:
            raise ValueError("command judge needs a command")
        self.timeout = timeout

    def score(self, question: str, item: dict) -> float:
        payload = json.dumps({"question": question, "text": item["text"]})
        done = subprocess.run(
            self.argv,
            input=payload,
            capture_output=True,
            text=True,
            timeout=self.timeout,
            check=False,
        )
        if done.returncode != 0:
            # Stderr may echo the evaluated text; report only the exit status.
            raise RuntimeError(f"judge {self.name} exited with status {done.returncode}")
        p = json.loads(done.stdout)["p_yes"]
        if not (isinstance(p, (int, float)) and 0.0 <= p <= 1.0):
            raise RuntimeError(f"judge {self.name} returned an invalid p_yes")
        return float(p)
