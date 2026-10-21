"""Citation check: do the paper labels cited in the Lean code exist in the published paper? (no AI)

Lean docstrings cite the paper ("Lemma 8.7", "Proposition 3.2"). Each cited label gets one status:

  in_paper        the paper has a statement with this label
  different_kind  the paper uses this number for another kind of statement (Lean "Lemma 8.3",
                  paper "Proposition 8.3"); usually a different result, see the blind check
  absent          no statement in the paper has this number (e.g. a section the paper does not have)

A label that exists may still point to a different result after renumbering; experiments/blind_lemmas.py
checks content for those.

Usage:
  python -m apology.citations ../NavierStokesAndEuler/NavierStokes ../papers/ns-openai.txt \
      > results/findings/citations_navier_stokes.json
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

KINDS = r"(Lemma|Proposition|Theorem|Corollary|Definition|Remark)"
CITE = re.compile(rf"\b{KINDS} (\d+\.\d+)\b")
HEADER = re.compile(rf"^\s*{KINDS} (\d+\.\d+)\s*[.(]", re.M)


def check(lean_dir: Path, paper_text: str) -> dict:
    headers = {(m.group(1), m.group(2)) for m in HEADER.finditer(paper_text)}
    numbers = {num: kind for kind, num in headers}

    cited: dict[tuple[str, str], list[str]] = {}
    for f in sorted(lean_dir.rglob("*.lean")):
        rel = str(f.relative_to(lean_dir.parent))
        for i, line in enumerate(f.read_text().split("\n"), 1):
            for m in CITE.finditer(line):
                cited.setdefault((m.group(1), m.group(2)), []).append(f"{rel}:{i}")

    rows = []
    for kind, num in sorted(cited, key=lambda k: (*map(int, k[1].split(".")), k[0])):
        if (kind, num) in headers:
            status, paper_has = "in_paper", f"{kind} {num}"
        elif num in numbers:
            status, paper_has = "different_kind", f"{numbers[num]} {num}"
        else:
            status, paper_has = "absent", None
        places = cited[(kind, num)]
        rows.append(
            {
                "label": f"{kind} {num}",
                "status": status,
                "paper_has": paper_has,
                "cited_at": places[:5],
                "n_citations": len(places),
            }
        )

    count = {s: sum(r["status"] == s for r in rows) for s in ("in_paper", "different_kind", "absent")}
    summary = {
        "labels_cited": len(rows),
        **count,
        "not_in_paper": count["different_kind"] + count["absent"],
        "paper_statement_headers": len(headers),
    }
    return {"summary": summary, "labels": rows}


def main(lean_dir: str, paper_txt: str) -> None:
    report = check(Path(lean_dir), Path(paper_txt).read_text())
    s = report["summary"]
    print(
        f"{s['labels_cited']} labels cited: {s['in_paper']} in the paper, {s['different_kind']} with the number "
        f"used for another kind of statement, {s['absent']} with no such number",
        file=sys.stderr,
    )
    for r in report["labels"]:
        if r["status"] != "in_paper":
            print(
                f"  {r['label']:18} {r['status']:15} paper: {r['paper_has'] or '-':18} e.g. {r['cited_at'][0]}",
                file=sys.stderr,
            )
    json.dump(report, sys.stdout, indent=1, ensure_ascii=False)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
