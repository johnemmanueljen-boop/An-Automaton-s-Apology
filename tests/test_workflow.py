import copy
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from apology import llm
from apology.bundles import inspect_bundle, source_span, validate_bundle_audit, run_bundle
from apology.dependencies import compute_review_scope, node_fingerprint, normalize_extraction
from apology.execution import LeanExecution
from apology.holes import body
from apology.probes import Probe, build_probe, run_probe
from apology.review import record_review, review_status
from apology.schema import digest, write_json, adapt_card
from apology.semantic_checks import compare_predicates, evaluate, witness_probe
from experiments.published_examples import examples, op, val


def sample_bundle():
    paper = "A main result and a corollary.\n"
    formal = "theorem Demo.main : True := by trivial\n"
    sibling = "theorem Demo.corollary : True := by trivial\n"
    return {"schema_version": 2, "id": "fixture", "documents": [
        {"id": "paper", "content": paper, "sha256": digest(paper), "version": "v1"}],
        "artifacts": [{"id": sid, "content": text, "sha256": digest(text), "repository": "fixture", "commit": "abc"}
                      for sid, text in (("main", formal), ("sibling", sibling))],
        "claims": [{"id": "corollary", "paper_source": "paper", "paper_span": [1, 1],
                    "formal_targets": [{"source_id": "sibling", "name": "Demo.corollary"}]}]}


def graph_fixture():
    def node(name, kind="definition"):
        return {"id": name, "name": name, "kind": kind, "type_sha256": digest(name), "body_sha256": digest(name),
                "extraction_complete": True, "source_span": {"source_id": "fixture", "source_sha256": "abc",
                                                               "start_line": 1, "end_line": 2}}
    return {"schema_version": 2, "nodes": [node("main", "theorem"), node("definition"), node("nested"),
                                           node("proof_only", "theorem"), node("axiom", "axiom")],
            "edges": [{"source": "main", "target": "definition", "site": "type"},
                      {"source": "definition", "target": "nested", "site": "value"},
                      {"source": "main", "target": "proof_only", "site": "value"},
                      {"source": "nested", "target": "definition", "site": "value"}]}


class BundleTests(unittest.TestCase):
    def test_sibling_is_visible_and_its_absence_is_incomplete(self):
        bundle = sample_bundle()
        with tempfile.TemporaryDirectory() as tmp:
            result = inspect_bundle(bundle, Path(tmp))
            self.assertEqual(result["coverage"][0]["mapping"], "mapped")
            self.assertIn("Demo.corollary", "".join(s["text"] for s in result["context"]["spans"]))
            bundle["artifacts"][1].pop("content")
            bundle["artifacts"][1]["path"] = "missing.lean"
            result = inspect_bundle(bundle, Path(tmp))
            self.assertEqual(result["coverage"][0]["availability"], "missing_sources")
            self.assertNotEqual(result["coverage"][0]["mapping"], "mapped")

    def test_hash_change_and_truncation_abstain(self):
        bundle = sample_bundle()
        with tempfile.TemporaryDirectory() as tmp:
            result = inspect_bundle(bundle, Path(tmp), max_chars=1)
            self.assertEqual(result["coverage"][0]["availability"], "truncated_context")
            proposed = {"coverage": [{"relation": "equivalent"}]}
            self.assertEqual(validate_bundle_audit(proposed, result)["coverage"][0]["relation"], "unknown")
            bundle["documents"][0]["content"] += "modified"
            self.assertTrue(inspect_bundle(bundle, Path(tmp))["blockers"])

    def test_pdf_form_feeds_do_not_shift_line_numbers(self):
        span = source_span({"id": "p", "content": "one\n\ftwo\nthree", "sha256": "abc"}, 3, 3)
        self.assertEqual(span["text"], "three")
        self.assertEqual(span["page"], 2)
        with self.assertRaises(ValueError):
            source_span({"id": "p", "content": "one", "sha256": "abc"}, True, 1)

    def test_run_is_unique_and_no_history_is_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            manifest = root / "fixture.json"
            write_json(manifest, sample_bundle())
            a, b = run_bundle(manifest, output_root=root), run_bundle(manifest, output_root=root)
            self.assertNotEqual(a, b)
            self.assertTrue((a / "report.md").exists())
            self.assertEqual(json.loads((a / "manifest.json").read_text())["actual_api_usd"], 0)

    def test_legacy_card_is_not_silently_upgraded(self):
        card = {"audit": {"flags": [{"citation_ok": True}]}}
        adapted = adapt_card(card)
        self.assertFalse(adapted["audit"]["flags"][0]["location_valid"])
        self.assertTrue(card["audit"]["flags"][0]["citation_ok"])


class OfflineTests(unittest.TestCase):
    def test_cache_misses_never_construct_client(self):
        with patch.dict(os.environ, {"APOLOGY_OFFLINE": "1"}), patch.object(llm, "cached", return_value=None), \
                patch.object(llm, "_client") as client:
            with self.assertRaises(llm.OfflineCacheMiss):
                llm.complete_json("unseen", "request")
            with self.assertRaises(llm.OfflineCacheMiss):
                llm.complete_json_many([("unseen", "request", 10)])
            client.assert_not_called()

    def test_cached_offline_response_is_copied(self):
        value = {"answer": [1]}
        with patch.dict(os.environ, {"APOLOGY_OFFLINE": "1"}), patch.object(llm, "cached", return_value=value):
            llm.complete_json("s", "u")["answer"].append(2)
            self.assertEqual(value["answer"], [1])


class GraphTests(unittest.TestCase):
    def test_compass_keeps_definition_values_and_axioms_handles_cycle(self):
        scope = compute_review_scope(graph_fixture(), ["main"])
        self.assertEqual(set(scope["relevant_ids"]), {"main", "definition", "nested", "axiom"})
        self.assertIn("proof_only", scope["full_dependency_ids"])

    def test_type_and_both_edges_from_theorems_are_retained(self):
        graph = graph_fixture()
        graph["edges"][-2]["site"] = "both"
        self.assertIn("proof_only", compute_review_scope(graph, ["main"])["relevant_ids"])

    def test_missing_mapping_or_unknown_external_is_blocker(self):
        graph = graph_fixture()
        graph["nodes"][1]["source_span"] = None
        graph["nodes"][2]["external"] = True
        scope = compute_review_scope(graph, ["main"])
        self.assertFalse(scope["complete"])
        self.assertTrue(any("untrusted external" in x for x in scope["blockers"]))

    def test_shared_dependency_or_paper_change_invalidates_review(self):
        graph = graph_fixture()
        context = {"paper_sha256": "paper-v1"}
        with tempfile.TemporaryDirectory() as tmp:
            store = Path(tmp)
            record_review(store, graph, "main", context, reviewer="fixture reviewer", decision="accepted",
                          rationale="checked definitions and source", paper_spans=[{"source_id": "p", "start_line": 1}])
            self.assertEqual(review_status(store, graph, "main", context)["status"], "accepted")
            graph["nodes"][2]["body_sha256"] = "changed"
            self.assertEqual(review_status(store, graph, "main", context)["status"], "stale")
            self.assertEqual(review_status(store, graph_fixture(), "main", {"paper_sha256": "v2"})["status"], "stale")

    def test_name_collision_in_environments_remains_distinct(self):
        raw = {"nodes": [{"name": "X", "kind": "definition", "module": "M", "type": "Nat", "value": "0"}]}
        a = normalize_extraction(raw, repository="r", commit="c", environment="challenge")
        b = normalize_extraction(raw, repository="r", commit="c", environment="solution")
        self.assertNotEqual(a["nodes"][0]["id"], b["nodes"][0]["id"])


class StructuredProbeTests(unittest.TestCase):
    def run_with(self, execution, *, targets=None, lean=None):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "s.lean").write_text("import Lean\n", encoding="utf-8")
            probe = build_probe("fixture", Path(tmp), "s.lean", "non-vacuity", "True holds", "True", "trivial")
            if targets is not None:
                probe.check_decls = targets
            if lean is not None:
                probe.lean = lean
            stdout = f"'{probe.check_decls[0]}' does not depend on any axioms\n" if probe.check_decls else ""
            execution.stdout = execution.stdout or stdout
            with patch("apology.probes.lean_check", return_value=execution):
                return run_probe(probe)

    def test_nonzero_exit_overrides_good_axiom_text(self):
        self.assertNotEqual(self.run_with(LeanExecution(returncode=1, stderr="unexpected diagnostic")).status, "GREEN")

    def test_checked_result_has_execution_and_identity(self):
        result = self.run_with(LeanExecution(returncode=0, mode="mock_fixture"))
        self.assertEqual(result.status, "GREEN")
        self.assertEqual(result.evidence_kind, "satisfiability_witness")
        self.assertTrue(result.artifact_sha256)

    def test_unexpected_axiom_or_missing_declaration_never_pass(self):
        self.assertNotEqual(self.run_with(LeanExecution(returncode=0, stdout="missing")).status, "GREEN")
        probe = build_probe("fixture", Path("."), "s.lean", "other", "", "True", "trivial")
        text = f"'{probe.check_decls[0]}' depends on axioms: [sorryAx]"
        self.assertNotEqual(self.run_with(LeanExecution(returncode=0, stdout=text)).status, "GREEN")
        self.assertNotEqual(self.run_with(LeanExecution(returncode=0), targets=["Nat.add_comm"]).status, "GREEN")

    def test_data_constructed_with_by_is_not_discarded(self):
        result = body(["def d : S where", "  value := by exact 5", "  proof := by trivial"], 0)
        self.assertIn("value := by exact 5", " ".join(result))


class SemanticTests(unittest.TestCase):
    def test_published_adaptations_and_synthetic_cases_have_expected_witnesses(self):
        results = [compare_predicates(spec) for spec in examples()]
        self.assertEqual(results[0]["witnesses"]["paper_not_formal"], {"x": 0})
        self.assertEqual(results[1]["witnesses"]["paper_not_formal"], {"x": 3})
        self.assertEqual(results[2]["witnesses"]["formal_not_paper"], {"x": 0})
        self.assertEqual(results[3]["witnesses"]["paper_not_formal"], {})

    def test_no_witness_does_not_establish_equivalence(self):
        spec = copy.deepcopy(examples()[2])
        spec["formal"] = spec["paper"]
        result = compare_predicates(spec)
        self.assertEqual(result["status"], "no_witness_in_bounds")
        self.assertEqual(result["directions"]["paper_implies_formal"], "unknown")

    def test_natural_subtraction_and_totalized_division(self):
        self.assertEqual(evaluate(op("sub", val(1), val(2)), {}, "Nat"), 0)
        self.assertEqual(evaluate(op("div", val(4), val(0)), {}, "Rat"), 0)
        self.assertEqual(evaluate(op("div", val(-3), val(-2)), {}, "Int"), 2)

    def test_generated_witness_preserves_explicit_domains(self):
        spec = examples()[1]
        probe = witness_probe(spec, compare_predicates(spec), "paper_not_formal", Path("."), "s.lean")
        self.assertIn(": Rat", probe.lean)
        self.assertIn(": Nat", probe.lean)
        self.assertEqual(len(probe.check_decls), 1)


if __name__ == "__main__":
    unittest.main()
