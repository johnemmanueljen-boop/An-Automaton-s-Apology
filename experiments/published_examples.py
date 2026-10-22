"""Build and evaluate attributed paper examples without API calls or base-environment packages."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from apology.bundles import run_bundle
from apology.paths import ROOT, DATA
from apology.schema import digest, read_json, write_json
from apology.semantic_checks import compare_predicates, evaluate


def val(x):
    return {"value": x}


def var(x):
    return {"var": x}


def op(name, a, b):
    return {"op": name, "args": [a, b]}


def examples():
    # Example 2.1 of Bastounis et al.: the claimed factorization is incorrect.
    # We compare signs at explicit rational samples; this does not audit the full theorem or its Lean proof.
    x = var("x")
    polynomial = op("add", op("sub", op("sub", op("mul", op("mul", x, x), x), op("mul", x, x)), x), val(1))
    wrong_factorization = op("mul", op("sub", x, val(1)), op("mul", op("add", x, val(1)), op("add", x, val(1))))
    poly = {"id": "bastounis-example-2-1-sign", "category": "goal-substitution", "variables": {"x": [-1, 0, 1, 2]},
            "paper": {"domain": "Rat", "predicate": op("ge", polynomial, val(0))},
            "formal": {"domain": "Rat", "predicate": op("ge", wrong_factorization, val(0))},
            "source_url": "https://arxiv.org/html/2610.08144v1", "source_location": "Example 2.1",
            "interpretation_note": "Adapted sign comparison of polynomial and erroneous NL factorization, not a newly discovered Lean error."}
    # Atlas example: expose a typed consequence of natural versus rational division.
    divide = op("div", x, val(2))
    typed = {"id": "atlas-section-1-division", "category": "type-default", "variables": {"x": [2, 3, 4]},
             "paper": {"domain": "Rat", "predicate": op("gt", divide, val(1))},
             "formal": {"domain": "Nat", "predicate": op("gt", divide, val(1))},
             "source_url": "https://arxiv.org/html/2604.16347v1", "source_location": "Section 1, 3/2 example",
             "interpretation_note": "Adapted threshold test: 3/2 > 1 in Rat but not Nat; source contrasts 1.5 with 1."}
    boundary = {"id": "synthetic-endpoint", "category": "boundary", "variables": {"x": [-1, 0, 1]},
                "paper": {"domain": "Int", "predicate": op("gt", x, val(0))},
                "formal": {"domain": "Int", "predicate": op("ge", x, val(0))}, "synthetic": True}
    finite = {"op": "eq", "args": [var("x"), var("y")]}
    quantifier = {"id": "synthetic-quantifier-order", "category": "quantifier", "variables": {},
                  "paper": {"domain": "Nat", "predicate": {"op": "forall", "var": "x", "values": [0, 1],
                            "body": {"op": "exists", "var": "y", "values": [0, 1], "body": finite}}},
                  "formal": {"domain": "Nat", "predicate": {"op": "exists", "var": "y", "values": [0, 1],
                             "body": {"op": "forall", "var": "x", "values": [0, 1], "body": finite}}}, "synthetic": True}
    return [poly, typed, boundary, quantifier]


def source(sid, text, kind, **kwargs):
    return {"id": sid, "content": text, "sha256": digest(text), **kwargs}


def build_manifests(destination: Path):
    destination.mkdir(parents=True, exist_ok=True)
    paths = []
    for spec in examples():
        paper = source("paper", spec.get("interpretation_note", "Synthetic controlled comparison."), "paper",
                       version="v1" if not spec.get("synthetic") else "synthetic-v1", url=spec.get("source_url"),
                       extraction_method="authored paraphrase verified against published HTML; not a PDF transcript")
        formal = source("formal", "import Mathlib\n-- Authored test encoding; not code extracted from the paper.\n",
                        "formal", repository="local-synthetic-encoding", commit=digest(spec))
        manifest = {"schema_version": 2, "id": spec["id"], "documents": [paper], "artifacts": [formal],
                    "claims": [{"id": "comparison", "paper_source": "paper", "paper_span": [1, 1], "formal_targets": []}],
                    "semantic_comparisons": [spec], "example_kind": "synthetic" if spec.get("synthetic") else "paper_adaptation"}
        path = destination / (spec["id"] + ".json")
        write_json(path, manifest)
        paths.append(path)
    case = read_json(DATA / "expert_cases" / "ns_lemma_8_6.json")
    manifest = {"schema_version": 2, "id": "navier-stokes-lemma-8-6-reproduction",
                "documents": [source("paper", case["paper_excerpt"], "paper", version="repository supplied excerpt",
                                     url="https://arxiv.org/html/2610.08144v1", extraction_method="existing expert-case input; see source credit")],
                "artifacts": [source("lean-excerpt", case["lean_context"], "formal",
                                     repository="https://github.com/openai/NavierStokesAndEuler", commit="f9e8bc5",
                                     excerpt_only=True)],
                "claims": [{"id": "lemma-8-6", "label": case["paper_ref"], "paper_source": "paper",
                            "formal_targets": [{"source_id": "lean-excerpt", "name": case["lean_target"]}]}],
                "example_kind": "historical_expert_reproduction",
                "credit": "Bastounis, Circelli and Hansen, arXiv:2610.08144, Example 3.1",
                "limitations": ["Supplied lemma pairing and assembled context; not fresh end-to-end discovery.",
                                "Stored model audit available separately; no new inference or Lean proof check."]}
    path = destination / "navier-stokes-lemma-8-6.json"
    write_json(path, manifest)
    paths.append(path)
    # Expected graph for a transparent synthetic source. It is not a native extraction artifact.
    text = ("namespace Demo\n"
            "def lower : Int := 0\n"
            "def positive (x : Int) : Prop := x > lower\n"
            "def nonnegative (x : Int) : Prop := x >= lower\n"
            "theorem helper : (0 : Int) >= 0 := by decide\n"
            "theorem endpoint : nonnegative 0 ∧ ¬ positive 0 := by\n"
            "  constructor\n  · exact helper\n  · decide\nend Demo\n")
    artifact = source("endpoint-source", text, "formal", repository="synthetic", commit=digest(text))
    names = ["Demo.lower", "Demo.positive", "Demo.nonnegative", "Demo.helper", "Demo.endpoint"]
    nodes = [{"id": name, "name": name, "kind": "theorem" if name in names[-2:] else "definition",
              "extraction_complete": False, "type_sha256": digest(name), "body_sha256": digest(name + text),
              "source_span": {"source_id": artifact["id"], "source_sha256": artifact["sha256"],
                              "start_line": i + 2, "end_line": i + 2 if i < 4 else 9}}
             for i, name in enumerate(names)]
    graph = {"schema_version": 2, "nodes": nodes, "edges": [
        {"source": "Demo.endpoint", "target": "Demo.positive", "site": "type"},
        {"source": "Demo.endpoint", "target": "Demo.nonnegative", "site": "type"},
        {"source": "Demo.endpoint", "target": "Demo.helper", "site": "value"},
        {"source": "Demo.positive", "target": "Demo.lower", "site": "value"},
        {"source": "Demo.nonnegative", "target": "Demo.lower", "site": "value"}],
        "provenance": {"kind": "hand_authored_expected_graph", "lean_compilation": "not_executed"},
        "blockers": ["Synthetic expected graph; native extraction was not executed."]}
    write_json(destination / "endpoint.expected-graph.json", graph)
    note = "Synthetic comparison: x > 0 and x >= 0 disagree at x = 0."
    bundle = {"schema_version": 2, "id": "synthetic-dependency-review", "documents": [
        source("paper", note, "paper", version="synthetic-v1")], "artifacts": [artifact],
        "claims": [{"id": "endpoint", "paper_source": "paper", "formal_targets": [
            {"source_id": artifact["id"], "name": "Demo.endpoint"}]}],
        "dependency_graph": {"path": "endpoint.expected-graph.json", "sha256": digest(graph), "targets": ["Demo.endpoint"]},
        "semantic_comparisons": [examples()[2]], "example_kind": "synthetic_expected_graph"}
    path = destination / "synthetic-dependency-review.json"
    write_json(path, bundle)
    return paths + [path]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build", action="store_true", help="write attributed example manifests")
    parser.add_argument("--run", action="store_true", help="inspect manifests and export new isolated run artifacts")
    args = parser.parse_args()
    folder = DATA / "bundles"
    paths = build_manifests(folder) if args.build else [p for p in sorted(folder.glob("*.json"))
                                                      if not p.name.endswith(".expected-graph.json")]
    if args.run:
        for path in paths:
            print(run_bundle(path))
    graph_path = folder / "endpoint.expected-graph.json"
    graph_check = None
    if graph_path.exists():
        from experiments.review_scope import measure
        graph_check = measure(read_json(graph_path), ["Demo.endpoint"])
    results = [compare_predicates(spec) for spec in examples()]
    checks = {"atlas_division_values": {"Rat": str(evaluate(op("div", val(3), val(2)), {}, "Rat")),
                                        "Nat": evaluate(op("div", val(3), val(2)), {}, "Nat")},
              "examples": results, "actual_api_usd": 0, "lean_verification": "not_executed",
              "synthetic_dependency_scope": graph_check,
              "interpretation": "authored finite encodings; not an unbiased accuracy benchmark"}
    write_json(ROOT / "results" / "evaluation" / "published_examples.json", checks)
    print(json.dumps(checks, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
