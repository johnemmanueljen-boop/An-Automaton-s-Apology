"""Parse Comparator challenge files into a structured corpus.

A Comparator challenge file holds a theorem's *statement* (plus every bespoke
definition it uses) with `sorry` proofs, importing only Mathlib. Comparator
checks that the real proof module proves exactly these statements. So the
challenge file is the full "trust surface": what a human must read to know
what was proved.

Usage:  python -m apology.corpus            # both repositories -> data/corpus.json
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .paths import DATA, REPOS

DECL_RE = re.compile(
    r"^(?P<indent>\s*)"
    r"(?P<mods>(?:@\[[^\]]*\]\s*)?(?:(?:noncomputable|private|protected|partial|unsafe)\s+)*)"
    r"(?P<kind>def|abbrev|structure|class|inductive|theorem|lemma|instance|opaque|axiom)\b"
    r"\s*(?P<name>[^\s:({\[]+)?"
)
NS_RE = re.compile(r"^\s*namespace\s+(\S+)")
END_RE = re.compile(r"^\s*end\b\s*(\S+)?")
SECTION_RE = re.compile(r"^\s*(noncomputable\s+)?section\b\s*(\S+)?")


@dataclass
class Decl:
    kind: str
    name: str  # fully qualified (best effort)
    short_name: str
    file: str
    start_line: int  # 1-based
    end_line: int
    text: str
    is_target_theorem: bool = False
    is_target_definition: bool = False

    @property
    def n_lines(self) -> int:
        return self.end_line - self.start_line + 1


@dataclass
class Challenge:
    repo: str
    challenge_file: str
    solution_module: str
    theorem_names: list[str]
    definition_names: list[str]
    permitted_axioms: list[str]
    total_lines: int
    nonblank_lines: int
    decls: list[Decl] = field(default_factory=list)


def _is_boundary(line: str) -> bool:
    s = line.strip()
    return bool(
        DECL_RE.match(line)
        or NS_RE.match(line)
        or END_RE.match(line)
        or SECTION_RE.match(line)
        or s.startswith(("open ", "export ", "variable", "universe", "set_option", "attribute ", "#", "mutual"))
        or s.startswith("/--")
    )


def comment_lines(lines: list[str]) -> set[int]:
    """Indices of lines that begin inside a /- ... -/ comment (nested comments allowed)."""
    inside, depth = set(), 0
    for i, line in enumerate(lines):
        if depth > 0:
            inside.add(i)
        depth += line.count("/-") - line.count("-/")
    return inside


def parse_file(path: Path) -> list[Decl]:
    lines = path.read_text().splitlines()
    in_comment = comment_lines(lines)
    scopes: list[tuple[str, str]] = []  # (kind, name)
    decls: list[Decl] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if i in in_comment:  # comment text such as "section of the ..." is not code
            i += 1
            continue
        if re.match(r"^\s*mutual\b", line):  # `mutual ... end` is not a scope
            scopes.append(("mutual", ""))
            i += 1
            continue
        m_ns = NS_RE.match(line)
        if m_ns:
            scopes.append(("namespace", m_ns.group(1)))
            i += 1
            continue
        m_sec = SECTION_RE.match(line)
        if m_sec and not DECL_RE.match(line):
            scopes.append(("section", m_sec.group(2) or ""))
            i += 1
            continue
        m_end = END_RE.match(line)
        if m_end and not DECL_RE.match(line):
            if scopes:
                scopes.pop()
            i += 1
            continue
        m = DECL_RE.match(line)
        if m and m.group("indent") == "":
            kind = m.group("kind")
            short = re.sub(r"\.(\{[^}]*\})?$", "", (m.group("name") or "").strip())  # drop a universe list `.{u}`
            if not short and i + 1 < len(lines) and kind != "instance":
                nxt = re.match(r"\s*([^\s:({\[]+)", lines[i + 1])
                short = nxt.group(1) if nxt else ""
            # a doc comment directly above belongs to this decl
            start = i
            if start > 0 and lines[start - 1].strip().endswith("-/"):
                j = start - 1
                while j >= 0 and "/--" not in lines[j]:
                    j -= 1
                if j >= 0:
                    start = j
            # body runs until the next top-level boundary
            j = i + 1
            while j < len(lines):
                if lines[j] and not lines[j][0].isspace() and _is_boundary(lines[j]):
                    break
                j += 1
            end = j - 1
            while end > i and not lines[end].strip():
                end -= 1
            ns = ".".join(n for k, n in scopes if k == "namespace" and n)
            if kind == "instance" and (not short or short.startswith(":")):
                short = "<anonymous instance>"
            full = f"{ns}.{short}" if ns and not short.startswith("<") else short
            decls.append(
                Decl(
                    kind=kind,
                    name=full,
                    short_name=short,
                    file=path.name,
                    start_line=start + 1,
                    end_line=end + 1,
                    text="\n".join(lines[start : end + 1]),
                )
            )
            i = end + 1
            continue
        i += 1
    return decls


def load_repo(repo_dir: Path) -> list[Challenge]:
    cdir = repo_dir / "ComparatorChallenges"
    out: list[Challenge] = []
    for cfg_path in sorted(cdir.glob("*.json")):
        cfg = json.loads(cfg_path.read_text())
        lean_path = cfg_path.with_suffix(".lean")
        text = lean_path.read_text()
        decls = parse_file(lean_path)
        thms, defs = set(cfg.get("theorem_names", [])), set(cfg.get("definition_names", []))
        for d in decls:
            d.is_target_theorem = d.name in thms
            d.is_target_definition = d.name in defs
        missing = (thms | defs) - {d.name for d in decls}
        if missing:
            print(f"warning: {lean_path.name}: not located by parser: {sorted(missing)}", file=sys.stderr)
        out.append(
            Challenge(
                repo=repo_dir.name,
                challenge_file=f"ComparatorChallenges/{lean_path.name}",
                solution_module=cfg.get("solution_module", ""),
                theorem_names=cfg.get("theorem_names", []),
                definition_names=cfg.get("definition_names", []),
                permitted_axioms=cfg.get("permitted_axioms", []),
                total_lines=len(text.splitlines()),
                nonblank_lines=sum(1 for l in text.splitlines() if l.strip()),
                decls=decls,
            )
        )
    return out


def main() -> None:
    data = []
    for repo_dir in REPOS.values():
        for challenge in load_repo(repo_dir):
            record = asdict(challenge)
            for d, decl in zip(record["decls"], challenge.decls, strict=True):
                d["n_lines"] = decl.n_lines
            data.append(record)
    (DATA / "corpus.json").write_text(json.dumps(data, indent=1, ensure_ascii=False))
    print(f"{len(data)} statement files -> data/corpus.json", file=sys.stderr)


if __name__ == "__main__":
    main()
