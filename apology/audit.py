"""Audit one result: does OpenAI's Lean statement say what the paper claims?

For one Comparator statement file this produces an audit card (results/cards/<name>.json):

  1. lint            deterministic junk-value and gotcha checks         (lint.py, no AI)
  2. audit           Opus reads the statement next to the paper excerpt  (prompts.AUDIT_SYSTEM)
                     -> plain reading, glossary, paper-vs-Lean coverage, flags with cited lines
  3. citations       every cited declaration and line is checked by code
  4. probes          Sonnet writes small Lean checks; Lean decides        (probes.py)
  5. restatements    clearer versions that Lean proves equivalent         (restate.py)

Usage:
  python -m apology.audit D_NonSoficGroup                # one result
  python -m apology.audit --all                          # every result in data/paper_map.json
  python -m apology.audit D_NonSoficGroup --no-probes    # audit only, no Lean needed
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict
from pathlib import Path

from .llm import complete_json
from .paths import CARDS, DATA, PAPERS, REPOS
from .probes import Probe, run_probe
from .prompts import AUDIT_SYSTEM, PROBE_SYSTEM
from .restate import llm_restate

# ---------------------------------------------------------------- inputs


def load_challenge(stem: str) -> tuple[dict, Path]:
    for ch in json.loads((DATA / "corpus.json").read_text()):
        if Path(ch["challenge_file"]).stem == stem:
            return ch, REPOS[ch["repo"]]
    raise SystemExit(f"unknown result {stem}")


def _paper_map() -> dict:
    return json.loads((DATA / "paper_map.json").read_text())


def _paper_entry(entry, default: str) -> tuple[str, list]:
    return (entry["file"], entry["ranges"]) if isinstance(entry, dict) else (default, entry)


def paper_excerpt(stem: str) -> str:
    pm = _paper_map()
    if stem not in pm["ranges"]:
        return "(no paper excerpt available)"
    file, ranges = _paper_entry(pm["ranges"][stem], pm["default_paper"])
    lines = (PAPERS / file).read_text().split("\n")  # not splitlines(): PDF form feeds would shift numbering
    return "\n...\n".join("\n".join(lines[a - 1 : b]) for a, b in ranges)


def sibling_note(stem: str) -> str:
    """Tell the auditor when other statement files formalize other theorems from the same paper excerpt,
    so it does not flag those theorems as 'not formalized' here."""
    pm = _paper_map()
    file, mine = _paper_entry(pm["ranges"].get(stem, []), pm["default_paper"])
    siblings = [
        other
        for other, entry in pm["ranges"].items()
        if other != stem
        and _paper_entry(entry, pm["default_paper"])[0] == file
        and any(a <= d and c <= b for a, b in mine for c, d in _paper_entry(entry, pm["default_paper"])[1])
    ]
    if not siblings:
        return ""
    return (
        "NOTE: this paper excerpt is shared with sibling challenge files "
        + ", ".join(siblings)
        + ", which formalize other theorems from the same paper. Do NOT flag claims as not_formalized merely "
        "because they are absent from THIS file; judge coverage only for the claims this file's targets address, "
        "and mark the others as 'covered elsewhere (sibling file)' in the coverage table.\n"
    )


def numbered(text: str, start: int = 1) -> str:
    return "\n".join(f"{i:4d}| {line}" for i, line in enumerate(text.splitlines(), start))


# ---------------------------------------------------------------- the AI audit


def audit_prompt(
    ch: dict, repo: Path, lint_findings: list[dict], excerpt: str | None = None, override_text: str | None = None
) -> str:
    """The auditor's user message: the line-numbered statement file, lint findings, paper excerpt."""
    src = override_text if override_text is not None else (repo / ch["challenge_file"]).read_text()
    stem = Path(ch["challenge_file"]).stem
    lint_view = [
        {"line": f["line"], "rule": f["rule"], "severity": f["severity"], "snippet": f["snippet"]}
        for f in lint_findings
        if f["severity"] in ("high", "medium")
    ]
    return (
        f"TARGET THEOREMS (checked by Comparator against the real proofs): {ch['theorem_names']}\n"
        f"TARGET DEFINITIONS: {ch['definition_names']}\n\n"
        f"=== LEAN STATEMENT FILE {ch['challenge_file']} (line-numbered) ===\n{numbered(src)}\n\n"
        f"=== STATIC LINT FINDINGS (give a verdict for each) ===\n{json.dumps(lint_view, ensure_ascii=False)}\n\n"
        f"=== PAPER EXCERPT (pdftotext; math may be garbled) ===\n"
        f"{excerpt if excerpt is not None else paper_excerpt(stem)}\n"
        f"{sibling_note(stem)}"
    )


def llm_audit(
    ch: dict, repo: Path, lint_findings: list[dict], excerpt: str | None = None, override_text: str | None = None
) -> dict:
    user = audit_prompt(ch, repo, lint_findings, excerpt, override_text)
    return complete_json(AUDIT_SYSTEM, user, max_tokens=24000, role="audit")


def verify_citations(ch: dict, audit: dict) -> None:
    """Mark each flag, glossary entry and claim citation_ok only if the cited declaration exists
    and the cited line falls inside it."""
    for key, field in (("flags", "decl"), ("glossary", "decl"), ("lean_claims", "theorem")):
        for item in audit.get(key, []):
            name = item.get(field) or ""
            exact = [d for d in ch["decls"] if d["name"] == name]
            matches = exact or [d for d in ch["decls"] if _names(d, name)]
            line = item.get("line")
            # Exactly one declaration, and a whole-number line inside it (bool is not a line number).
            item["citation_ok"] = (
                len(matches) == 1 and type(line) is int and matches[0]["start_line"] <= line <= matches[0]["end_line"]
            )


def _names(decl: dict, cited: str) -> bool:
    """Does a name the audit cited (full, short, or partly qualified) refer to this declaration?"""
    return cited in (decl["name"], decl["short_name"]) or decl["name"].endswith("." + cited)


def _used_by_targets(decls: list[dict]) -> set[str]:
    """Declarations the target theorems depend on, directly or through other declarations."""
    by_short: dict[str, list[str]] = {}
    for d in decls:
        by_short.setdefault(d["short_name"], []).append(d["name"])
    text = {d["name"]: d["text"] for d in decls}
    used = {d["name"] for d in decls if d.get("is_target_theorem")}
    todo = list(used)
    while todo:
        for token in re.findall(r"[A-Za-z_][\w'.]*", text[todo.pop()]):
            for name in by_short.get(token.split(".")[-1], []):
                if name not in used:
                    used.add(name)
                    todo.append(name)
    return used


def trust_burden(ch: dict, audit: dict, restatements: list[dict] | None = None) -> dict:
    """Statement lines a person still has to read to trust the result.

    Counted: every target theorem (it is the claim itself), every flagged declaration, and every
    declaration the theorems use that the audit did not judge standard. Not counted: declarations no
    target theorem uses, and definitions Lean has certified equivalent to a statement in standard
    Mathlib terms (the reader reads that version instead)."""
    decls = ch["decls"]
    standard = [g["decl"] for g in audit.get("glossary", []) if g.get("matches_standard") == "yes"]
    flagged = [f["decl"] for f in audit.get("flags", []) if f.get("severity") in ("high", "medium") and f.get("decl")]
    certified = {r["target"] for r in restatements or [] if r.get("status") == "CERTIFIED" and r.get("mathlib_only")}
    used = _used_by_targets(decls)
    needs = 0
    for d in decls:
        if d["name"] not in used:
            continue
        is_target = d["kind"] in ("theorem", "lemma") and d["is_target_theorem"]
        is_flagged = any(_names(d, n) for n in flagged)
        is_cleared = any(_names(d, n) for n in standard) or d["name"] in certified
        if is_target or is_flagged or not is_cleared:
            needs += sum(1 for line in d["text"].splitlines() if line.strip())
    return {
        "statement_lines": ch["nonblank_lines"],
        "lines_needing_human_review": needs,
        "note": "target theorems and flagged declarations always need review; a definition is cleared when "
        "judged standard or certified by Lean in Mathlib terms; declarations no target uses are not counted",
    }


def recount(stem: str) -> dict:
    """Recompute a stored card's human-review count (no AI, no Lean)."""
    path = CARDS / f"{stem}.json"
    card = json.loads(path.read_text())
    ch, _ = load_challenge(stem)
    card["trust_burden"] = trust_burden(ch, card["audit"], card.get("restatements"))
    path.write_text(json.dumps(card, indent=1, ensure_ascii=False))
    return card


# ---------------------------------------------------------------- Lean probes


def probe_for(ch: dict, repo: Path, target: dict, max_repairs: int = 2) -> dict:
    """Ask Sonnet for a Lean probe that bears on `target`; feed Lean's errors back up to `max_repairs` times."""
    src = (repo / ch["challenge_file"]).read_text()
    base = f"=== CHALLENGE FILE {ch['challenge_file']} ===\n{src}\n\n=== WHAT TO CHECK ===\n{json.dumps(target, ensure_ascii=False)}\n"
    history, attempts = "", []
    for attempt in range(max_repairs + 1):
        spec = complete_json(PROBE_SYSTEM, base + history, max_tokens=10000)
        probe = Probe(
            id=f"{target.get('id', 'probe')}-a{attempt}",
            repo_dir=str(repo),
            challenge_file=ch["challenge_file"],
            kind=spec.get("kind", "other"),
            claim=spec.get("claim", ""),
            lean=spec["lean"],
            check_decls=spec.get("check_decls", []),
        )
        result = run_probe(probe)
        attempts.append(
            {"lean": probe.lean, "status": result.status, "detail": result.detail, "seconds": result.seconds}
        )
        if result.status != "YELLOW":
            break
        history += (
            f"\n=== ATTEMPT {attempt + 1} FAILED ===\n{probe.lean}\nLean said: {result.detail}\n"
            "Fix it, or switch to a smaller probe that still bears on the claim.\n"
        )
    return {"target": target, "result": asdict(result), "lean": probe.lean, "attempts": attempts}


def probe_targets(audit: dict) -> list[dict]:
    """Flags with a probe idea, lint findings the audit wants settled, and always one non-vacuity check."""
    targets = [
        {
            "id": f["id"],
            "decl": f["decl"],
            "line": f["line"],
            "explanation": f["explanation"],
            "probe_idea": f["probe_idea"],
        }
        for f in audit.get("flags", [])
        if f.get("probe_idea")
    ]
    targets += [
        {
            "id": f"L{v['line']}",
            "rule": v["rule"],
            "line": v["line"],
            "explanation": v["why"],
            "probe_idea": "settle this lint finding",
        }
        for v in audit.get("lint_verdicts", [])
        if v.get("verdict") in ("needs-probe", "concern")
    ]
    targets.append(
        {
            "id": "NV",
            "explanation": "Non-vacuity: exhibit a concrete object satisfying the central "
            "bespoke definition(s) the target theorems quantify over.",
            "probe_idea": "construct an instance of the main definition",
        }
    )
    return targets


# ---------------------------------------------------------------- one card


def run(stem: str, do_probes: bool = True, max_probes: int = 4, max_restate: int = 3) -> dict:
    ch, repo = load_challenge(stem)
    findings = [f for f in json.loads((DATA / "lint.json").read_text()) if f["file"] == Path(ch["challenge_file"]).name]
    print(f"[{stem}] audit", file=sys.stderr)
    audit = llm_audit(ch, repo, findings)
    verify_citations(ch, audit)

    probes, restatements = [], []
    if do_probes:
        seen = set()
        for target in probe_targets(audit)[:max_probes]:
            print(f"[{stem}] probe {target['id']}", file=sys.stderr)
            res = probe_for(ch, repo, target)
            if (key := " ".join(res["lean"].split())) not in seen:  # skip an identical probe
                seen.add(key)
                probes.append(res)

        # target theorems first, then definitions the audit did not judge standard
        names = list(ch["theorem_names"])
        for g in audit.get("glossary", []):
            if g.get("matches_standard") in ("partly", "no", "unclear"):
                full = next((d["name"] for d in ch["decls"] if d["short_name"] == g["decl"]), g["decl"])
                names.append(g["decl"] if "." in g["decl"] else full)
        for i, name in enumerate(list(dict.fromkeys(names))[:max_restate]):
            print(f"[{stem}] restate {name}", file=sys.stderr)
            try:
                restatements.append(asdict(llm_restate(ch, repo, name, "iff", i)))
            except Exception as e:  # record the failure and keep going
                restatements.append({"target": name, "status": "FAILED", "detail": f"error: {e}"})

    card = {
        "result": stem,
        "repo": ch["repo"],
        "challenge_file": ch["challenge_file"],
        "theorems": ch["theorem_names"],
        "lint": findings,
        "audit": audit,
        "probes": probes,
        "restatements": restatements,
        "trust_burden": trust_burden(ch, audit, restatements),
    }
    CARDS.mkdir(parents=True, exist_ok=True)
    (CARDS / f"{stem}.json").write_text(json.dumps(card, indent=1, ensure_ascii=False))
    return card


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("stem", nargs="?", help="result name, e.g. D_NonSoficGroup")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--no-probes", action="store_true")
    ap.add_argument("--max-probes", type=int, default=4)
    ap.add_argument("--max-restate", type=int, default=3)
    ap.add_argument("--recount", action="store_true", help="only recompute the human-review count of stored cards")
    a = ap.parse_args()
    stems = list(_paper_map()["ranges"]) if a.all else [a.stem]
    for stem in stems:
        try:
            card = recount(stem) if a.recount else run(stem, not a.no_probes, a.max_probes, a.max_restate)
        except RuntimeError as e:
            print(f"{stem}: stopped: {e}")
            if "Budget cap" in str(e):
                break
            continue
        tb = card["trust_burden"]
        print(
            f"{stem}: {len(card['audit'].get('flags', []))} flags, "
            f"probes {[p['result']['status'] for p in card['probes']]}, "
            f"restatements {[r.get('status') for r in card['restatements']]}, "
            f"human review {tb['lines_needing_human_review']}/{tb['statement_lines']} lines"
        )


if __name__ == "__main__":
    main()
