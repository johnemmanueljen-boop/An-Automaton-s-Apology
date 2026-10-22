"""Lean probes: the AI (or a human) writes a small check, Lean decides.

A probe is Lean code appended to a copy of a statement file, so it can use every definition in it.

  GREEN   compiled, no `sorry`, and only the three standard axioms -> machine-checked evidence
  YELLOW  did not compile, or was rejected by the guard -> inconclusive, never counted as evidence
  RED     a probe marked `expect_fail` (a claimed counterexample) compiled anyway

Guards: anything that could fake a proof or change the meaning of OpenAI's definitions (`sorry`, new
axioms or instances, options, attributes, macros, meta-code) is rejected before Lean runs, and every
probe theorem's axioms are printed and checked afterwards.

Usage:  python -m apology.probes data/examples/probes_sofic.json
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from .paths import REPOS

ELAN_BIN = Path.home() / ".elan" / "bin"
STANDARD_AXIOMS = {"propext", "Classical.choice", "Quot.sound"}
FORBIDDEN = re.compile(
    r"\bsorry\b|\badmit\b|\baxiom\b|\bopaque\b|native_decide|\binstance\b|\battribute\b|@\[|set_option|"
    r"\bmacro\b|\bsyntax\b|\bnotation\b|\binfix|\belab\b|run_cmd|run_tac|implemented_by|\bextern\b|\bunsafe\b|\blocal\b"
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


@dataclass
class ProbeResult:
    id: str
    status: str  # GREEN | YELLOW | RED
    claim: str
    kind: str
    seconds: float
    detail: str
    axioms: dict[str, list[str]]


def lean_check(repo: Path, source: str, timeout: int = 900) -> tuple[str, float, int]:
    """Compile `source` inside `repo` with Lean; return (output, seconds, exit code). Raises on timeout."""
    env = dict(os.environ, PATH=f"{ELAN_BIN}:{os.environ.get('PATH', '')}")
    with tempfile.NamedTemporaryFile("w", suffix=".lean", dir=repo, prefix="_probe_", delete=False) as f:
        f.write(source)
        tmp = Path(f.name)
    started = time.time()
    try:
        proc = subprocess.run(
            ["lake", "env", "lean", str(tmp)], cwd=repo, env=env, capture_output=True, text=True, timeout=timeout
        )
    finally:
        tmp.unlink(missing_ok=True)
    return proc.stdout + proc.stderr, time.time() - started, proc.returncode


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


def run_probe(p: Probe, timeout: int = 900) -> ProbeResult:
    def result(status, detail, seconds=0.0, axioms=None):
        return ProbeResult(p.id, status, p.claim, p.kind, round(seconds, 1), detail, axioms or {})

    if m := FORBIDDEN.search(p.lean):
        return result("YELLOW", f"rejected by guard: forbidden construct {m.group(0)!r}")

    repo = Path(p.repo_dir).resolve()
    statement = (repo / p.challenge_file).read_text()
    print_axioms = "\n".join(f"#print axioms {d}" for d in p.check_decls)
    source = f"{statement.rstrip()}\n\n-- ===== probe: {p.id} =====\n{p.lean.strip()}\n\n{print_axioms}\n"
    try:
        output, seconds, exit_code = lean_check(repo, source, timeout)
    except subprocess.TimeoutExpired:
        return result("YELLOW", "timed out", timeout)

    errors, used_sorry = _errors(output, probe_start=statement.count("\n") + 3)
    axioms = _axioms(output, p.check_decls)
    bad_axioms = {d: extra for d, ax in axioms.items() if (extra := [a for a in ax if a not in STANDARD_AXIOMS])}
    # A pass needs Lean to exit cleanly and at least one named theorem with its axioms printed.
    checked = bool(p.check_decls) and len(axioms) == len(p.check_decls)
    compiled = exit_code == 0 and not errors and not used_sorry and not bad_axioms and checked

    if p.expect_fail:
        if compiled:
            return result("RED", "negative test compiled: the claimed counterexample exists", seconds, axioms)
        # Lean failing to prove something is not a proof of its negation.
        return result("YELLOW", "negative test did not compile: inconclusive", seconds, axioms)
    if compiled:
        return result("GREEN", "compiled; axioms clean", seconds, axioms)

    reasons = errors[:3]
    if used_sorry:
        reasons.append("probe uses sorry")
    if bad_axioms:
        reasons.append(f"non-standard axioms: {bad_axioms}")
    if (missing := set(p.check_decls) - set(axioms)) and not errors:
        reasons.append(f"declarations not found: {sorted(missing)}")
    if not p.check_decls:
        reasons.append("no theorem named to check")
    if exit_code != 0 and not errors:
        reasons.append(f"Lean exited with code {exit_code}")
    return result("YELLOW", " | ".join(reasons) or "did not compile", seconds, axioms)


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
