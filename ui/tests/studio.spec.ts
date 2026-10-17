// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 The OmniSI Authors
import { expect, test } from '@playwright/test';

test('studio changes judge/method, exposes agreement and bias, and imports reports', async ({ page }, testInfo) => {
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto('/');
  await expect(page.getByRole('heading', { name: /Can you trust/ })).toBeVisible();
  await page.getByLabel('Judge', { exact: true }).selectOption('judge-noisy');
  await page.getByLabel('Method', { exact: true }).selectOption('histogram');
  await expect(page.getByRole('img', { name: /Reliability curve/ })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Decision threshold' })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath('reliability.png'), fullPage: true });
  await page.getByRole('button', { name: 'Agreement', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Inter-judge agreement' })).toBeVisible();
  await expect(page.getByText(/Fleiss’ κ/)).toBeVisible();
  await page.getByRole('button', { name: 'Bias', exact: true }).click();
  await expect(page.getByRole('rowheader', { name: 'first-position', exact: true })).toBeVisible();
  await page.getByText('Import calibration results', { exact: true }).click();
  await page.getByLabel('Calibration report JSON').fill('{"schema_version":1}');
  await page.getByRole('button', { name: 'Load report', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('Expected a JevLab v1');
  const response = await page.request.get('/report.json');
  const report = await response.json();
  report.fixture.rubric_id = '<img src=x onerror=alert(1)>';
  await page.getByLabel('Calibration report JSON').fill(JSON.stringify(report));
  await page.getByRole('button', { name: 'Load report', exact: true }).click();
  await expect(page.getByRole('alert')).toHaveCount(0);
  await expect(page.locator('.jevlab header')).toContainText('<img src=x onerror=alert(1)>');
  await expect(page.locator('.jevlab img')).toHaveCount(0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  expect(errors).toEqual([]);
});

test('self-contained HTML renders calibration and bias at each viewport', async ({ page }, testInfo) => {
  const outside: string[] = [];
  page.on('request', request => { if (!request.url().startsWith('http://127.0.0.1:4179/')) outside.push(request.url()); });
  await page.goto('/report.html');
  await expect(page).toHaveTitle('JevLab · Calibration & Reliability Report');
  await expect(page.getByRole('heading', { name: 'Inter-judge agreement' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Position swap & bias diagnostics' })).toBeVisible();
  await expect(page.locator('svg')).toHaveCount(9);
  await expect(page.locator('script')).toHaveCount(0);
  await page.screenshot({ path: testInfo.outputPath('report.png'), fullPage: true });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  expect(outside).toEqual([]);
});
