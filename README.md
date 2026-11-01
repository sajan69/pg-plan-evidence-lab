# PostgreSQL Plan Evidence Lab

Offline PostgreSQL query-plan inspection and context-gated comparison. The reader separates structural changes, per-loop row estimates and measured execution fields, without treating a changed plan as a performance regression.

## Setup and use

Python 3.11 or newer; no runtime dependencies, database connection or network access required.

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install .
pg-plan-evidence inspect examples/plan.json --manifest examples/manifest.json --out inspection.json
pg-plan-evidence compare examples/plan.json examples/plan.json \
  --left-manifest examples/manifest.json --right-manifest examples/manifest.json --out comparison.json
pg-plan-evidence inspect examples/plan.json --manifest examples/manifest.json --format html --out report.html
python -m unittest discover -s tests -v
```

Output destinations must be new files. Comparisons with mismatched query, fixture, workload, source or exact server version produce `status: blocked`; consumers must check this field. A context match is a caller-declared precondition, not proof of equivalent queries or conditions. Settings hashes may differ to describe a deliberate configuration experiment.

The example is a **handwritten synthetic JSON fixture**, not a PostgreSQL execution or benchmark. Its repeated inner node has estimated rows 4, actual rows 2 per loop and 3 loops: q-error is 2 and approximate emitted rows across loops are 6. Missing actuals remain unknown. The example is independent of the [disposable synthetic PostgreSQL lab](docs/LAB.md); measured lab artifacts are generated separately.

## Evidence and safety

The adapter supports a reviewed structural/numeric subset of PostgreSQL 16/18 JSON plans. It removes SQL, expressions, object names and worker detail from the projection. Input hashes and controlled context aliases remain; review these before sharing. This is not a general redaction service.

`EXPLAIN ANALYZE` executes its statement. The installed offline commands only read files and never execute SQL. The repository-only lab collector explicitly runs reviewed synthetic queries. The collector must use reviewed fixed queries in a disposable synthetic database; a read-only transaction alone is not an arbitrary-SQL sandbox.

Planner costs are not milliseconds. Actual rows and node times are per-loop averages. Parent times and buffers include descendants, and parallel or partially consumed plans complicate interpretation. Matching projected shape does not establish equivalent predicates, indexes, work or performance.

The reader validates JSON/context, projects allowed evidence, computes hashes/diagnostics and serializes bounded reports. The separate lab script supplies trusted synthetic captures and correctness/measurement evidence.

See [input and diagnostic semantics](docs/INPUTS.md), [security boundaries](docs/SECURITY.md) and [actual synthetic lab outcomes](docs/EVALUATION.md). The recorded experiment contains all 18 executions per engine and separate server/client medians; it does not certify production performance.

## References

- [PostgreSQL 18: using EXPLAIN](https://www.postgresql.org/docs/18/using-explain.html)
- [PostgreSQL 16: EXPLAIN command](https://www.postgresql.org/docs/16/sql-explain.html)
- [PostgreSQL 18: EXPLAIN command](https://www.postgresql.org/docs/18/sql-explain.html)

The version-specific references were checked on 1 November 2026. New development-branch fields are not assumed to be released features.
