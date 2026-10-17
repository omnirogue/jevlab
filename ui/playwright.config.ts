// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 The OmniSI Authors
import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests',
  workers: 1,
  use: { baseURL: 'http://127.0.0.1:4179', headless: true },
  webServer: { command: 'node tests/serve.mjs', url: 'http://127.0.0.1:4179', reuseExistingServer: false },
  projects: [
    { name: 'desktop', use: { viewport: { width: 1440, height: 1000 } } },
    { name: 'mobile', use: { viewport: { width: 390, height: 844 } } },
  ],
});
