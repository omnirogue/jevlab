# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 The OmniSI Authors
"""Scrubbed JEV Lab: an offline benchmark harness for yes/no judgment calibration.

The harness scores judges (JEV, an LLM, a heuristic, a person) against known truth on synthetic
or self-supplied fixtures. It never calls a model provider itself: live judges plug in through
``CommandJudge``, which runs a command you choose. No customer data, rubric or prompt ships here.
"""

__version__ = "0.1.0"
