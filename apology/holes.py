"""Definition-hole check.

Comparator treats every name in a config's `definition_names` as a *hole*: it checks
the solution's declaration has the right name and type, but NOT that its body matches
the body written in the challenge file. A community audit showed fake solutions
(defining things as `False`) passing for 3 results in OpenAI's October release.

For each hole we locate the solution module's declaration of the same fully-qualified
name and compare its data fields with the challenge file's, ignoring proof fields that
the challenge leaves as `sorry` (e.g. `disjoint := by sorry`).

Usage:
  python -m apology.holes                       # ten-proofs + Navier-Stokes -> data/holes.json
  python -m apology.holes ../oai-math/lean      # any repository; prints JSON
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from .paths import DATA, REPOS

DECL = re.compile(
    r"^(?:@\[[^\]]*\]\s*)?(?:(?:noncomputable|private|protected)\s+)*(?:def|abbrev|structure|instance)\s+(\S+)"
)


def scan(lines: list[str]) -> dict[str, list[int]]:
    """Map fully-qualified declaration name -> start line indices, tracking namespaces."""
    stack: list[str] = []
    found: dict[str, list[int]] = {}
    for i, l in enumerate(lines):
        m = re.match(r"^namespace\s+(\S+)", l)
        if m:
            stack.append(m.group(1))
            continue
        m = re.match(r"^end\s+(\S+)\s*$", l)
        if m and stack and stack[-1] == m.group(1):
            stack.pop()
            continue
        m = DECL.match(l)
        if m:
            full = ".".join(stack + [m.group(1)])
            found.setdefault(full, []).append(i)
    return found


def body(lines: list[str], start: int) -> list[str]:
    """Declaration text from `start` until the next top-level line, minus proof-only fields."""
    out = [lines[start]]
    for l in lines[start + 1 :]:
        if l and not l[0].isspace():
            break
        out.append(l)
    text = "\n".join(out)
    # drop proof fields of the form `<field> ... := by ...` (indented two spaces) and their continuation
    kept, skip = [], False
    for l in text.split("\n"):
        if re.match(r"^  \w[\w']*(\s+[\w'⟨⟩_]+)*\s*:=\s*by\b", l):
            skip = True
            continue
        if skip and (l.startswith("    ") or not l.strip()):
            continue
        skip = False
        kept.append(l)
    return [" ".join(k.split()) for k in kept if k.strip()]


def _shape(lines: list[str]) -> str:
    """The text with every identifier replaced by x: equal shapes differ only by renaming."""
    return re.sub(r"[A-Za-zα-ωΑ-Ω_][\w'₀-₉]*", "x", " ".join(lines))


def module_path(repo: Path, module: str) -> Path:
    return repo / (module.replace(".", "/") + ".lean")


def check_repo(repo: Path) -> list[dict]:
    rows = []
    for cfg_path in sorted((repo / "ComparatorChallenges").glob("*.json")):
        cfg = json.loads(cfg_path.read_text())
        holes = cfg.get("definition_names", [])
        if not holes:
            continue
        ch_lines = cfg_path.with_suffix(".lean").read_text().split("\n")
        sol_path = module_path(repo, cfg["solution_module"])
        sol_lines = sol_path.read_text().split("\n") if sol_path.exists() else []
        ch_idx, sol_idx = scan(ch_lines), scan(sol_lines)
        for name in holes:
            row = {"repo": repo.name, "config": cfg_path.name, "hole": name}
            if name not in ch_idx:
                row.update(status="NOT_IN_CHALLENGE")
            elif not sol_lines:
                row.update(status="SOLUTION_NOT_FOUND", detail=str(sol_path))
            elif name not in sol_idx:
                # the definition lives in a module the solution imports; we did not compare its body
                a = body(ch_lines, ch_idx[name][0])
                joined = " ".join(a)
                has = not re.search(r":=\s*(by\s+)?sorry\s*$", joined)
                row.update(
                    status="BODY_NOT_COMPARED" if has else "UNSPECIFIED_IN_CHALLENGE",
                    detail="solution defines it in an imported module (not fetched)"
                    if has
                    else "challenge leaves the body as sorry: the statement does not pin this definition down",
                )
            else:
                a = body(ch_lines, ch_idx[name][0])
                b = body(sol_lines, sol_idx[name][-1])
                joined = " ".join(a)
                ch_has_body = (
                    not re.search(r":=\s*(by\s+)?sorry\s*$", joined)
                    and not re.search(r"\bwhere\s*$", joined)
                    and not (len(a) <= 2 and any("sorry" in x for x in a))
                )
                if not ch_has_body:
                    row.update(
                        status="UNSPECIFIED_IN_CHALLENGE",
                        detail="challenge leaves the body as sorry: the statement does not pin this definition down",
                    )
                elif a == b:
                    row.update(status="MATCH", solution_line=sol_idx[name][-1] + 1)
                else:
                    diff = [(x, y) for x, y in zip(a, b, strict=False) if x != y][:3]
                    # identical up to identifier renaming? compare after erasing identifiers' spelling
                    status = "TEXT_DIFFERS_RENAMING_ONLY?" if _shape(a) == _shape(b) else "TEXT_DIFFERS"
                    row.update(status=status, solution_line=sol_idx[name][-1] + 1, first_differences=diff)
            rows.append(row)
    return rows


def main(argv: list[str]) -> None:
    repos = [Path(r) for r in argv[1:]] or list(REPOS.values())
    rows = [row for repo in repos for row in check_repo(repo)]
    for row in rows:
        print(f"[{row['status']:24}] {row['config']}: {row['hole']}", file=sys.stderr)
    text = json.dumps(rows, indent=1, ensure_ascii=False)
    if argv[1:]:
        print(text)
    else:
        (DATA / "holes.json").write_text(text)


if __name__ == "__main__":
    main(sys.argv)
