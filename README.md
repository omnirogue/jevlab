# JevLab

**Evaluate the judge. Measure bias. Calibrate confidence.**

JevLab is an offline, standard-library Python toolkit for LLM-as-judge evaluation, bias diagnostics and calibration. Compare recorded judges with golden labels, fit probability calibrators, inspect an HTML reliability report, and expose the same tools to an MCP client.

[Apache-2.0](LICENSE) · Python 3.10+ · [Repository](https://github.com/omnirogue/jevlab)

## Quickstart

Install from this checkout (a package-registry release is not assumed):

```bash
python3 -m pip install .
jevlab bench
jevlab bench --fixture fixtures/synthetic_sample.json --json
jevlab calibrate --output calibration_report.html
jevlab calibrate --fixture fixtures/synthetic_sample.json --pairs fixtures/bias_pairs.json --json > calibration_report.json
jevlab bias-audit --pairs fixtures/bias_pairs.json --json
jevlab rubrics list
jevlab rubrics show code_review_correctness
```

Open `calibration_report.html` in a browser. It is a self-contained dark report with inline SVG reliability curves, before/after ECE, MCE and Brier, agreement heatmaps, bias tables and fit-selected thresholds. It requires no server, JavaScript, remote fonts or network access. Expand each method to compare Platt, temperature and histogram calibration. The [React studio](ui/README.md) consumes the JSON version.

Without installation: `PYTHONPATH=. python3 -m jevlab_oss.cli bench`. `python3 -m jevlab`, `jevlab`, and `jevlab-oss` use the same CLI. Both `jevlab.*` and historical `jevlab_oss.*` imports work. The original `metrics.py`, `fixtures.py`, `judges.py`, and `bench.py` are preserved; the enhanced API lives in `calibration.py`.

## Calibration, with an honest holdout

For binary judgments, supply **p(yes)** and a boolean golden label, not confidence in whichever class won. Humans supply the labels; bundled labels and judge outputs are simulated. Fit calibrators and select decision thresholds on `split: "fit"`. Only then evaluate on `split: "holdout"`. Keep cases, related variants and near duplicates in the same split to prevent leakage.

For occupied equal-width bins Bₘ, with mean predicted probability p̄ₘ and observed positive frequency ȳₘ:

- **ECE** = Σₘ (|Bₘ| / N) · |p̄ₘ − ȳₘ|.
- **MCE** = maxₘ |p̄ₘ − ȳₘ|; empty bins are omitted.
- **Brier** = (1/N) Σᵢ (pᵢ − yᵢ)².
- **Platt scaling**: p′ = sigmoid(a · logit(p) + b).
- **Temperature scaling**: p′ = sigmoid(logit(p) / T), T > 0; the intercept is fixed at zero.
- **Histogram calibration**: p′ = (positive count + α) / (bin count + 2α), α = 1 by default. Empty fit bins retain p.

Platt and temperature scaling use pure-Python gradient descent with backtracking on binary cross-entropy and a tiny ridge penalty. Logits clip probabilities to [10⁻⁶, 1−10⁻⁶]. Temperature scaling preserves ranking; unconstrained Platt can invert a systematically reversed judge. Histogram calibration need not preserve ranking. The legacy calibrator in `metrics.py` retains its original damped Newton implementation.

```python
from jevlab.calibration import PlattCalibrator, HistogramCalibrator, TemperatureCalibrator

fit_scores = [.99, .99, .99, .01, .01, .01]
fit_labels = [True, True, False, False, False, True]
# Use independently labeled cases for evaluation, even when scores happen to match.
holdout_scores = [.98, .97, .96, .02, .03, .04]
holdout_labels = [True, False, True, False, True, False]
model = PlattCalibrator().fit(fit_scores, fit_labels)
comparison = model.evaluate(holdout_scores, holdout_labels)
print(comparison["improvement"])  # before minus after: negative means worse
```

A positive improvement means lower error. ECE depends on binning and sample size; a better ECE does not guarantee a better Brier score. The report displays regressions without clipping them. Do not repeatedly pick models against the same holdout and call that an unbiased evaluation. Use a separate validation split for model selection and a final untouched test set for a release decision. See [Guo et al., 2017](https://proceedings.mlr.press/v70/guo17a.html) for background on temperature scaling.

The threshold recommendation minimizes empirical equal-cost errors **on fit data**, with deterministic tie breaking toward 0.5. It includes all-positive and all-negative rules (a threshold just above 1 means always negative). The report separately shows holdout accuracy at that threshold. `optimal_threshold(..., false_positive_cost=..., false_negative_cost=...)` supports explicit positive error costs. It does not infer your business cost model.

## Bias diagnostics

A pair fixture has `synthetic: true`, `license: "Apache-2.0"`, and a `pairs` array:

```json
{
  "synthetic": true,
  "license": "Apache-2.0",
  "pairs": [{
    "judge": "judge-a", "a": "Four.", "b": "## Answer\n- Four.",
    "forward": 0.8, "swapped": 0.2,
    "judge_model": "model-a", "a_model": "model-a", "b_model": "model-b"
  }]
}
```

`forward` is p(first wins) for **A/B**; `swapped` is p(first wins) for **B/A**. The same candidate winning both orders is consistent. If both probabilities exceed 0.5, the judge picked the first position twice: the candidate winner flipped. Exact 0.5 is a tie, excluded from decisive flip rates and reported separately.

`BiasAuditor().audit(pairs)` returns per-judge:

- Position swap flip rate; first/second win rates; signed first-minus-second bias; mean probability inconsistency.
- Spearman rank correlation (average ranks for ties) between **character-length delta** and order-averaged A preference `(forward + 1 − swapped) / 2`.
- Correlation with markdown/list-line density delta. Density is the fraction of nonblank lines containing recognizable markdown markers.
- Self-preference using `judge_model`, `a_model`, and `b_model`: only pairs with exactly one own-model response are eligible. Reports mean own-response preference and correlation with own-model position.

Constant vectors, insufficient samples and absent provenance produce `null`, not a fabricated zero. Style correlation alone cannot establish self-preference. Match quality and content across controlled pairs; observational correlations are not proof of causal bias. The default bias demo is separate from the calibration fixture and is explicitly synthetic; custom calibration fixtures get no demo bias rows unless supplied via `--pairs`.

## Agreement and cost frontier

```python
from jevlab import AgreementMatrix
matrix = AgreementMatrix({"small": [True, False, True], "large": [True, False, False]})
print(matrix.pairwise())       # Cohen's kappa, including undefined (None) cells
print(matrix.fleiss_kappa())   # binary multi-rater kappa
print(matrix.pareto_frontier({"small": 0.01, "large": 0.05}, [True, False, False]))
```

All raters must label the same aligned items; missing ratings are rejected. Cohen’s κ = (observed agreement − chance agreement) / (1 − chance agreement). Fleiss’ κ uses each item's pairwise agreement and pooled category proportions; it is undefined with fewer than two raters or perfect chance agreement. Agreement is not accuracy.

For cost comparisons, supply `judge_costs` in your fixture as a map of every judge name to a finite, non-negative cost in **one common unit on the same workload**. A judge dominates another only if it is no more expensive and no less accurate, with at least one strict improvement. Rank 1 is the Pareto frontier; subsequent ranks remove preceding frontiers. Duplicate points share a rank. Missing costs produce no ranking; nothing is assumed to be free.

## Fixture schema and existing integrations

```json
{
  "schema_version": 1, "synthetic": true, "license": "Apache-2.0",
  "rubric": {"id": "example", "questions": [{"id": "q1", "text": "Does the answer cite evidence?"}]},
  "judge_costs": {"judge-a": 0.01},
  "items": [
    {"id": "f1", "split": "fit", "question_id": "q1", "text": "Example evidence.", "truth": true, "judgments": {"judge-a": 0.9}},
    {"id": "h1", "split": "holdout", "question_id": "q1", "text": "Another example.", "truth": false, "judgments": {"judge-a": 0.4}}
  ]
}
```

The two-row snippet illustrates structure, not an adequate calibration dataset. Every item must record the same judges and both splits must exist. Existing fixture scrub rules are preserved: the release harness requires synthetic fixtures under Apache-2.0 and rejects non-example email domains. A declaration alone is not a privacy scrub; inspect all data before sharing. The Python calibrator API can process separately governed local arrays without publishing them as fixtures.

Legacy commands remain available:

```bash
jevlab validate fixtures/synthetic_sample.json
jevlab template
jevlab run fixtures/synthetic_sample.json --out benchmark.json
jevlab run fixtures/synthetic_sample.json --judge-cmd 'custom=python3 adapter.py'
```

A `CommandJudge` receives `{"question": ..., "text": ...}` on stdin and must return `{"p_yes": 0.8}`. The executable inherits the launching environment; use only trusted adapters and environment variable names for provider secrets. The core harness has no provider SDK or networking dependency. MCP deliberately does not expose command judges.

## Ten public rubric templates

`rubrics/*.yaml` are JSON-form YAML 1.2 for dependency-free, safe loading. Each has a purpose, scoring instructions and three evidence-based yes/no questions. Adapt them to your task and validate with human labels:

| ID | Measures |
| --- | --- |
| `code_review_correctness` | Grounded findings, behavior and actionable fixes |
| `rag_citation_grounding` | Source support, citation entailment and uncertainty |
| `patch_minimalism` | Scope, necessary changes and compatibility |
| `security_diff_review` | Trust boundaries, plausible impact and mitigations |
| `tool_call_precision` | Tool fit, arguments and result handling |
| `sql_equivalence` | Row multisets, NULL semantics and ordering |
| `summarization_faithfulness` | Source support, coverage and qualifiers |
| `api_contract_safety` | Schemas, error semantics and authorization contracts |
| `test_quality` | Observable behavior, regression detection and boundaries |
| `agent_trajectory_efficiency` | Progress, evidence and justified tool use |

These are generic, newly authored templates, not production compliance rubrics.

## MCP setup

After `pip install .`, configure a client supporting local stdio servers:

```json
{
  "mcpServers": {
    "jevlab": { "command": "jevlab-mcp", "args": [] }
  }
}
```

Use the installed executable's absolute path if the client has a different PATH. Alternatively use `python3 -m jevlab_oss.mcp_server` from an environment where JevLab is installed. There is no HTTP endpoint or API key to configure.

| Tool | Optional arguments | Result |
| --- | --- | --- |
| `jevlab_bench` | `fixture` object, `n_bins` | Legacy benchmark JSON |
| `jevlab_calibrate` | `fixture` object, `n_bins`, `pairs` array | Calibration JSON, including agreement and bias |
| `jevlab_bias_audit` | `pairs` array | Paired bias JSON |
| `jevlab_list_rubrics` | none | All ten rubric objects |

Omitted data uses bundled synthetic demos. Tools accept inline data only, with a 1 MiB character message limit, 1,000 items/pairs and 16 recorded judges. Larger runs use the Python API. MCP tools are read-only and perform no command execution, path reads, report writes or network calls. Use the CLI to create HTML.

The server implements the [MCP 2025-06-18 stdio transport](https://modelcontextprotocol.io/specification/2025-06-18/basic/transports): one JSON-RPC message per line, protocol-only stdout, initialization followed by `notifications/initialized`, `ping`, `tools/list`, and `tools/call`. Results include text plus structured JSON. Tool validation failures return `isError`; protocol failures use JSON-RPC error codes. Notifications produce no replies and do not execute tools.

## Open-Source JevLab vs. OmniSI Cloud JEV Oracle (Proprietary Rust Engine)

| Capability | Open-source JevLab (Apache-2.0) | OmniSI Cloud JEV Oracle |
| --- | --- | --- |
| Offline evaluation and synthetic fixtures | Included, pure Python | Managed integration |
| Calibration, bias diagnostics and agreement | Included | Managed production workflows |
| HTML reliability reports and React studio | Included | Hosted application integration |
| Public rubric starter templates | Ten included | Separate proprietary production compliance rubrics |
| Local stdio MCP tools | Included | Separate authenticated cloud interfaces |
| Multi-tenant Rust oracle and ledger | **Excluded** | Proprietary |
| Live consensus router | **Excluded** | Proprietary |
| Customer corpora, provider credentials, internal prompts | **Excluded** | Private, outside this release |

**No Rust source, crates, Cargo manifests, proprietary router logic or production compliance rubrics are distributed.** There is no Rust dependency or build step. JevLab can evaluate outputs from any judge; it does not require the cloud service.

## Development and verification

```bash
python3 scripts/audit_release.py
python3 -m unittest discover -s tests
python3 -m pip install build
python3 -m build
cd ui
npm install --ignore-scripts --package-lock=false
npm run typecheck
npx playwright install chromium
npx playwright test
```

CI runs on GitHub Actions with Python 3.10/3.12/3.13, tests the wheel outside the source tree, checks the standalone component, and exercises report imports, tabs and desktop/mobile rendering. CI builds artifacts only; it never deploys or publishes a package. `.github/workflows/ci.yml` works at this repository's root without any parent repository files.

The source `fixtures/` and `rubrics/` assets are mirrored into `jevlab_oss/data/` for wheel installation. Update both copies together; the release audit rejects drift. See [CONTRIBUTING.md](CONTRIBUTING.md), [SECURITY.md](SECURITY.md), [NOTICE](NOTICE), and the explicit export boundary in [audit-manifest.json](audit-manifest.json).
