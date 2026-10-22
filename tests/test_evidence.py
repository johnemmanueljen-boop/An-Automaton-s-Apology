import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from apology.audit import trust_burden, verify_citations
from apology.probes import Probe, run_probe


class CitationTests(unittest.TestCase):
    def challenge(self):
        return {"nonblank_lines": 3, "decls": [
            {"name": "A.foo", "short_name": "foo", "start_line": 1, "end_line": 3,
             "text": "def foo : Nat := 1", "kind": "def", "is_target_theorem": False}
        ]}

    def test_missing_or_malformed_line_never_passes(self):
        for line in (None, "2", True, 0, 4):
            with self.subTest(line=line):
                card = {"flags": [{"decl": "A.foo", "line": line}]}
                verify_citations(self.challenge(), card)
                self.assertFalse(card["flags"][0]["citation_ok"])

    def test_short_name_cannot_select_another_namespace(self):
        card = {"flags": [{"decl": "Wrong.foo", "line": 2}]}
        verify_citations(self.challenge(), card)
        self.assertFalse(card["flags"][0]["citation_ok"])

    def test_valid_location_is_not_semantic_review(self):
        card = {"flags": [{"decl": "A.foo", "line": 2, "supports_claim": "supported"}]}
        verify_citations(self.challenge(), card)
        self.assertTrue(card["flags"][0]["citation_ok"])
        self.assertEqual(card["flags"][0]["supports_claim"], "unreviewed")

    def test_model_cannot_clear_human_review(self):
        burden = trust_burden(self.challenge(), {"glossary": [{"decl": "A.foo", "matches_standard": "yes"}]})
        self.assertGreater(burden["lines_needing_human_review"], 0)


class ProbeTests(unittest.TestCase):
    def test_empty_targets_cannot_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "Statement.lean").write_text("import Lean\n", encoding="utf-8")
            p = Probe("empty", tmp, "Statement.lean", "other", "no evidence", "", [])
            with patch("apology.probes.lean_check", return_value=("", .01)):
                self.assertNotEqual(run_probe(p).status, "GREEN")

    def test_expected_failure_is_not_a_proof(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "Statement.lean").write_text("import Lean\n", encoding="utf-8")
            p = Probe("negative", tmp, "Statement.lean", "other", "unproved", "theorem probe_n : False := by trivial",
                      ["probe_n"], expect_fail=True)
            with patch("apology.probes.lean_check", return_value=("file.lean:5:1: error: unsolved goals", .01)):
                self.assertNotEqual(run_probe(p).status, "GREEN")


if __name__ == "__main__":
    unittest.main()
