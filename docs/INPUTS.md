# Capture and diagnostic semantics

The CLI takes a local PostgreSQL `EXPLAIN (FORMAT JSON)` document containing exactly one statement object and one `Plan`, plus a separate manifest. UTF-8 JSON only; duplicate keys, BOM, nonfinite values (including overflow in discarded fields), malformed JSON and trailing content are refused. There is no skip-invalid mode.

## Manifest v1

All fields are required; unknown fields are refused:

| Field | Meaning |
| --- | --- |
| `schema_version` | Integer 1 |
| `source` | `synthetic_fixture`, `synthetic_lab` or `manual_export` |
| `server_version_num` | PostgreSQL numeric version in reviewed major 16 or 18 |
| `query_alias` | Lowercase ASCII alias, up to 48 characters |
| `captured_at` | Explicit-offset ISO timestamp, normalized to UTC; year 2000–2100 |
| `query_sha256` | Hash of the caller's exact query representation |
| `fixture_sha256` | Hash of the caller's dataset/fixture definition |
| `workload_sha256` | Hash of parameters and workload definition |
| `settings_sha256` | Hash of the caller's settings representation |

Hashes are 64 lowercase hexadecimal characters. Their contents and representation are caller-defined and unverified. Capture timestamps, source labels and hashes do not authenticate PostgreSQL, execution, query equivalence, completeness, cache state or a data vintage. Hashes can also reveal equality across captures; they are not anonymisation.

Examples use a handwritten three-node JSON fixture and hashes of descriptive synthetic strings. Its numbers illustrate semantics and are not measured results. `captured_at` is fixture metadata, not evidence of a database run.

## Projection and identity

The adapter projects node type, ordered child paths, reviewed structural enums/booleans, selected cost/row/time/buffer counters and statement planning/execution times. Raw SQL, expressions, names, settings values, trigger details, JIT sections and worker detail are discarded. Unknown scalar fields are ignored after whole-document JSON validation. Unknown node types and Custom/Foreign Scan implementations are refused; this is not a complete PostgreSQL plan interpreter. `ModifyTable` is a recognised offline plan shape, not permission to execute modifications.

An observation ID hashes adapter version, normalized context and the raw input hash. The projection hash covers retained node fields, diagnostics and statement times. The shape hash covers only node types, retained structural fields and ordered child counts/paths. A discarded expression change affects the raw observation ID but may leave projection and shape unchanged. Matching shape cannot detect changed index/object names, predicates, parameter values or unprojected execution details. Hashes identify bytes/projections, not publisher authenticity.

Numeric fields must be finite, nonnegative and either zero or between 1e-12 and 1e18. Booleans and numeric strings are refused. Loops must be integral. Actual rows and loops must occur together; zero loops require zero actual rows. Costs and node timing endpoints must occur as valid ordered pairs. Node timing requires actual rows/loops, but `TIMING OFF` actuals without node times are supported. Missing fields are left absent; there is no inferred zero or inferred execution status from absent measurements.

## Row diagnostics

For positive actual and estimated rows and at least one loop, q-error is `max(estimate/actual, actual/estimate)`, comparing the **per-loop** row counts. It is a descriptive discrepancy, not a general optimizer-quality score: early termination, filters, limits and parallel execution can affect observations. Both recorded counts zero gives q-error 1; a single zero gives `zero_mismatch` and null q-error, not infinity. Missing actuals give `not_measured`, zero loops `not_executed`, missing estimate `estimate_missing`.

`approx_emitted_rows_all_loops = actual_rows * actual_loops`. Actual counts are displayed averages and may be rounded. The product is approximate emitted work for that node, not distinct tuples, rows returned to the client, or an additive tree total. Worker arrays are omitted; parallel plans retain an explicit general caution. Timing and buffer values are inclusive and must not be added across nodes. Statement execution time is the reported instrumented statement measurement; it excludes a full client/application latency measurement.

## Comparisons and bounds

Different source, exact server version, query alias/hash, fixture hash or workload hash blocks shape comparison. All mismatch names are returned. Settings hashes and acquisition timestamps may differ; `settings_changed` is explicit. Exact-version gating is conservative: cross-version captures can be inspected individually but are not declared comparable. Matching declarations cannot prove a controlled experiment, and there is no automatic performance verdict or position-based claim that two different tree nodes correspond.

Input caps are 2 MiB per plan and 16 KiB per manifest. Whole JSON has depth 64 and 50,000 value visits; the plan tree has depth 32, at most 1,000 nodes and at most 1,000 children per node. The JSON depth budget can refuse a deeply nested plan before the tree limit. Limits apply before reports are written. JSON outputs are capped at 2 MiB after serialization and refused rather than truncated. Blocked comparison is a valid report with CLI exit 0; input/operational failures exit 2 with fixed sanitized codes.

## Report formats

Both CLI commands accept `--format json|csv|html` (default JSON). HTML is a standalone script-free document with escaped text, a hash-allowlisted fixed stylesheet, no remote assets and expandable capture provenance. Tables scroll inside the report at narrow widths; no JavaScript or upload endpoint is present. It shows each capture independently and does not infer node correspondence from matching paths in changed trees.

CSV repeats source, capture time, query/version/data/workload/settings identity, comparison status and caveats on every node row. Unknown numeric values are empty cells, not zero. Node paths have an explicit `node:` prefix to avoid spreadsheet conversion to decimal numbers. All cells are quoted; formula-like strings receive a leading apostrophe after whitespace/NFKC checks. This is a spreadsheet mitigation, not a universal import guarantee. JSON retains all projected fields; HTML/CSV are diagnostic views rather than a raw-plan archive.
