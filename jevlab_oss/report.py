# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 The OmniSI Authors
"""Self-contained, script-free HTML calibration reports with inline SVG charts."""

from __future__ import annotations

from html import escape
from pathlib import Path


def _num(value: float | None) -> str:
    return "n/a" if value is None else f"{value:.4f}"


def reliability_svg(before: list[dict], after: list[dict]) -> str:
    parts = ['<svg viewBox="0 0 420 320" role="img" aria-label="Reliability curve: predicted positive probability versus observed positive rate">',
             '<title>Reliability diagram. Dashed line is perfect calibration.</title>',
             '<rect x="50" y="20" width="340" height="240" rx="6" fill="#111c32"/>']
    for tick in (0, 0.25, 0.5, 0.75, 1):
        x, y = 50 + 340 * tick, 260 - 240 * tick
        parts.append(f'<path d="M{x} 20V260 M50 {y}H390" stroke="#29364e"/>')
        parts.append(f'<text x="{x}" y="282" text-anchor="middle">{tick:g}</text><text x="40" y="{y + 4}" text-anchor="end">{tick:g}</text>')
    parts.append('<path d="M50 260L390 20" stroke="#91a1bc" stroke-dasharray="5 5"/>')
    for bins, color, label in ((before, "#f8b86a", "Before"), (after, "#66e2ca", "After")):
        coords = " ".join(f'{50 + 340 * b["mean_p"]:.2f},{260 - 240 * b["observed"]:.2f}' for b in bins)
        parts.append(f'<polyline points="{coords}" fill="none" stroke="{color}" stroke-width="2.5"/>')
        for b in bins:
            parts.append(f'<circle cx="{50 + 340 * b["mean_p"]:.2f}" cy="{260 - 240 * b["observed"]:.2f}" r="5" fill="{color}"><title>{label}: n={b["count"]}, predicted={b["mean_p"]:.3f}, observed={b["observed"]:.3f}</title></circle>')
    parts.append('<text x="220" y="310" text-anchor="middle">Predicted positive probability</text><text transform="translate(12,145) rotate(-90)" text-anchor="middle">Observed positive rate</text></svg>')
    return "".join(parts)


def render_report(report: dict) -> str:
    """Render a calibrate_fixture result. User-controlled labels are HTML escaped."""
    e = lambda value: escape(str(value), quote=True)
    sections = []
    for name, judge in report["judges"].items():
        methods = []
        for method, result in judge["methods"].items():
            cards = []
            for metric in ("ece", "mce", "brier"):
                delta = result["improvement"][metric]
                tone = "good" if delta >= 0 else "bad"
                cards.append(f'<div class="metric"><span>{metric.upper()}</span><strong>{_num(result["before"][metric])} → {_num(result["after"][metric])}</strong><small class="{tone}">{delta:+.4f} improvement</small></div>')
            decision = result["decision"]
            threshold_label = "Always negative" if decision["threshold"] > 1 else f'{decision["threshold"]:.6g}'
            methods.append(f'''<details {"open" if method == "platt" else ""}><summary>{e(method.title())} scaling / calibration</summary>
                <div class="metrics">{"".join(cards)}</div><div class="chart-grid">
                <div>{reliability_svg(result["before"]["reliability"], result["after"]["reliability"])}<p class="legend"><span>● Before</span> <span>● After</span> · dashed: ideal</p></div>
                <div><h3>Decision threshold</h3><p class="threshold">{threshold_label}</p><p>Recommend positive when calibrated p ≥ <code>{e(decision["threshold"])}</code> (exact threshold).</p>
                <p>Selected on fit data to minimize equal-cost errors. Fit accuracy: {_num(decision["fit_accuracy"])}. Holdout accuracy at this threshold: {_num(decision["holdout_accuracy"])}.</p>
                <p class="muted">A threshold above 1 means always negative. This is an empirical recommendation, not a guarantee for new data.</p></div></div></details>''')
        sections.append(f'<section><h2>{e(name)}</h2>{"".join(methods)}</section>')

    agreement = report["agreement"]
    names = list(agreement["pairwise"])
    header = "".join(f'<th scope="col">{e(name)}</th>' for name in names)
    rows = []
    for a in names:
        cells = []
        for b in names:
            value = agreement["pairwise"][a][b]
            opacity = 0 if value is None else (value + 1) / 2 * 0.65
            cells.append(f'<td style="background:rgba(65,190,171,{opacity:.3f})">{_num(value)}</td>')
        rows.append(f'<tr><th scope="row">{e(a)}</th>{"".join(cells)}</tr>')
    heatmap = f'<div class="scroll"><table><caption>Pairwise Cohen’s κ on raw holdout verdicts (p ≥ 0.5)</caption><thead><tr><th>Judge</th>{header}</tr></thead><tbody>{"".join(rows)}</tbody></table></div>'
    pareto = ""
    if agreement["pareto"]:
        cost_rows = "".join(f'<tr><td>{e(r["judge"])}</td><td>{r["cost"]:g}</td><td>{r["accuracy"]:.4f}</td><td>{r["pareto_rank"]}</td></tr>' for r in agreement["pareto"])
        pareto = f'<div class="scroll"><table><caption>Cost / accuracy Pareto layers · rank 1 is the frontier</caption><thead><tr><th>Judge</th><th>Cost</th><th>Accuracy</th><th>Rank</th></tr></thead><tbody>{cost_rows}</tbody></table></div>'
    bias = '<p class="muted">No paired judgments supplied. Pass --pairs to include bias diagnostics.</p>'
    if report.get("bias"):
        bias_rows = []
        for name, item in report["bias"]["judges"].items():
            p = item["position_swap"]
            vals = [p["flip_rate"], p["directional_bias"], item["verbosity"]["spearman"],
                    item["format"]["spearman"], item["self_preference"]["mean_own_probability"]]
            bias_rows.append(f'<tr><th scope="row">{e(name)}</th><td>{item["pairs"]}</td><td>{p["tie_pairs"]}</td>' + "".join(f'<td>{_num(v)}</td>' for v in vals) + '</tr>')
        bias = f'<div class="scroll"><table><caption>Position swaps and response-style associations</caption><thead><tr><th>Judge</th><th>Pairs</th><th>Tie pairs</th><th>Flip rate</th><th>First − second bias</th><th>Length ρ</th><th>Format ρ</th><th>Own-model p</th></tr></thead><tbody>{"".join(bias_rows)}</tbody></table></div><p class="muted">Ties are excluded from flip rates. Positive directional bias favors the first position. Correlation is not causation; self-preference requires model identities. n/a means undefined or missing evidence.</p>'
    f = report["fixture"]
    notes = "".join(f'<li>{e(note)}</li>' for note in report["notes"])
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; img-src data:; base-uri 'none'; form-action 'none'">
<title>JevLab · Calibration &amp; Reliability Report</title><style>
:root{{color-scheme:dark}}*{{box-sizing:border-box}}body{{margin:0;background:#0a1020;color:#e4edf9;font:16px/1.6 system-ui,sans-serif}}main{{max-width:1140px;margin:auto;padding:48px 24px}}header{{padding:24px 0 36px;border-bottom:1px solid #2b3853}}.eyebrow{{color:#66e2ca;letter-spacing:.16em;font-size:12px;font-weight:700}}h1{{font-size:clamp(30px,5vw,48px);line-height:1.15;max-width:800px}}h2{{font-size:25px}}h3{{font-size:18px}}section{{margin:32px 0;background:#10192d;border:1px solid #2b3853;border-radius:18px;padding:24px}}p,.muted,li{{color:#aebed6}}.tag{{display:inline-block;border:1px solid #425778;border-radius:99px;padding:4px 12px;margin:4px;font-size:13px}}.metrics{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px;margin:20px 0}}.metric{{padding:18px;background:#17233b;border-radius:12px}}.metric span,.metric small{{display:block}}.metric strong{{display:block;font-size:20px;margin:8px 0}}.good{{color:#66e2ca}}.bad{{color:#ffab9e}}.chart-grid{{display:grid;grid-template-columns:1.2fr 1fr;gap:30px;align-items:center}}svg{{width:100%;height:auto}}svg text{{fill:#aebed6;font-size:12px}}.threshold{{font-size:40px;color:#66e2ca;font-weight:650;margin:8px 0}}.legend{{text-align:center;font-size:13px}}.legend span:first-child{{color:#f8b86a}}.legend span:nth-child(2){{color:#66e2ca}}summary{{cursor:pointer;font-weight:650;padding:16px 0}}details+details{{border-top:1px solid #2b3853}}table{{border-collapse:collapse;width:100%;font-size:14px}}caption{{text-align:left;color:#aebed6;padding:12px 0}}th,td{{text-align:left;border:1px solid #34435e;padding:12px}}td{{font-variant-numeric:tabular-nums}}.scroll{{overflow:auto;margin:18px 0}}footer{{color:#aebed6;font-size:13px}}@media(max-width:700px){{main{{padding:24px 14px}}section{{padding:16px}}.metrics,.chart-grid{{grid-template-columns:1fr}}}}@media print{{body{{background:white;color:#111}}section{{break-inside:avoid}}}}
</style></head><body><main><header><div class="eyebrow">JEVLAB / EVALUATION STUDIO</div><h1>Calibration &amp;<br>Reliability Report</h1><p>How well does your judge know what it knows?</p><span class="tag">Synthetic fixture</span><span class="tag">{e(f["rubric_id"])}</span><span class="tag">{f["fit"]} fit / {f["holdout"]} holdout</span><span class="tag">{report["n_bins"]} bins</span></header>
{"".join(sections)}<section><h2>Inter-judge agreement</h2><p>Fleiss’ κ: <strong>{_num(agreement["fleiss_kappa"])}</strong>. Agreement measures consistency, not correctness; degenerate κ is n/a.</p>{heatmap}{pareto}<p class="muted">{e(agreement["cost_note"])}</p></section>
<section><h2>Position swap &amp; bias diagnostics</h2>{bias}</section><section><h2>Reading this report</h2><ul>{notes}</ul><p>ECE is a count-weighted calibration gap; MCE is the largest occupied-bin gap. Brier is mean squared probability error. Lower is better for all three. Orange is before, mint is after.</p></section><footer>JevLab 0.1.0 · Apache-2.0 · Offline report · No scripts, remote fonts, telemetry or network requests.</footer></main></body></html>'''


def write_report(report: dict, path: str | Path) -> Path:
    path = Path(path)
    path.write_text(render_report(report), encoding="utf-8")
    return path
