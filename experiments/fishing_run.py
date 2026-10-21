"""Fishing run: blind audits of randomly sampled results from OpenAI's October release.

For each sampled result (data/fishing_sample.json) the smallest statement file is audited against an
automatically extracted paper excerpt (abstract plus the main-theorem region), via the Batch API.
Medium/high flags were then triaged by hand against OpenAI's scope notes: results/findings/fishing_triage.json.
The original run was stopped by the budget cap after 18 of the sampled results; those 18 are reported.

Usage:  python -m experiments.fishing_run
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import asdict
from pathlib import Path

from apology import lint as lintmod
from apology.audit import audit_prompt
from apology.corpus import parse_file
from apology.llm import cache_key, cached, complete_json_many, model_name
from apology.paths import DATA, OAI_MATH, RESULTS, WORKSPACE
from apology.prompts import AUDIT_SYSTEM

REPO = OAI_MATH


def excerpt(txt_path: str, max_lines: int = 170) -> str:
    lines = Path(txt_path).read_text(errors="ignore").split("\n")
    start = next((i for i, l in enumerate(lines) if re.search(r"\bAbstract\b", l)), 0)
    thm = next((i for i, l in enumerate(lines) if re.match(r"^\s*(Main )?Theorem (1(\.1)?|A)\b", l)), None)
    chunks = ["\n".join(lines[start : start + 25])]
    if thm is not None:
        chunks.append("\n".join(lines[max(thm - 5, 0) : thm + max_lines - 25]))
    else:
        chunks.append("\n".join(lines[start + 25 : start + max_lines]))
    return "\n...\n".join(chunks)


def main() -> None:
    sample = json.loads((DATA / "fishing_sample.json").read_text())
    picked, seen = [], set()
    for row in sorted(sample, key=lambda r: r["statement_lines"]):  # smallest statement file per result
        if row["note"] not in seen:
            seen.add(row["note"])
            picked.append(row)

    items, metas = [], []
    for row in picked:
        lean_file = REPO / "lean" / "ComparatorChallenges" / f"{row['config']}.lean"
        config = json.loads(lean_file.with_suffix(".json").read_text())
        decls = [asdict(d) for d in parse_file(lean_file)]
        findings = [asdict(f) for d in decls for f in lintmod.lint_decl("oai-math", d)]
        ch = {
            "challenge_file": f"lean/ComparatorChallenges/{row['config']}.lean",
            "theorem_names": config.get("theorem_names", []),
            "definition_names": config.get("definition_names", []),
            "decls": decls,
        }
        paper = excerpt(str(WORKSPACE / row["paper_text"]))
        items.append((AUDIT_SYSTEM, audit_prompt(ch, REPO, findings, excerpt=paper), 9000))
        metas.append({"note": row["note"], "config": row["config"], "lines": row["statement_lines"]})

    print(f"submitting {len(items)} audits", file=sys.stderr)
    try:
        results = complete_json_many(items, role="audit")
    except RuntimeError as e:  # the budget cap stopped the original run after 18 audits; keep those
        print(f"stopped: {e}", file=sys.stderr)
        results = [cached(cache_key(model_name("audit"), *item)) for item in items]
    out = []
    for meta, result in zip(metas, results, strict=True):
        if result is None:
            continue
        flags = result.get("flags", [])
        medium_high = [f for f in flags if f.get("severity") in ("high", "medium")]
        out.append(
            {
                **meta,
                "summary": result.get("summary"),
                "coverage": result.get("coverage"),
                "flags_medium_high": medium_high,
                "all_flags": flags,
            }
        )
        print(f"\n### {meta['note']} {meta['config']} ({meta['lines']} lines): {len(medium_high)} medium/high")
        for f in medium_high:
            print(f"   [{f['severity']}/{f['category']}] L{f.get('line')}: {f['explanation'][:300]}")
    (RESULTS / "findings" / "fishing_audits.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
