"""Citation check across a random sample of OpenAI's October release (openai/math). No AI.

For each sampled scope note (lean/docs/NNN.md):
  1. papers  = the preprint PDFs the note links  -> printed statement headers ("Lemma 4.4." ...) via pdftotext
  2. modules = solution modules of the note's Comparator configs -> scan the module's directory for
               docstring/comment citations "Lemma 4.4", "Proposition 3.2", ...
  3. a cited label is UNDEFINED if no linked paper prints a statement header with that label.

Caveat: Lean comments may cite theorems of OTHER papers (e.g. "Kun's Theorem 2.1"); every undefined label is a
candidate for human review, not a finding. Lines mentioning a citation key or another author are reported so the
reviewer can discard them quickly.

Usage (the two samples reported; the second excludes the first):
  python -m experiments.citations_release --seed 2026 > results/findings/citations_release_sample_seed2026.json
  python -m experiments.citations_release --seed 2027 \
      --exclude results/findings/citations_release_sample_seed2026.json \
      > results/findings/citations_release_sample_seed2027.json
"""

from __future__ import annotations

import argparse
import json
import random
import re
import subprocess
import sys
from pathlib import Path

from apology.paths import OAI_MATH, WORKSPACE

CITE = re.compile(r"\b(Lemma|Proposition|Theorem|Corollary|Definition|Remark|Claim) (\d+(?:\.\d+)+)\b")
HEADER = re.compile(r"^\s*(Lemma|Proposition|Theorem|Corollary|Definition|Remark|Claim) (\d+(?:\.\d+)+)[.\s(]", re.M)
EXTERNAL_HINT = re.compile(
    r"\[[A-Z][A-Za-z+]*\d{2}|\bof \[|\b(in|from) \[|[A-Z][a-z]+(?:'s| et al\.?| and [A-Z][a-z]+)\s+(?:Lemma|Theorem|Proposition|Corollary)"
)


def sh(cmd: list[str], cwd: Path) -> str:
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=1500).stdout


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=str(OAI_MATH))
    ap.add_argument("--sample", type=int, default=15)
    ap.add_argument("--seed", type=int, default=2026)
    ap.add_argument("--textdir", default=str(WORKSPACE / "oai-text"))
    ap.add_argument("--exclude", default=None, help="JSON from an earlier run; its notes are excluded")
    a = ap.parse_args()
    repo = Path(a.repo).resolve()
    textdir = Path(a.textdir).resolve()
    textdir.mkdir(exist_ok=True)

    notes = sorted((repo / "lean" / "docs").glob("*.md"))
    if a.exclude:
        done = {r["note"] for r in json.loads(Path(a.exclude).read_text())}
        notes = [n for n in notes if n.name not in done]
    rng = random.Random(a.seed)
    sample = sorted(rng.sample(notes, min(a.sample, len(notes))))
    plan = []
    for note in sample:
        text = note.read_text()
        pdfs = sorted(set(re.findall(r"\(\.\./\.\./(preprints/[^)]+\.pdf)\)", text)))
        cfgs = sorted(set(re.findall(r"ComparatorChallenges/([A-Za-z0-9_]+)\.lean", text)))
        mods = []
        for c in cfgs:
            cj = repo / "lean" / "ComparatorChallenges" / f"{c}.json"
            if cj.exists():
                m = json.loads(cj.read_text()).get("solution_module")
                if m:
                    mods.append(m)
        dirs = sorted({"lean/" + "/".join(m.split(".")[:-1]) + "/" for m in mods})
        plan.append(
            {
                "note": note.name,
                "title": text.splitlines()[0].lstrip("# ").strip(),
                "pdfs": pdfs,
                "configs": cfgs,
                "modules": mods,
                "dirs": dirs,
            }
        )

    # fetch only what the sample needs (sparse checkout)
    sparse = repo / ".git" / "info" / "sparse-checkout"
    want = [p["pdfs"] for p in plan] + [p["dirs"] for p in plan]
    with sparse.open("a") as f:
        for group in want:
            for w in group:
                f.write(w + "\n")
    sh(["git", "read-tree", "-mu", "HEAD"], repo)

    out = []
    for p in plan:
        headers = set()
        for pdf in p["pdfs"]:
            txt = textdir / (pdf.replace("preprints/", "").replace("/", "__")[:-4] + ".txt")
            if not txt.exists() and (repo / pdf).exists():
                subprocess.run(["pdftotext", "-layout", str(repo / pdf), str(txt)], capture_output=True, timeout=300)
            if txt.exists():
                headers |= {f"{m.group(1)} {m.group(2)}" for m in HEADER.finditer(txt.read_text(errors="ignore"))}
        cited: dict[str, list[dict]] = {}
        n_files = 0
        for d in p["dirs"]:
            for f in sorted((repo / d).rglob("*.lean")):
                n_files += 1
                for i, line in enumerate(f.read_text(errors="ignore").split("\n"), 1):
                    for m in CITE.finditer(line):
                        lab = f"{m.group(1)} {m.group(2)}"
                        cited.setdefault(lab, []).append(
                            {
                                "at": f"{f.relative_to(repo)}:{i}",
                                "line": line.strip()[:200],
                                "external_hint": bool(EXTERNAL_HINT.search(line)),
                            }
                        )
        undefined = {k: v for k, v in cited.items() if k not in headers}
        likely_internal = {k: v for k, v in undefined.items() if not all(x["external_hint"] for x in v)}
        row = {
            **p,
            "paper_headers": len(headers),
            "lean_files_scanned": n_files,
            "labels_cited": len(cited),
            "undefined": len(undefined),
            "undefined_without_external_hint": len(likely_internal),
            "undefined_detail": {k: v[:3] for k, v in sorted(likely_internal.items())},
            "external_hint_only": sorted(set(undefined) - set(likely_internal)),
        }
        out.append(row)
        print(
            f"{p['note']:8} {p['title'][:55]:55} files={n_files:5} headers={len(headers):3} cited={len(cited):3} "
            f"undefined={len(undefined):3} (no external hint: {len(likely_internal)})",
            file=sys.stderr,
        )
    json.dump(out, sys.stdout, indent=1, ensure_ascii=False)


if __name__ == "__main__":
    main()
