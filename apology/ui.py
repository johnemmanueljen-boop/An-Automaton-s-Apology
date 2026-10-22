"""Marimo components for bundle inspection; importing this module needs only the standard library."""
from __future__ import annotations

import json
from pathlib import Path

from .schema import read_json, digest


def available_inspections(root: Path) -> dict:
    records = {}
    for path in sorted((root / "results" / "runs").glob("*/inspection.json"), reverse=True):
        try:
            inspection = read_json(path)
            records[f"{inspection['bundle_id']} · {path.parent.name}"] = str(path)
        except (OSError, ValueError, KeyError):
            continue
    return records


def render_bundle(mo, path: Path, root: Path):
    from .review import record_review, review_queue
    data = read_json(path)
    sources = data["sources"]
    paper_blocks, formal_blocks = [], []
    for sid, source in sources.items():
        text = source.get("content", "") if source["available"] else source.get("unavailable_reason", "missing")
        header = f"{sid} · {source.get('version', source.get('commit', 'unknown version'))}"
        block = mo.vstack([mo.md(header), mo.plain_text(text)])
        (formal_blocks if source["source_kind"] == "artifacts" else paper_blocks).append(block)
    coverage = [{"Claim": r["paper_ref"], "Context": r["availability"], "Mapping": r["mapping"],
                 "Semantic relation": r["relation"], "Evidence": r["evidence_level"]} for r in data["coverage"]]
    comparisons = [{"Comparison": r["comparison_id"], "Outcome": r["status"],
                    "Witnesses": json.dumps(r.get("witnesses"), ensure_ascii=False),
                    "Interpretation": "proposed", "Lean check": r.get("lean_verification", "not_executed")}
                   for r in data.get("semantic_comparisons", [])]
    blocks = [mo.md(f"## Result bundle · {data['bundle_id']}"),
              mo.md("Source locations, model concerns, bounded calculations, and human decisions carry separate evidence labels."),
              mo.hstack([mo.accordion({"Paper and scope": mo.vstack(paper_blocks)}),
                         mo.accordion({"Formal artifacts": mo.vstack(formal_blocks)})]),
              mo.ui.table(coverage, selection=None),
              mo.ui.table(comparisons, selection=None) if comparisons else mo.md("No bounded predicate comparisons supplied.")]
    problems = data["blockers"] + data["context"]["omissions"]
    if problems:
        blocks.append(mo.callout(mo.plain_text("Context incomplete\n" + "\n".join(problems)), kind="warn"))
    if "audit" in data:
        blocks.append(mo.accordion({"Model concerns · unreviewed": mo.plain_text(json.dumps(data["audit"], ensure_ascii=False, indent=2))}))
    form = None
    graph = data.get("dependency_graph")
    if graph and data.get("review_scope"):
        context = {"bundle_id": data["bundle_id"], "sources": {sid: source.get("sha256") for sid, source in sources.items()},
                   "trusted_base": graph.get("trusted_base", []), "claim_inventory_sha256": digest(data["coverage"]),
                   "context_complete": not problems}
        store = root / "results" / "reviews"
        targets = data["review_scope"]["targets"]
        queue = review_queue(store, graph, targets, context)
        data["human_review_queue"] = queue
        blocks.append(mo.ui.table([{"Declaration": r["name"], "Kind": r["kind"], "Review": r["status"],
                                    "Why relevant": json.dumps(r["reasons"], ensure_ascii=False)} for r in queue["items"]], selection=None))
        options = {r["name"] + " · " + r["node_id"]: r["node_id"] for r in queue["items"]}
        paper_spans = [span for span in data["context"]["spans"] if sources[span["source_id"]]["source_kind"] == "documents"]
        def submit(value):
            if value:
                record_review(store, graph, value["node"], context, reviewer=value["reviewer"],
                              decision=value["decision"], rationale=value["rationale"], paper_spans=paper_spans)
        def validate(value):
            if not value or not value.get("reviewer", "").strip() or not value.get("rationale", "").strip():
                return "Enter your name and the reason for your decision."
            if value.get("decision") == "accepted" and (queue["scope"]["blockers"] or problems):
                return "Complete the missing source/dependency context before accepting."
            return None
        if options:
            form = mo.md("### Record a human review\n\n{node}\n\n{reviewer}\n\n{decision}\n\n{rationale}").batch(
                node=mo.ui.dropdown(options=options, value=next(iter(options)), label="Declaration"),
                reviewer=mo.ui.text(label="Reviewer"), decision=mo.ui.dropdown(options=["needs_context", "accepted", "mismatch"],
                                                                                           value="needs_context", label="Decision"),
                rationale=mo.ui.text_area(label="Compared sources and rationale")).form(
                    submit_button_label="Save review", validate=validate, on_change=submit)
            blocks.append(form)
    else:
        blocks.append(mo.md("Dependency extraction unavailable for this bundle; semantic review remains unreviewed."))
    blocks.append(mo.download(data=json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8"),
                              filename="audit.json", mimetype="application/json", label="Download audit JSON"))
    report = path.parent / "report.md"
    if report.exists():
        blocks.append(mo.download(data=report.read_bytes(), filename="audit.md", mimetype="text/markdown", label="Download audit report"))
    return mo.vstack(blocks), form
