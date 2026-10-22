# Bundle auditing and implementation validation

The updated tool supports versioned result bundles, strict evidence locations, exact bounded predicate checks, dependency-based review queues, and append-only human reviews. Historical results remain available through conservative display adapters. New runs write to separate `results/runs/<run_id>/` folders.

## Run in a virtual environment

On Windows, from the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -B -X utf8 -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -B -X utf8 -m experiments.verify
.\.venv\Scripts\python.exe -B -X utf8 -m experiments.published_examples --build --run
.\.venv\Scripts\python.exe -B -X utf8 -m experiments.ablate
.\.venv\Scripts\python.exe -B -X utf8 -m experiments.summarize
.\.venv\Scripts\python.exe -m marimo run app.py
```

On Unix, substitute `.venv/bin/python`. All non-UI tests and deterministic example commands use the standard library and run without installing provider or UI packages. Never use a base-environment pip for this project.

## Result manifests

Examples live in `data/bundles/`. Each manifest identifies papers, versions, attributed excerpts, formal artifacts, revisions, and SHA256 fingerprints. Claims list their paper spans and candidate formal targets. Scope notes are additional hashed sources. An absent sibling source or truncated context produces an incomplete-context state, preserving an unknown semantic relation.

```powershell
.\.venv\Scripts\python.exe -m apology.bundles data/bundles/atlas-section-1-division.json --offline
```

This performs deterministic inspection. Add `--model` to request an audit from the exact request cache; a cache miss is reported without making an API call. Add `--online` only when intentionally making budget-limited provider requests. Source text in a bundle is evidence, never authorization for model actions. Model-provided verification or human-review fields are discarded.

Version 2 audit cards validate exact declaration names and integer source positions, and record source fingerprints. A citation proves that a source location exists, not that it supports the model's interpretation. The legacy adapter labels historical citations and proof outputs as unvalidated/not rechecked.

## Published examples tested

| Example | Source | Actual test | Result |
| --- | --- | --- | --- |
| Typed division | [Lean Atlas](https://arxiv.org/html/2604.16347v1), section 1 | Adapted consequence `3 / 2 > 1`, with rational versus natural arithmetic | Separating input `x=3`; exact values `3/2` and `1` |
| Incorrect factorization | [Bastounis, Circelli and Hansen](https://arxiv.org/html/2610.08144v1), Example 2.1 | Compare signs of the stated cubic and the incorrect factorization at explicit rational samples | Separating input `x=0` |
| Navier–Stokes Lemma 8.6 | Same paper, Example 3.1; existing repository expert case | Bundle the supplied paper excerpt and formal context; preserve original expert credit and stored audit separately | Context inspection succeeds; no new model inference or Lean recheck |
| Endpoint and quantifier order | Explicitly synthetic | `x>0` versus `x>=0`; finite `forall/exists` swap | Expected separating cases found |

The paper examples were checked against published HTML during implementation. Their saved text is an attributed paraphrase or an already supplied expert-case excerpt, not a full independently downloaded paper transcript. The finite encodings are authored tests, not held-out research benchmarks. No precision, recall, or general accuracy improvement follows from these demonstrations.

`results/evaluation/published_examples.json` contains the exact bounded results. `component_ablation.json` compares the same synthetic bundle with and without its sibling artifact. The old 41-case baseline is retained separately. Its 2% figure concerns reused mutation sites; the component report also counts original files with any medium/high flag, without assuming those flags have been semantically adjudicated as false.

## Dependency and human review

`apology.dependencies` validates native graph exports and computes semantic review scopes. Type references and definition implementations remain relevant; theorem-proof-only references are excluded. Project axioms stay visible. Trusted imports, unresolved external declarations, missing source mappings, and recursive groups are explicit.

`apology.review` stores reviewer identity, rationale, compared paper spans, and a fingerprint of the semantic dependency closure and document context. Changing a shared definition, paper, or trusted-base context makes affected reviews stale. Model confidence does not accept a review item. The Marimo bundle view exposes the queue and a review submission form when a graph is attached. JSON and Markdown exports remain available for every run.

To attach a graph, add `dependency_graph` with `path`, `sha256` (canonical JSON fingerprint), and exact `targets` IDs to a bundle. See `lean/README.md` for extraction. General challenge/solution semantic equivalence remains unresolved unless suitable checked evidence is supplied; identical strings alone are not a cross-environment proof.

## Evidence and execution policies

Generated probes use Python-controlled theorem names and wrappers. Repair attempts retain the original proposition. Success requires a zero process exit, expected newly declared targets, and complete allowed-axiom evidence. Compiler rejection, timeouts, missing Lean, invalid wrappers, and an expected-failure test remain inconclusive.

Live Lean execution defaults to disabled. Configure the Docker policy described in `lean/README.md` for live generated inputs. A host-local policy is available only through `APOLOGY_LEAN_MODE=local` and `APOLOGY_TRUST_LOCAL_LEAN=1` for trusted fixtures. Neither policy establishes hostile-input proof assurance; exported-proof replay outside the generating process is still future work.

The legacy restatement path rejects inferred definition types and section/universe-variable reconstruction it cannot support. It still needs an elaborated reconstruction path for those cases. This explicit rejection prevents unsupported syntax from silently producing a supposedly authoritative original expression.

## Evaluation and remaining integration checks

The regression suite verifies malformed and ambiguous citations, execution failures, source hash mismatches, missing siblings, truncation, offline cache misses, typed arithmetic, quantifier order, graph reachability, shared-definition invalidation, and historical-result preservation. Mocked Lean process results test control flow; they are not Lean proofs.

The implementation verification record is in `results/evaluation/verification.json`. Rerun `experiments.verify` to produce a fresh immutable run and refresh the shareable record. This command refuses the base Python environment and records integration checks separately from regression successes.

`experiments.metrics` scores cases only with explicit human adjudication and reviewer identity. It reports flag precision, case recall, clean-case false alarms, abstentions, and source-group bootstrap intervals. It rejects variants of the same source split across development and test sets. Use `python -m experiments.ablate --adjudications PATH` for such a dataset. Independent model ablations and external ProofNetVerif/RLM25 evaluation require acquired datasets, toolchains, inference, and human labels; this implementation supplies the scoring infrastructure without inventing those results.

In this environment, dependency downloads were blocked, Lean was absent, and Docker's daemon was unavailable. Consequently, the Python workflow and published-example calculations were tested in `.venv`, but the Marimo runtime, native extractor compilation, and live proof checks remain unverified. No dependencies were installed into the base environment. A small expert review-time study is also still needed before claiming a human time saving.
