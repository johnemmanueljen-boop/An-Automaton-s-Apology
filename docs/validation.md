# How the auditor was tested

The auditor is an AI, so its output is only useful if we know how often it is right. Each test below says
what it measures, how contamination was avoided, and what it found, misses included.
`python -m experiments.summarize` recomputes every number here from the stored results.

## Contamination

- The papers, Lean code and published critiques all date from September–October 2026, after the models'
  training cutoff (about June 2026).
- Planted-error prompts are scanned for words that could give the answer away (`mutant`, `planted`,
  `injected`, ...). A pilot benchmark leaked a hint (a hypothesis named `h_mut`); it was discarded and
  the held-out set below was generated afterwards, avoiding the pilot's sites.
- For the blind lemma test, Lean lemmas were paired with paper lemmas by code, not by hand.

## 1. Expert ground truth

| Case | Found by | Result |
|---|---|---|
| Navier–Stokes Lemma 8.6 | Bastounis, Circelli, Hansen (about two weeks) | Main gap (5 vs 4 derivatives) found in one call; second, more cosmetic point missed: 1 of 2 |
| Quasi-Riemann hypothesis, ζ(1) | community audit, grwtsk/openai-math #14 | Opus flagged it blind at low severity; Sonnet missed it. After a general rule "functions with poles take convention values" was added to the prompt, Opus flagged it at medium (not blind) |

The Sonnet miss is why audits use Opus. For the Navier–Stokes case we supplied the right lemma–paper pair.
A flag counts as matching an expert item only if it contains all of that item's keyword groups
(`data/expert_cases/ns_lemma_8_6.json`).

## 2. Planted errors that Lean accepts (held out)

- **What:** 53 copies of OpenAI statement files, each with one planted error of the five kinds in the
  Lean Atlas taxonomy (wrong assumption, quantifier, number type, constant/goal, definition). 49 still
  compile, so Lean alone cannot catch them.
- **Excluded:** 8 that the author judged not to change the meaning (e.g. a cast Lean undoes); each with a
  reason in `results/validation/heldout_adjudicated.json`. 41 remain.
- **Caught:** a medium/high flag within 2 lines of the planted error. **False alarm:** the same rule on the
  unmutated file. Lint "catches" an error if a high-severity lint warning sits within 2 lines.

| | AI | AI + lint |
|---|---|---|
| Caught | 29/41 = 71% | 32/41 = 78% |
| False alarms on clean files | 1/41 = 2% | 4/41 = 10% |

By kind (AI): assumptions 9/9, quantifiers 10/12, number types 3/4, constants/goals 5/10, definitions 2/6.
Most misses are subtle boundary changes (`<` vs `≤`) and changed constants inside definitions.

## 3. Negative control: textbook theorems

12 textbook theorems (Lagrange, Fermat's little theorem, ...) stated exactly as Mathlib states them, each
proven identical to the Mathlib lemma, with names and docstrings stripped. **0 of 12** got a medium/high flag.

## 4. Lean-checked outputs

- **Restatements:** 29 of 37 attempted were proven equivalent to OpenAI's statement by Lean. The demo
  includes two deliberate cheats: a wrong restatement (Lean refused it) and a `sorry` (the guard refused it).
- **Probes:** 22 of 25 passed. A probe that fails is reported as inconclusive, never as evidence.

## 5. Blind lemma audit

7 Navier–Stokes Lean lemmas paired automatically with the paper lemma of the label they cite. Most pairs
turned out to be different results, which led to finding 3 in [findings.md](findings.md).

## Which experiments re-run exactly from the cache

See [experiments/README.md](../experiments/README.md). In short: everything above re-runs with no API key
except three runs made with an earlier prompt (the blind lemma audit, and the quasi-RH and Hecke audits from
before the pole rule); their answers are stored, but re-running them sends today's prompt.
