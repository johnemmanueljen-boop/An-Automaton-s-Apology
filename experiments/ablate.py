"""Deterministic component ablations plus optional scoring of human-adjudicated model experiments."""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path

from apology.bundles import inspect_bundle
from apology.paths import ROOT, DATA
from apology.schema import digest, new_run, read_json, write_json
from apology.semantic_checks import compare_predicates
from experiments.metrics import evaluate_adjudicated
from experiments.published_examples import examples


def component_report() -> dict:
    # Isolate the impact of complete source context on an explicitly mapped synthetic sibling result.
    main, sibling = "theorem Demo.main : True := by trivial\n", "theorem Demo.sibling : True := by trivial\n"
    bundle = {"schema_version": 2, "id": "synthetic-sibling-ablation", "documents": [
        {"id": "paper", "content": "Main claim and sibling claim.", "sha256": digest("Main claim and sibling claim."), "version": "synthetic-v1"}],
        "artifacts": [{"id": sid, "content": text, "sha256": digest(text), "repository": "synthetic", "commit": digest(text)}
                      for sid, text in (("main", main), ("sibling", sibling))],
        "claims": [{"id": "sibling", "paper_source": "paper", "formal_targets": [{"source_id": "sibling", "name": "Demo.sibling"}]}]}
    full = inspect_bundle(bundle, ROOT)
    incomplete = copy.deepcopy(bundle)
    incomplete["artifacts"][1].pop("content")
    incomplete["artifacts"][1]["path"] = "intentionally_missing_synthetic_sibling.lean"
    partial = inspect_bundle(incomplete, ROOT)
    legacy = read_json(ROOT / "results" / "validation" / "heldout_benchmark.json")
    excluded = set(read_json(ROOT / "results" / "validation" / "heldout_adjudicated.json")["equivalent_mutants_author_adjudicated"])
    kept = [r for r in legacy["rows"] if r["mutant"] not in excluded]
    clean = legacy["clean_flags"]
    independent_clean_hits = sum(any(f.get("severity") in {"medium", "high"} for f in flags) for flags in clean.values())
    return {"schema_version": 2, "experiment_type": "component_regression_not_accuracy_benchmark",
            "baseline": {"historical_detected": sum(r["detected_strict"] for r in kept), "historical_cases": len(kept),
                         "scoring": "legacy within-two-lines mutation-site metric",
                         "unique_clean_files_with_any_medium_high_flag": independent_clean_hits,
                         "unique_clean_files": len(clean),
                         "note": "Original source files are controls, not independently adjudicated clean research results."},
            "bundle_ablation": {"with_sibling": full["coverage"], "without_sibling": partial["coverage"],
                                 "expected": "mapped candidate with complete manifest; abstention when sibling unavailable"},
            "bounded_checks": [compare_predicates(s) for s in examples()], "actual_api_usd": 0,
            "model_accuracy_improvement": "not_measured; requires new inference and blinded semantic adjudication",
            "lean_integration": "not_executed", "source_group_splits": "required before fresh accuracy evaluation"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--adjudications", type=Path, help="human-reviewed case labels for a real semantic evaluation")
    args = parser.parse_args()
    report = evaluate_adjudicated(read_json(args.adjudications)) if args.adjudications else component_report()
    folder, manifest = new_run(ROOT, "semantic_evaluation" if args.adjudications else "component_ablation",
                               {"adjudications_sha256": digest(read_json(args.adjudications)) if args.adjudications else None})
    write_json(folder / "evaluation.json", report)
    write_json(folder / "manifest.json", manifest)
    # A shareable stable report in addition to the immutable run.
    stable_name = "semantic_evaluation.json" if args.adjudications else "component_ablation.json"
    write_json(ROOT / "results" / "evaluation" / stable_name, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"Run artifacts: {folder}")


if __name__ == "__main__":
    main()
