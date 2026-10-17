// SPDX-License-Identifier: Apache-2.0
// Copyright 2026 The OmniSI Authors
import { build } from 'esbuild';
import { execFileSync } from 'node:child_process';
import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { createServer } from 'node:http';
import { resolve } from 'node:path';

const root = resolve('..');
const assets = resolve('.test-assets');
mkdirSync(assets, { recursive: true });
const json = execFileSync('python3', ['-m', 'jevlab_oss.cli', 'calibrate', '--json', '--output', resolve(assets, 'report.html')], { cwd: root, encoding: 'utf8' });
writeFileSync(resolve(assets, 'report.json'), json);
await build({ entryPoints: ['tests/app.tsx'], outfile: resolve(assets, 'studio.js'), bundle: true, jsx: 'automatic', platform: 'browser' });
const html = '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>JevLab Studio checks</title></head><body style="margin:0;background:#0a1020"><div id="root"></div><script src="/studio.js"></script></body></html>';
createServer((req, res) => {
  const route = req.url?.split('?')[0];
  const files = { '/studio.js': ['studio.js', 'text/javascript'], '/report.html': ['report.html', 'text/html'], '/report.json': ['report.json', 'application/json'] };
  if (route === '/') { res.setHeader('Content-Type', 'text/html'); res.end(html); return; }
  if (Object.hasOwn(files, route)) {
    const [file, type] = files[route];
    res.setHeader('Content-Type', type); res.end(readFileSync(resolve(assets, file))); return;
  }
  res.writeHead(404); res.end();
}).listen(4179, '127.0.0.1');
