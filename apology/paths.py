"""Where things live.

The repository expects OpenAI's repositories and the papers' text next to it (override with
APOLOGY_WORKSPACE):

    workspace/
      an-automatons-apology/    this repository
      ten-proofs/               git clone https://github.com/openai/ten-proofs
      NavierStokesAndEuler/     git clone https://github.com/openai/NavierStokesAndEuler
      oai-math/                 git clone https://github.com/openai/math   (October release; optional)
      papers/                   pdftotext -layout output: ten.txt, ns-openai.txt, euler-openai.txt
"""

from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORKSPACE = Path(os.environ.get("APOLOGY_WORKSPACE", ROOT.parent)).resolve()

DATA = ROOT / "data"
RESULTS = ROOT / "results"
CARDS = RESULTS / "cards"
CACHE = ROOT / ".llm_cache"

PAPERS = WORKSPACE / "papers"
REPOS = {
    "ten-proofs": WORKSPACE / "ten-proofs",
    "NavierStokesAndEuler": WORKSPACE / "NavierStokesAndEuler",
}
OAI_MATH = WORKSPACE / "oai-math"
