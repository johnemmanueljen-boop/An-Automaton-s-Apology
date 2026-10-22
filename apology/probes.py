"""Lean probes: the AI (or a human) writes a small check, Lean decides.

A probe is Lean code appended to a copy of a statement file, so it can use every definition in it.

  GREEN   compiled, no `sorry`, and only the three standard axioms -> machine-checked evidence
  YELLOW  did not compile, or was rejected by the guard -> inconclusive, never counted as evidence
  Expected compiler failures are inconclusive, regardless of the historical RED/GREEN convention.

Guards reject known escape hatches; they are not an isolation boundary. Execution policy, process
status, target identity, and printed axiom evidence are checked separately. Live execution is disabled
by default. A checked formal expression does not establish correspondence to natural language.

Usage:  python -m apology.probes data/examples/probes_sofic.json
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .paths import REPOS
from .execution import LeanExecution, execute_lean
from .schema import contained_path, digest

STANDARD_AXIOMS = {"propext", "Classical.choice", "Quot.sound"}
FORBIDDEN = re.compile(
    r"\bsorry\b|\badmit\b|\baxiom\b|\bopaque\b|native_decide|\binstance\b|\battribute\b|@\[|set_option|"
    r"\bmacro\b|\bsyntax\b|\bnotation\b|\binfix|\belab\b|run_cmd|run_elab|run_tac|implemented_by|\bextern\b|\bunsafe\b|\blocal\b|"
    r"#|\bdef\b|\babbrev\b|\bopaque\b|\bclass\b|\bstructure\b|\binductive\b|\bimport\b|\bexample\b"
)


@dataclass
class Probe:
    id: str
    repo_dir: str  # repository with a built Mathlib (.lake)
    challenge_file: str  # statement file, relative to repo_dir
    kind: str  # non-vacuity | unit-test | mathlib-equivalence | junk-check | discrepancy | ...
    claim: str  # what a successful compile establishes, in plain English
    lean: str  # code to append; must declare every name in check_decls
    check_decls: list[str]  # declarations whose axioms are checked
    expect_fail: bool = False
    proposition: str = ""
    interpretation_status: str = "proposed"


@dataclass
class ProbeResult:
    id: str
    status: str  # GREEN | YELLOW | RED
    claim: str
    kind: str
    seconds: float
    detail: str
    axioms: dict[str, list[str]]
    execution_status: str = "inconclusive"
    evidence_kind: str = "none"
    execution: dict = field(default_factory=dict)
    source_sha256: str = ""
    artifact_sha256: str = ""
    interpretation_status: str = "proposed"


def lean_check(repo: Path, source: str, timeout: int = 120) -> LeanExecution:
    return execute_lean(repo, source, timeout)


def declared_theorems(source: str) -> list[str]:
    """Conservative wrapper validation; execution isolation remains a separate requirement."""
    names, scopes = [], []
    for line in source.splitlines():
        if match := re.match(r"^namespace\s+([\w.]+)\s*$", line):
            scopes.append(match[1])
        elif re.match(r"^end(?:\s+[\w.]+)?\s*$", line):
            if not scopes:
                raise ValueError("unbalanced namespace")
            scopes.pop()
        elif match := re.match(r"^\s*(?:theorem|lemma)\s+([\w.]+)\b", line):
            names.append(".".join(scopes + [match[1]]))
    if scopes:
        raise ValueError("unclosed namespace")
    return names


def build_probe(probe_id: str, repo: Path, challenge_file: str, kind: str, claim: str,
                proposition: str, proof: str) -> Probe:
    """The model supplies expressions; Python owns the theorem identity and wrapper."""
    forbidden = re.compile(FORBIDDEN.pattern + r"|\btheorem\b|\blemma\b|\bnamespace\b|\bend\b|\bsection\b|\bopen\b|\bvariable\b")
    if not proposition.strip() or not proof.strip() or forbidden.search(proposition + "\n" + proof):
        raise ValueError("invalid proposition or proof body")
    name = "probe_" + digest([probe_id, proposition])[:16]
    lean = f"theorem {name} : ({proposition}) := by\n" + "\n".join("  " + line for line in proof.splitlines()) + "\n"
    return Probe(probe_id, str(repo), challenge_file, kind, claim, lean, [name], proposition=proposition)


def _errors(output: str, probe_start: int) -> tuple[list[str], bool]:
    """Lean errors (with probe-relative line numbers) and whether the probe itself used `sorry`."""
    errors, used_sorry = [], False
    for m in re.finditer(r"^\S+?:(\d+):(\d+): (error|warning): (.*?)(?=^\S+?:\d+:\d+: |\Z)", output, re.M | re.S):
        line, severity, msg = int(m.group(1)), m.group(3), m.group(4).strip()
        if line < probe_start:
            if severity == "error":
                errors.append(f"(statement file line {line}) {msg[:300]}")
        elif severity == "error":
            errors.append(f"line {line - probe_start}: {msg[:400]}")
        elif "sorry" in msg:
            used_sorry = True
    return errors, used_sorry


def _axioms(output: str, decls: list[str]) -> dict[str, list[str]]:
    found = {}
    for d in decls:
        m = re.search(rf"'{re.escape(d)}' depends on axioms: \[(.*?)\]", output, re.S)
        if m:
            found[d] = [a.strip() for a in m.group(1).split(",") if a.strip()]
        elif re.search(rf"'{re.escape(d)}' does not depend on any axioms", output):
            found[d] = []
    return found


def run_probe(p: Probe, timeout: int = 120) -> ProbeResult:
    def result(status, detail, seconds=0.0, axioms=None):
        return ProbeResult(p.id, status, p.claim, p.kind, round(seconds, 1), detail, axioms or {})

    if m := FORBIDDEN.search(p.lean):
        return result("YELLOW", f"rejected by guard: forbidden construct {m.group(0)!r}")

    if (not p.check_decls or len(p.check_decls) != len(set(p.check_decls))
            or any(not re.fullmatch(r"(?:[\w]+\.)*probe_\w+", d) for d in p.check_decls)):
        return result("YELLOW", "expected nonempty unique generated probe theorem names")
    try:
        if sorted(declared_theorems(p.lean)) != sorted(p.check_decls):
            return result("YELLOW", "every checked theorem must be newly declared by the probe")
        repo = Path(p.repo_dir).resolve()
        statement = contained_path(repo, p.challenge_file).read_text(encoding="utf-8")
    except (OSError, ValueError) as exc:
        return result("YELLOW", str(exc))
    print_axioms = "\n".join(f"#print axioms {d}" for d in p.check_decls)
    source = f"{statement.rstrip()}\n\n-- ===== probe: {p.id} =====\n{p.lean.strip()}\n\n{print_axioms}\n"
    try:
        execution = lean_check(repo, source, timeout)
    except subprocess.TimeoutExpired:
        return result("YELLOW", "timed out", timeout)
    except OSError as exc:
        return result("YELLOW", str(exc))
    if not isinstance(execution, LeanExecution):
        return result("YELLOW", "missing structured process result")
    output, seconds = execution.output, execution.seconds

    errors, used_sorry = _errors(output, probe_start=statement.count("\n") + 3)
    axioms = _axioms(output, p.check_decls)
    bad_axioms = {d: extra for d, ax in axioms.items() if (extra := [a for a in ax if a not in STANDARD_AXIOMS])}
    compiled = (execution.returncode == 0 and not execution.timed_out and not errors and not used_sorry
                and not bad_axioms and len(axioms) == len(p.check_decls))

    if p.expect_fail:
        res = result("YELLOW", "expected-failure tests provide no mathematical evidence", seconds, axioms)
        res.execution = asdict(execution)
        res.source_sha256, res.artifact_sha256 = digest(statement), digest(source)
        return res
    if compiled:
        res = result("GREEN", "compiled; checked generated theorems; axioms clean", seconds, axioms)
        res.execution_status = "checked_under_execution_policy"
        res.evidence_kind = {"non-vacuity": "satisfiability_witness", "discrepancy": "separating_witness",
                             "restatement": "formal_equivalence", "corollary": "formal_implication"}.get(p.kind, "formal_theorem")
        res.execution = asdict(execution)
        res.source_sha256, res.artifact_sha256 = digest(statement), digest(source)
        res.interpretation_status = p.interpretation_status
        return res

    reasons = errors[:3]
    if used_sorry:
        reasons.append("probe uses sorry")
    if bad_axioms:
        reasons.append(f"non-standard axioms: {bad_axioms}")
    if (missing := set(p.check_decls) - set(axioms)) and not errors:
        reasons.append(f"declarations not found: {sorted(missing)}")
    if execution.returncode != 0:
        reasons.append(f"process exit={execution.returncode}: {execution.stderr[:300]}")
    res = result("YELLOW", " | ".join(reasons) or "inconclusive", seconds, axioms)
    res.execution = asdict(execution)
    res.source_sha256, res.artifact_sha256 = digest(statement), digest(source)
    return res


def main(path: str) -> None:
    results = []
    for raw in json.loads(Path(path).read_text()):
        raw["repo_dir"] = str(REPOS[raw.pop("repo")])
        r = run_probe(Probe(**raw))
        print(f"[{r.status:6}] {r.id} ({r.seconds}s): {r.detail}", file=sys.stderr)
        results.append(asdict(r))
    json.dump(results, sys.stdout, indent=1, ensure_ascii=False)


if __name__ == "__main__":
    main(sys.argv[1])
