// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 The OmniSI Authors
// Standalone adaptation of the JEV Lab calibration studio. React is the only import.
import { useId, useState } from "react";

export interface ReliabilityBin {
  lower: number; upper: number; count: number; mean_p: number; observed: number;
}
export interface CalibrationMetrics {
  n: number; ece: number; mce: number; brier: number; accuracy: number;
  reliability: ReliabilityBin[];
}
export interface MethodResult {
  before: CalibrationMetrics; after: CalibrationMetrics;
  improvement: { ece: number; mce: number; brier: number };
  decision: { threshold: number; fit_accuracy: number; holdout_accuracy: number };
}
export interface BiasResult {
  pairs: number;
  position_swap: { flip_rate: number | null; directional_bias: number; tie_pairs: number };
  verbosity: { spearman: number | null }; format: { spearman: number | null };
  self_preference: { eligible_pairs: number; mean_own_probability: number | null };
}
export interface CalibrationReport {
  schema_version: 1;
  fixture: { rubric_id: string; fit: number; holdout: number; synthetic: boolean };
  n_bins: number;
  judges: Record<string, { before: CalibrationMetrics; methods: Record<Method, MethodResult> }>;
  agreement: {
    pairwise: Record<string, Record<string, number | null>>; fleiss_kappa: number | null;
    pareto: { judge: string; cost: number; accuracy: number; pareto_rank: number }[];
    cost_note: string;
  };
  bias: { pairs: number; judges: Record<string, BiasResult> } | null;
  notes: string[];
}
export interface JevLabStudioProps {
  /** A result from jevlab calibrate --json or the jevlab_calibrate MCP tool. */
  report?: CalibrationReport;
  /** Receives validated imports; no file or network operations are performed by the component. */
  onReportChange?: (report: CalibrationReport) => void;
}
type Method = "platt" | "temperature" | "histogram";
const METHODS: Method[] = ["platt", "temperature", "histogram"];
const record = (v: unknown): v is Record<string, unknown> => typeof v === "object" && v !== null && !Array.isArray(v);
const finite = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v);
const maybe = (v: unknown) => v === null || finite(v);
const unit = (v: unknown) => finite(v) && v >= 0 && v <= 1;
const count = (v: unknown) => finite(v) && Number.isInteger(v) && v >= 0;
const fmt = (v: number | null) => v === null ? "n/a" : v.toFixed(4);

function validMetrics(v: unknown): boolean {
  return record(v) && count(v.n) && [v.ece, v.mce, v.brier, v.accuracy].every(unit) &&
    Array.isArray(v.reliability) && v.reliability.every(b => record(b) && count(b.count) &&
      [b.lower, b.upper, b.mean_p, b.observed].every(unit));
}
/** Validate all fields rendered by the studio; arbitrary HTML is never rendered. */
export function parseCalibrationReport(value: unknown): CalibrationReport {
  const fail = (): never => { throw new Error("Expected a JevLab v1 calibration report. Export it with jevlab calibrate --json."); };
  if (!record(value) || value.schema_version !== 1 || !record(value.fixture) ||
    typeof value.fixture.rubric_id !== "string" || typeof value.fixture.synthetic !== "boolean" ||
    !count(value.fixture.fit) || !count(value.fixture.holdout) || !count(value.n_bins) ||
    !record(value.judges) || Object.keys(value.judges).length === 0 ||
    !Array.isArray(value.notes) || !value.notes.every(n => typeof n === "string")) return fail();
  for (const judge of Object.values(value.judges)) {
    if (!record(judge) || !validMetrics(judge.before) || !record(judge.methods)) return fail();
    for (const method of METHODS) {
      const m = judge.methods[method];
      if (!record(m) || !validMetrics(m.before) || !validMetrics(m.after) || !record(m.improvement) ||
        ![m.improvement.ece, m.improvement.mce, m.improvement.brier].every(finite) || !record(m.decision) ||
        !finite(m.decision.threshold) || !unit(m.decision.fit_accuracy) || !unit(m.decision.holdout_accuracy)) return fail();
    }
  }
  const agreement = value.agreement;
  if (!record(agreement) || !record(agreement.pairwise) || !maybe(agreement.fleiss_kappa) ||
    typeof agreement.cost_note !== "string" || !Array.isArray(agreement.pareto)) return fail();
  for (const name of Object.keys(value.judges)) {
    const row = agreement.pairwise[name];
    if (!record(row) || !Object.keys(value.judges).every(n => maybe(row[n]))) return fail();
  }
  if (!agreement.pareto.every(r => record(r) && typeof r.judge === "string" && finite(r.cost) &&
    r.cost >= 0 && unit(r.accuracy) && count(r.pareto_rank))) return fail();
  if (value.bias !== null) {
    if (!record(value.bias) || !count(value.bias.pairs) || !record(value.bias.judges)) return fail();
    for (const row of Object.values(value.bias.judges)) {
      if (!record(row) || !count(row.pairs) || !record(row.position_swap) ||
        !maybe(row.position_swap.flip_rate) || !finite(row.position_swap.directional_bias) ||
        !count(row.position_swap.tie_pairs) || !record(row.verbosity) || !maybe(row.verbosity.spearman) ||
        !record(row.format) || !maybe(row.format.spearman) || !record(row.self_preference) ||
        !count(row.self_preference.eligible_pairs) || !maybe(row.self_preference.mean_own_probability)) return fail();
    }
  }
  return value as unknown as CalibrationReport;
}

function ReliabilityCurve({ before, after }: { before: ReliabilityBin[]; after: ReliabilityBin[] }) {
  const titleId = useId();
  return <svg viewBox="0 0 440 340" role="img" aria-labelledby={titleId}>
    <title id={titleId}>Reliability curve: before in amber, after in mint; dashed line is ideal</title>
    {[0, .25, .5, .75, 1].map(t => <g key={t}>
      <path d={`M${55 + 350 * t} 20V275 M55 ${275 - 255 * t}H405`} stroke="#2a3850" />
      <text x={55 + 350 * t} y={298} textAnchor="middle">{t}</text>
      <text x={42} y={279 - 255 * t} textAnchor="end">{t}</text>
    </g>)}
    <path d="M55 275L405 20" stroke="#8ca0bd" strokeDasharray="5 5" />
    {[{ bins: before, color: "#f8b86a", label: "Before" }, { bins: after, color: "#66e2ca", label: "After" }].map(({ bins, color, label }) =>
      <g key={label}>
        <polyline points={bins.map(b => `${55 + b.mean_p * 350},${275 - b.observed * 255}`).join(" ")} fill="none" stroke={color} strokeWidth="3" />
        {bins.map((b, i) => <circle key={i} cx={55 + b.mean_p * 350} cy={275 - b.observed * 255} r="5" fill={color}>
          <title>{label}: {b.count} samples; predicted {fmt(b.mean_p)}, observed {fmt(b.observed)}</title>
        </circle>)}
      </g>)}
    <text x="230" y="330" textAnchor="middle">Predicted positive probability</text>
    <text transform="translate(14,148) rotate(-90)" textAnchor="middle">Observed positive rate</text>
  </svg>;
}

const CSS = `
.jevlab{color-scheme:dark;background:#0a1020;color:#e4edf9;font:15px/1.6 system-ui,sans-serif;padding:clamp(20px,4vw,48px);border-radius:20px;max-width:1200px;margin:auto}.jevlab *{box-sizing:border-box}.jevlab h1{font-size:clamp(30px,5vw,48px);line-height:1.15;margin:16px 0}.jevlab h2{font-size:23px}.jevlab p,.jevlab small{color:#afbed4}.jevlab .eyebrow{color:#66e2ca;letter-spacing:.14em;font-size:12px}.jevlab .toolbar{display:flex;gap:16px;flex-wrap:wrap;align-items:center;margin:24px 0}.jevlab button,.jevlab select,.jevlab textarea{font:inherit;color:inherit;background:#17243c;border:1px solid #435572;border-radius:8px;padding:10px 14px}.jevlab button{cursor:pointer}.jevlab button:focus-visible,.jevlab select:focus-visible,.jevlab textarea:focus-visible{outline:2px solid #66e2ca;outline-offset:3px}.jevlab button[aria-pressed=true]{background:#66e2ca;color:#092522;border-color:#66e2ca}.jevlab .panel{padding:22px;background:#101b30;border:1px solid #2c3c57;border-radius:14px;margin:22px 0}.jevlab .metrics{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:16px}.jevlab .metric{background:#17243c;border-radius:12px;padding:18px}.jevlab strong{display:block;font-size:23px;margin:8px 0}.jevlab .good{color:#66e2ca}.jevlab .bad{color:#ffab9e}.jevlab .chart{display:grid;grid-template-columns:1.3fr 1fr;gap:28px;align-items:center}.jevlab svg{width:100%;height:auto}.jevlab svg text{fill:#afbed4;font-size:12px}.jevlab table{border-collapse:collapse;width:100%;font-size:14px}.jevlab th,.jevlab td{padding:12px;border:1px solid #384861;text-align:left}.jevlab caption{text-align:left;padding:12px 0;color:#afbed4}.jevlab .scroll{overflow:auto}.jevlab textarea{width:100%;resize:vertical}.jevlab .legend{display:flex;gap:20px}.jevlab .error{color:#ffab9e}.jevlab summary{cursor:pointer}.jevlab .threshold{font-size:40px;color:#66e2ca}.jevlab code{overflow-wrap:anywhere}.jevlab label{display:flex;gap:10px;align-items:center}@media(max-width:720px){.jevlab .metrics,.jevlab .chart{grid-template-columns:1fr}.jevlab .panel{padding:14px}}
`;

/** Offline report studio. No application imports, provider clients, persistence or cloud endpoints. */
export function JevLabStudio({ report, onReportChange }: JevLabStudioProps) {
  const [imported, setImported] = useState<CalibrationReport>();
  const [text, setText] = useState("");
  const [error, setError] = useState("");
  const [judgeName, setJudgeName] = useState("");
  const [method, setMethod] = useState<Method>("platt");
  const [tab, setTab] = useState("Reliability");
  const data = imported ?? report;
  const names = data ? Object.keys(data.judges) : [];
  const name = names.includes(judgeName) ? judgeName : names[0];
  const chosen = data?.judges[name]?.methods[method];
  const editorId = useId();
  function loadReport() {
    try {
      if (text.length > 2_000_000) throw new Error("Report is too large (2 MB limit).");
      const parsed = parseCalibrationReport(JSON.parse(text));
      setImported(parsed); setError(""); onReportChange?.(parsed);
    } catch (e) { setError(e instanceof Error ? e.message : "Unable to read report."); }
  }
  return <div className="jevlab">
    <style>{CSS}</style>
    <header><span className="eyebrow">JEVLAB / OPEN EVALUATION STUDIO</span><h1>Can you trust<br />your judge’s confidence?</h1>
      <p>Inspect calibration, agreement and bias from your own evaluation runs.</p>
      {data && <small>{data.fixture.synthetic ? "Synthetic fixture" : "User-supplied fixture"} · {data.fixture.rubric_id} · {data.fixture.fit} fit / {data.fixture.holdout} holdout · {data.n_bins} bins</small>}
    </header>
    <details className="panel" open={!data}>
      <summary>Import calibration results</summary>
      <p>Run <code>jevlab calibrate --json &gt; calibration_report.json</code> and paste the JSON below.</p>
      <label htmlFor={editorId}>Calibration report JSON</label>
      <textarea id={editorId} rows={6} value={text} onChange={e => setText(e.target.value)} spellCheck={false} />
      <div className="toolbar"><button type="button" onClick={loadReport}>Load report</button>
        {imported && report && <button type="button" onClick={() => setImported(undefined)}>Use supplied report</button>}
        <small>Processed in this browser. No uploads.</small></div>
      {error && <p className="error" role="alert">{error}</p>}
    </details>
    {data && chosen && <>
      <nav className="toolbar" aria-label="Report sections">{["Reliability", "Agreement", "Bias"].map(t =>
        <button type="button" key={t} aria-pressed={tab === t} onClick={() => setTab(t)}>{t}</button>)}</nav>
      {tab === "Reliability" && <section className="panel" aria-label="Calibration and reliability">
        <div className="toolbar"><label>Judge <select aria-label="Judge" value={name} onChange={e => setJudgeName(e.target.value)}>{names.map(n => <option key={n}>{n}</option>)}</select></label>
          <label>Method <select aria-label="Method" value={method} onChange={e => setMethod(e.target.value as Method)}>{METHODS.map(m => <option key={m}>{m}</option>)}</select></label></div>
        <div className="metrics">{(["ece", "mce", "brier"] as const).map(metric => <div className="metric" key={metric}>
          <small>{metric.toUpperCase()} · lower is better</small><strong>{fmt(chosen.before[metric])} → {fmt(chosen.after[metric])}</strong>
          <span className={chosen.improvement[metric] >= 0 ? "good" : "bad"}>{chosen.improvement[metric] >= 0 ? "+" : ""}{fmt(chosen.improvement[metric])} improvement</span>
        </div>)}</div>
        <div className="chart"><div><ReliabilityCurve before={chosen.before.reliability} after={chosen.after.reliability} />
          <p className="legend"><span style={{ color: "#f8b86a" }}>● Before</span><span className="good">● After</span><span>Dashed: ideal</span></p></div>
          <div><h2>Decision threshold</h2><strong className="threshold">{chosen.decision.threshold > 1 ? "Always negative" : chosen.decision.threshold.toPrecision(5)}</strong>
            <p>Positive when calibrated p ≥ <code>{String(chosen.decision.threshold)}</code> (exact threshold). Selected on fit data with equal error costs. Above 1 means always negative.</p>
            <p>Fit accuracy: {fmt(chosen.decision.fit_accuracy)}<br />Holdout accuracy: {fmt(chosen.decision.holdout_accuracy)}</p>
            <small>Validate on new data before deployment.</small></div></div>
        <details><summary>Reliability bins after calibration</summary><div className="scroll"><table><thead><tr><th>Bin</th><th>n</th><th>Predicted</th><th>Observed</th></tr></thead>
          <tbody>{chosen.after.reliability.map((b, i) => <tr key={i}><td>{b.lower.toFixed(2)}–{b.upper.toFixed(2)}</td><td>{b.count}</td><td>{fmt(b.mean_p)}</td><td>{fmt(b.observed)}</td></tr>)}</tbody></table></div></details>
      </section>}
      {tab === "Agreement" && <section className="panel"><h2>Inter-judge agreement</h2><p>Fleiss’ κ: {fmt(data.agreement.fleiss_kappa)}. Agreement does not establish correctness. Undefined κ is n/a.</p>
        <div className="scroll"><table><caption>Cohen’s κ · raw holdout verdicts at p ≥ 0.5</caption><thead><tr><th>Judge</th>{names.map(n => <th key={n}>{n}</th>)}</tr></thead>
          <tbody>{names.map(a => <tr key={a}><th scope="row">{a}</th>{names.map(b => {
            const k = data.agreement.pairwise[a][b];
            return <td key={b} style={{ background: `rgba(65,190,171,${k === null ? 0 : (k + 1) / 2 * .65})` }}>{fmt(k)}</td>;
          })}</tr>)}</tbody></table></div>
        <h2>Cost / accuracy frontier</h2><p>{data.agreement.cost_note}</p>
        {data.agreement.pareto.length > 0 && <div className="scroll"><table><caption>Rank 1: non-dominated judges</caption><thead><tr><th>Judge</th><th>Cost</th><th>Accuracy</th><th>Pareto rank</th></tr></thead>
          <tbody>{data.agreement.pareto.map(r => <tr key={r.judge}><td>{r.judge}</td><td>{r.cost}</td><td>{fmt(r.accuracy)}</td><td>{r.pareto_rank}</td></tr>)}</tbody></table></div>}
      </section>}
      {tab === "Bias" && <section className="panel"><h2>Position &amp; style diagnostics</h2>
        {data.bias ? <div className="scroll"><table><caption>Positive directional bias favors the first option. Ties are excluded from flip rates.</caption><thead><tr><th>Judge</th><th>Pairs / ties</th><th>Swap flips</th><th>First − second</th><th>Length ρ</th><th>Format ρ</th><th>Own-model p / n</th></tr></thead>
          <tbody>{Object.entries(data.bias.judges).map(([n, b]) => <tr key={n}><th scope="row">{n}</th><td>{b.pairs} / {b.position_swap.tie_pairs}</td><td>{fmt(b.position_swap.flip_rate)}</td><td>{fmt(b.position_swap.directional_bias)}</td><td>{fmt(b.verbosity.spearman)}</td><td>{fmt(b.format.spearman)}</td><td>{fmt(b.self_preference.mean_own_probability)} / {b.self_preference.eligible_pairs}</td></tr>)}</tbody></table></div> : <p>No paired data supplied. Add --pairs to your calibration command.</p>}
        <p>Associations need matched quality controls. Self-preference requires model provenance; style similarity alone is insufficient evidence.</p>
      </section>}
      <details className="panel"><summary>Methodology &amp; limitations</summary><ul>{data.notes.map((note, i) => <li key={i}>{note}</li>)}</ul></details>
    </>}
    <footer><small>JevLab · Apache-2.0 · Local evaluation, transparent evidence.</small></footer>
  </div>;
}
export default JevLabStudio;
