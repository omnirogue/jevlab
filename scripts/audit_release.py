# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 The OmniSI Authors
"""Fast standalone export audit. Reports file names only, never secret values."""

import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IGNORE = {'.git', '__pycache__', '.venv', 'node_modules', 'dist', 'build', '.test-assets',
          'test-results', 'playwright-report'}
PRIVATE = re.compile('|'.join([
    r'\bmw' + r'2[a-z0-9-]*\b',
    r'[a-z0-9-]+\.ts\.net\b', r'/Users/[a-zA-Z]',
]), re.I)
SECRETS = re.compile('|'.join([
    r'sk-ant-[A-Za-z0-9_-]{8,}', r'sk-[A-Za-z0-9_-]{20,}',
    r'(?:AKIA|ASIA)[0-9A-Z]{16}', r'gh[pousr]_[A-Za-z0-9]{30,}',
    r'github_pat_[A-Za-z0-9_]{20,}', r'xox[abprs]-[A-Za-z0-9-]{10,}',
    r'-----BEGIN [A-Z ]*PRIVATE KEY-----', r'(?:sk|rk)_live_[A-Za-z0-9]{10,}',
    r'eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}',
]))
EMAIL = re.compile(r'[A-Za-z0-9._%+-]+@([A-Za-z0-9.-]+\.[A-Za-z]{2,})')
RESERVED = re.compile(r'(^|\.)example\.(com|org|net)$|\.(example|test|invalid)$', re.I)
APACHE_SHA = 'cfc7749b96f63bd31c3c42b5c471bf756814053e847c10f3eb003417bc523d30'


def audit(root=ROOT):
    findings, paths = [], []
    for path in sorted(root.rglob('*')):
        rel = path.relative_to(root)
        if set(rel.parts) & IGNORE or any(p.endswith('.egg-info') for p in rel.parts):
            continue
        if path.is_symlink():
            findings.append(f'symlink: {rel}')
            continue
        if not path.is_file():
            continue
        paths.append(rel.as_posix())
        if path.suffix == '.rs' or path.name in ('Cargo.toml', 'Cargo.lock'):
            findings.append(f'excluded source: {rel}')
        if path.name == '.env' or path.name.startswith('.env.') or path.suffix in ('.pem', '.key', '.pyc'):
            findings.append(f'excluded artifact: {rel}')
        try:
            content = path.read_text(encoding='utf-8')
        except UnicodeError:
            findings.append(f'unexpected binary: {rel}')
            continue
        if PRIVATE.search(content):
            findings.append(f'private identifier: {rel}')
        if SECRETS.search(content):
            findings.append(f'credential pattern: {rel}')
        if any(not RESERVED.search(domain) for domain in EMAIL.findall(content)):
            findings.append(f'non-example email: {rel}')
        if path.suffix in ('.py', '.tsx', '.ts', '.mjs', '.yaml', '.yml', '.toml') and 'SPDX-License-Identifier: Apache-2.0' not in content:
            findings.append(f'missing SPDX: {rel}')
    if hashlib.sha256((root / 'LICENSE').read_bytes()).hexdigest() != APACHE_SHA:
        findings.append('LICENSE: expected full canonical Apache-2.0 text')
    manifest = json.loads((root / 'audit-manifest.json').read_text())
    if manifest.get('rust_included') is not False or manifest.get('included_crates'):
        findings.append('manifest includes excluded engine')
    if manifest.get('repository') != 'https://github.com/omnirogue/jevlab':
        findings.append('incorrect repository identity')
    # Setuptools adds these two metadata files when building an sdist. Their
    # content is still scanned above, but they are not authored export files.
    generated_metadata = {'PKG-INFO', 'setup.cfg'} - set(manifest.get('package_files', []))
    if set(manifest.get('package_files', [])) != set(paths) - generated_metadata:
        findings.append('manifest package_files differs from export inventory')
    for folder, glob in [('fixtures', '*.json'), ('rubrics', '*.yaml')]:
        sources = {p.name: p.read_bytes() for p in (root / folder).glob(glob)}
        bundled = {p.name: p.read_bytes() for p in (root / 'jevlab_oss' / 'data' / folder).glob(glob)}
        if sources != bundled:
            findings.append(f'bundled assets differ: {folder}')
    templates = list((root / 'rubrics').glob('*.yaml'))
    if len(templates) != 10:
        findings.append('expected exactly ten public rubric templates')
    for path in templates:
        rubric = json.loads(path.read_text())
        if rubric.get('license') != 'Apache-2.0' or rubric.get('id') != path.stem:
            findings.append(f'invalid rubric metadata: {path.name}')
    return findings, paths


if __name__ == '__main__':
    findings, paths = audit()
    for finding in findings:
        print(f'FAIL: {finding}')
    if findings:
        raise SystemExit(1)
    print(f'PASS: {len(paths)} export files; no Rust, private identifiers or credential patterns; assets match.')
