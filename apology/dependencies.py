"""Validate elaborated graphs and compute Lean Compass semantic review scopes."""
from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict, deque
from pathlib import Path

from .schema import digest, read_json, write_json

THEOREMS = {"theorem", "lemma"}
KINDS = THEOREMS | {"definition", "def", "abbrev", "structure", "class", "inductive", "constructor", "recursor",
                    "projection", "instance", "opaque", "axiom", "external"}


def validate_graph(graph: dict) -> None:
    if graph.get("schema_version") != 2:
        raise ValueError("dependency graph requires schema version 2")
    ids = [n["id"] for n in graph["nodes"]]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate dependency IDs")
    known = set(ids)
    for node in graph["nodes"]:
        if node.get("kind") not in KINDS:
            raise ValueError(f"unknown declaration kind: {node.get('kind')}")
    for edge in graph["edges"]:
        if edge["source"] not in known or edge["target"] not in known or edge["site"] not in {"type", "value", "both"}:
            raise ValueError("dangling or invalid dependency edge")


def recursive_groups(ids: set, adjacency: dict) -> list[list[str]]:
    """Iterative Kosaraju traversal: avoid recursion limits on large formal projects."""
    order, seen, reverse = [], set(), defaultdict(list)
    for source in ids:
        for target in adjacency.get(source, []):
            if target in ids:
                reverse[target].append(source)
    for root in sorted(ids):
        if root in seen:
            continue
        stack = [(root, False)]
        while stack:
            current, done = stack.pop()
            if done:
                order.append(current)
            elif current not in seen:
                seen.add(current)
                stack.append((current, True))
                stack.extend((x, False) for x in adjacency.get(current, []) if x in ids and x not in seen)
    seen, groups = set(), []
    for root in reversed(order):
        if root in seen:
            continue
        group, queue = [], [root]
        while queue:
            current = queue.pop()
            if current in seen:
                continue
            seen.add(current)
            group.append(current)
            queue.extend(reverse[current])
        if len(group) > 1 or root in adjacency.get(root, []):
            groups.append(sorted(group))
    return groups


def compute_review_scope(graph: dict, target_ids: list[str], trusted_base=()) -> dict:
    """Type references and definition implementations matter; theorem proof-only edges do not."""
    validate_graph(graph)
    nodes = {n["id"]: n for n in graph["nodes"]}
    if not target_ids or set(target_ids) - nodes.keys():
        raise ValueError("review scope requires known, nonempty targets")
    edges = defaultdict(list)
    for edge in graph["edges"]:
        edges[edge["source"]].append(edge)
    trusted = set(trusted_base)
    blockers, reasons = list(graph.get("blockers", [])), defaultdict(list)

    def walk(prune):
        queue = deque(target_ids + [n["id"] for n in graph["nodes"] if n["kind"] == "axiom" and not n.get("external")])
        visited = set()
        while queue:
            current = queue.popleft()
            if current in visited:
                continue
            visited.add(current)
            node = nodes[current]
            if current in trusted:
                continue
            for edge in edges[current]:
                if prune and node["kind"] in THEOREMS and edge["site"] == "value":
                    continue
                if prune:
                    reasons[edge["target"]].append({"from": current, "site": edge["site"]})
                queue.append(edge["target"])
        return visited

    relevant, full = walk(True), walk(False)
    for node_id in sorted(relevant - trusted):
        node = nodes[node_id]
        if node.get("external"):
            blockers.append(f"untrusted external declaration: {node_id}")
        if not node.get("extraction_complete", False):
            blockers.append(f"incomplete extraction: {node_id}")
        if not node.get("source_span"):
            blockers.append(f"source mapping unavailable: {node_id}")
        if node.get("kind") == "opaque" and not node.get("body_available", False):
            blockers.append(f"opaque body unavailable: {node_id}")
    semantic_adjacency = defaultdict(list)
    for edge in graph["edges"]:
        if not (nodes[edge["source"]]["kind"] in THEOREMS and edge["site"] == "value"):
            semantic_adjacency[edge["source"]].append(edge["target"])
    return {"schema_version": 2, "targets": target_ids, "relevant_ids": sorted(relevant - trusted),
            "trusted_ids": sorted(relevant & trusted), "full_dependency_ids": sorted(full - trusted),
            "reasons": dict(reasons), "blockers": sorted(set(blockers)),
            "retained_nodes": len(relevant - trusted), "full_nodes": len(full - trusted),
            "complete": not blockers, "recursive_groups": recursive_groups(relevant - trusted, semantic_adjacency),
            "graph_sha256": digest(graph), "proof_verification": "not_established_by_graph"}


def node_fingerprint(graph: dict, node_id: str, context: dict) -> str:
    """Fingerprint the semantic closure and immutable review context; source invalidation is conservative."""
    scope = compute_review_scope(graph, [node_id], context.get("trusted_base", []))
    ids = set(scope["relevant_ids"] + scope["trusted_ids"])
    nodes = sorted(({k: v for k, v in n.items() if not (n["kind"] in THEOREMS and k in {"body_sha256", "value"})}
                    for n in graph["nodes"] if n["id"] in ids), key=lambda x: x["id"])
    semantic_edges = [e for e in graph["edges"] if e["source"] in ids and e["target"] in ids
                      and not (next(n for n in graph["nodes"] if n["id"] == e["source"])["kind"] in THEOREMS
                               and e["site"] == "value")]
    return digest({"nodes": nodes, "edges": sorted(semantic_edges, key=lambda e: (e["source"], e["target"], e["site"])),
                   "context": context})


def normalize_extraction(raw: dict, *, repository: str, commit: str, environment: str, source_map=None,
                         trusted_modules=("Init", "Lean", "Std", "Mathlib")) -> dict:
    """Map native extractor output into environment-qualified IDs. Source maps are supplied independently."""
    from .schema import declaration_id
    source_map = source_map or {}
    records = raw["nodes"]
    names = {node["name"] for node in records}
    all_names = names | {name for n in records for key in ("type_deps", "value_deps") for name in n.get(key, [])}
    by_name = {n["name"]: n for n in records}
    def identity(name):
        return declaration_id(repository, commit, by_name.get(name, {}).get("module", "external"), name, environment)
    nodes, edges, trusted = [], [], []
    for name in sorted(all_names):
        node = by_name.get(name)
        module = node.get("module", "") if node else ""
        external = bool(node.get("external", False)) if node else True
        record = {"id": identity(name), "name": name, "module": module, "external": external,
                  "kind": node.get("kind", "external") if node else "external",
                  "type_sha256": digest(node.get("type", "")) if node else None,
                  "body_sha256": digest(node.get("value", "")) if node and node.get("value") is not None else None,
                  "body_available": bool(node and node.get("value") is not None),
                  "source_span": source_map.get(name), "extraction_complete": node is not None}
        nodes.append(record)
        if external and any(module == p or module.startswith(p + ".") for p in trusted_modules):
            trusted.append(identity(name))
        if node:
            t, v = set(node.get("type_deps", [])), set(node.get("value_deps", []))
            for dep in sorted(t | v):
                edges.append({"source": identity(name), "target": identity(dep),
                              "site": "both" if dep in t & v else "type" if dep in t else "value"})
    graph = {"schema_version": 2, "nodes": nodes, "edges": edges, "trusted_base": trusted,
             "provenance": {"repository": repository, "commit": commit, "environment": environment,
                            "extractor": "lean/Extract.lean", "execution": raw.get("execution", "unverified_import")}}
    validate_graph(graph)
    return graph


def extract_graph(repo: Path, module: str, prefix: str, repository: str, commit: str, source_map=None) -> dict:
    from .execution import execute_lean
    from .paths import ROOT
    from dataclasses import asdict
    if not re.fullmatch(r"[\w.]+", module) or not re.fullmatch(r"[\w.]+", prefix):
        raise ValueError("module and prefix must be Lean names")
    extractor = (ROOT / "lean" / "Extract.lean").read_text(encoding="utf-8")
    src = "import " + module + "\n" + extractor + f'\n#apology_graph "{prefix}"\n'
    # Imports must precede commands. Extract.lean imports Lean at its beginning.
    result = execute_lean(repo, src)
    marker = "APOLOGY_GRAPH:"
    records = [line.split(marker, 1)[1] for line in result.stdout.splitlines() if marker in line]
    if result.returncode != 0 or len(records) != 1:
        raise RuntimeError(f"Lean graph extraction unavailable: {result.stderr or result.stdout}")
    raw = json.loads(records[0])
    raw["execution"] = asdict(result)
    graph = normalize_extraction(raw, repository=repository, commit=commit, environment=module, source_map=source_map)
    toolchain = repo / "lean-toolchain"
    graph["provenance"]["lean_toolchain"] = toolchain.read_text(encoding="utf-8").strip() if toolchain.exists() else "unavailable"
    graph["provenance"]["extractor_sha256"] = digest(extractor)
    return graph


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("graph", type=Path)
    parser.add_argument("targets", nargs="*")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--extract", action="store_true", help="extract a native graph into GRAPH using a configured Lean execution policy")
    parser.add_argument("--repo", type=Path)
    parser.add_argument("--module")
    parser.add_argument("--prefix")
    parser.add_argument("--repository")
    parser.add_argument("--commit")
    parser.add_argument("--source-map", type=Path, help="qualified name to verified SourceSpan JSON; missing spans remain blockers")
    args = parser.parse_args()
    if args.extract:
        if not all((args.repo, args.module, args.prefix, args.repository, args.commit)):
            parser.error("--extract requires --repo, --module, --prefix, --repository, --commit")
        result = extract_graph(args.repo, args.module, args.prefix, args.repository, args.commit,
                               read_json(args.source_map) if args.source_map else None)
        write_json(args.graph, result)
        print(f"Exported {len(result['nodes'])} nodes to {args.graph}")
        return
    graph = read_json(args.graph)
    result = compute_review_scope(graph, args.targets, graph.get("trusted_base", []))
    if args.output:
        write_json(args.output, result)
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
