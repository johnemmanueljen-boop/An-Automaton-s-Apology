"""Static "Lean gotcha" linter for theorem statements and definitions.

Mathlib makes partial operations total by returning a *junk value* (usually 0)
outside their domain: x / 0 = 0, sInf ∅ = 0 in ℕ, log 0 = 0, a non-summable
series sums to 0, a non-integrable function integrates to 0, and so on. A
statement can therefore type-check, be proved, and still say something
different from the paper. These rules don't prove anything is wrong; they point
a human (or a Lean probe) at the exact spot that needs a second look.

Usage:  python -m apology.lint              # data/corpus.json -> data/lint.json
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import asdict, dataclass

from .paths import DATA

# (id, severity, regex, explanation, suggested probe)
RULES: list[tuple[str, str, str, str, str]] = [
    (
        "junk-sInf",
        "high",
        r"\bsInf\b|\bsSup\b|\biInf\b|\biSup\b|⨅|⨆",
        "sInf/sSup (and ⨅/⨆) return a junk value when the set is empty or unbounded "
        "(sInf ∅ = 0 in ℕ; sSup of an unbounded set in ℝ is 0).",
        "Prove the set is nonempty / bounded for the parameters the theorem talks about.",
    ),
    (
        "junk-div",
        "medium",
        r"(?<![/-])/(?![/-])",
        "Division by zero is defined as 0; in ℕ and ℤ division also truncates.",
        "Check every denominator is provably nonzero (and in the intended type).",
    ),
    (
        "int-literal-div",
        "high",
        r"\(\s*\d+\s*:\s*[ℕℤ]\s*\)\s*/|/\s*\(\s*\d+\s*:\s*[ℕℤ]\s*\)",
        "Division of an explicit ℕ/ℤ literal truncates: (3 : ℕ) / 2 = 1 and (1 : ℕ) / 2 = 0, even inside a real-valued expression.",
        "Check the literal is meant to be an integer; otherwise cast to ℝ before dividing.",
    ),
    (
        "nat-sub",
        "medium",
        r"(?<![<>=←-])\s-\s(?![>-])",
        "Subtraction in ℕ truncates at 0 (2 - 5 = 0).",
        "Confirm the operands are not ℕ, or that the left side is ≥ the right.",
    ),
    (
        "junk-log",
        "medium",
        r"Real\.log\b|\blog\b",
        "Real.log 0 = 0 and Real.log (-x) = Real.log x, so bounds involving log can hold vacuously at small arguments.",
        "Check the arguments of log are > 1 (or > 0) in the range the theorem quantifies over.",
    ),
    (
        "junk-sqrt",
        "low",
        r"Real\.sqrt\b|√",
        "Real.sqrt of a negative number is 0.",
        "Check the radicand is nonnegative.",
    ),
    (
        "junk-rpow",
        "low",
        r"\^\s*\(\s*\(?\s*[0-9]+\s*:\s*ℝ\s*\)?\s*/|\^\s*\(\(1",
        "Real powers x ^ (r : ℝ) give junk values for x < 0 (and 0 ^ 0 = 1).",
        "Check the base is nonnegative.",
    ),
    (
        "meta-code",
        "high",
        r"\brun_cmd\b|\brun_tac\b|\bmodifyEnv\b|\belab\b|\bmacro\b|implemented_by|\bextern\b|\bunsafe\b|set_option (?!autoImplicit false|relaxedAutoImplicit false|maxHeartbeats|maxRecDepth|linter\.)",
        "Metaprogramming or option changes inside a statement file: code here can alter how Lean elaborates or what the environment contains, so the statement cannot be trusted by reading alone.",
        "Read what the command does; confirm it cannot change the meaning of any target statement.",
    ),
    (
        "junk-pole",
        "medium",
        r"riemannZeta|hurwitzZeta|LSeries|LFunction|Complex\.Gamma|Real\.Gamma|\bGamma\b|Gammaℝ|Gammaℂ|digamma",
        "Functions with poles are totalized in Mathlib (riemannZeta 1 is a finite convention value; Gamma is 0 at non-positive integers). A statement over a region containing a pole makes a claim about a convention value.",
        "Check whether the hypotheses exclude the pole (e.g. s ≠ 1), and whether the paper excludes or allows it.",
    ),
    (
        "junk-tsum",
        "high",
        r"∑'|\btsum\b",
        "An infinite sum (∑') of a non-summable family is defined as 0.",
        "Prove Summable for the family, or check the statement includes it.",
    ),
    (
        "junk-integral",
        "high",
        r"∫|\bintegral\b|MeasureTheory\.integral",
        "The Bochner integral of a non-integrable function is 0.",
        "Prove Integrable, or check the statement includes it as a hypothesis/conclusion.",
    ),
    (
        "junk-deriv",
        "high",
        r"\bderiv\b|\bfderiv\b|\biteratedDeriv\b|\biteratedFDeriv\b|lineDeriv",
        "deriv/fderiv of a non-differentiable function is 0.",
        "Check differentiability is asserted (e.g. ContDiff / Differentiable) wherever the derivative is used.",
    ),
    (
        "junk-lim",
        "high",
        r"\blimUnder\b|\blim\b",
        "limUnder of a non-convergent sequence is an arbitrary junk value.",
        "Check convergence is asserted separately.",
    ),
    (
        "toNat-trunc",
        "medium",
        r"\.toNat\b|Int\.toNat|⌊|⌈|Nat\.floor|Nat\.ceil",
        "toNat / floor / ceil into ℕ truncate negatives to 0.",
        "Check the argument is nonnegative.",
    ),
    (
        "classical-choose",
        "medium",
        r"Classical\.choose\b|Classical\.epsilon\b|Function\.invFun\b|Exists\.choose\b",
        "Classical.choose / invFun pick an arbitrary witness; if existence fails the value is junk.",
        "Check existence is proved where the definition is used.",
    ),
    (
        "decide-prop",
        "low",
        r"Classical\.propDecidable|@decide",
        "A Prop is turned into a Bool classically; fine logically, but the definition is not computable and can't be unit-tested by #eval.",
        "Unit-test the Prop version instead.",
    ),
    (
        "vacuous-def",
        "high",
        r":=\s*True\b|:\s*Prop\s*:=\s*True|=>\s*True\b",
        "A definition or field that is literally True makes everything depending on it vacuous.",
        "Check this was intended.",
    ),
    (
        "extended-arith",
        "medium",
        r"ENNReal|ℝ≥0∞|ENat|ℕ∞|EReal",
        "Extended number types have ⊤ (infinity); ⊤ - ⊤ = 0 and ⊤ * 0 = 0, and an inequality can hold because a side is ⊤.",
        "Check finiteness where it matters.",
    ),
    (
        "card-zero",
        "medium",
        r"Fintype\.card|Nat\.card|Finset\.card|\.card\b|Cardinal",
        "Nat.card of an infinite type is 0; dividing by a cardinality that can be 0 gives 0.",
        "Check finiteness / nonemptiness.",
    ),
    (
        "eventually",
        "low",
        r"∀ᶠ|∃ᶠ|=O\[|=o\[|=Θ\[|Tendsto|atTop",
        "Asymptotic statements: check the filter and direction match the paper (e.g. 'for all large k' vs 'for all k ≥ 2').",
        "Compare with the paper's quantifier carefully.",
    ),
    (
        "hypothesis-in-structure",
        "low",
        r"^\s+\w+\s*:\s*.*(?:<|≤|≠|∀|∃).*$",
        "A Prop field inside a structure is an assumption baked into the definition; easy to miss when reading the theorem.",
        "List these as hidden hypotheses on the audit card.",
    ),
]

COMPILED = [(rid, sev, re.compile(rx, re.M), expl, probe) for rid, sev, rx, expl, probe in RULES]
SEV_ORDER = {"high": 0, "medium": 1, "low": 2}


@dataclass
class Finding:
    rule: str
    severity: str
    repo: str
    file: str
    decl: str
    decl_kind: str
    line: int
    snippet: str
    explanation: str
    suggested_probe: str


def _strip_comments(text: str) -> str:
    text = re.sub(r"/-.*?-/", lambda m: re.sub(r"[^\n]", " ", m.group(0)), text, flags=re.S)
    return re.sub(r"--[^\n]*", lambda m: " " * len(m.group(0)), text)


def lint_decl(repo: str, decl: dict) -> list[Finding]:
    out: list[Finding] = []
    body = _strip_comments(decl["text"])
    lines = body.splitlines()
    for rid, sev, rx, expl, probe in COMPILED:
        if rid == "hypothesis-in-structure" and decl["kind"] not in ("structure", "class"):
            continue
        seen_lines: set[int] = set()
        for m in rx.finditer(body):
            ln = body.count("\n", 0, m.start())
            if ln in seen_lines:
                continue
            seen_lines.add(ln)
            if rid == "nat-sub" and re.search(r"\(\s*\w+\s*:\s*ℝ\s*\)|ℝ", lines[ln]):
                continue  # clearly real-valued line
            out.append(
                Finding(
                    rule=rid,
                    severity=sev,
                    repo=repo,
                    file=decl["file"],
                    decl=decl["name"],
                    decl_kind=decl["kind"],
                    line=decl["start_line"] + ln,
                    snippet=lines[ln].strip()[:160],
                    explanation=expl,
                    suggested_probe=probe,
                )
            )
    return out


def main() -> None:
    findings: list[Finding] = []
    for ch in json.loads((DATA / "corpus.json").read_text()):
        for d in ch["decls"]:
            findings.extend(lint_decl(ch["repo"], d))
    findings.sort(key=lambda f: (f.repo, f.file, SEV_ORDER[f.severity], f.line))
    (DATA / "lint.json").write_text(json.dumps([asdict(f) for f in findings], indent=1, ensure_ascii=False))
    print(f"{len(findings)} findings -> data/lint.json", file=sys.stderr)


if __name__ == "__main__":
    main()
