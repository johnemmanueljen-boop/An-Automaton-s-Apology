"""Blind lemma audit: pair Lean lemmas with paper lemmas automatically, then audit each pair.

OpenAI's Navier-Stokes Lean files cite paper labels in docstrings. Each cited Lean theorem is paired
with the paper's statement of the same label, with no human choosing or cropping the pair. Lemma 8.6
(already published by Bastounis, Circelli and Hansen) is excluded. This test is what revealed that the
labels follow an earlier draft: most pairs turned out to be different results.

Provenance: results/validation/blind_lemmas.json came from an earlier version of BLIND_USER, before the
CAUTION paragraph about the earlier draft was added (that paragraph exists because of this run). Its
answers are in the cache but a re-run sends the current prompt, so it is not a free re-run.

Usage:
  python -m experiments.blind_lemmas --list          # show the pairs, no API cost
  python -m experiments.blind_lemmas --run --max 10  # audit up to 10 pairs
"""

from __future__ import annotations

import argparse
import json
import re
import sys

from apology.audit import numbered
from apology.llm import complete_json
from apology.paths import PAPERS, REPOS, RESULTS
from apology.prompts import AUDIT_SYSTEM, BLIND_USER

REPO = REPOS["NavierStokesAndEuler"]
PAPER = PAPERS / "ns-openai.txt"
OUT = RESULTS / "validation" / "blind_lemmas.json"
KNOWN = {"Lemma 8.6"}  # already publicly analysed (arXiv 2610.08144); excluded to keep the test blind
LABEL = re.compile(r"\b(Lemma|Proposition|Theorem|Corollary) (\d+\.\d+)\b")
DECL = re.compile(
    r"^(?:@\[[^\]]*\]\s*)?(?:(?:noncomputable|private|protected)\s+)*(theorem|lemma|def|abbrev|structure)\s+(\S+)"
)


def index_decls() -> tuple[list[dict], dict[str, str]]:
    """All declarations in NavierStokes/ with their docstring; plus name -> text for defs/structures."""
    decls, defs = [], {}
    for path in sorted((REPO / "NavierStokes").rglob("*.lean")):
        lines = path.read_text().split("\n")
        for i, l in enumerate(lines):
            m = DECL.match(l)
            if not m:
                continue
            kind, name = m.group(1), m.group(2)
            # docstring directly above
            doc, j = "", i - 1
            if j >= 0 and lines[j].rstrip().endswith("-/"):
                k = j
                while k >= 0 and "/--" not in lines[k]:
                    k -= 1
                if k >= 0:
                    doc = "\n".join(lines[k : j + 1])
            # statement text: up to top-level ':= by' / ':=' / 'where'
            body = []
            for l2 in lines[i : i + 60]:
                body.append(l2)
                if re.search(r":=\s*(by\b|$)|\bwhere\s*$", l2) and kind in ("theorem", "lemma"):
                    break
                if kind in ("def", "abbrev", "structure") and len(body) > 1 and l2 and not l2[0].isspace():
                    body.pop()
                    break
            text = "\n".join(body)
            rec = {
                "kind": kind,
                "name": name,
                "file": str(path.relative_to(REPO)),
                "line": i + 1,
                "doc": doc,
                "text": text,
            }
            decls.append(rec)
            if kind in ("def", "abbrev", "structure"):
                defs.setdefault(name.split(".")[-1], (doc + "\n" if doc else "") + text[:1500])
    return decls, defs


def paper_statement(label: str, paper_lines: list[str]) -> str | None:
    """The paper's statement of `label`: from the line starting with '<label>.' to just after 'Proof.'"""
    pat = re.compile(rf"^\s*{re.escape(label)}[.\s(]")
    for i, l in enumerate(paper_lines):
        if pat.match(l):
            out = []
            for l2 in paper_lines[i : i + 70]:
                out.append(l2)
                if re.match(r"^\s*Proof\b", l2) and len(out) > 2:
                    out += paper_lines[i + len(out) : i + len(out) + 6]  # a little of the proof for context
                    break
            return "\n".join(out)
    return None


def pairs() -> list[dict]:
    decls, defs = index_decls()
    paper_lines = PAPER.read_text().split("\n")
    by_label: dict[str, list[dict]] = {}
    for d in decls:
        if d["kind"] not in ("theorem", "lemma"):
            continue
        for m in LABEL.finditer(d["doc"]):
            label = f"{m.group(1)} {m.group(2)}"
            if label in KNOWN or label.startswith("Theorem 1."):
                continue
            by_label.setdefault(label, []).append(d)
    out = []
    for label, ds in sorted(by_label.items()):
        # prefer a declaration whose docstring starts by naming the label, then the longest statement
        ds.sort(
            key=lambda d: (
                not re.match(rf"/--\s*{re.escape(label)}", d["doc"]),
                "Theorem 1.1" in d["doc"],
                -len(d["text"]),
            )
        )
        d = ds[0]
        ps = paper_statement(label, paper_lines)
        if not ps:
            continue
        idents = set(re.findall(r"[A-Za-z_][\w']*", d["text"])) - {d["name"]}
        ctx = [f"-- definition of {n} (from repo)\n{defs[n]}" for n in sorted(idents) if n in defs][:6]
        lean = "\n\n".join(
            ctx + [f"-- {d['file']}:{d['line']}\n{d['doc']}\n{d['text']}\n  -- (proof omitted; kernel-checked)"]
        )
        out.append(
            {
                "label": label,
                "decl": d["name"],
                "file": d["file"],
                "line": d["line"],
                "lean": lean,
                "paper": ps,
                "n_candidates": len(ds),
            }
        )
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--max", type=int, default=10)
    a = ap.parse_args()
    ps = pairs()
    if a.list or not a.run:
        for p in ps:
            print(
                f"{p['label']:18} -> {p['decl']:50} {p['file']}:{p['line']}  (candidates: {p['n_candidates']}, "
                f"lean ctx {len(p['lean'])} chars, paper {len(p['paper'])} chars)"
            )
        return
    results = []
    for p in ps[: a.max]:
        user = BLIND_USER.format(
            target=p["decl"],
            file=p["file"],
            line=p["line"],
            label=p["label"],
            lean=numbered(p["lean"]),
            paper=p["paper"],
        )
        print(f"auditing {p['label']} ({p['decl']}) ...", file=sys.stderr)
        audit = complete_json(AUDIT_SYSTEM, user, max_tokens=12000, role="audit")
        results.append({**{k: p[k] for k in ("label", "decl", "file", "line")}, "audit": audit})
        OUT.write_text(json.dumps(results, indent=1, ensure_ascii=False))
    for r in results:
        fl = [f for f in r["audit"].get("flags", []) if f.get("severity") in ("high", "medium")]
        print(f"{r['label']:18} {r['decl']:45} medium/high flags: {len(fl)}")


if __name__ == "__main__":
    main()
