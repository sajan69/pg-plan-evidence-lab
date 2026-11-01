# PostgreSQL Plan Evidence Lab

PostgreSQL query-plan analysis and reproducible performance experiments for a disposable synthetic database.

The research scope is offline comparison of bounded `EXPLAIN (FORMAT JSON)` captures and controlled PostgreSQL 16/18 lab workloads. Plan structure, row estimates, execution measurements and workload provenance are separate kinds of evidence; a changed plan alone does not establish a performance regression.

## Data and execution boundaries

Use synthetic lab data. Raw plans can contain SQL expressions, literals and database object names; do not publish production captures or assume that removing selected fields guarantees redaction.

`EXPLAIN ANALYZE` executes the statement. Any lab collector must execute only reviewed, fixed queries in a disposable database. A read-only transaction alone is not a sandbox for arbitrary SQL.

No executable tooling or measured results are included yet.

## References

- [PostgreSQL 18: using EXPLAIN](https://www.postgresql.org/docs/18/using-explain.html)
- [PostgreSQL 18: EXPLAIN command](https://www.postgresql.org/docs/18/sql-explain.html)

Planner costs are not milliseconds. Actual row counts and execution times reported for repeatedly executed nodes are per-execution averages; loop counts matter when interpreting them. Inclusive parent/child timings must not be summed as independent work.
