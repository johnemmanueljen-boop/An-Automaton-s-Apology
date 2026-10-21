"""Measure the auditor: expert ground truth and the planted-error benchmark.

  cases     Real mismatches found by human experts (data/expert_cases/). For Navier-Stokes Lemma 8.6
            (Bastounis, Circelli and Hansen, about two weeks of work) the auditor gets the Lean lemma and
            the paper's lemma. An expert item counts as found if one flag mentions all its keyword groups.

  mutants   The held-out planted errors (data/heldout_mutants/), each still accepted by Lean. The auditor
            sees the mutated statement file and the paper excerpt, exactly as in a real audit. Found means
            a medium/high flag within 2 lines of the planted error ("strict"), or naming the mutated
            declaration ("loose"). False alarms use the same rule on the unmutated file. Before anything is
            sent, every prompt is scanned for words that could give the answer away.

Usage:
  python -m experiments.benchmark_evaluate cases
  python -m experiments.benchmark_evaluate mutants --batch --with-lint
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from collections import defaultdict
from dataclasses import asdict
from pathlib import Path

from apology import lint as lintmod
from apology.audit import audit_prompt, load_challenge, numbered
from apology.corpus import parse_file
from apology.llm import complete_json, complete_json_many, model_name
from apology.paths import DATA, RESULTS, ROOT
from apology.prompts import AUDIT_SYSTEM, CASE_USER

OUT = RESULTS / "validation"
LEAK_PATTERNS = [
    r"\bmutants?\b",
    r"\bmutat(ed|ion|ions)\b",
    r"h_mut",
    r"\binjected\b",
    r"\bplanted\b",
    r"\bbenchmark",
    r"\bmanifest\b",
    r"\bsabotag",
    r"\bdeliberate(ly)?\b",
]


# ---------------------------------------------------------------- expert cases


def run_cases() -> list[dict]:
    report = []
    for path in sorted((DATA / "expert_cases").glob("*.json")):
        case = json.loads(path.read_text())
        user = CASE_USER.format(
            target=case["lean_target"],
            lean=numbered(case["lean_context"]),
            paper_ref=case["paper_ref"],
            paper=case["paper_excerpt"],
        )
        audit = complete_json(AUDIT_SYSTEM, user, max_tokens=12000, role="audit")
        flags = audit.get("flags", [])
        hits = []
        for gt in case["ground_truth"]:
            matched = next(
                (
                    f["id"]
                    for f in flags
                    if all(any(k.lower() in _flag_text(f) for k in group) for group in gt["keywords"])
                ),
                None,
            )
            hits.append({"gt": gt["id"], "label": gt["label"], "matched_flag": matched})
        report.append(
            {
                "case": case["id"],
                "found_by": case["found_by"],
                "hits": hits,
                "n_flags": len(flags),
                "flags": flags,
                "summary": audit.get("summary"),
            }
        )
        found = sum(h["matched_flag"] is not None for h in hits)
        print(f"{case['id']}: {found}/{len(hits)} expert items found ({len(flags)} flags)", file=sys.stderr)
        (OUT / f"expert_case_{path.stem}.json").write_text(json.dumps(report[-1:], indent=1, ensure_ascii=False))
    return report


def _flag_text(flag: dict) -> str:
    return ((flag.get("explanation") or "") + " " + (flag.get("probe_idea") or "")).lower()


# ---------------------------------------------------------------- planted errors


def flag_hits(flags: list[dict], line: int, decl: str, strict: bool) -> dict | None:
    """The first medium/high flag pointing at the planted error, else None."""
    short = decl.split(".")[-1]
    for f in flags:
        if f.get("severity") not in ("high", "medium"):
            continue
        try:
            flag_line = int(f.get("line") or -999)
        except (TypeError, ValueError):
            flag_line = -999
        flag_decl = (f.get("decl") or "").split(".")[-1]
        if abs(flag_line - line) <= 2 or (not strict and flag_decl == short):
            return f
    return None


def lint_text(repo_name: str, file_name: str, text: str) -> list[dict]:
    """Lint a (possibly mutated) statement file exactly as the pipeline lints a real one."""
    with tempfile.TemporaryDirectory() as d:
        tmp = Path(d) / file_name
        tmp.write_text(text)
        decls = [asdict(x) for x in parse_file(tmp)]
    return [asdict(f) for dd in decls for f in lintmod.lint_decl(repo_name, dd)]


def run_mutants(manifest: Path, batch: bool, with_lint: bool, out_name: str) -> dict:
    mutants = [m for m in json.loads(manifest.read_text()) if m.get("compiles")]
    all_lint = json.loads((DATA / "lint.json").read_text())

    prompts, metas = [], []
    for m in mutants:
        ch, repo = load_challenge(Path(m["challenge_file"]).stem)
        text = (ROOT / m["path"]).read_text()
        findings = lint_text(ch["repo"], Path(ch["challenge_file"]).name, text) if with_lint else []
        prompts.append(audit_prompt(ch, repo, findings, override_text=text))
        metas.append(("mutant", m))
    for stem in sorted({Path(m["challenge_file"]).stem for m in mutants}):  # the unmutated files
        ch, repo = load_challenge(stem)
        findings = (
            [f for f in all_lint if f["file"] == Path(ch["challenge_file"]).name and f["repo"] == ch["repo"]]
            if with_lint
            else []
        )
        prompts.append(audit_prompt(ch, repo, findings))
        metas.append(("clean", stem))

    leaks = [(i, w) for i, p in enumerate(prompts) for w in LEAK_PATTERNS if re.search(w, p.lower())]
    if leaks:
        raise RuntimeError(f"possible answer leak in prompts: {leaks[:5]}")

    items = [(AUDIT_SYSTEM, p, 24000) for p in prompts]
    results = (
        complete_json_many(items, role="audit")
        if batch
        else [complete_json(s, u, max_tokens=n, role="audit") for s, u, n in items]
    )

    clean_flags = {
        meta[1]: (res or {}).get("flags", []) for meta, res in zip(metas, results, strict=True) if meta[0] == "clean"
    }
    by_pattern = defaultdict(lambda: {"strict": 0, "loose": 0, "total": 0})
    rows = []
    for (kind, m), res in zip(metas, results, strict=True):
        if kind != "mutant":
            continue
        flags = (res or {}).get("flags", [])
        strict, loose = flag_hits(flags, m["line"], m["decl"], True), flag_hits(flags, m["line"], m["decl"], False)
        stats = by_pattern[m["pattern"]]
        stats["strict"] += bool(strict)
        stats["loose"] += bool(loose)
        stats["total"] += 1
        rows.append(
            {
                "mutant": m["id"],
                "pattern": m["pattern"],
                "operator": m["operator"],
                "line": m["line"],
                "detected_strict": bool(strict),
                "detected_loose": bool(loose),
                "matching_flag": (strict or loose or {}).get("explanation"),
                "all_flags": flags,
                "original": m["original"],
                "mutated": m["mutated"],
            }
        )

    def false_alarms(strict: bool) -> int:
        return sum(
            bool(flag_hits(clean_flags[Path(m["challenge_file"]).stem], m["line"], m["decl"], strict)) for m in mutants
        )

    n = max(len(rows), 1)
    ds, dl, fs, fl = (
        sum(r["detected_strict"] for r in rows),
        sum(r["detected_loose"] for r in rows),
        false_alarms(True),
        false_alarms(False),
    )
    summary = {
        "model": model_name("audit"),
        "with_lint": with_lint,
        "mutants_evaluated": len(rows),
        "strict": {
            "detected": ds,
            "rate": round(ds / n, 3),
            "false_alarms_on_clean": fs,
            "false_alarm_rate": round(fs / n, 3),
        },
        "loose": {
            "detected": dl,
            "rate": round(dl / n, 3),
            "false_alarms_on_clean": fl,
            "false_alarm_rate": round(fl / n, 3),
        },
        "by_pattern": dict(by_pattern),
        "note": "strict = a medium/high flag within ±2 lines of the planted bug; loose = strict or a flag naming the "
        "mutated declaration. False alarms apply the same rule to the unmutated file.",
    }
    (OUT / out_name).write_text(
        json.dumps({"summary": summary, "rows": rows, "clean_flags": clean_flags}, indent=1, ensure_ascii=False)
    )
    return summary


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("which", choices=["cases", "mutants"])
    ap.add_argument("--manifest", default=str(DATA / "heldout_mutants" / "manifest.json"))
    ap.add_argument("--batch", action="store_true", help="Message Batches API, half price")
    ap.add_argument("--with-lint", action="store_true", help="show the auditor the lint findings, as in real use")
    ap.add_argument("--out", default="heldout_benchmark.json")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    if a.which == "cases":
        for case in run_cases():
            print(json.dumps({k: v for k, v in case.items() if k != "flags"}, indent=1, ensure_ascii=False))
    else:
        print(json.dumps(run_mutants(Path(a.manifest), a.batch, a.with_lint, a.out), indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
