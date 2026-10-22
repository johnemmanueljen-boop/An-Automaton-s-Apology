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
import sys
from dataclasses import asdict
from pathlib import Path

from .llm import complete_json
from .paths import DATA, PAPERS, REPOS
from .probes import run_probe, build_probe
from .prompts import AUDIT_SYSTEM
from .restate import llm_restate
from .schema import validate_location, validate_audit, new_run, write_json, digest

# ---------------------------------------------------------------- inputs


def load_challenge(stem: str) -> tuple[dict, Path]:
    repository, _, name = stem.partition(":")
    matches = [ch for ch in json.loads((DATA / "corpus.json").read_text(encoding="utf-8"))
               if Path(ch["challenge_file"]).stem == (name or stem)
               and (not name or ch["repo"] == repository)]
    if len(matches) > 1:
        raise ValueError(f"ambiguous result {stem}; use repository:stem")
    if matches:
        return matches[0], REPOS[matches[0]["repo"]]
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
    return validate_audit(complete_json(AUDIT_SYSTEM, user, max_tokens=24000, role="audit"))


def verify_citations(ch: dict, audit: dict) -> None:
    """Mark each flag, glossary entry and claim citation_ok only if the cited declaration exists
    and the cited line falls inside it."""
    for key, field in (("flags", "decl"), ("glossary", "decl"), ("lean_claims", "theorem")):
        for item in audit.get(key, []):
            item.update(validate_location(ch["decls"], item.get(field), item.get("line"), item.get("end_line")))


def trust_burden(ch: dict, audit: dict) -> dict:
    """Unique declaration lines await human review; an LLM cannot clear this burden."""
    spans = set()
    for d in ch["decls"]:
        for offset, line in enumerate(d["text"].splitlines()):
            if line.strip():
                spans.add(d["start_line"] + offset)
    return {
        "statement_lines": ch["nonblank_lines"],
        "lines_needing_human_review": len(spans),
        "human_reviewed": 0,
        "note": "all unique declaration lines await human review; model confidence only sets priority",
    }


# ---------------------------------------------------------------- Lean probes


def probe_for(ch: dict, repo: Path, target: dict, max_repairs: int = 2) -> dict:
    """Ask Sonnet for a Lean probe that bears on `target`; feed Lean's errors back up to `max_repairs` times."""
    src = (repo / ch["challenge_file"]).read_text()
    base = f"=== CHALLENGE FILE {ch['challenge_file']} ===\n{src}\n\n=== WHAT TO CHECK ===\n{json.dumps(target, ensure_ascii=False)}\n"
    system = ("Return JSON with kind, claim, proposition (one Lean Prop), proof (tactic body). "
              "Never emit declarations, commands, sorry, or new axioms. Use exact qualified names from the source. "
              "Preserve the proposition across repair attempts; only repair the proof. "
              "A non-vacuity check must construct a witness. A failed proof is inconclusive.")
    history, attempts, locked = "", [], None
    for attempt in range(max_repairs + 1):
        spec = complete_json(system, base + history, max_tokens=10000)
        proposed = spec["proposition"]
        if locked is None:
            locked = proposed
        if proposed != locked:
            attempts.append({"status": "YELLOW", "detail": "goal change refused; original proposition retained"})
        probe = build_probe(target.get("id", "probe"), repo, ch["challenge_file"],
                            spec.get("kind", "other"), spec.get("claim", ""), locked, spec["proof"])
        result = run_probe(probe)
        attempts.append(
            {"lean": probe.lean, "status": result.status, "detail": result.detail, "seconds": result.seconds}
        )
        if result.status != "YELLOW":
            break
        history += (
            f"\n=== ATTEMPT {attempt + 1} FAILED ===\n{probe.lean}\nLean said: {result.detail}\n"
            f"Keep this exact proposition: {locked}. Repair only the proof.\n"
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
    targets.insert(0,
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
    from .llm import REQUEST_TRACE
    trace_start = len(REQUEST_TRACE)
    ch, repo = load_challenge(stem)
    findings = [f for f in json.loads((DATA / "lint.json").read_text(encoding="utf-8"))
                if f["file"] == Path(ch["challenge_file"]).name and f["repo"] == ch["repo"]]
    print(f"[{stem}] audit", file=sys.stderr)
    audit = llm_audit(ch, repo, findings)
    source_text = (repo / ch["challenge_file"]).read_text(encoding="utf-8")
    source_lines = source_text.splitlines()
    snapshot_matches = all("\n".join(source_lines[d["start_line"] - 1:d["end_line"]]) == d["text"] for d in ch["decls"])
    verify_citations(ch, audit)
    for key in ("flags", "glossary", "lean_claims"):
        for item in audit.get(key, []):
            item["source_sha256"] = digest(source_text)
            item["location_valid"] = item["citation_ok"] = item["citation_ok"] and snapshot_matches
            if not snapshot_matches:
                item["citation_status"] = "stale_corpus_snapshot"

    probes, restatements = [], []
    if do_probes:
        seen = set()
        for target in probe_targets(audit)[:max_probes]:
            print(f"[{stem}] probe {target['id']}", file=sys.stderr)
            try:
                res = probe_for(ch, repo, target)
            except (ValueError, KeyError, RuntimeError) as exc:
                probes.append({"target": target, "result": {"status": "YELLOW", "kind": "other", "claim": "",
                                                           "detail": str(exc), "execution_status": "inconclusive"},
                               "attempts": [], "lean": ""})
                continue
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
        "schema_version": 2,
        "result": stem,
        "repo": ch["repo"],
        "challenge_file": ch["challenge_file"],
        "theorems": ch["theorem_names"],
        "lint": findings,
        "audit": audit,
        "probes": probes,
        "restatements": restatements,
        "trust_burden": trust_burden(ch, audit),
    }
    from .paths import ROOT
    from .llm import is_offline
    folder, manifest = new_run(ROOT, "single_file_audit", {"repo": ch["repo"], "file": ch["challenge_file"],
                                                         "source_sha256": digest((repo / ch["challenge_file"]).read_bytes())},
                               offline=is_offline())
    card["run_id"] = manifest["run_id"]
    card["probe_skipped_reason"] = "disabled or zero budget" if not do_probes or max_probes <= 0 else None
    manifest["requests"] = list(REQUEST_TRACE[trace_start:])
    manifest["actual_api_usd"] = sum(x.get("actual_api_usd", 0) for x in manifest["requests"])
    write_json(folder / "card.json", card)
    write_json(folder / "manifest.json", manifest)
    return card


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("stem", nargs="?", help="result name, e.g. D_NonSoficGroup")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--no-probes", action="store_true")
    ap.add_argument("--max-probes", type=int, default=4)
    ap.add_argument("--max-restate", type=int, default=3)
    ap.add_argument("--offline", action="store_true", help="refuse provider calls on cache miss (default)")
    ap.add_argument("--online", action="store_true", help="allow budget-limited provider calls")
    a = ap.parse_args()
    import os
    os.environ["APOLOGY_OFFLINE"] = "0" if a.online and not a.offline else "1"
    stems = list(_paper_map()["ranges"]) if a.all else [a.stem]
    for stem in stems:
        try:
            card = run(stem, not a.no_probes, a.max_probes, a.max_restate)
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
