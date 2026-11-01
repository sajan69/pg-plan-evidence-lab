# Synthetic PostgreSQL evidence

These are actual executions of the fixed 20,000-row synthetic lab, not production database performance, universal index recommendations or an automatic regression detector. The handwritten `examples/plan.json` and its standalone report remain separate illustrative data.

## Recorded acquisition

The machine-readable records [PostgreSQL 16](reports/lab-pg16.json) and [PostgreSQL 18](reports/lab-pg18.json) were parsed from the successful [source CI run](https://github.com/sajan69/pg-plan-evidence-lab/actions/runs/41283168513) at collector commit `702b382e02712e0609aa17eafdfc0286d009a787`, acquired 1 November 2026. Each record includes every individual sample, hashes, medians, environment and method. Later CI repetitions have different timestamps and timings; they do not replace this recorded sample.

Each database independently passed exact fixture-content and query-result comparisons in baseline and indexed configurations. Fixture SHA-256 is `d783d0d5865093380c1e15985daa5ff0ebd65d5e96adb3ea433ffe71efe628fe` in both engines. It hashes ordered `id|cohort|amount` rows separated by LF, without a trailing LF. There are 20,000 rows, 1,000 cohorts and no personal data. Query results have 20, 10 and 12 rows respectively; the repeated inner count is 20 for each of the 12 outer rows.

## Measured outcomes

Milliseconds below are medians of **three** individual executions per query/configuration. Server execution is PostgreSQL's instrumented `Execution Time` with node timing disabled. Client wall includes a new psql process, authentication/connection, transaction setup, SQL execution, transfer and strict JSON parsing. Inspection and writes are outside that timer.

| Server | Query | Baseline server ms | Indexed server ms | Baseline client ms | Indexed client ms |
| --- | --- | ---: | ---: | ---: | ---: |
| 16.15 | selective | 0.611 | 0.046 | 25.054 | 25.166 |
| 16.15 | aggregate | 2.024 | 0.092 | 27.957 | 25.935 |
| 16.15 | repeated_inner | 5.741 | 0.652 | 31.230 | 24.983 |
| 18.6 | selective | 0.764 | 0.049 | 31.835 | 30.197 |
| 18.6 | aggregate | 2.845 | 0.113 | 34.234 | 30.336 |
| 18.6 | repeated_inner | 8.150 | 0.836 | 39.136 | 31.698 |

The indexed configuration had lower reported server medians for these particular synthetic queries. That does not imply universally faster client requests: PostgreSQL 16's selective-query client median was slightly higher with the index. Connection/process overhead dominates many client samples, and three repetitions cannot establish statistical significance or production tail latency. There is no percentage-improvement, throughput, real-user, cost-savings or cross-version speed ranking claim.

This is a bounded serial experiment with a no-index baseline and one covering `(cohort,id) INCLUDE(amount)` index. Data and session settings stay fixed; ANALYZE runs once before baseline. Baseline always runs first, query order is fixed, and correctness SELECTs warm data before each measured group. Index construction also touches data. There is no cold-cache measurement, explicit warmup phase, randomised configuration order, dedicated hardware, concurrency or independent prospective trial. Parser/report throughput was not measured by these database timers.

## Environment and method

Both recorded jobs used Python 3.12.15, Linux 7.0.0-1017-azure x86_64/glibc 2.39, four reported logical CPUs on separate shared GitHub runners. PostgreSQL servers were 16.15 and 18.6 (Debian PGDG builds); the psql client in both jobs was 16.15 (Ubuntu PGDG). Exact version strings are in the records. This client/server combination was actually exercised; future major-tag Docker images and shared-runner hardware may differ.

Three fixed queries × three repeats × two configurations gives **18 measured captures per engine**. Fixture setup, VACUUM ANALYZE, index creation, reference-generation, correctness reads, projections and file output are excluded from client timers. Server instrumentation still incurs EXPLAIN/BUFFERS overhead. Read sessions disable JIT and parallel query workers, use 16MB work_mem, a 5-second statement timeout and 1-second lock timeout. See [lab reproduction and constraints](LAB.md). Memory/cache/storage characteristics beyond these settings were not controlled.

## Verification and interpretation

The offline suite has 21 distinct test methods: 11 plan/context/diagnostic tests, three CLI/file tests, four lab invocation/reference tests and three report tests. It covers duplicate/nonfinite/underflow JSON, bounds, unsupported operators, missing/zero/unexecuted observations, per-loop ratios, immutable byte identity, shape limitations, mismatch gates, output exclusivity, synthetic result references, loopback/environment controls and inert report text. These cases are not a coverage percentage, security certification or exhaustive PostgreSQL compatibility claim. Mocked subprocess tests verify invocation constraints; the PostgreSQL jobs separately exercise actual SQL, grants, fixture construction and plans.

The [integrated validation run](https://github.com/sajan69/pg-plan-evidence-lab/actions/runs/41283565021) at `29ea5a88922d97f9662fd991daaf227392a6d667` passed installed-wheel tests on Python 3.11–3.13, both real database jobs, capture-byte/manifest reinspection equality and JSON/CSV/HTML exports of actual repeated-inner captures. Re-running on the populated cluster was refused. Four actual Chromium checks passed: displayed row/loop values and caveats, expandable provenance, contained 390px table scrolling, and inert IMG/SCRIPT text with no remote requests, dialogs or page errors. CI artifacts contain raw plans, manifests, inspections, comparison reports and screenshots for seven days; the aggregate timing records above are retained in Git.

Node paths belong to each individual projected tree. Shape hashes omit object names, predicates, expressions and worker details, and context hashes are caller declarations rather than query authentication. A matching shape does not mean matching work, and changed shape does not prove regression. Recorded row counts may be rounded per-loop averages; partial consumption and parallel execution can confound estimates. No parent/child time or buffer summation is used. Missing measurements stay unknown and zero mismatches do not become an artificial infinite ratio.

The PostgreSQL 18 integrated repeated-inner capture illustrates why loop-aware interpretation matters: the inner Seq Scan (baseline) and Index Only Scan (indexed) each reported 20 rows per loop over 12 loops, approximately 240 emitted rows for that node. The per-loop q-error was 1 in both, despite different plan shapes and timings. Its parent aggregate emitted one row per loop, approximately 12 overall. Parent/child shared-buffer counters overlapped and were not summed. These observations come from the integrated validation run above, separate from the recorded timing acquisition.
