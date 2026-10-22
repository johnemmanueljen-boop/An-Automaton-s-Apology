# An Automaton's Apology

**Lean checks the proof. We check the claim.**

AI labs now publish mathematics with "Lean-verified" code. Lean never makes mistakes, but it checks only
the exact statement written in the code. If a paper says *2 + 1 = 2* and the code says *2 + 0 = 2*, Lean
approves the code, and the paper's claim is still unchecked.

This project finds those places in OpenAI's formalized results and marks each one *not formally
verified yet*. That isn't the same as wrong: it means a human should look there.

- **For mathematicians:** a short list with the exact lines to check, instead of weeks of matching paper to code.
- **For AI labs:** a cheap audit before release.
- **The principle:** AI reads; Lean and plain code decide. Every AI claim is either checked by Lean, checked
  by code, or reported with its measured error rate.

Submission to the 2026 Open Scientific Intelligence Hackathon (mathematics). The name follows G. H. Hardy's
*A Mathematician's Apology*.

## Headlines

| | |
|---|---|
| **An error sat exactly where Lean wasn't checking** | OpenAI later corrected a claim about cones in *Taming implies compatibility*. Run blind on the original paper, the pipeline marked that claim "not formally verified": it was never in the Lean code. Asked to referee the same proof, the raw AI model called it sound. |
| **Re-found an expert gap in minutes, for cents** | Navier–Stokes Lemma 8.6: the Lean code needs 5 extra derivatives where the paper claims 4. Bastounis, Circelli and Hansen first found this over about two weeks. |
| **The code cites an earlier draft** | 16 of 25 paper labels cited in OpenAI's Navier–Stokes Lean files are not in the published paper (6 numbers don't exist at all, including a whole Section 11). A second formalization, Unique Games / Max-Cut, has the same problem. Found with no AI. |
| **Measured, not claimed** | 71% of 41 planted errors that Lean accepts were caught (78% with lint), with 2% false alarms. No false flags on 12 textbook theorems. 29 readable restatements proven equivalent by Lean. |
| **Whole-release checks, no AI** | All 242 scope notes, 426 links, 416 statement files and 537 target theorems of OpenAI's October release are consistent. 64 definitions in 9 files are never compared by OpenAI's checker. 17 statement files run metaprograms. |

None of this shows that any OpenAI theorem is false. Details: [docs/findings.md](docs/findings.md).

## How it works

| Step | Code | AI? | What it does |
|---|---|---|---|
| 1. Parse | `apology/corpus.py` | no | Reads OpenAI's statement files: the part of a result a human has to trust |
| 2. Lint | `apology/lint.py` | no | Flags Lean "junk values" (`x / 0 = 0`, `ζ(1)` finite, non-integrable `∫ = 0`), ℕ truncation, meta-code |
| 3. Audit | `apology/audit.py` | Opus | Reads the statement next to the paper: plain reading, paper-vs-Lean coverage, sticky notes with line numbers |
| 4. Check citations | `apology/audit.py` | no | Every line the AI cites must exist inside the declaration it names |
| 5. Probe | `apology/probes.py` | Sonnet writes | Small Lean checks (e.g. "this definition is satisfiable"); Lean decides |
| 6. Restate | `apology/restate.py` | Sonnet writes | Clearer versions that Lean must prove equivalent to OpenAI's statement |
| 7. Holes | `apology/holes.py` | no | Definitions OpenAI's checker compares only by name and type |
| 8. Citations | `apology/citations.py` | no | Paper labels cited in the code vs the published paper |

Every instruction the AI receives is in one file: [`apology/prompts.py`](apology/prompts.py).
Why a "certified" label can be trusted, and what it does not guarantee: [docs/trust.md](docs/trust.md).

## Results

All from blind or held-out tests; misses are reported. Method and caveats: [docs/validation.md](docs/validation.md).

| Test | Result |
|---|---|
| Expert case: Navier–Stokes Lemma 8.6 | Main gap found in one call (~US$0.05–0.09); the second, more cosmetic point missed (1 of 2) |
| Expert case: quasi-Riemann hypothesis (ζ pole at s = 1) | Opus flagged it blind, at low severity; Sonnet missed it |
| 41 planted errors that Lean accepts (held out) | 71% caught by the AI, 78% with lint; 2% false alarms (10% with lint) |
| By error type | assumptions 9/9 · quantifiers 10/12 · number types 3/4 · constants/goals 5/10 · definitions 2/6 |
| 12 textbook theorems, stated as in Mathlib | 0 false flags |
| Readable restatements | 29 of 37 proven equivalent by Lean; 22 of 25 Lean probes passed |

The main weakness: subtle boundary changes (`0 < x` vs `0 ≤ x`) are caught only about half the time.

## Try it

The implementation now includes versioned bundle audits and local review workflows. See
[implementation and validation](docs/implementation.md) for the changes, published examples, and integration limits.

Use a virtual environment for every Python command:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -B -X utf8 -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -B -X utf8 -m experiments.published_examples --build --run
.\.venv\Scripts\python.exe -m marimo run app.py
```

For Unix, use `.venv/bin/python`. The original commands below should likewise use the virtual environment's interpreter.

```sh
marimo run app.py                    # browse audit cards, validation and findings
python -m experiments.summarize      # recompute every number above from the stored results
```

Neither needs an API key or Lean. Every AI answer is cached in `.llm_cache/`, so re-running the
experiments costs nothing (see [experiments/README.md](experiments/README.md) for which ones re-run exactly).

To audit new results you need Lean, OpenAI's repositories and the paper text next to this folder
(layout in [`apology/paths.py`](apology/paths.py)):

```sh
curl -sSfL https://raw.githubusercontent.com/leanprover/elan/master/elan-init.sh | sh -s -- -y
git clone --depth 1 https://github.com/openai/ten-proofs ../ten-proofs
git clone --depth 1 https://github.com/openai/NavierStokesAndEuler ../NavierStokesAndEuler
(cd ../ten-proofs && lake exe cache get) && (cd ../NavierStokesAndEuler && lake exe cache get)
# papers: pdftotext -layout each paper into ../papers/ (ten.txt, ns-openai.txt, euler-openai.txt)
cp .env.example .env                 # add ANTHROPIC_API_KEY; LLM_BUDGET_USD caps spending

python -m apology.corpus && python -m apology.lint
python -m apology.audit D_NonSoficGroup
```

## Repository

```
apology/        the pipeline (steps 1-8 above) and the prompts
experiments/    how each number was measured: benchmark, controls, blind tests, release checks
data/           inputs: parsed statements, paper line map, planted errors, expert cases, controls
results/        outputs: audit cards, validation results, findings
docs/           findings, validation method, why to trust a label
app.py          Marimo app
```

## Limitations

- An AI flag is a reason to look, not a verdict. Publish one only after a human confirms it.
- Subtle boundary changes are the main weakness (about half caught).
- Few expert ground-truth cases exist yet: published audits of AI papers are only weeks old.
- Audits read one statement file against one paper excerpt. Results spread over several papers or files
  cause false "not formalized" flags (4 of 18 in the fishing run). Next step: audit whole results with all
  linked papers and scope notes.

## Credits and AI disclosure

**AI disclosure.** I designed and directed this project: the problem, the restatement idea, the validation
design (blind and held-out tests, negative controls) and the framing. The code and much of the analysis were
written with an AI coding assistant. The pipeline's AI steps use Claude Opus 5.5 (audits) and Claude
Sonnet 5.5 (writing Lean checks) through their API; the whole project cost about US$14 (`.llm_cache/ledger.jsonl`).

**Independence.** The models that audit OpenAI's work here come from another lab, so the design does not ask
you to trust them: every AI flag's accuracy is measured and its misses are reported, every certified
statement is checked by Lean, and the deterministic findings (citations, definition holes, release checks)
use no model at all. Only `apology/llm.py` talks to a model provider.

**Findings reproduced, with credit to the people who found them:**
[Navier–Stokes lost in translation](https://arxiv.org/abs/2610.08144) (Bastounis, Circelli, Hansen: Lemma 8.6) ·
[grwtsk/openai-math #14](https://github.com/grwtsk/openai-math/issues/14) (ζ pole) ·
[punk01-shaka/hadwiger-nelson-audit #1](https://github.com/punk01-shaka/hadwiger-nelson-audit/issues/1) (definition holes) ·
OpenAI's own correction of *Taming implies compatibility* (we only ran the retrospective test) ·
OpenAI's scope notes in openai/math (scope facts in the fishing run).

**Related work:** [Lean Atlas](https://arxiv.org/pdf/2604.16347) (the error taxonomy behind the benchmark) ·
[Beyond Compilation](https://arxiv.org/abs/2606.31002v1) ·
[BEq](https://proceedings.iclr.cc/paper_files/paper/2025/hash/d630537fc4402cfa3ebbc7450a0cac91-Abstract-Conference.html) ·
[Kallel](https://arxiv.org/pdf/2608.28997) · [ten-slops](https://github.com/Nemo-010/ten-slops).

**Data and tools:** openai/ten-proofs, openai/NavierStokesAndEuler and openai/math (Apache-2.0; read, not
redistributed, apart from short statement excerpts in results), Lean 4 and Mathlib (Apache-2.0), Marimo.

MIT licence.
