import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from pg_plan_evidence.io import read, write
from pg_plan_evidence.contract import EvidenceError
import test_analysis as fixture


class CliTests(unittest.TestCase):
    def test_installed_inspect_compare_and_exclusive_outputs(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            plan, manifest = root / 'plan.json', root / 'manifest.json'
            plan.write_text(json.dumps(fixture.plan()))
            manifest.write_text(json.dumps(fixture.context()))
            out = root / 'result.json'
            command = ['pg-plan-evidence', 'inspect', str(plan), '--manifest', str(manifest), '--out', str(out)]
            result = subprocess.run(command, capture_output=True, text=True, check=True)
            self.assertEqual(result.stdout.strip(), 'written')
            report = json.loads(out.read_text())
            self.assertEqual(len(report['nodes']), 3)
            self.assertNotIn('secret@', out.read_text())
            if os.name == 'posix':
                self.assertEqual(stat.S_IMODE(out.stat().st_mode), 0o600)
            again = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(again.returncode, 2)
            self.assertIn('output_exists', again.stderr)
            compared = root / 'compare.json'
            subprocess.run(['pg-plan-evidence', 'compare', str(plan), str(plan),
                            '--left-manifest', str(manifest), '--right-manifest', str(manifest),
                            '--out', str(compared)], capture_output=True, check=True)
            self.assertTrue(json.loads(compared.read_text())['same_shape'])

    def test_file_bounds_nonregular_and_symlink(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            with self.assertRaises(EvidenceError):
                read(root, 10)
            target = root / 'target'
            target.write_bytes(b'123456')
            with self.assertRaises(EvidenceError):
                read(target, 5)
            link = root / 'link'
            link.symlink_to(target)
            with self.assertRaises(EvidenceError):
                read(link, 10)
            with self.assertRaises(FileExistsError):
                write(link, {})
            self.assertEqual(target.read_bytes(), b'123456')

    def test_output_cap_before_creation_and_sanitized_errors(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'output'
            with self.assertRaises(EvidenceError):
                write(path, {'data': 'a' * (2 * 1024 * 1024)})
            self.assertFalse(path.exists())
            result = subprocess.run(['pg-plan-evidence', 'inspect', str(Path(temp) / 'private-secret'),
                                     '--manifest', 'missing', '--out', str(path)],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(result.stderr.strip(), 'error: file_operation')
            self.assertFalse(path.exists())
