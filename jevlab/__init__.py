# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 The OmniSI Authors
"""Public JevLab namespace; legacy jevlab_oss imports remain supported."""

import importlib
import sys

from jevlab_oss import __version__
from jevlab_oss.calibration import (
    AgreementMatrix, BiasAuditor, HistogramCalibrator, PlattCalibrator, TemperatureCalibrator,
)

for _module in ("metrics", "fixtures", "judges", "bench", "calibration", "report", "resources"):
    globals()[_module] = importlib.import_module(f"jevlab_oss.{_module}")
    sys.modules[f"{__name__}.{_module}"] = globals()[_module]

__all__ = ["AgreementMatrix", "BiasAuditor", "HistogramCalibrator", "PlattCalibrator", "TemperatureCalibrator", "__version__"]
