# Contributing to JevLab

Contributions are licensed under [Apache-2.0](LICENSE), including its patent grant. Sign off each commit with `git commit -s` under the Developer Certificate of Origin. Submit only work you have permission to release.

Use Python 3.10+ and keep the runtime dependency-free. Preserve `jevlab_oss` imports and legacy CLI commands. New numerical code needs known-answer cases, boundary cases and fit/holdout isolation checks. An undefined statistic should be `None`/JSON `null`, with a documented reason. Avoid claims of causal bias from correlations alone.

Source files carry `SPDX-License-Identifier: Apache-2.0` and `Copyright 2026 The OmniSI Authors`. Fixtures are synthetic and use reserved example domains. Never include customer data, internal infrastructure, private rubrics, tokens or credentials. The cloud Rust engine and consensus router are outside the contribution scope.

From this repository's root, run `python3 scripts/audit_release.py`, `python3 -m unittest discover -s tests` and `python3 -m build`. UI changes use the checks in [ui/README.md](ui/README.md) and the GitHub workflow. Maintainers using machines restricted from running suites should run these in GitHub Actions or on an approved build host; local CLI smoke checks suffice only for the local stage.

Public assets in `fixtures/` and `rubrics/` have identical wheel copies under `jevlab_oss/data/`; update both. Keep tests focused and describe exactly which checks passed or remain pending in your pull request. Do not introduce runtime network calls or package installation hooks.
