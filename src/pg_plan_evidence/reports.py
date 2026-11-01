"""Bounded static report serialization; accepts internal inspection results only."""
import base64
import csv
import hashlib
from html import escape
import io
import json
import unicodedata
from .contract import fail

STYLE = ('body{font:16px system-ui,sans-serif;margin:auto;padding:24px;max-width:1100px;color:#173042;'
         'background:#f5f8fa}h1,h2{line-height:1.2}article{padding:16px;margin:20px 0;background:white;'
         'border:1px solid #cad5dc;border-radius:8px}.scroll{overflow-x:auto}table{border-collapse:collapse;'
         'width:100%;font-size:14px}th,td{padding:8px;text-align:left;border-bottom:1px solid #dce4e9;'
         'white-space:nowrap}th{background:#e8f0f4}pre{white-space:pre-wrap;overflow-wrap:anywhere}'
         'p,li,summary{overflow-wrap:anywhere}summary{cursor:pointer}code{overflow-wrap:anywhere}')


def captures(report):
    if 'left' in report:
        return [('left', report['left']), ('right', report['right'])]
    return [('inspection', report)]


def text(value):
    return 'unknown' if value is None else str(value)


def cell(value):
    if isinstance(value, str):
        checked = unicodedata.normalize('NFKC', value).lstrip()
        if checked.startswith(('=', '+', '-', '@')) or value.startswith(('\t', '\r', '\n')):
            return "'" + value
    return value


def render_csv(report):
    buf = io.StringIO(newline='')
    writer = csv.writer(buf, quoting=csv.QUOTE_ALL)
    writer.writerow(['capture', 'comparison_status', 'context_mismatches', 'source', 'query_alias',
                     'server_version_num', 'captured_at', 'observation_id', 'raw_sha256',
                     'shape_sha256', 'query_sha256', 'fixture_sha256', 'workload_sha256',
                     'settings_sha256', 'node_path', 'node_type', 'estimated_rows_per_loop',
                     'actual_rows_per_loop', 'actual_loops', 'approx_emitted_rows_all_loops',
                     'q_error_per_loop', 'diagnostic_status', 'caveats'])
    for label, capture in captures(report):
        ctx = capture['provenance']['context']
        for node in capture['nodes']:
            fields, diagnostic = node['fields'], node['diagnostic']
            values = [label, report.get('status', 'inspection'),
                      ','.join(report.get('context_mismatches', [])), ctx['source'], ctx['query_alias'],
                      ctx['server_version_num'], ctx['captured_at'], capture['observation_id'],
                      capture['provenance']['raw_sha256'], capture['shape_sha256'],
                      ctx['query_sha256'], ctx['fixture_sha256'], ctx['workload_sha256'],
                      ctx['settings_sha256'], 'node:' + node['path'], fields['Node Type'],
                      fields.get('Plan Rows'), fields.get('Actual Rows'), fields.get('Actual Loops'),
                      diagnostic['approx_emitted_rows_all_loops'], diagnostic['q_error_per_loop'],
                      diagnostic['status'], ' '.join(capture['warnings'])]
            writer.writerow([cell(v) if v is not None else '' for v in values])
    return buf.getvalue()


def render_html(report):
    e = lambda value: escape(text(value), quote=True)
    digest = base64.b64encode(hashlib.sha256(STYLE.encode()).digest()).decode()
    csp = f"default-src 'none'; style-src 'sha256-{digest}'; base-uri 'none'; form-action 'none'"
    parts = ['<!doctype html><html lang="en"><meta charset="utf-8">',
             '<meta name="viewport" content="width=device-width,initial-scale=1">',
             '<meta http-equiv="Content-Security-Policy" content="' + escape(csp, quote=True) + '">',
             '<title>PostgreSQL Plan Evidence</title><style>' + STYLE + '</style><body>',
             '<h1>PostgreSQL Plan Evidence</h1>',
             '<p>Offline structural and row-estimate evidence. No performance regression verdict.</p>']
    if 'status' in report:
        parts.append('<p>Comparison: <strong>' + e(report['status']) + '</strong>. Context mismatches: '
                     + e(', '.join(report['context_mismatches']) or 'none')
                     + '. Same projected shape: ' + e(report['same_shape']) + '.</p>')
    for label, capture in captures(report):
        ctx = capture['provenance']['context']
        parts.append('<article><h2>' + e(label) + ': ' + e(ctx['query_alias']) + '</h2>'
                     '<p>Source: ' + e(ctx['source']) + '; PostgreSQL numeric version: '
                     + e(ctx['server_version_num']) + '; captured: ' + e(ctx['captured_at']) + '.</p>'
                     + ('<p>Handwritten synthetic fixture: these values illustrate semantics and were not measured.</p>' if ctx['source'] == 'synthetic_fixture' else '')
                     + '<p>' + ('Illustrative execution-time field: ' if ctx['source'] == 'synthetic_fixture' else 'Reported server execution time: ') + e(capture['statement_times_ms'].get('Execution Time'))
                     + ' ms. This is not client latency. Planner costs are arbitrary units.</p><ul>')
        parts.extend('<li>' + e(warning) + '</li>' for warning in capture['warnings'])
        parts.append('</ul><div class="scroll"><table><thead><tr>'
                     '<th>Path</th><th>Node</th><th>Estimated rows/loop</th><th>Actual rows/loop</th>'
                     '<th>Loops</th><th>Approx. emitted rows</th><th>Q-error</th><th>Status</th>'
                     '</tr></thead><tbody>')
        for node in capture['nodes']:
            f, d = node['fields'], node['diagnostic']
            values = (node['path'], f['Node Type'], f.get('Plan Rows'), f.get('Actual Rows'),
                      f.get('Actual Loops'), d['approx_emitted_rows_all_loops'],
                      d['q_error_per_loop'], d['status'])
            parts.append('<tr>' + ''.join('<td>' + e(v) + '</td>' for v in values) + '</tr>')
        provenance = {key: capture[key] for key in ('provenance', 'observation_id', 'projection_sha256', 'shape_sha256')}
        parts.append('</tbody></table></div><details><summary>Capture provenance</summary><pre>'
                     + escape(json.dumps(provenance, indent=2)) + '</pre></details></article>')
    parts.append('<p>Node paths belong to each capture. Matching paths in different shapes do not establish correspondence. '
                 'Unknown measurements remain unknown, never zero.</p></body></html>')
    return ''.join(parts)


def serialize(report, format):
    if format == 'json':
        result = json.dumps(report, indent=2, allow_nan=False) + '\n'
    elif format == 'csv':
        result = render_csv(report)
    elif format == 'html':
        result = render_html(report)
    else:
        fail('output_format')
    raw = result.encode()
    if len(raw) > 2 * 1024 * 1024:
        fail('output_size')
    return raw
