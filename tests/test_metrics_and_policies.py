import copy
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from apology.audit import probe_targets
from apology.bundles import inspect_bundle, validate_bundle_audit
from apology.execution import execute_lean
from apology.probes import run_probe
from apology.restate import split_def, split_theorem
from apology.review import record_review
from apology.schema import contained_path
from experiments.metrics import evaluate_adjudicated, wilson
from test_workflow import sample_bundle, graph_fixture


class ExecutionPolicyTests(unittest.TestCase):
    def test_disabled_and_untrusted_local_mode_never_launch_process(self):
        for env in ({"APOLOGY_LEAN_MODE": "disabled"}, {"APOLOGY_LEAN_MODE": "local", "APOLOGY_TRUST_LOCAL_LEAN": "0"}):
            with patch.dict(os.environ, env), patch("apology.execution.subprocess.run") as proc:
                result = execute_lean(Path("."), "import Lean")
                self.assertIsNone(result.returncode)
                proc.assert_not_called()

    def test_docker_requires_pinned_image(self):
        with patch.dict(os.environ, {"APOLOGY_LEAN_MODE": "docker", "APOLOGY_LEAN_IMAGE": "mutable:latest"}), \
                patch("apology.execution.subprocess.run") as proc:
            self.assertIsNone(execute_lean(Path("."), "import Lean").returncode)
            proc.assert_not_called()

    def test_paths_cannot_escape_source_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                contained_path(Path(tmp), "../escape.lean")

    def test_non_vacuity_is_reserved_before_other_flags(self):
        targets = probe_targets({"flags": [{"id": str(i), "decl": "d", "line": 1,
                                             "explanation": "x", "probe_idea": "x"} for i in range(10)]})
        self.assertEqual(targets[0]["id"], "NV")

    def test_unsupported_restatement_types_fail_explicitly(self):
        with self.assertRaises(ValueError):
            split_def("structure Foo where\n  value : Nat", "Foo")
        with self.assertRaises(ValueError):
            split_theorem("theorem foo : True", "foo")


class MetricTests(unittest.TestCase):
    def rows(self):
        return [{"id": "positive", "source_group": "paper-a", "expected_mismatch": True,
                 "true_positive_flags": 1, "false_positive_flags": 0, "adjudication": "human_reviewed", "reviewer": "fixture"},
                {"id": "clean", "source_group": "paper-b", "expected_mismatch": False,
                 "true_positive_flags": 0, "false_positive_flags": 1, "adjudication": "human_reviewed", "reviewer": "fixture"}]

    def test_unadjudicated_results_are_not_semantic_accuracy(self):
        rows = self.rows()
        rows[0]["adjudication"] = "model"
        with self.assertRaises(ValueError):
            evaluate_adjudicated(rows)

    def test_metrics_have_correct_units_and_raw_counts(self):
        report = evaluate_adjudicated(self.rows())
        self.assertEqual(report["precision_by_flag"]["rate"], .5)
        self.assertEqual(report["recall_by_case"]["rate"], 1)
        self.assertEqual(report["clean_case_false_alarm_rate"]["denominator"], 1)
        self.assertEqual(report["source_groups"], 2)

    def test_same_source_cannot_leak_across_splits(self):
        rows = self.rows()
        rows[1]["source_group"] = rows[0]["source_group"]
        rows[0]["split"], rows[1]["split"] = "train", "test"
        with self.assertRaises(ValueError):
            evaluate_adjudicated(rows)

    def test_small_controls_do_not_prove_zero_error_rate(self):
        self.assertGreater(wilson(0, 12)[1], .2)


class MoreEvidenceTests(unittest.TestCase):
    def test_absent_declaration_is_not_a_mapped_target(self):
        bundle = sample_bundle()
        bundle["claims"][0]["formal_targets"][0]["name"] = "Demo.absent"
        self.assertEqual(inspect_bundle(bundle, Path("."))["coverage"][0]["mapping"], "ambiguous")

    def test_model_cannot_certify_a_location_not_in_prompt(self):
        bundle = sample_bundle()
        result = inspect_bundle(bundle, Path("."), max_chars=1)
        audit = {"flags": [{"id": "f", "severity": "high", "source_id": "main", "decl": "Demo.main", "line": 1,
                             "paper_source_id": "paper", "paper_line": 1}]}
        self.assertFalse(validate_bundle_audit(audit, result)["flags"][0]["location_valid"])

    def test_acceptance_requires_complete_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                record_review(Path(tmp), graph_fixture(), "main", {"context_complete": False}, reviewer="test",
                              decision="accepted", rationale="insufficient", paper_spans=[{"source_id": "p"}])


if __name__ == "__main__":
    unittest.main()
