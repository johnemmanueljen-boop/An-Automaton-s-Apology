# Findings in OpenAI's releases

A finding here means *not covered by the formal verification*, or *a bookkeeping problem*. None of them
shows that an OpenAI theorem is false. Each entry gives the evidence file and how it was produced.

## 1. An error sat exactly where Lean wasn't checking (Taming implies compatibility)

- **What OpenAI corrected.** The original paper (September 23) claimed, as a corollary, an equality of
  cones K^t = K^c + H_J^- on every closed four-manifold, citing Li–Zhang. The corrected version
  (October 6) says equality holds only when h_J^- = b₂⁺ − 1, and gives a four-torus with strict inclusion.
- **What Lean covers.** Only the main theorem (taming implies compatibility). The corollary has no Lean statement.
- **Test 1, the pipeline (blind, original paper).** The main theorem was judged equivalent to its Lean
  statement. The cone corollary was marked *not formalized*. The claim OpenAI later corrected lay entirely
  in the part the pipeline marks "not formally verified".
- **Test 2, an AI referee (blind, original paper).** Asked to check each step of the corollary's proof,
  Opus called it sound and recalled the cited result as unconditional.
- **Contamination.** The correction was published on October 7, after the model's training cutoff (about
  June 2026). The prompts contain only the original text.
- **Why it matters.** Knowing exactly what Lean verified catches what an AI's opinion of the proof does not.
- Evidence: `results/findings/taming_retrospective*.json`. Of the 28 revised papers in the release, 3 have a
  formalization; only this one had a corrected claim.

## 2. Navier–Stokes Lemma 8.6: 5 extra derivatives, not 4 (reproduced)

- Given the Lean lemma and the paper's Lemma 8.6, the auditor flagged in one call that the Lean bound needs
  5 extra derivatives where the paper claims a loss of 4.
- First found by Bastounis, Circelli and Hansen ([arXiv 2610.08144](https://arxiv.org/abs/2610.08144)), over
  about two weeks. Their second, more cosmetic point (Lean bounds one derivative at a time, the paper a whole C^m norm) was not matched.
- Evidence: `results/validation/expert_case_ns_lemma_8_6.json`.

## 3. The Lean code cites an earlier draft of the paper (new, to our knowledge)

**Navier–Stokes.** The Lean docstrings cite 25 paper labels. Checked against the published paper
(`python -m apology.citations`, no AI):

| Status | Count | Labels |
|---|---|---|
| In the paper | 9 | e.g. Theorem 1.1, Lemma 4.4, Lemma 6.1 |
| Number used for another kind of statement | 10 | Lean "Lemma 8.3" is the paper's Proposition 8.3; Lean "Remark 8.6" is the paper's Lemma 8.6 |
| Number does not exist | 6 | Lemmas 3.5, 3.6, 3.7 (section 3 stops at 3.3); Lemma 11.3, Propositions 11.4, 11.7 (the paper ends at section 10) |

- 13 Lean files say they follow a "candidate manuscript" or "supplied manuscript".
- Spot checks of the 10 reused numbers show mostly different results (Lean "Remark 8.6" is about scaling;
  the paper's Lemma 8.6 is a Fourier-series bound). A blind content check of the labels that do exist found
  most point to different results too (Lean "Lemma 4.4" is published Theorem 4.6, eq. (4.29)).
- So the mathematics may well be in the paper, under other numbers; the citations are not a usable map
  from code to paper.
- Evidence: `results/findings/citations_navier_stokes.json`, `results/validation/blind_lemmas.json`.

**Unique Games / Max-Cut (October release).** Two random samples of 15 results each
(`experiments/citations_release.py`, seeds 2026 and 2027) found a second case: the code cites
Definition 4.6, Lemmas 6.3, 6.7, 6.8, Propositions 4.3, 6.9 and equation (6.25), none of which appear in
any of its 5 linked papers. The published Max-Cut paper's section 6 has only Lemma 6.1. Citations of
other papers were excluded by hand. Evidence: `results/findings/citations_ugc_maxcut.json`.

Across the 30 sampled results only 3 cite any paper label at all, so usually there is no map from code
to paper in the first place.

## 4. Coverage gaps (the code proves less than the paper's headline)

- **Non-sofic groups.** The paper proves a specific group is not sofic; Lean proves that *some* finitely
  presented group is not.
- **Permanent lower bounds.** The headline circuit bound is not formalized.
- **Hecke L-functions.** The Lean "L-function" is a custom construction of about 150 lines; nothing in the
  statement file shows it equals the standard one.

Evidence: `results/cards/`, `results/findings/hecke_l_function_audit.json`.

## 5. Whole-release checks (October release, no AI)

`python -m experiments.release_integrity` (output: `results/findings/release_integrity.txt`):

- 242 scope notes, 426 links to statement files, 416 statement files, 537 target theorems: no broken links,
  no unlinked files, every target theorem is declared in its file.
- 17 of 416 statement files run Lean metaprograms (`run_cmd` or `run_elab`), mostly resetting internal caches. Probably
  housekeeping, but these files are meant to be trusted by reading them.
- **Definition holes** (reproducing a community audit): OpenAI's checker compares some definitions only
  by name and type. 64 written-out definitions in 9 statement files are never compared with the solution's
  (`python -m apology.holes ../oai-math/lean`, `results/findings/definition_holes_oai_math.json`).

## 6. Fishing run: blind audits of 18 random October results

- 11 clean.
- 2 flags confirmed, both matching OpenAI's own scope notes (Ising perceptron: only finiteness formalized;
  tetrahedron covers: only the regular tetrahedron).
- 1 minor gap: explicit constants weakened to "there exist constants".
- 4 false alarms, all from auditing one statement file against one paper when the result spans several.
- OpenAI's October scope notes are candid about what is formalized.
- Evidence: `results/findings/fishing_audits.json` (raw), `results/findings/fishing_triage.json` (hand triage).
