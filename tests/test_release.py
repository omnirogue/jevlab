# SPDX-License-Identifier: Apache-2.0
# Copyright 2026 The OmniSI Authors
"""Namespace, CLI, public template and export-boundary regression checks."""

import contextlib
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path

import jevlab
import jevlab_oss
from jevlab_oss import bench, resources
from jevlab_oss.cli import main


class Release(unittest.TestCase):
    def test_legacy_modules_are_the_same_objects(self):
        self.assertIs(jevlab.bench, bench)
        self.assertEqual(jevlab.__version__, jevlab_oss.__version__)
        from jevlab.metrics import PlattCalibrator as legacy
        from jevlab_oss.metrics import PlattCalibrator
        self.assertIs(legacy, PlattCalibrator)

    def test_ten_unique_public_templates(self):
        rubrics = resources.list_rubrics()
        self.assertEqual(len(rubrics), 10)
        self.assertEqual(len({r['id'] for r in rubrics}), 10)
        for rubric in rubrics:
            self.assertEqual(resources.show_rubric(rubric['id']), rubric)
            self.assertEqual(rubric['license'], 'Apache-2.0')
            self.assertEqual(len(rubric['questions']), 3)
        with self.assertRaises(ValueError):
            resources.show_rubric('../LICENSE')

    def test_cli_json_and_clean_errors(self):
        for args in (['bench', '--json'], ['bias-audit', '--json'], ['rubrics', 'show', 'test_quality']):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(main(args), 0)
            self.assertIsInstance(json.loads(output.getvalue()), dict)
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(['bench', '--fixture', 'missing-fixture.json']), 2)
            self.assertEqual(main(['bench', '--bins', '0']), 2)
            self.assertEqual(main(['rubrics', 'show', 'missing']), 2)
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()) as output:
            html = Path(tmp) / 'report.html'
            self.assertEqual(main(['calibrate', '--output', str(html), '--json']), 0)
            self.assertEqual(json.loads(output.getvalue())['schema_version'], 1)
            self.assertIn('Reliability Report', html.read_text())

    def test_export_audit(self):
        root = Path(__file__).resolve().parents[1]
        spec = importlib.util.spec_from_file_location('release_audit', root / 'scripts/audit_release.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        findings, paths = module.audit(root)
        self.assertEqual(findings, [])
        self.assertTrue(paths)


if __name__ == '__main__':
    unittest.main()
