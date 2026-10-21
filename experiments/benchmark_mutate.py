"""Planted-error benchmark, step 1: write statement files with one planted error each.

Each mutant changes one thing in an OpenAI statement file. The operators follow the five kinds of
"semantic hallucination" catalogued by Lean Atlas (arXiv 2604.16347):

  definition-mismatch     change a constant / comparison inside a bespoke definition
  assumption              drop a hypothesis, or add a contradictory one (vacuity)
  goal-substitution       weaken/strengthen the conclusion (< vs ≤, constants)
  quantifier              swap ∀/∃, ∀ᶠ/∃ᶠ
  type-default            move a cast from ℝ to ℕ / ℤ

Every mutant is compiled and only those that still type-check are used: exactly the errors Lean
cannot catch on its own. The held-out set in data/heldout_mutants/ was generated after the pilot, with
the pilot's sites excluded:

  python -m experiments.benchmark_mutate --out data/heldout_mutants --per-file 4 --seed 2026 --compile \
      --exclude-manifest data/pilot_mutants_manifest.json
"""

from __future__ import annotations

import argparse
import json
import os
import random
import re
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path

from apology.paths import DATA, REPOS
from apology.probes import ELAN_BIN

# (pattern, operator id, regex, replacement-function)
OPERATORS = [
    ("goal-substitution", "lt-to-le", r"(?<![<=≤])<(?![=-])", lambda m: "≤"),
    ("goal-substitution", "le-to-lt", r"≤", lambda m: "<"),
    ("goal-substitution", "const-bump", r"(?<![\w.])([2-9])(?![\w.])", lambda m: str(int(m.group(1)) + 1)),
    (
        "goal-substitution",
        "frac-change",
        r"\(1 / 3 : ℝ\)|\(1 / 2 : ℝ\)",
        lambda m: m.group(0).replace("1 /", "1 / 2 *") if "1 / 2" not in m.group(0) else "(1 / 3 : ℝ)",
    ),
    ("quantifier", "forall-to-exists", r"∀(?!ᶠ)", lambda m: "∃"),
    ("quantifier", "exists-to-forall", r"∃(?![ᶠ!])", lambda m: "∀"),
    ("quantifier", "eventually-to-frequently", r"∀ᶠ", lambda m: "∃ᶠ"),
    ("type-default", "real-cast-to-nat", r":\s*ℝ\)", lambda m: ": ℕ)"),
    ("type-default", "real-cast-to-int", r":\s*ℝ\)", lambda m: ": ℤ)"),
    ("assumption", "vacuous-epsilon", r"0 < ε →", lambda m: "0 < ε → ε < 0 →"),
    (
        "assumption",
        "add-false-hyp",
        r"theorem (\S+)\s*(\(|:|\{)",
        lambda m: f"theorem {m.group(1)} (hbase : (1 : ℕ) = 0) {m.group(2)}",
    ),
    ("definition-mismatch", "succ-shift", r"\+ 1\b", lambda m: "+ 2"),
    ("definition-mismatch", "one-minus-eps", r"1 - ε", lambda m: "ε"),
    ("definition-mismatch", "strict-to-nonstrict-def", r"(?<![<=≤])<(?![=-])", lambda m: "≤"),
]


@dataclass
class Mutant:
    id: str
    repo: str
    challenge_file: str
    decl: str
    decl_kind: str
    pattern: str
    operator: str
    line: int
    original: str
    mutated: str
    compiles: bool | None = None
    path: str = ""


def _candidate_sites(decl: dict, op) -> list[re.Match]:
    pattern, opid, rx, _ = op
    text = decl["text"]
    is_thm = decl["kind"] in ("theorem", "lemma")
    if pattern == "definition-mismatch" and is_thm:
        return []
    if (
        pattern in ("goal-substitution", "quantifier", "type-default")
        and opid != "strict-to-nonstrict-def"
        and not is_thm
    ):
        # restrict goal/quantifier/type mutations to theorem statements (definitions get their own operators)
        return []
    if opid == "add-false-hyp" and not decl.get("is_target_theorem"):
        return []
    # don't mutate inside comments or the proof
    stmt_end = text.find(":= by")
    region = text if stmt_end < 0 else text[:stmt_end]
    out = []
    for m in re.finditer(rx, region):
        line = region[: m.start()].split("\n")[-1]
        if "--" in line or line.strip().startswith(("/-", "-/")):
            continue
        out.append(m)
    return out


def generate(corpus: list[dict], per_file: int, seed: int) -> list[tuple[Mutant, str]]:
    rng = random.Random(seed)
    results = []
    for ch in corpus:
        src_path = Path(ch["_repo_dir"]) / ch["challenge_file"]
        src = src_path.read_text()
        sites = []
        for d in ch["decls"]:
            for op in OPERATORS:
                for m in _candidate_sites(d, op):
                    sites.append((d, op, m))
        rng.shuffle(sites)
        # spread across patterns: round-robin by pattern
        by_pattern: dict[str, list] = {}
        for s in sites:
            by_pattern.setdefault(s[1][0], []).append(s)
        chosen = []
        while len(chosen) < per_file and any(by_pattern.values()):
            for k in list(by_pattern):
                if by_pattern[k] and len(chosen) < per_file:
                    chosen.append(by_pattern[k].pop())
        for n, (d, (pattern, opid, _rx, fn), m) in enumerate(chosen):
            decl_off = src.find(d["text"])
            if decl_off < 0:
                continue
            abs_start, abs_end = decl_off + m.start(), decl_off + m.end()
            new = fn(m)
            mutated_src = src[:abs_start] + new + src[abs_end:]
            line_no = src.count("\n", 0, abs_start) + 1
            orig_line = src.splitlines()[line_no - 1]
            mut_line = mutated_src.splitlines()[line_no - 1]
            mid = f"{Path(ch['challenge_file']).stem}-{n:02d}-{opid}"
            results.append(
                (
                    Mutant(
                        mid,
                        ch["repo"],
                        ch["challenge_file"],
                        d["name"],
                        d["kind"],
                        pattern,
                        opid,
                        line_no,
                        orig_line.strip(),
                        mut_line.strip(),
                    ),
                    mutated_src,
                )
            )
    return results


def compile_ok(repo_dir: Path, text: str) -> bool:
    env = dict(os.environ, PATH=f"{ELAN_BIN}:{os.environ.get('PATH', '')}")
    tmp = repo_dir / "_mutant_check.lean"
    tmp.write_text(text)
    try:
        p = subprocess.run(
            ["lake", "env", "lean", str(tmp)], cwd=repo_dir, env=env, capture_output=True, text=True, timeout=900
        )
        return p.returncode == 0 and ": error" not in (p.stdout + p.stderr)
    except subprocess.TimeoutExpired:
        return False
    finally:
        tmp.unlink(missing_ok=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data/heldout_mutants")
    ap.add_argument("--per-file", type=int, default=6)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--compile", action="store_true")
    ap.add_argument("--only-repo", default=None)
    ap.add_argument(
        "--exclude-manifest", default=None, help="skip sites already used in another benchmark (held-out set)"
    )
    a = ap.parse_args()
    repo_dirs = REPOS
    corpus = [c for c in json.loads((DATA / "corpus.json").read_text()) if a.only_repo in (None, c["repo"])]
    for c in corpus:
        c["_repo_dir"] = str(repo_dirs[c["repo"]])
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    muts = generate(corpus, a.per_file + 4, a.seed)
    if a.exclude_manifest:
        used = {
            (m["challenge_file"], m["line"], m["operator"]) for m in json.loads(Path(a.exclude_manifest).read_text())
        }
        muts = [(m, t) for m, t in muts if (m.challenge_file, m.line, m.operator) not in used]
    # keep at most per_file per challenge file
    kept, count = [], {}
    for m, t in muts:
        if count.get(m.challenge_file, 0) < a.per_file:
            count[m.challenge_file] = count.get(m.challenge_file, 0) + 1
            kept.append((m, t))
    muts = kept
    manifest = []
    for mut, text in muts:
        p = out / f"{mut.id}.lean"
        p.write_text(text)
        mut.path = str(p)
        if a.compile:
            mut.compiles = compile_ok(repo_dirs[mut.repo], text)
            print(
                f"{'OK ' if mut.compiles else 'ERR'} {mut.id}: {mut.original[:60]!r} -> {mut.mutated[:60]!r}",
                flush=True,
            )
        manifest.append(asdict(mut))
        (out / "manifest.json").write_text(json.dumps(manifest, indent=1, ensure_ascii=False))
    print(f"{len(manifest)} mutants written to {out}/", flush=True)


if __name__ == "__main__":
    main()
