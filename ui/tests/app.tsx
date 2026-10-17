// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 The OmniSI Authors
import { createRoot } from 'react-dom/client';
import { JevLabStudio, parseCalibrationReport } from '../JevLabStudio';
import sample from '../.test-assets/report.json';

createRoot(document.getElementById('root')!).render(
  <JevLabStudio report={parseCalibrationReport(sample)} />,
);
