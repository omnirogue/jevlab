# JevLab Studio

`JevLabStudio.tsx` is a standalone React component for calibration reports. Copy it into your React + TypeScript application. It imports only React: no component library, cloud routes, authentication, icons, or internal modules. Styles are inline and scoped to `.jevlab`; React 18+ and the automatic JSX runtime are sufficient.

```tsx
import { JevLabStudio, parseCalibrationReport } from './JevLabStudio';
import rawReport from './calibration_report.json';

const report = parseCalibrationReport(rawReport);
export default function EvaluationPage() {
  return <JevLabStudio report={report} />;
}
```

Generate input with `jevlab calibrate --json > calibration_report.json`, or use the structured result of `jevlab_calibrate`. With no props, the component opens a JSON import panel. Paste a report and select a judge, calibration method, or the Agreement/Bias sections. `onReportChange(report)` receives validated imports. Imported reports remain selected until “Use supplied report” is clicked or the component remounts.

The studio displays before/after ECE, MCE and Brier, an inline SVG reliability curve, a fit-selected threshold with holdout accuracy, Cohen/Fleiss kappa, Pareto layers when costs exist, and paired bias diagnostics. It sends no requests, persists nothing, and renders labels as text. A host Content Security Policy must allow this component's inline styles, or move `CSS` into a host stylesheet.

This adapts the original JEV Lab calibration view into an offline report studio. Application-specific service, ledger, organization, subject handoff and Rust quickstart code are excluded. Evaluation happens in Python; the component does not pretend to run a live judge.

CI typechecks this component independently and runs browser interaction checks against locally served test assets on GitHub Actions. No hosted product or deployment is required.
