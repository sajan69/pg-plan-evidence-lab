import csv
from html.parser import HTMLParser
import io
import json
from pathlib import Path
import tempfile
import unittest
from pg_plan_evidence.contract import EvidenceError
from pg_plan_evidence.io import write
from pg_plan_evidence.reports import serialize
import test_analysis as fixture


class Tags(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = []
    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)


class ReportTests(unittest.TestCase):
    def test_html_and_csv_unknown_loop_semantics(self):
        report = fixture.run(ctx=fixture.context(source='synthetic_fixture'))
        html = serialize(report, 'html').decode()
        self.assertIn('Actual rows/loop', html)
        self.assertIn('were not measured', html)
        self.assertIn('No performance regression verdict', html)
        rows = list(csv.DictReader(io.StringIO(serialize(report, 'csv').decode())))
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[2]['approx_emitted_rows_all_loops'], '6')
        unknown = fixture.run([{'Plan': {'Node Type': 'Result'}}])
        row = list(csv.DictReader(io.StringIO(serialize(unknown, 'csv').decode())))[0]
        self.assertEqual(row['actual_rows_per_loop'], '')
        self.assertEqual(row['diagnostic_status'], 'not_measured')

    def test_inert_text_and_spreadsheet_mitigation(self):
        report = fixture.run()
        report['warnings'].append('<img src="https://example.test/x" onerror="alert(1)"><script>alert(1)</script>')
        report['provenance']['context']['query_alias'] = ' ＝1+1'
        html = serialize(report, 'html').decode()
        parser = Tags(); parser.feed(html)
        self.assertNotIn('img', parser.tags)
        self.assertNotIn('script', parser.tags)
        self.assertIn('&lt;script&gt;', html)
        self.assertIn("default-src &#x27;none&#x27;", html)
        rows = list(csv.DictReader(io.StringIO(serialize(report, 'csv').decode())))
        self.assertEqual(rows[0]['query_alias'], "' ＝1+1")

    def test_blocked_comparison_exports_and_output_cap(self):
        report = fixture.compare(fixture.run(), fixture.run(ctx=fixture.context(query_alias='other')))
        self.assertIn('blocked', serialize(report, 'html').decode())
        rows = list(csv.DictReader(io.StringIO(serialize(report, 'csv').decode())))
        self.assertTrue(all(row['comparison_status'] == 'blocked' for row in rows))
        self.assertTrue(all(row['context_mismatches'] == 'query_alias' for row in rows))
        self.assertEqual(len(rows), 6)
        report['left']['warnings'] = ['a' * (2 * 1024 * 1024)]
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp) / 'out.html'
            with self.assertRaises(EvidenceError):
                write(out, report, 'html')
            self.assertFalse(out.exists())
