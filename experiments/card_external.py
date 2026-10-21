"""Full audit card (audit, probes, certified restatements) for a statement file from any repository.

Steps: corpus parse -> lint -> definition-hole status (if a holes JSON is given) -> Opus audit with machine-checked
citations -> Lean probes and certified restatements (Sonnet writes, Lean decides) -> card JSON + printed report.

The challenge must compile in `lean_repo` (a directory with a built Mathlib). If that is not the repository the
challenge came from, the card records it.

Usage:
  python -m experiments.card_external --challenge ../ten-proofs/ComparatorChallengesExternal/EuclideanFiveColor.lean \
      --lean-repo ../ten-proofs --paper <paper.tex> --lines 55:125 --out results/cards_external/EuclideanFiveColor.json \
      --holes results/findings/definition_holes_oai_math.json
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

from apology import lint as lintmod
from apology.audit import llm_audit, probe_for, verify_citations
from apology.corpus import parse_file
from apology.restate import llm_restate


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--challenge", required=True)
    ap.add_argument("--lean-repo", required=True)
    ap.add_argument("--paper", required=True)
    ap.add_argument("--lines", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--holes", default=None)
    ap.add_argument("--max-probes", type=int, default=2)
    ap.add_argument("--max-restate", type=int, default=2)
    a = ap.parse_args()

    lean_path = Path(a.challenge).resolve()
    repo = Path(a.lean_repo).resolve()
    rel = str(lean_path.relative_to(repo))
    cfg = json.loads(lean_path.with_suffix(".json").read_text())
    decls = [asdict(d) for d in parse_file(lean_path)]
    for d in decls:
        d["is_target_theorem"] = d["name"] in cfg.get("theorem_names", [])
    ch = {
        "repo": repo.name,
        "challenge_file": rel,
        "theorem_names": cfg.get("theorem_names", []),
        "definition_names": cfg.get("definition_names", []),
        "decls": decls,
        "nonblank_lines": sum(1 for l in lean_path.read_text().splitlines() if l.strip()),
    }

    print("[1/5] lint", file=sys.stderr)
    findings = [asdict(f) for d in decls for f in lintmod.lint_decl(repo.name, d)]

    holes = []
    if a.holes:
        holes = [h for h in json.loads(Path(a.holes).read_text()) if h["config"] == lean_path.with_suffix(".json").name]

    print("[2/5] audit (Opus)", file=sys.stderr)
    lines = Path(a.paper).read_text().split("\n")
    excerpt = "\n...\n".join(
        "\n".join(lines[int(x) - 1 : int(y)]) for x, y in (r.split(":") for r in a.lines.split(","))
    )
    audit = llm_audit(ch, repo, findings, excerpt=excerpt)
    verify_citations(ch, audit)

    print("[3/5] Lean probes", file=sys.stderr)
    targets = [
        {
            "id": f["id"],
            "decl": f.get("decl"),
            "line": f.get("line"),
            "explanation": f["explanation"],
            "probe_idea": f["probe_idea"],
        }
        for f in audit.get("flags", [])
        if f.get("probe_idea")
    ]
    targets.append(
        {
            "id": "NV",
            "explanation": "Non-vacuity: exhibit a concrete object satisfying the central bespoke "
            "definition(s) the target theorems quantify over.",
            "probe_idea": "construct an instance",
        }
    )
    probes, seen = [], set()
    for t in targets[: a.max_probes]:
        r = probe_for(ch, repo, t)
        key = " ".join(r["lean"].split())
        if key not in seen:
            seen.add(key)
            probes.append(r)

    print("[4/5] certified restatements", file=sys.stderr)
    names = list(ch["theorem_names"]) + [d["name"] for d in decls if d["kind"] in ("def", "abbrev", "structure")]
    rests = []
    for i, n in enumerate(dict.fromkeys(names)):
        if i >= a.max_restate:
            break
        try:
            rests.append(asdict(llm_restate(ch, repo, n, "iff", i)))
        except Exception as e:
            rests.append({"target": n, "status": "FAILED", "detail": f"error: {e}"})

    print("[5/5] card", file=sys.stderr)
    card = {
        "challenge": str(lean_path),
        "checked_with_lean_repo": repo.name,
        "paper": a.paper,
        "lines": a.lines,
        "lint": findings,
        "holes": holes,
        "audit": audit,
        "probes": probes,
        "restatements": rests,
    }
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(card, indent=1, ensure_ascii=False))

    # ---- human-readable report
    P = print
    P("=" * 100)
    P("AUDIT CARD:", lean_path.name, f"(Lean checks run with {repo.name}'s Mathlib)")
    P("=" * 100)
    P("\nPLAIN READING:\n ", audit.get("summary"))
    P("\nPAPER vs LEAN:")
    for c in audit.get("coverage", []):
        P(
            f"  - {c.get('paper_ref')} -> {(c.get('lean_theorem') or '-').split('.')[-1]}: {c.get('relation')} | {c.get('why')}"
        )
    P("\nFLAGS (sticky notes):")
    for f in audit.get("flags", []):
        P(
            f"  [{f['severity']}/{f['category']}] line {f.get('line')} {'(citation verified)' if f.get('citation_ok') else '(citation UNVERIFIED)'}: {f['explanation']}"
        )
    P("\nGLOSSARY:")
    for g in audit.get("glossary", []):
        P(f"  - {g['decl'].split('.')[-1]}: {g['plain']} [standard? {g.get('matches_standard')}]")
    P("\nDETERMINISTIC LINT:", [(f["rule"], f["line"]) for f in findings] or "none")
    if holes:
        P("DEFINITION HOLES:", [(h["hole"].split(".")[-1], h["status"]) for h in holes])
    P("\nLEAN PROBES (AI writes, Lean decides):")
    for p in probes:
        r = p["result"]
        P(f"  [{r['status']}] {r['claim']}\n      attempts: {len(p['attempts'])}; {r['detail'][:150]}")
    P("\nCERTIFIED RESTATEMENTS:")
    for r in rests:
        P(f"  [{r['status']}] {r['target'].split('.')[-1]}: {r.get('english', '')}")
        if r["status"] == "CERTIFIED":
            P(
                f"      Lean proved: (original) {'↔' if r.get('mode', 'iff') == 'iff' else '→'} ({r.get('restated', '')})"
            )
        else:
            P(f"      {(r.get('detail') or '')[:200]}")


if __name__ == "__main__":
    main()
