"""Allowlisted projection. Shape equality is deliberately narrower than plan equality."""
from .contract import canonical, fail, manifest, sha, strict_json

# Reviewed PostgreSQL 16/18 built-in plan types. Extensions and new operators need review.
OPERATORS = frozenset("""Result|ProjectSet|ModifyTable|Append|Merge Append|Recursive Union|
BitmapAnd|BitmapOr|Seq Scan|Sample Scan|Index Scan|Index Only Scan|Bitmap Index Scan|
Bitmap Heap Scan|Tid Scan|Tid Range Scan|Subquery Scan|Function Scan|Table Function Scan|
Values Scan|CTE Scan|Named Tuplestore Scan|WorkTable Scan|Foreign Scan|Custom Scan|
Nested Loop|Merge Join|Hash Join|Materialize|Memoize|Sort|Incremental Sort|Group|
Aggregate|WindowAgg|Unique|Gather|Gather Merge|Hash|SetOp|LockRows|Limit""".replace("\n", "").split("|"))
# Foreign/Custom Scan names are recognized but their implementation isn't interpreted.
ENUMS = {
    "Parent Relationship": {"Outer", "Inner", "SubPlan", "InitPlan", "Member"},
    "Join Type": {"Inner", "Left", "Full", "Right", "Semi", "Anti", "Right Anti"},
    "Strategy": {"Plain", "Sorted", "Hashed", "Mixed"},
    "Partial Mode": {"Simple", "Partial", "Finalize"},
    "Scan Direction": {"Forward", "Backward", "NoMovement"},
}
NUMBERS = ("Startup Cost", "Total Cost", "Plan Rows", "Plan Width", "Actual Rows",
           "Actual Loops", "Actual Startup Time", "Actual Total Time",
           "Shared Hit Blocks", "Shared Read Blocks", "Shared Dirtied Blocks",
           "Shared Written Blocks", "Local Hit Blocks", "Local Read Blocks",
           "Temp Read Blocks", "Temp Written Blocks", "Rows Removed by Filter",
           "Rows Removed by Join Filter", "Heap Fetches", "Workers Planned", "Workers Launched")
WARNINGS = [
    "Caller-declared context and hashes are not publisher or query authentication.",
    "Projection omits SQL, names, expressions and worker details; it is not a general redactor.",
    "Shape excludes predicates, object names and many execution properties; equal shape is not equal work.",
    "Actual rows are per-loop averages; products are approximate emitted rows, not distinct tuples.",
    "Partial consumption, parallel execution and early termination can confound estimate comparisons.",
    "Node times and buffer counts include descendants; do not sum them across the tree.",
    "A single instrumented execution is not a latency benchmark or regression verdict.",
]


def number(value):
    if type(value) not in (int, float) or not (value == 0 or 1e-12 <= value <= 10**18):
        fail("plan_number")
    return value


def diagnostic(node):
    estimate, actual, loops = (node.get(k) for k in ("Plan Rows", "Actual Rows", "Actual Loops"))
    product = None if actual is None or loops is None else actual * loops
    ratio = None
    if actual is None:
        status = "not_measured"
    elif loops == 0:
        status = "not_executed"
    elif estimate is None:
        status = "estimate_missing"
    elif estimate == actual == 0:
        status, ratio = "both_zero", 1.0
    elif estimate == 0 or actual == 0:
        status = "zero_mismatch"
    else:
        status, ratio = "positive", max(estimate / actual, actual / estimate)
    return {"status": status, "q_error_per_loop": ratio,
            "approx_emitted_rows_all_loops": product}


def inspect(plan_raw, manifest_raw):
    context = manifest(manifest_raw)
    value = strict_json(plan_raw, 2 * 1024 * 1024)
    if not isinstance(value, list) or len(value) != 1 or not isinstance(value[0], dict):
        fail("statement_count")
    summary = value[0]
    root = summary.get("Plan")
    rows, shapes = [], []
    # Iterative traversal; path addresses are stable only within this ordered projection.
    stack = [(root, "0", 0)]
    while stack:
        node, path, depth = stack.pop()
        if not isinstance(node, dict) or depth > 32 or len(rows) >= 1000:
            fail("plan_budget")
        kind = node.get("Node Type")
        if not isinstance(kind, str) or kind not in OPERATORS or kind in {"Custom Scan", "Foreign Scan"}:
            fail("unsupported_operator")
        selected = {"Node Type": kind}
        for key, allowed in ENUMS.items():
            if key in node:
                if not isinstance(node[key], str) or node[key] not in allowed:
                    fail("plan_enum")
                selected[key] = node[key]
        for key in ("Parallel Aware", "Async Capable"):
            if key in node:
                if type(node[key]) is not bool:
                    fail("plan_boolean")
                selected[key] = node[key]
        shape = {**selected, "path": path}
        for key in NUMBERS:
            if key in node:
                selected[key] = number(node[key])
        if ("Actual Rows" in selected) != ("Actual Loops" in selected):
            fail("incomplete_actuals")
        if selected.get("Actual Loops") == 0 and selected.get("Actual Rows") != 0:
            fail("unexecuted_rows")
        if "Actual Loops" in selected and selected["Actual Loops"] != int(selected["Actual Loops"]):
            fail("fractional_loops")
        for start, end in (("Startup Cost", "Total Cost"), ("Actual Startup Time", "Actual Total Time")):
            if (start in selected) != (end in selected):
                fail("incomplete_range")
            if start in selected and selected[start] > selected[end]:
                fail("inverted_range")
        if "Actual Total Time" in selected and "Actual Rows" not in selected:
            fail("timing_without_actuals")
        children = node.get("Plans", [])
        if not isinstance(children, list) or len(children) > 1000:
            fail("plan_children")
        shape["children"] = len(children)
        rows.append({"path": path, "fields": selected, "diagnostic": diagnostic(selected)})
        shapes.append(shape)
        stack.extend((child, f"{path}.{i}", depth + 1)
                     for i, child in reversed(list(enumerate(children))))
    times = {key: number(summary[key]) for key in ("Planning Time", "Execution Time") if key in summary}
    projected = {"nodes": rows, "statement_times_ms": times}
    raw_hash = sha(plan_raw)
    observation = {"adapter": "pg-explain-v1", "context": context, "raw_sha256": raw_hash}
    return {"schema_version": 1, "observation_id": sha(canonical(observation)),
            "provenance": observation, "projection_sha256": sha(canonical(projected)),
            "shape_sha256": sha(canonical(shapes)), **projected, "warnings": WARNINGS.copy()}


def compare(left, right):
    """Only accept reports produced by inspect within this process (internal API)."""
    a, b = (x["provenance"]["context"] for x in (left, right))
    # Settings may deliberately change; query/workload/fixture/version must agree.
    keys = ("source", "server_version_num", "query_alias", "query_sha256", "fixture_sha256", "workload_sha256")
    reasons = [key for key in keys if a[key] != b[key]]
    return {"schema_version": 1, "status": "blocked" if reasons else "context_matched",
            "context_mismatches": reasons,
            "left_observation": left["observation_id"], "right_observation": right["observation_id"],
            "same_shape": None if reasons else left["shape_sha256"] == right["shape_sha256"],
            "settings_changed": a["settings_sha256"] != b["settings_sha256"],
            "left": left, "right": right,
            "verdict": "No performance regression verdict; repeated controlled measurements are required."}
