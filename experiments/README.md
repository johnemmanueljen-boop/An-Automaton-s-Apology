# Experiments

Each script produces one result file. "Re-runs from cache" means running it again with no API key
reproduces the stored file exactly (checked before submission). All scripts run from the repository root
as modules, e.g. `python -m experiments.summarize`.

| Script | What it measures | Output | Re-runs from cache |
|---|---|---|---|
| `summarize.py` | Recomputes every headline number from the files below | printed | yes (no AI) |
| `benchmark_mutate.py` | Writes the planted-error files (needs Lean to keep only those that compile) | `data/heldout_mutants/` | yes (no AI; seed 2026, 4 per file) |
| `benchmark_evaluate.py cases` | Expert ground truth, Navier–Stokes Lemma 8.6 | `results/validation/expert_case_ns_lemma_8_6.json` | yes |
| `benchmark_evaluate.py mutants --batch --with-lint` | 49 planted errors Lean accepts | `results/validation/heldout_benchmark.json` | yes |
| `negative_control.py` | False flags on 12 textbook theorems | `results/validation/negative_control.json` | yes |
| `blind_lemmas.py --run` | Automatic Lean ↔ paper lemma pairing | `results/validation/blind_lemmas.json` | no: made with an earlier prompt* |
| `audit_external.py` | Audit any statement file against paper lines: quasi-RH, Taming, Hecke | `results/validation/expert_case_quasi_rh_*.json`, `results/findings/taming_retrospective_audit.json`, `hecke_l_function_audit.json` | quasi-RH (after rule) and Taming: yes; quasi-RH blind and Hecke: earlier prompt* |
| `card_external.py` | Full card (audit, probes, restatements) for any statement file | `results/cards_external/` | audit yes; probes need Lean |
| `citations_release.py` | Paper labels cited in random samples of the October release | `results/findings/citations_release_sample_seed*.json` | yes (no AI) |
| `release_integrity.py` | Links, files, targets and meta-code across the October release | `results/findings/release_integrity.txt` | yes (no AI) |
| `fishing_run.py` | Blind audits of randomly sampled October results | `results/findings/fishing_audits.json` | yes |

\* These answers are stored in the cache, but the prompt has since changed (the blind lemma prompt gained a
warning about the earlier draft *because* of this run; the audit prompt gained the "poles take convention
values" rule after the quasi-RH test). Re-running sends today's prompt and costs a few cents.

Not scripted: the AI-referee half of the Taming retrospective was a single ad-hoc call whose prompt was not
saved (its answer is in `results/findings/taming_retrospective_referee.json`). Triage of the fishing run and
of the Unique Games citations was done by hand (`fishing_triage.json`, `citations_ugc_maxcut.json`).
