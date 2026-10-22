"""Report dependency retention, blockers, and review state for an exported graph."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from apology.dependencies import compute_review_scope
from apology.schema import read_json, write_json


def measure(graph: dict, targets: list[str]) -> dict:
    scope = compute_review_scope(graph, targets, graph.get("trusted_base", []))
    return {"retained_nodes": scope["retained_nodes"], "full_nodes": scope["full_nodes"],
            "retention_fraction": scope["retained_nodes"] / scope["full_nodes"] if scope["full_nodes"] else None,
            "complete": scope["complete"], "blockers": scope["blockers"],
            "human_review_time": "not_measured", "proof_verification": "not_established_by_graph"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("graph", type=Path)
    parser.add_argument("targets", nargs="+")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = measure(read_json(args.graph), args.targets)
    if args.output:
        write_json(args.output, result)
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
