"""Lean-certified restatements: a clearer version of a statement that Lean proves means the same.

The AI proposes a more readable form of a theorem or definition (ideally in standard Mathlib terms).
We build the theorem and Lean must prove

    original ↔ restated      (same meaning, easier to read)
    original → corollary     (a simpler consequence)

These only unfold definitions, so they never need OpenAI's long proofs.

Why a CERTIFIED result can be trusted:
  * We write the original side, not the AI: OpenAI's theorem statement verbatim, or OpenAI's
    definition applied to all of its parameters. The AI supplies only the restated side and a proof.
  * Escape hatches (sorry, axioms, new definitions or instances, options, macros, attributes) are
    rejected before Lean runs, and the result may use only the three standard axioms.
  * The restated side may not mention the target, so "A ↔ A" cannot pass.

Usage:  python -m apology.restate data/examples/restate_demo.json   # hand-written specs, no AI
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .llm import complete_json
from .probes import Probe, run_probe
from .prompts import RESTATE_SYSTEM

FORBIDDEN = re.compile(
    r"\bsorry\b|\badmit\b|\baxiom\b|\bopaque\b|native_decide|\bdef\b|\babbrev\b|\binstance\b|\bstructure\b|"
    r"\bclass\b|\binductive\b|set_option|\bmacro\b|\bsyntax\b|\bnotation\b|\binfix|\bprefix\b|\bpostfix\b|"
    r"\battribute\b|@\[|\belab\b|run_cmd|run_tac|#eval|implemented_by|\bextern\b|\bunsafe\b|"
    r"\btheorem\b|\blemma\b|\bnamespace\b|\bsection\b|\bend\b|\bopen\b|\bvariable\b|\bexport\b|\bmutual\b"
)
BRACKETS = {"(": ")", "[": "]", "{": "}", "⦃": "⦄", "⟨": "⟩"}


@dataclass
class RestateSpec:
    target: str  # fully qualified Lean name (definition or theorem in the challenge file)
    mode: str  # "iff" (restatement) or "implies" (corollary)
    restated: str  # Lean proposition
    proof: str  # tactic proof (body after `by`)
    english: str = ""  # AI-written plain-English reading of `restated`
    why_clearer: str = ""


@dataclass
class RestateResult:
    target: str
    mode: str
    status: str  # CERTIFIED | REJECTED (guard) | FAILED (Lean did not accept)
    original_expr: str
    restated: str
    english: str
    mathlib_only: bool
    bespoke_used: list[str] = field(default_factory=list)
    detail: str = ""
    lean: str = ""
    seconds: float = 0.0


def split_theorem(decl_text: str, short_name: str) -> tuple[str, str]:
    """Return (binders, statement) of a theorem declaration."""
    header = re.search(rf"\b(?:theorem|lemma)\s+{re.escape(short_name)}(?=[\s:(\[{{])", decl_text)
    if header is None:
        raise ValueError("unsupported theorem header")
    i = header.end()
    body = decl_text[i:]
    end = body.rfind(":= by")
    if end < 0:
        end = body.rfind(":=")
    if end < 0:
        raise ValueError("theorem has no supported proof delimiter")
    body = body[:end]
    depth = 0
    for j, c in enumerate(body):
        if c in BRACKETS:
            depth += 1
        elif c in BRACKETS.values():
            depth -= 1
        elif c == ":" and depth == 0 and body[j : j + 2] != ":=":
            return body[:j].strip(), body[j + 1 :].strip()
    raise ValueError("no top-level ':' found in theorem")


def split_def(decl_text: str, short_name: str) -> tuple[str, str]:
    """Return (binders, type) of a def/abbrev/structure/class: text up to the first top-level
    `:=` or ` where`, split at the last top-level `:` (or type "Prop"/"Type" defaults)."""
    i = decl_text.find(short_name) + len(short_name)
    body = decl_text[i:]
    depth, stop, colon = 0, len(body), None
    for j, c in enumerate(body):
        if c in BRACKETS:
            depth += 1
        elif c in BRACKETS.values():
            depth -= 1
        elif depth == 0 and body.startswith(":=", j) or depth == 0 and re.match(r"\s(where|extends)\b", body[j:]):
            stop = j
            break
        elif depth == 0 and c == ":" and not body.startswith(":=", j):
            colon = j
    head = body[:stop]
    if colon is None or colon >= stop:
        raise ValueError("inferred definition types require Lean extraction; refusing to guess Prop")
    return head[:colon].strip(), head[colon + 1 :].strip()


def binder_args(binders: str) -> list[str]:
    """Explicit argument list for `@Target ...` from a binder string, '_' for anonymous instances."""
    args, depth, cur = [], 0, ""
    groups = []
    for c in binders:
        if c in BRACKETS and depth == 0:
            cur = c
            depth = 1
            continue
        if depth:
            if c in BRACKETS:
                depth += 1
            elif c in BRACKETS.values():
                depth -= 1
                if depth == 0:
                    groups.append(cur)
                    continue
            cur += c
    for g in groups:
        inner = g[1:]
        if ":" in inner:
            names = inner.split(":", 1)[0].split()
            args += names if names else ["_"]
        else:  # anonymous instance binder like [Group G]
            args.append("_")
    return args


def _namespace_of(decl: dict) -> str:
    return decl["name"][: -len(decl["short_name"]) - 1] if decl["name"] != decl["short_name"] else ""


def _file_opens(src: str) -> list[str]:
    return [l.strip() for l in src.splitlines() if re.match(r"^\s*open\b", l)]


def assemble(ch: dict, repo: Path, spec: RestateSpec, idx: int) -> tuple[str | None, str, str, list[str], str]:
    """Build the probe Lean code. Returns (lean or None, original_expr, check_decl, bespoke_used, reject_reason)."""
    decl = next((d for d in ch["decls"] if d["name"] == spec.target), None)
    if decl is None:
        return None, "", "", [], f"target {spec.target} not found in {ch['challenge_file']}"
    for part, label in ((spec.restated, "restated"), (spec.proof, "proof")):
        m = FORBIDDEN.search(part or "")
        if m:
            return None, "", "", [], f"guard: forbidden token {m.group(0)!r} in {label}"
    if spec.mode not in ("iff", "implies"):
        return None, "", "", [], "mode must be iff or implies"

    ns = _namespace_of(decl)
    source_text = (repo / ch["challenge_file"]).read_text(encoding="utf-8")
    if re.search(r"^\s*(?:variable|universe|include|omit)\b", source_text, re.M):
        return None, "", "", [], "section variables/universes require an elaborated target type; unsupported lexical reconstruction"
    if decl["kind"] in ("theorem", "lemma"):
        binders, stmt = split_theorem(decl["text"], decl["short_name"])
        original = f"∀ {binders}, {stmt}" if binders else stmt
        lhs_binders = ""
    else:
        # The original side is built by US from OpenAI's own definition header: the definition applied to
        # every one of its parameters, fully general. The AI cannot pick a special case.
        binders, typ = split_def(decl["text"], decl["short_name"])
        call = f"@{decl['short_name']} " + " ".join(binder_args(binders)) if binders else decl["short_name"]
        call = call.strip()
        if typ == "Prop":
            original = call
        elif typ == "Bool":
            original = f"{call} = true"
        else:
            if spec.mode != "iff":
                return None, "", "", [], f"guard: corollaries need a Prop/Bool-valued target (type is {typ})"
            original, typ = call, "term"
        lhs_binders = binders

    short_names = {d["short_name"] for d in ch["decls"] if not d["short_name"].startswith("<")}
    if re.search(rf"(?<![\w.]){re.escape(decl['short_name'])}(?![\w])", spec.restated):
        return None, original, "", [], "guard: restated side mentions the target itself (A ↔ A)"
    bespoke = sorted(n for n in short_names if re.search(rf"(?<![\w]){re.escape(n)}(?![\w])", spec.restated))

    name = f"probe_restate_{idx}"
    arrow = "↔" if spec.mode == "iff" else "→"
    if decl["kind"] not in ("theorem", "lemma") and typ == "term":
        arrow = "="  # value-valued definition: certify an equal, clearer formula
    proof = "\n".join("  " + l for l in spec.proof.strip().splitlines())
    opens = "\n".join(_file_opens((repo / ch["challenge_file"]).read_text()))
    lean = (
        (f"namespace {ns}\n" if ns else "")
        + (opens + "\n" if opens else "")
        + f"theorem {name} {lhs_binders} :\n    ({original}) {arrow}\n    ({spec.restated}) := by\n{proof}\n"
        + (f"end {ns}\n" if ns else "")
    )
    full = f"{ns}.{name}" if ns else name
    return lean, original, full, bespoke, ""


def certify(ch: dict, repo: Path, spec: RestateSpec, idx: int = 0) -> RestateResult:
    try:
        lean, original, check, bespoke, reason = assemble(ch, repo, spec, idx)
    except (ValueError, OSError) as exc:
        lean, original, check, bespoke, reason = None, "", "", [], str(exc)
    base = dict(
        target=spec.target,
        mode=spec.mode,
        original_expr=original,
        restated=spec.restated,
        english=spec.english,
        mathlib_only=False,
        bespoke_used=bespoke,
    )
    if lean is None:
        return RestateResult(status="REJECTED", detail=reason, **base)
    r = run_probe(
        Probe(
            id=f"restate-{idx}",
            repo_dir=str(repo),
            challenge_file=ch["challenge_file"],
            kind="restatement" if spec.mode == "iff" else "corollary",
            claim=spec.english,
            lean=lean,
            check_decls=[check],
        )
    )
    base["mathlib_only"] = not bespoke
    status = "CERTIFIED" if r.status == "GREEN" else "FAILED"
    return RestateResult(status=status, detail=r.detail, lean=lean, seconds=r.seconds, **base)


# ---------------------------------------------------------------- AI-proposed restatements


def llm_restate(
    ch: dict, repo: Path, target: str, mode: str = "iff", idx: int = 0, max_repairs: int = 2
) -> RestateResult:
    src = (repo / ch["challenge_file"]).read_text()
    base = f"=== CHALLENGE FILE {ch['challenge_file']} ===\n{src}\n\n=== TARGET ===\n{target}\n=== MODE ===\n{mode}\n"
    history, res = "", None
    locked = None
    for attempt in range(max_repairs + 1):
        js = complete_json(RESTATE_SYSTEM, base + history, max_tokens=10000)
        spec = RestateSpec(
            target=target,
            mode=js.get("mode", mode),
            restated=js["restated"],
            proof=js["proof"],
            english=js.get("english", ""),
            why_clearer=js.get("why_clearer", ""),
        )
        if locked is None:
            locked = (spec.mode, spec.restated)
        spec.mode, spec.restated = locked
        res = certify(ch, repo, spec, idx * 10 + attempt)
        if res.status == "CERTIFIED":
            return res
        history += f"\n=== ATTEMPT {attempt + 1}: {res.status} ===\nrestated: {spec.restated}\nproof:\n{spec.proof}\nreason: {res.detail}\nFix it.\n"
    return res


def main(path: str) -> None:
    from .audit import load_challenge

    specs = json.loads(Path(path).read_text())
    out = []
    for i, raw in enumerate(specs):
        stem = raw.pop("challenge")
        ch, repo = load_challenge(stem)
        r = certify(ch, repo, RestateSpec(**raw), i)
        print(
            f"[{r.status:9}] {r.target} ({r.seconds}s) mathlib_only={r.mathlib_only} {r.detail[:200]}", file=sys.stderr
        )
        out.append(asdict(r))
    json.dump(out, sys.stdout, indent=1, ensure_ascii=False)


if __name__ == "__main__":
    main(sys.argv[1])
