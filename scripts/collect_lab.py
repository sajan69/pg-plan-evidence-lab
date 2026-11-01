"""Trusted canned SQL only, on a fresh disposable loopback PostgreSQL cluster."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import time

from pg_plan_evidence.analysis import inspect
from pg_plan_evidence.contract import EvidenceError, canonical, fail, sha, strict_json
from pg_plan_evidence.io import write

DATABASE = 'plan_evidence_lab'
READER_PASSWORD = 'local-synthetic-reader-only'
ROWS = 20000
QUERIES = {
    'selective': 'SELECT id, amount FROM evidence.events WHERE cohort = 7 ORDER BY id',
    'aggregate': 'SELECT cohort, count(*), sum(amount) FROM evidence.events GROUP BY cohort ORDER BY cohort LIMIT 10',
    'repeated_inner': ('SELECT x.id, (SELECT count(*) FROM evidence.events AS y WHERE y.cohort = x.cohort) '
                       'AS matches FROM evidence.events AS x WHERE x.id <= 12 ORDER BY x.id'),
}
SETTINGS = {'jit': 'off', 'max_parallel_workers_per_gather': '0', 'work_mem': '16MB',
            'statement_timeout': '5s', 'lock_timeout': '1s', 'search_path': 'pg_catalog,evidence'}
READ_PREFIX = ("BEGIN READ ONLY; SET LOCAL statement_timeout='5s'; SET LOCAL lock_timeout='1s'; "
               "SET LOCAL jit=off; SET LOCAL max_parallel_workers_per_gather=0; "
               "SET LOCAL work_mem='16MB'; SET LOCAL search_path=pg_catalog,evidence;")


def environment():
    host = os.environ.get('PGHOST', '127.0.0.1')
    port = os.environ.get('PGPORT', '5432')
    password = os.environ.get('PGPASSWORD')
    if host not in ('127.0.0.1', '::1', 'localhost') or not port.isascii() or not port.isdigit():
        fail('loopback_configuration')
    if not 1024 <= int(port) <= 65535 or not password:
        fail('loopback_configuration')
    # No inherited PGSERVICE/PGOPTIONS/PGDATABASE/PSQLRC. No credential-file fallback.
    base = {'PATH': os.environ.get('PATH', ''), 'LANG': 'C.UTF-8',
            'PGCONNECT_TIMEOUT': '3', 'PGPASSFILE': os.devnull,
            'PGSSLMODE': 'disable', 'PGCLIENTENCODING': 'UTF8'}
    return host, port, password, base


def sql(config, commands, *, reader=False, lab=True):
    """Internal trusted-programmer API, not arbitrary SQL input validation."""
    host, port, admin_password, env = config
    args = ['psql', '-X', '-qAt', '-w', '-v', 'ON_ERROR_STOP=1', '-h', host, '-p', port,
            '-U', 'plan_reader' if reader else 'postgres', '-d', DATABASE if lab else 'postgres']
    for command in commands:
        args.extend(['-c', command])
    try:
        completed = subprocess.run(args, input=b'', capture_output=True, timeout=20,
                                   env={**env, 'PGPASSWORD': READER_PASSWORD if reader else admin_password})
    except (OSError, subprocess.TimeoutExpired):
        fail('psql_operation')
    if completed.returncode != 0 or len(completed.stdout) > 2 * 1024 * 1024:
        fail('psql_operation')
    try:
        return completed.stdout.decode('utf-8').strip()
    except UnicodeError:
        fail('psql_encoding')


def read_query(config, query):
    return sql(config, [READ_PREFIX, query, 'ROLLBACK'], reader=True)


def expected(alias):
    if alias == 'selective':
        return '\n'.join(f'{i}|{i % 97}' for i in range(1, ROWS + 1) if i % 1000 == 7)
    if alias == 'aggregate':
        return '\n'.join(f'{c}|20|{sum(i % 97 for i in range(1, ROWS + 1) if i % 1000 == c)}'
                         for c in range(10))
    if alias == 'repeated_inner':
        return '\n'.join(f'{i}|20' for i in range(1, 13))
    fail('unknown_canned_query')


def fresh(config):
    # Refuse a populated cluster rather than guessing which existing resources are safe.
    check = sql(config, ["SELECT (SELECT count(*) FROM pg_database WHERE datname NOT IN "
                         "('postgres','template0','template1')) + (SELECT count(*) FROM pg_roles "
                         "WHERE left(rolname,3) <> 'pg_' AND rolname <> 'postgres')"], lab=False)
    if check != '0':
        fail('cluster_not_fresh')
    version = int(sql(config, ["SHOW server_version_num"], lab=False))
    if version // 10000 not in (16, 18):
        fail('server_version')
    return version


def bootstrap(config):
    sql(config, ["CREATE ROLE plan_owner NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS",
                 "CREATE ROLE plan_reader LOGIN PASSWORD 'local-synthetic-reader-only' "
                 "NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS",
                 'CREATE DATABASE plan_evidence_lab OWNER plan_owner'], lab=False)
    sql(config, ['REVOKE ALL ON DATABASE plan_evidence_lab FROM PUBLIC',
                 'GRANT CONNECT ON DATABASE plan_evidence_lab TO plan_reader',
                 'REVOKE ALL ON SCHEMA public FROM PUBLIC',
                 'SET ROLE plan_owner', 'CREATE SCHEMA evidence AUTHORIZATION plan_owner',
                 'CREATE TABLE evidence.events (id integer NOT NULL, cohort integer NOT NULL, amount integer NOT NULL)',
                 f'INSERT INTO evidence.events SELECT i, i % 1000, i % 97 FROM generate_series(1,{ROWS}) AS g(i)',
                 'GRANT USAGE ON SCHEMA evidence TO plan_reader',
                 'GRANT SELECT ON evidence.events TO plan_reader',
                 'VACUUM (ANALYZE) evidence.events'])
    guard(config)


def guard(config):
    result = read_query(config, "SELECT current_user = 'plan_reader' AND NOT rolsuper AND NOT rolbypassrls "
        "AND NOT rolcreatedb AND NOT rolcreaterole AND NOT EXISTS "
        "(SELECT 1 FROM pg_auth_members WHERE member = (SELECT oid FROM pg_roles WHERE rolname=current_user)) "
        "AND has_table_privilege(current_user,'evidence.events','SELECT') "
        "AND NOT has_table_privilege(current_user,'evidence.events','INSERT,UPDATE,DELETE,TRUNCATE') "
        "AND NOT has_schema_privilege(current_user,'evidence','CREATE') "
        "AND (SELECT relowner FROM pg_class WHERE oid='evidence.events'::regclass) <> oid "
        "FROM pg_roles WHERE rolname=current_user")
    if result != 't':
        fail('reader_role_drift')


def collect(config, out):
    version = fresh(config)
    Path(out).mkdir(mode=0o700)  # Refuses existing outputs before any writes to the database.
    bootstrap(config)
    # Actual table bytes are checked independently of SELECT/EXPLAIN result correctness.
    table = read_query(config, 'SELECT id,cohort,amount FROM evidence.events ORDER BY id')
    wanted = '\n'.join(f'{i}|{i % 1000}|{i % 97}' for i in range(1, ROWS + 1))
    if table != wanted:
        fail('fixture_mismatch')
    fixture_hash = sha(table.encode())
    workload_hash = sha(canonical({'queries': QUERIES, 'repeats': 3, 'rows': ROWS}))
    records = []
    for phase in ('baseline', 'indexed'):
        if phase == 'indexed':
            sql(config, ['SET ROLE plan_owner',
                         'CREATE INDEX events_cohort_id ON evidence.events (cohort,id) INCLUDE (amount)'])
        guard(config)
        settings_hash = sha(canonical({'session': SETTINGS, 'index': phase == 'indexed'}))
        for alias, query in QUERIES.items():
            # Correctness check is outside the timer but warms buffers; explicitly recorded.
            result = read_query(config, query)
            if result != expected(alias):
                fail('query_result_mismatch')
            result_hash = sha(result.encode())
            for repeat in range(3):
                captured = datetime.now(timezone.utc).isoformat()
                start = time.perf_counter()
                raw = read_query(config, 'EXPLAIN (ANALYZE, BUFFERS, TIMING OFF, FORMAT JSON) ' + query).encode()
                parsed = strict_json(raw, 2 * 1024 * 1024)
                client_ms = (time.perf_counter() - start) * 1000
                ctx = {'schema_version': 1, 'source': 'synthetic_lab',
                       'server_version_num': version, 'query_alias': alias, 'captured_at': captured,
                       'query_sha256': sha(query.encode()), 'fixture_sha256': fixture_hash,
                       'workload_sha256': workload_hash, 'settings_sha256': settings_hash}
                report = inspect(raw, canonical(ctx))
                server_ms = report['statement_times_ms'].get('Execution Time')
                if server_ms is None or not parsed[0].get('Plan'):
                    fail('missing_execution_evidence')
                stem = f'{phase}-{alias}-{repeat + 1}'
                raw_path = Path(out) / f'{stem}-raw.json'
                with os.fdopen(os.open(raw_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'wb') as handle:
                    handle.write(raw)
                write(Path(out) / f'{stem}-manifest.json', ctx)
                write(Path(out) / f'{stem}-inspection.json', report)
                if sha(raw_path.read_bytes()) != report['provenance']['raw_sha256']:
                    fail('capture_hash_mismatch')
                records.append({'phase': phase, 'query_alias': alias, 'repeat': repeat + 1,
                                'result_sha256': result_hash, 'result_rows': len(result.splitlines()),
                                'client_wall_ms': client_ms, 'server_execution_ms': server_ms,
                                'observation_id': report['observation_id'],
                                'shape_sha256': report['shape_sha256'], 'nodes': len(report['nodes'])})
    summaries = []
    for alias in QUERIES:
        for phase in ('baseline', 'indexed'):
            rows = [r for r in records if r['query_alias'] == alias and r['phase'] == phase]
            summaries.append({'query_alias': alias, 'phase': phase,
                              'client_wall_median_ms': statistics.median(r['client_wall_ms'] for r in rows),
                              'server_execution_median_ms': statistics.median(r['server_execution_ms'] for r in rows)})
    report = {'schema_version': 1, 'completed': True, 'source': 'synthetic_lab',
              'acquired_at': datetime.now(timezone.utc).isoformat(),
              'fixture_rows': ROWS, 'fixture_sha256': fixture_hash, 'workload_sha256': workload_hash,
              'server_version_num': version, 'server_version': sql(config, ['SELECT version()']),
              'python': platform.python_version(), 'platform': platform.platform(),
              'logical_cpus': os.cpu_count(), 'psql_version': subprocess.check_output(['psql', '--version'], text=True).strip(),
              'session_settings': SETTINGS, 'records': records, 'summaries': summaries,
              'method': 'Three fixed queries, three repeats per configuration; baseline always before indexed. '
                        'Correctness SELECT before each timed group warms caches. TIMING OFF retains statement time. '
                        'Client wall includes psql startup, connection, SQL and JSON parsing; excludes inspection and writes. '
                        'No cache reset or independent latency baseline; instrumented server time is not application latency.'}
    write(Path(out) / 'lab-report.json', report)
    return report


def main(argv=None):
    p = argparse.ArgumentParser(description='Fresh disposable synthetic PostgreSQL lab only')
    p.add_argument('--disposable-lab', action='store_true', required=True)
    p.add_argument('--out', required=True)
    args = p.parse_args(argv)
    try:
        if os.path.lexists(args.out):
            fail('output_exists')
        report = collect(environment(), args.out)
        print('LAB_REPORT=' + json.dumps(report, separators=(',', ':')))
        return 0
    except EvidenceError as exc:
        print(f'error: {exc}', file=sys.stderr)
    except (OSError, ValueError, subprocess.SubprocessError):
        print('error: lab_operation', file=sys.stderr)
    return 2


if __name__ == '__main__':
    raise SystemExit(main())
