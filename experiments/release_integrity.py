"""Whole-release bookkeeping checks on OpenAI's October release (openai/math). No AI, no Lean.

  - every scope note (lean/docs/*.md) links statement files that exist, and every statement file is linked
  - every statement file has a config whose target theorems are declared in it
  - how many statement files run Lean metaprograms (the `meta-code` lint rule)

Usage:  python -m experiments.release_integrity
"""

from __future__ import annotations

import json
import re

from apology import lint as lintmod
from apology.corpus import parse_file
from apology.paths import OAI_MATH

LINK = re.compile(r"ComparatorChallenges/([A-Za-z0-9_]+)\.lean")
META = next(rx for rule, _, rx, _, _ in lintmod.COMPILED if rule == "meta-code")


def main() -> None:
    lean = OAI_MATH / "lean"
    notes = sorted((lean / "docs").glob("*.md"))
    statements = {p.stem: p for p in (lean / "ComparatorChallenges").glob("*.lean")}

    links = [(n.name, m.group(1)) for n in notes for m in LINK.finditer(n.read_text())]
    broken = sorted({f"{n} -> {s}" for n, s in links if s not in statements})
    unlinked = sorted(set(statements) - {s for _, s in links})

    targets, undeclared, meta = 0, [], []
    for stem, path in sorted(statements.items()):
        config = json.loads(path.with_suffix(".json").read_text())
        decls = parse_file(path)
        names = {d.name for d in decls}
        targets += len(config.get("theorem_names", []))
        undeclared += [f"{stem}: {t}" for t in config.get("theorem_names", []) if t not in names]
        if META.search(lintmod._strip_comments(path.read_text())):  # whole file: run_cmd sits outside declarations
            meta.append(stem)

    print(f"scope notes:            {len(notes)}")
    print(f"statement links:        {len(links)} ({len(broken)} broken)")
    print(f"statement files:        {len(statements)} ({len(unlinked)} not linked from any note)")
    print(f"target theorems:        {targets} ({len(undeclared)} not found in their statement file)")
    print(f"files with meta-code:   {len(meta)}: {', '.join(meta)}")
    for line in broken + unlinked + undeclared:
        print("  ", line)


if __name__ == "__main__":
    main()
