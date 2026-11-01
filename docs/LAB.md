# Disposable PostgreSQL experiment

The repository-only collector executes fixed synthetic SQL on a fresh loopback PostgreSQL 16 or 18 cluster. It is separate from the installed offline reader and requires `psql` on PATH. No arbitrary query, table, database, URL or credentials-file input is accepted. The internal Python helpers are trusted programming interfaces.

```sh
# With the package installed and its virtual environment active:
docker compose up -d --wait
mkdir -p artifacts
PGHOST=127.0.0.1 PGPORT=5432 PGPASSWORD=disposable-lab-admin \
  python -m scripts.collect_lab --disposable-lab --out artifacts/lab
```

The Compose password and reader password are public disposable examples, unsuitable for real data. The container port is bound to loopback. The collector refuses any pre-existing non-template/non-postgres database or non-built-in/non-postgres role. It creates fixed `plan_evidence_lab`, non-login `plan_owner` and restricted login `plan_reader`. It never drops, overwrites or automatically cleans an existing database/role. Bootstrap role and database creation is not atomic: failure can leave partial resources that cause the next attempt to refuse. Use a new disposable instance; do not run alongside other clients.

`PGHOST` must be localhost/127.0.0.1/::1, `PGPORT` a bounded integer and `PGPASSWORD` the disposable postgres administrator password. Only explicit connection arguments and a small environment allowlist reach psql. Credential-file/service/options overrides are not inherited; `-X` skips startup files and `-w` prevents prompts. Loopback identifies the allowed destination class, not server authenticity. No TLS or malicious-server isolation is claimed. The supplied credentials and server must be trusted, local and disposable.

## Dataset and workload

The owner creates `evidence.events` with exactly 20,000 integer rows: `id=1..20000`, `cohort=id % 1000`, `amount=id % 97`, no personal fields. It runs VACUUM ANALYZE once. The reader's ordered full-table projection must exactly match independently generated Python rows before experiments proceed; its SHA-256 is recorded.

Three reviewed queries are in `scripts/collect_lab.py`:

| Alias | Work | Expected result |
| --- | --- | --- |
| `selective` | cohort 7, ordered by id | 20 id/amount rows |
| `aggregate` | group by cohort, order, limit 10 | 10 count/sum rows; 20 per group |
| `repeated_inner` | first 12 ids, correlated cohort count | 12 rows, each count 20 |

Baseline has no index. The owner then creates one covering B-tree `(cohort,id) INCLUDE(amount)` and repeats the same workload. The fixture data remains unchanged and ANALYZE is not rerun after index creation. The configuration hash covers the fixed session settings **and index presence**; fixture/workload/query hashes remain fixed. This is a configuration comparison, not a guaranteed index benefit or controlled causal estimate. Table size, selectivity, cache state and planner choices matter.

Each phase runs a correctness SELECT before three measured EXPLAIN executions per query, 18 measured captures total. Exact result text must match Python reference output in both configurations. Correctness reads warm buffers and are excluded from timers. Baseline always precedes indexed and queries have a fixed order; no cache flush, randomised order, dedicated hardware, concurrency, steady-state assumption or production capacity claim. Planner statistics and future image patch versions can vary. Docker major tags are not immutable image digests; actual server, client, Python and host details are recorded.

## Execution and measurements

Measured sessions use `plan_reader` with schema usage and table SELECT only, no membership, ownership, superuser, BYPASSRLS, role/database creation or table writes. The guard rechecks these properties each phase. Queries run in a read-only transaction with statement timeout 5s, lock timeout 1s, parallel workers 0, JIT off and work_mem 16MB. `EXPLAIN (ANALYZE, BUFFERS, TIMING OFF, FORMAT JSON)` executes only the fixed trusted SELECTs. Read-only transactions and role grants are controls for this workload, not an arbitrary-SQL sandbox.

Client wall milliseconds use `perf_counter` around psql process startup, connection, transaction settings, EXPLAIN, result transfer and strict JSON parse. Inspection, hashing/projection, artifact writes, fixture/index construction and correctness SELECTs are outside the timer. Server `Execution Time` remains available with TIMING OFF and measures the instrumented statement, not full application latency; no per-node timings are invented. Raw individual samples and per-configuration/query medians are recorded. A single digit or rounded server value is retained as reported; no percent improvement is inferred automatically.

Each psql operation has a 20-second process timeout, 3-second connection timeout and output acceptance cap 2 MiB. Captured subprocess output is checked after collection; this is not a bounded hostile-server streaming client. Commands and outputs are fixed/small under the trusted lab assumptions. Errors are sanitized without echoing SQL/passwords. Database bootstrap and post-run version queries are privileged; measured queries use the reader.

## Artifacts and reproducibility

A new output directory receives 18 exact raw plan byte captures, 18 manifests, 18 inspections and `lab-report.json` only after all comparisons succeed. Stored raw bytes are checked against inspection hashes; output is private 0600 in a new 0700 directory on POSIX. Failures can leave partial artifacts and database resources. These files contain synthetic table/index identifiers and controlled SQL in the source code; real production captures remain excluded.

Re-inspect any saved `*-raw.json` with its corresponding `*-manifest.json` using the installed CLI. `lab-report.json` includes hashes, query-result hashes/cardinalities, every wall/server sample, medians, server/client/Python/platform details and limitations. The completion flag is emitted only after both configurations and all correctness checks finish. CI repeats the workload on PostgreSQL 16 and 18, separately from offline unit tests. Unit mocks verify invocation constraints, not database performance or actual grants.

See [PostgreSQL psql reference](https://www.postgresql.org/docs/18/app-psql.html) and [EXPLAIN](https://www.postgresql.org/docs/18/sql-explain.html), checked 1 November 2026.
