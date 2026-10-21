"""Recompute every headline number in the README from the stored results (no AI, no Lean).

Usage:  python -m experiments.summarize
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from apology.paths import DATA, RESULTS, ROOT
from experiments.benchmark_evaluate import lint_text

VALID, FIND = RESULTS / "validation", RESULTS / "findings"


def load(path: Path):
    return json.loads(path.read_text())


def lint_near(findings: list[dict], line: int) -> bool:
    """A high-severity lint warning within 2 lines of `line`."""
    return any(f["severity"] == "high" and abs(f["line"] - line) <= 2 for f in findings)


def benchmark() -> list[str]:
    rows = load(VALID / "heldout_benchmark.json")["rows"]
    excluded = load(VALID / "heldout_adjudicated.json")["equivalent_mutants_author_adjudicated"]
    manifest = {m["id"]: m for m in load(DATA / "heldout_mutants" / "manifest.json")}
    clean_lint = load(DATA / "lint.json")

    real = [r for r in rows if r["mutant"] not in excluded]
    caught_ai = caught_any = alarm_ai = alarm_any = 0
    by_kind = Counter()
    totals = Counter()
    clean_flags = load(VALID / "heldout_benchmark.json")["clean_flags"]
    for r in real:
        m = manifest[r["mutant"]]
        name = Path(m["challenge_file"]).name
        stem = Path(name).stem
        lint_hit = lint_near(lint_text(m["repo"], name, (ROOT / m["path"]).read_text()), m["line"])
        lint_alarm = lint_near([f for f in clean_lint if f["file"] == name and f["repo"] == m["repo"]], m["line"])
        ai_alarm = any(
            f.get("severity") in ("high", "medium") and abs(int(f.get("line") or -999) - m["line"]) <= 2
            for f in clean_flags[stem]
        )
        caught_ai += r["detected_strict"]
        caught_any += r["detected_strict"] or lint_hit
        alarm_ai += ai_alarm
        alarm_any += ai_alarm or lint_alarm
        by_kind[r["pattern"]] += r["detected_strict"]
        totals[r["pattern"]] += 1
    n = len(real)
    kinds = " · ".join(f"{k} {by_kind[k]}/{totals[k]}" for k in sorted(totals))
    return [
        f"Planted errors Lean accepts: {len(rows)} ({len(excluded)} judged meaning-preserving, {n} kept)",
        f"  caught by the AI:          {caught_ai}/{n} = {caught_ai / n:.0%}   (with lint {caught_any}/{n} = {caught_any / n:.0%})",
        f"  false alarms on clean files: {alarm_ai}/{n} = {alarm_ai / n:.0%}   (with lint {alarm_any}/{n} = {alarm_any / n:.0%})",
        f"  by error type (AI):        {kinds}",
    ]


def main() -> None:
    lines = ["== Validation"]
    case = load(VALID / "expert_case_ns_lemma_8_6.json")[0]
    found = sum(h["matched_flag"] is not None for h in case["hits"])
    lines.append(f"Expert case, Navier-Stokes Lemma 8.6: {found}/{len(case['hits'])} expert items found")
    for name in ("sonnet_blind", "opus_blind", "opus_after_rule"):
        flags = load(VALID / f"expert_case_quasi_rh_{name}.json")["audit"]["flags"]
        pole = [f["severity"] for f in flags if f["category"] == "junk-value"]
        lines.append(f"Expert case, quasi-RH zeta pole ({name}): {'flagged ' + pole[0] if pole else 'missed'}")
    lines += benchmark()
    nc = load(VALID / "negative_control.json")
    lines.append(f"Textbook theorems with Mathlib statements: {nc['with_medium_high']}/{nc['n']} false flags")

    cards = [load(p) for p in sorted((RESULTS / "cards").glob("*.json"))]
    rest = [r for c in cards for r in c["restatements"]]
    probes = [p for c in cards for p in c["probes"]]
    lines.append(
        f"Restatements certified by Lean: {sum(r['status'] == 'CERTIFIED' for r in rest)}/{len(rest)}; "
        f"Lean probes passed: {sum(p['result']['status'] == 'GREEN' for p in probes)}/{len(probes)}"
    )

    lines.append("\n== Findings")
    cit = load(FIND / "citations_navier_stokes.json")["summary"]
    lines.append(
        f"Navier-Stokes citations: {cit['not_in_paper']}/{cit['labels_cited']} labels not in the published paper "
        f"({cit['absent']} numbers absent, {cit['different_kind']} used for another kind of statement)"
    )
    holes = load(FIND / "definition_holes_oai_math.json")
    open_holes = [h for h in holes if h["status"] != "UNSPECIFIED_IN_CHALLENGE"]
    lines.append(
        f"Definition holes, October release: {len(open_holes)} written-out definitions in "
        f"{len({h['config'] for h in open_holes})} configs not compared by the checker "
        f"({dict(Counter(h['status'] for h in holes))})"
    )
    triage = load(FIND / "fishing_triage.json")
    lines.append(
        f"Fishing run: {triage['audited']} audits, {triage['clean']} clean, "
        f"{len(triage['confirmed_matches_openai_scope_note'])} match OpenAI's scope notes, "
        f"{len(triage['false_alarms_from_test_setup'])} false alarms from the one-file setup"
    )

    spent = sum(
        json.loads(x)["usd"] for x in (ROOT / ".llm_cache" / "ledger.jsonl").read_text().splitlines() if x.strip()
    )
    lines.append(f"\nTotal API spend (ledger): US${spent:.2f}")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
