"""Negative control: does the auditor raise false alarms on statements that are known to be right?

12 textbook theorems, each stated in Lean exactly as Mathlib states it (community-reviewed; each file
proves its statement identical to the Mathlib lemma). Names and docstrings are stripped so the model
cannot simply recognise them. Any medium/high flag is a candidate false alarm.

Usage:  python -m experiments.negative_control
"""

from __future__ import annotations

import json
from dataclasses import asdict

from apology import lint as lintmod
from apology.audit import audit_prompt
from apology.corpus import parse_file
from apology.llm import complete_json_many
from apology.paths import DATA, RESULTS
from apology.prompts import AUDIT_SYSTEM

CONTROLS = DATA / "negative_controls"


def main() -> None:
    spec = json.loads((CONTROLS / "spec.json").read_text())
    prompts = []
    for x in spec:
        path = CONTROLS / f"{x['id']}.lean"
        decls = [asdict(d) for d in parse_file(path)]
        findings = [asdict(f) for d in decls for f in lintmod.lint_decl("negative_controls", d)]
        ch = {"challenge_file": "Statement.lean", "theorem_names": ["stmt"], "definition_names": [], "decls": decls}
        prompts.append(audit_prompt(ch, CONTROLS, findings, excerpt=x["paper"], override_text=path.read_text()))
    results = complete_json_many([(AUDIT_SYSTEM, p, 24000) for p in prompts], role="audit")
    rows = []
    for x, res in zip(spec, results, strict=True):
        flags = res.get("flags", [])
        mh = [f for f in flags if f.get("severity") in ("high", "medium")]
        rel = [c.get("relation") for c in res.get("coverage", [])]
        rows.append(
            {
                "id": x["id"],
                "paper": x["paper"],
                "relations": rel,
                "n_flags": len(flags),
                "medium_high": mh,
                "summary": res.get("summary"),
            }
        )
        print(f"{x['id']}: relations={rel} medium/high flags={len(mh)}")
        for f in mh:
            print(f"    [{f['severity']}/{f['category']}] {f['explanation'][:300]}")
    out = {
        "n": len(rows),
        "with_medium_high": sum(1 for r in rows if r["medium_high"]),
        "weaker_or_different": sum(
            1 for r in rows if any(v in ("lean_weaker", "different", "not_formalized") for v in r["relations"])
        ),
        "rows": rows,
    }
    (RESULTS / "validation" / "negative_control.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))
    print(
        f"\n{out['with_medium_high']}/{out['n']} statements got a medium/high flag; "
        f"{out['weaker_or_different']}/{out['n']} judged weaker/different/not formalized"
    )


if __name__ == "__main__":
    main()
