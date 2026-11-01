import copy
import json
import unittest
from pg_plan_evidence.analysis import inspect, compare
from pg_plan_evidence.contract import EvidenceError, canonical


def context(**updates):
    return {"schema_version": 1, "source": "synthetic_lab", "server_version_num": 180006,
            "query_alias": "nested_demo", "captured_at": "2026-11-01T10:00:00+10:00",
            "query_sha256": "a" * 64, "fixture_sha256": "b" * 64,
            "workload_sha256": "c" * 64, "settings_sha256": "d" * 64, **updates}


def plan():
    return [{"Plan": {"Node Type": "Nested Loop", "Plan Rows": 10, "Startup Cost": 0,
                      "Total Cost": 100, "Actual Rows": 6, "Actual Loops": 1,
                      "Plans": [{"Node Type": "Seq Scan", "Plan Rows": 5,
                                 "Actual Rows": 3, "Actual Loops": 1},
                                {"Node Type": "Index Scan", "Parent Relationship": "Inner",
                                 "Plan Rows": 4, "Actual Rows": 2, "Actual Loops": 3,
                                 "Actual Startup Time": 0.01, "Actual Total Time": 0.02,
                                 "Filter": "secret@example.test", "Relation Name": "private_table"}]},
             "Execution Time": 0.2, "Planning Time": 0.1}]


def run(value=None, ctx=None):
    return inspect(canonical(plan() if value is None else value),
                   canonical(context() if ctx is None else ctx))


class AnalysisTests(unittest.TestCase):
    def test_per_loop_diagnostic_and_no_sensitive_fields(self):
        result = run()
        inner = result["nodes"][2]
        self.assertEqual(inner["diagnostic"], {"status": "positive", "q_error_per_loop": 2,
                                               "approx_emitted_rows_all_loops": 6})
        serialized = json.dumps(result)
        self.assertNotIn("secret@", serialized)
        self.assertNotIn("private_table", serialized)
        self.assertNotIn("Filter", serialized)
        self.assertEqual(result["provenance"]["context"]["captured_at"], "2026-11-01T00:00:00+00:00")

    def test_unknowns_zero_and_not_executed(self):
        for node, status, q in [({"Node Type": "Result"}, "not_measured", None),
                               ({"Node Type": "Result", "Actual Rows": 0, "Actual Loops": 0}, "not_executed", None),
                               ({"Node Type": "Result", "Actual Rows": 0, "Actual Loops": 1, "Plan Rows": 0}, "both_zero", 1),
                               ({"Node Type": "Result", "Actual Rows": 0, "Actual Loops": 1, "Plan Rows": 1}, "zero_mismatch", None),
                               ({"Node Type": "Result", "Actual Rows": 2, "Actual Loops": 1}, "estimate_missing", None)]:
            with self.subTest(status=status):
                d = run([{"Plan": node}])["nodes"][0]["diagnostic"]
                self.assertEqual((d["status"], d["q_error_per_loop"]), (status, q))

    def test_strict_json_everywhere(self):
        for raw in (b'[{"Plan":{},"Plan":{}}]', b'[{"extra":NaN}]', b'[{"extra":1e999}]', b'[{"extra":1e-999}]',
                    b'\xff', b'\xef\xbb\xbf[]', b'[] trailing'):
            with self.subTest(raw=raw), self.assertRaises(EvidenceError):
                inspect(raw, canonical(context()))

    def test_numeric_types_ranges_and_pairs(self):
        for patch in ({"Plan Rows": True}, {"Plan Rows": -1}, {"Plan Rows": "3"},
                      {"Plan Rows": 1e19}, {"Plan Rows": 1e-320},
                      {"Actual Rows": 1}, {"Actual Loops": 1},
                      {"Actual Loops": 0, "Actual Rows": 1},
                      {"Actual Loops": 1.5, "Actual Rows": 1},
                      {"Startup Cost": 2}, {"Startup Cost": 3, "Total Cost": 2},
                      {"Actual Startup Time": 0, "Actual Total Time": 1}):
            with self.subTest(patch=patch), self.assertRaises(EvidenceError):
                run([{"Plan": {"Node Type": "Result", **patch}}])

    def test_manifest_contract(self):
        for patch in ({"schema_version": True}, {"server_version_num": 190000},
                      {"server_version_num": 170001}, {"query_alias": "<script>"},
                      {"source": "production_attested"}, {"captured_at": "2026-01-01"},
                      {"captured_at": "bad"}, {"query_sha256": "x" * 64}, {"extra": "secret"}):
            with self.subTest(patch=patch), self.assertRaises(EvidenceError):
                run(ctx=context(**patch))
        self.assertEqual(run(ctx=context(server_version_num=160015))["schema_version"], 1)

    def test_shape_ignores_values_but_observation_preserves_change(self):
        first = run()
        value = plan()
        value[0]["Plan"]["Actual Rows"] = 100
        second = run(value)
        self.assertEqual(first["shape_sha256"], second["shape_sha256"])
        self.assertNotEqual(first["projection_sha256"], second["projection_sha256"])
        self.assertNotEqual(first["observation_id"], second["observation_id"])
        self.assertEqual(first, run())
        value[0]["Plan"]["Plans"][1]["Node Type"] = "Index Only Scan"
        self.assertNotEqual(first["shape_sha256"], run(value)["shape_sha256"])

    def test_discarded_field_changes_raw_identity_not_projection(self):
        value = plan()
        value[0]["Query Text"] = "hidden query"
        self.assertEqual(run()["projection_sha256"], run(value)["projection_sha256"])
        self.assertNotEqual(run()["observation_id"], run(value)["observation_id"])

    def test_context_gates_and_settings_change(self):
        a = run()
        for key, val in (("query_sha256", "e" * 64), ("fixture_sha256", "e" * 64),
                         ("workload_sha256", "e" * 64), ("query_alias", "other"),
                         ("server_version_num", 160015), ("source", "manual_export")):
            with self.subTest(key=key):
                result = compare(a, run(ctx=context(**{key: val})))
                self.assertEqual(result["status"], "blocked")
                self.assertIsNone(result["same_shape"])
                self.assertEqual(result["context_mismatches"], [key])
        result = compare(a, run(ctx=context(settings_sha256="e" * 64)))
        self.assertEqual(result["status"], "context_matched")
        self.assertTrue(result["settings_changed"])
        self.assertTrue(result["same_shape"])

    def test_operator_and_structure_refusal(self):
        for value in ([], [{}, {}], [{"Plan": None}], [{"Plan": {"Node Type": "SecretOperator"}}],
                      [{"Plan": {"Node Type": "Custom Scan"}}],
                      [{"Plan": {"Node Type": "Result", "Plans": {}}}],
                      [{"Plan": {"Node Type": "Result", "Parallel Aware": 1}}],
                      [{"Plan": {"Node Type": "Result", "Strategy": "secret"}}]):
            with self.subTest(value=value), self.assertRaises(EvidenceError):
                run(value)

    def test_input_and_tree_budgets(self):
        with self.assertRaises(EvidenceError):
            inspect(b' ' * (2 * 1024 * 1024 + 1), canonical(context()))
        deep = {"Node Type": "Result"}
        for _ in range(34):
            deep = {"Node Type": "Result", "Plans": [deep]}
        with self.assertRaises(EvidenceError):
            run([{"Plan": deep}])
        wide = {"Node Type": "Append", "Plans": [{"Node Type": "Result"}] * 1000}
        with self.assertRaises(EvidenceError):
            run([{"Plan": wide}])

    def test_parallel_and_early_termination_caveats(self):
        value = [{"Plan": {"Node Type": "Gather", "Workers Planned": 2, "Workers Launched": 1,
                            "Plans": [{"Node Type": "Seq Scan", "Parallel Aware": True,
                                       "Workers": [{"Worker Number": 0, "Filter": "secret"}]}]}}]
        result = run(value)
        self.assertTrue(result["nodes"][1]["fields"]["Parallel Aware"])
        self.assertNotIn("Workers", result["nodes"][1]["fields"])
        self.assertTrue(any("parallel" in w for w in result["warnings"]))
