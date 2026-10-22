"""Local human review records tied to immutable semantic context."""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from .dependencies import compute_review_scope, node_fingerprint
from .schema import read_json, write_json, digest

DECISIONS = {"accepted", "mismatch", "needs_context"}


def record_review(store: Path, graph: dict, node_id: str, context: dict, *, reviewer: str, decision: str,
                  rationale: str, paper_spans: list[dict]) -> dict:
    if decision not in DECISIONS or not reviewer.strip() or not rationale.strip() or not paper_spans:
        raise ValueError("human review requires a decision, reviewer, rationale, and compared paper spans")
    scope = compute_review_scope(graph, [node_id], context.get("trusted_base", []))
    if decision == "accepted" and (scope["blockers"] or context.get("context_complete") is False):
        raise ValueError("cannot accept an item with incomplete extraction or context")
    fingerprint = node_fingerprint(graph, node_id, context)
    record = {"schema_version": 2, "node_id": node_id, "decision": decision, "reviewer": reviewer,
              "rationale": rationale, "paper_spans": paper_spans, "context": context,
              "fingerprint": fingerprint, "created_at": datetime.now(timezone.utc).isoformat()}
    # Append-only journal: preserve previous decisions and their source context.
    path = store / (digest(record) + ".json")
    if path.exists():
        raise ValueError("review already recorded")
    write_json(path, record)
    return record


def review_status(store: Path, graph: dict, node_id: str, context: dict) -> dict:
    records = [read_json(p) for p in store.glob("*.json")]
    records = [r for r in records if r.get("node_id") == node_id]
    if not records:
        return {"status": "unreviewed"}
    latest = max(records, key=lambda r: r["created_at"])
    matches = latest["fingerprint"] == node_fingerprint(graph, node_id, context)
    return {"status": latest["decision"] if matches else "stale", "review": latest}


def review_queue(store: Path, graph: dict, targets: list[str], context: dict) -> dict:
    scope = compute_review_scope(graph, targets, context.get("trusted_base", []))
    nodes = {n["id"]: n for n in graph["nodes"]}
    rows = [{"node_id": node_id, "name": nodes[node_id].get("name", node_id),
             "kind": nodes[node_id]["kind"], "reasons": scope["reasons"].get(node_id, []),
             **review_status(store, graph, node_id, context)} for node_id in scope["relevant_ids"]]
    spans = set()
    for row in rows:
        span = nodes[row["node_id"]].get("source_span")
        if span and row["status"] != "accepted":
            for line in range(span["start_line"], span["end_line"] + 1):
                spans.add((span.get("source_sha256"), span.get("source_id"), line))
    return {"scope": scope, "items": rows, "unreviewed_unique_lines": len(spans),
            "human_accepted": sum(r["status"] == "accepted" for r in rows)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("graph", type=Path)
    parser.add_argument("node_id")
    parser.add_argument("--context", type=Path, required=True)
    parser.add_argument("--store", type=Path, default=Path("results/reviews"))
    parser.add_argument("--decision", choices=sorted(DECISIONS))
    parser.add_argument("--reviewer")
    parser.add_argument("--rationale")
    parser.add_argument("--paper-spans", type=Path)
    args = parser.parse_args()
    graph, context = read_json(args.graph), read_json(args.context)
    if args.decision:
        if not all((args.reviewer, args.rationale, args.paper_spans)):
            parser.error("recording a decision requires --reviewer, --rationale, --paper-spans")
        result = record_review(args.store, graph, args.node_id, context, reviewer=args.reviewer,
                               decision=args.decision, rationale=args.rationale, paper_spans=read_json(args.paper_spans))
    else:
        result = review_queue(args.store, graph, [args.node_id], context)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
