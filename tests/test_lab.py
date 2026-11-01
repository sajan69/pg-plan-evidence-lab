import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from scripts import collect_lab as lab
from pg_plan_evidence.contract import EvidenceError


class LabTests(unittest.TestCase):
    def test_refuse_existing_destination_before_database_access(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(lab, 'collect') as collect:
            self.assertEqual(lab.main(['--disposable-lab', '--out', temp]), 2)
            collect.assert_not_called()

    def test_loopback_and_environment_isolation(self):
        for host in ('db.example.test', '/tmp', '127.0.0.1 host=evil'):
            with patch.dict(os.environ, {'PGHOST': host, 'PGPASSWORD': 'dummy'}, clear=True):
                with self.assertRaises(EvidenceError):
                    lab.environment()
        with patch.dict(os.environ, {'PGHOST': '127.0.0.1', 'PGPORT': '5432', 'PGPASSWORD': 'dummy',
                                    'PGOPTIONS': '-c dangerous=value', 'PGSERVICE': 'external'}, clear=True):
            config = lab.environment()
        self.assertNotIn('PGOPTIONS', config[3])
        self.assertNotIn('PGSERVICE', config[3])
        self.assertEqual(config[3]['PGPASSFILE'], os.devnull)
        done = subprocess.CompletedProcess([], 0, b'1\n', b'')
        with patch.object(lab.subprocess, 'run', return_value=done) as run:
            self.assertEqual(lab.read_query(config, 'SELECT 1'), '1')
        args, kwargs = run.call_args
        self.assertIn('-X', args[0])
        self.assertIn('plan_reader', args[0])
        self.assertIn(lab.DATABASE, args[0])
        self.assertNotIn('shell', kwargs)
        self.assertEqual(kwargs['timeout'], 20)
        self.assertEqual(kwargs['env']['PGPASSWORD'], lab.READER_PASSWORD)
        self.assertIn('BEGIN READ ONLY', args[0][args[0].index('-c') + 1])

    def test_reference_queries_and_cardinality(self):
        selective = lab.expected('selective').splitlines()
        self.assertEqual(len(selective), 20)
        self.assertEqual(selective[0], '7|7')
        self.assertEqual(selective[-1], '19007|92')
        aggregate = lab.expected('aggregate').splitlines()
        self.assertEqual(len(aggregate), 10)
        self.assertEqual(aggregate[0], '0|20|965')
        self.assertEqual(lab.expected('repeated_inner').splitlines(), [f'{i}|20' for i in range(1, 13)])
        with self.assertRaises(EvidenceError):
            lab.expected('arbitrary')

    def test_populated_cluster_refusal(self):
        with patch.object(lab, 'sql', return_value='1') as sql:
            with self.assertRaisesRegex(EvidenceError, 'cluster_not_fresh'):
                lab.fresh(None)
            self.assertEqual(sql.call_count, 1)
