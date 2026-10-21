"""Audit any Comparator statement file, from any repository, against lines of its paper (audit only).

Used for the quasi-Riemann hypothesis case and the Taming retrospective:
  python -m experiments.audit_external \
      --challenge ../oai-math/lean/ComparatorChallenges/QuasiRiemannHypothesis.lean \
      --paper ../oai-math/preprints/The-Quasi-Riemann-Hypothesis-September-30-2026/build/paper.tex \
      --lines 64:118 --out results/validation/expert_case_quasi_rh_opus_after_rule.json
  python -m experiments.audit_external \
      --challenge ../oai-math/lean/ComparatorChallenges/TamingCompatibility.lean \
      --paper ../oai-math/preprints/Taming-implies-compatibility-on-four-manifolds-September-23-2026/build/sections/01-introduction.tex \
      --lines 15:72 --out results/findings/taming_retrospective_audit.json

The config JSON next to the challenge supplies the target theorem/definition names. Lint runs with the
standard rules. The LLM sees only the line-numbered statement file, the lint findings and the excerpt.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from apology import lint as lintmod
from apology.audit import llm_audit
from apology.corpus import parse_file


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--challenge", required=True)
    ap.add_argument("--paper", required=True)
    ap.add_argument("--lines", required=True, help="a:b, 1-based inclusive, may repeat with commas")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    lean_path = Path(a.challenge)
    cfg = json.loads(lean_path.with_suffix(".json").read_text())
    decls = [asdict(d) for d in parse_file(lean_path)]
    repo_name = lean_path.resolve().parents[2].name
    findings = [asdict(f) for d in decls for f in lintmod.lint_decl(repo_name, d)]
    paper_lines = Path(a.paper).read_text().split("\n")
    excerpt = "\n...\n".join(
        "\n".join(paper_lines[int(x) - 1 : int(y)]) for x, y in (r.split(":") for r in a.lines.split(","))
    )
    ch = {
        "challenge_file": str(lean_path.name),
        "theorem_names": cfg.get("theorem_names", []),
        "definition_names": cfg.get("definition_names", []),
        "decls": decls,
    }
    audit = llm_audit(ch, lean_path.parent, findings, excerpt=excerpt, override_text=lean_path.read_text())
    out = {"challenge": str(lean_path), "paper": a.paper, "lines": a.lines, "lint": findings, "audit": audit}
    Path(a.out).write_text(json.dumps(out, indent=1, ensure_ascii=False))
    print("SUMMARY:", audit.get("summary"))
    for c in audit.get("coverage", []):
        print("COVERAGE:", c.get("paper_ref"), "->", c.get("lean_theorem"), c.get("relation"), "|", c.get("why"))
    for f in audit.get("flags", []):
        print(f"FLAG [{f['severity']}/{f['category']}] L{f.get('line')}: {f['explanation']}")
        if f.get("probe_idea"):
            print("   probe idea:", f["probe_idea"])
    print("LINT:", [(f["rule"], f["line"]) for f in findings])


if __name__ == "__main__":
    main()
