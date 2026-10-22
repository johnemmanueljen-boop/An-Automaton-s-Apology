# An Automaton's Apology implementation handoff

Prepared 22 October 2026 for an implementation model.

## Recommended direction

Develop the existing auditor into a reproducible review workflow for an entire mathematical result: collect its papers and formal artifacts, identify the definitions that affect its claims, produce precise discrepancy evidence, and let a human record the final semantic judgment.

Keep the Python pipeline, Marimo app, cached experiments, and Lean probes. The strongest hackathon contribution is an auditable connection between a paper claim and the exact formal statement and definitions supporting it. A reviewer should be able to answer: **What was claimed, what was formalized, what differs, and what evidence supports that assessment?**

Implement in this order:

1. Repair evidence-validation and probe-status edge cases.
2. Audit bundles containing all artifacts for a result, addressing known false coverage alarms.
3. Add Lean-extracted dependency information and a focused review queue.
4. Add targeted checks for boundaries, hidden assumptions, and definition bodies.
5. Evaluate each addition separately and present a reproducible demonstration.

This is an implementation plan, not a claim that these changes have been implemented or their benefits measured.

## Review scope and starting point

Repository: [johnemmanueljen-boop/An-Automaton-s-Apology](https://github.com/johnemmanueljen-boop/An-Automaton-s-Apology).

The initial review inspected public web versions on `main`. A subsequent local review checked the clone at `An-Automaton-s-Apology/`, commit `5bea176b4dd418e420bcdfc490d33944a4aabd47`, with a clean worktree. The citation, probe-status, and definition-field issues described below are present in that checkout. The local source and stored results confirm the planned priorities; no architectural change to this plan was needed.

Local verification: `python -B -X utf8 -m experiments.summarize` completed successfully and reproduced the headline counts from stored artifacts, including 29/41 model detections, 32/41 with lint, 1/41 and 4/41 false alarms under the existing metric, 29/37 restatements, and 22/25 probes. This checks aggregation and the script's deterministic lint recomputation; it does not rerun model inference, independently adjudicate labels, or recheck the stored Lean proofs. The Marimo interface and live Lean integration were not executed. Recheck the checkout SHA before implementation if the repository changes.

Existing strengths to retain:

- Separate deterministic checks, model judgments, Lean evidence, and human interpretation.
- Preserve audit cards, readable restatements, expert cases, planted errors, negative controls, and request caching.
- Keep prompts centralized and keep provider calls behind `apology/llm.py`.
- Preserve the distinction between a formalization discrepancy and a false mathematical theorem.

The project already cites Lean Atlas and uses its taxonomy. The opportunity is to implement additional mechanisms and improve measurement, rather than simply add the citation again. The baseline counts above reproduce from the stored results, while their underlying model judgments and mathematical evidence still require the validation described in this plan. [Validation methodology](https://github.com/johnemmanueljen-boop/An-Automaton-s-Apology/blob/main/docs/validation.md)

## Research to use

| Source | Relevant finding or method | Proposed application |
| --- | --- | --- |
| [Lean Atlas, Yanahama and Sannai, arXiv 2604.16347](https://arxiv.org/pdf/2604.16347), especially sections 3–6 | Lean Compass distinguishes type dependencies from value dependencies. It removes edges originating in theorem proofs while retaining definition implementations, then computes reachability from selected targets and includes axioms. Semantic correctness still requires human review. | Extract dependencies from Lean, expose why each definition matters, and track review explicitly. |
| [Rethinking and Improving Autoformalization, Liu et al., ICLR 2025](https://proceedings.iclr.cc/paper_files/paper/2025/hash/d630537fc4402cfa3ebbc7450a0cac91-Abstract-Conference.html) | BEq evaluates formal statements through bidirectional checks; dependency retrieval supplies relevant formal context. | Retrieve exact definitions and library context before judging a mismatch. Preserve the direction and evidence of each formal comparison. |
| [Reliable Evaluation and Benchmarks for Statement Autoformalization, Poiroux et al., EMNLP 2025](https://aclanthology.org/2025.emnlp-main.907/) | BEq+ provides a deterministic formal-reference metric; ProofNetVerif supplies human labels; ProofNet# corrects benchmark errors; RLM25 addresses research-level context. | Use a small external evaluation set, stronger adjudication, and reference-based checks where a trusted formal reference exists. |
| [Beyond Compilation, Zhang et al., version 2](https://arxiv.org/html/2606.31002v2) | Compilation and semantic faithfulness diverge. Human-calibrated model consensus can be useful as an aggregate measure, but is not an equivalence oracle. | Report proof execution and semantic assessment separately. Evaluate an optional second judge only after measuring the simpler pipeline. |
| [Lean documentation on validating proofs](https://lean-lang.org/doc/reference/latest/ValidatingProofs/) | Axiom checks, execution trust, statement identity, and the correctness of referenced definitions are separate concerns. Stronger validation isolates potentially malicious code and rechecks exported proofs. | Make evidence validation fail closed and state the execution assumptions behind a certificate. |

Important adaptation: Comparator challenge files already remove most proof bodies. My expectation is that their additional dependency reduction will be smaller than on full solution projects. Measure it against the current challenge-file workflow. The Atlas paper measures node reduction, not human review time, so do not translate its results into a claimed time saving for this project.

## Concrete issues visible in the current code

These are source-inspection findings. Add regression cases before fixing them; a runtime exploit or measured failure rate has not been established here.

| Priority | Location | Observation and consequence |
| --- | --- | --- |
| P0 | `apology/audit.py::verify_citations` | A known declaration with a missing or non-integer line can receive `citation_ok=True`. Short-name fallback can also resolve ambiguously. Evidence location needs strict validation. |
| P0 | `apology/probes.py::lean_check`, `run_probe` | The subprocess return code is discarded. An empty `check_decls` list can satisfy the evidence-count condition without checking a theorem. |
| P0 | `apology/probes.py::run_probe` | In the `expect_fail` branch, compilation failure becomes GREEN. Failure to prove a statement is not evidence of its negation. |
| P0 | `app.py` | Missing `citation_ok` defaults to a checked citation. Coverage judgments also use green labels that need an explicit evidence category. |
| P0 | `apology/audit.py::trust_burden` | Model-generated `matches_standard=yes` can remove a definition from the displayed human-review burden. This is prioritization, not human verification. |
| P1 | `apology/audit.py::sibling_note`, `paper_excerpt` | Sibling handling supplies names, not the sibling statements or all papers and scope notes. This cannot establish complete coverage. |
| P1 | `apology/audit.py::load_challenge`, `run`; card filenames | Identity and some filtering use only a stem or basename. Different repositories can have colliding names. |
| P1 | `apology/audit.py::probe_targets`, `run` | The non-vacuity probe is appended last and then the list is truncated. The documented always-present check can be skipped. |
| P1 | `apology/holes.py::body` | Fields assigned using `by` are discarded syntactically. A data-valued field can also be constructed by tactics, so this is not a reliable proof-field test. |
| P1 | `experiments/benchmark_evaluate.py::flag_hits`, `false_alarms` | Line proximity can count an unrelated flag as a detection. False alarms are counted at mutation sites on reused original files, not across independent clean files. |

Source links: [audit.py](https://github.com/johnemmanueljen-boop/An-Automaton-s-Apology/blob/main/apology/audit.py), [probes.py](https://github.com/johnemmanueljen-boop/An-Automaton-s-Apology/blob/main/apology/probes.py), [app.py](https://github.com/johnemmanueljen-boop/An-Automaton-s-Apology/blob/main/app.py), [holes.py](https://github.com/johnemmanueljen-boop/An-Automaton-s-Apology/blob/main/apology/holes.py), [benchmark_evaluate.py](https://github.com/johnemmanueljen-boop/An-Automaton-s-Apology/blob/main/experiments/benchmark_evaluate.py).

## Phase 0 Make evidence labels reliable

Modify `audit.py`, `probes.py`, `restate.py`, `app.py`, and `docs/trust.md`. Introduce a small `apology/schema.py` or equivalent shared validation module. Use the existing dependency style; a large framework is unnecessary.

### Citation validation

Require a unique, fully qualified declaration identity, matching source snapshot, and integer source span contained within the declaration. Use `type(line) is int` so Python booleans do not qualify. Reject nulls, strings, out-of-range values, and ambiguous short names. If an old card cannot satisfy the new contract, show `legacy_unvalidated`.

Keep two fields separate:

- `location_valid`: the cited source exists at the recorded position.
- `supports_claim`: `unreviewed`, `supported`, `unsupported`, or `uncertain`.

A valid location does not establish that the text supports the model's explanation. Paper citations need document identity, version, page where available, text span, and content hash as well as a theorem label.

### Probe validation

Return structured execution data: exit code, stdout, stderr, timeout state, duration, and checked declarations. Require successful exit, no relevant errors, a nonempty unique set of expected newly created theorem names, and complete axiom evidence within the configured allowlist. Missing diagnostics or axiom evidence must produce `inconclusive`, never success.

Generate theorem names and wrappers in trusted code. Let the model propose a proposition and proof body; do not let it select an unrelated pre-existing theorem as the evidence target. Preserve the requested proposition across repair attempts and record any deliberate change as a new probe.

Remove mathematical success from `expect_fail`. A compiler rejection can satisfy an implementation regression test, but its mathematical outcome remains inconclusive. To establish a discrepancy, prove a positive witness such as `FormalPredicate x ∧ ¬ IntendedPredicate x` for explicitly identified predicates.

Separate `execution_status` from `evidence_kind`. A successful non-vacuity check, a proved implication, a proved equivalence, and a proved counterexample establish different facts. None alone establishes that a natural-language paper was faithfully translated.

Reserve a non-vacuity slot when the probe budget permits; expose a skipped reason otherwise. Use `os.pathsep` for PATH construction and catch missing executable errors. The current runner uses a Unix separator, relevant to this Windows workspace.

### Execution trust

The current regex guards and parsed console output should not be described as a sandbox. Generated tactics and imported statement files execute Lean code. For live runs use a disposable environment without provider credentials, network access, or writable original repositories, with resource limits. If this environment is unavailable, ship a cached demo and disable arbitrary live probes in that mode.

For hostile-input assurance, a later phase must recheck exported proof artifacts and statement identity outside the generating process, following Lean's validation guidance. A container limits filesystem access; it does not by itself prevent forged certificate output. Keep that stronger guarantee out of hackathon claims until implemented. [Lean proof validation](https://lean-lang.org/doc/reference/latest/ValidatingProofs/)

### Acceptance cases

- Missing/string/bool/out-of-range citation and duplicate short names never appear checked.
- A nonzero process exit with unrecognized output is inconclusive.
- Empty, duplicate, missing, or pre-existing-only proof targets cannot establish success.
- `sorryAx`, unexpected axioms, timeout, and missing Lean produce no mathematical certificate.
- An expected compiler failure never counts as a proved counterexample.
- Existing valid fixtures retain their precise evidence type; historical files remain unchanged.

## Phase 1 Audit a complete result bundle

Create `apology/bundles.py` and versioned manifests under `data/bundles/`. Adapt `audit.py`, `paths.py`, and `prompts.py`; retain an adapter for existing `paper_map.json` and audit cards.

The repository's fishing run reports four false alarms caused by distributing a result across several files or papers. Use those as regression examples, with explicit labels that they are already known cases. [Recorded findings](https://github.com/johnemmanueljen-boop/An-Automaton-s-Apology/blob/main/docs/findings.md)

Concrete fixture candidates from local `results/findings/fishing_triage.json`: `049 AbhyankarSathaye` needs sibling `StableCoordinateFour.lean`; `174 StrongThinTree` needs `AlgorithmicThinTrees.lean`; `157 ListHadwiger` used the wrong linked paper; `072 BrennanSharp` requires the context for the Koebe endpoint statement. Confirm the mappings against the upstream artifacts when constructing the bundles.

A bundle must contain:

| Record | Required content |
| --- | --- |
| Identity | Stable result ID, schema version, source repository URL and commit, audited checkout/tool versions. |
| Documents | Paper URLs and versions, PDF/text hashes, extracted text, page and line mapping, extraction tool/version. |
| Formal artifacts | Challenge paths, solution modules, comparator configuration, target declarations, allowed axioms, definition holes, source hashes. |
| Scope | Published scope notes as attributed evidence; a human-maintained inventory of claims the bundle intends to assess. |
| Retrieval | Selected spans, document/declaration IDs, why each was selected, and unresolved or unavailable artifacts. |

Use `(repository, commit, module, fully_qualified_name)` for declaration identity. Include challenge-versus-solution environment identity when names coincide. Keep outputs under `results/runs/<run_id>/` so a new experiment cannot silently replace an old card.

Retrieve by explicit links, declaration names, paper labels, and lexical search first. Include neighboring hypotheses and definition context, with a token budget and recorded truncation. Embeddings are optional later. A matching theorem number is a candidate association, not sufficient evidence when paper versions differ. If PDF extraction garbles a formula, surface the page for review and mark the affected comparison uncertain.

Represent coverage with separate axes:

- Availability: `complete_for_manifest`, `missing_sources`, or `truncated_context`.
- Claim mapping: `mapped`, `unmapped`, `ambiguous`, or `outside_declared_scope`.
- Proposed relation: `equivalent`, `lean_stronger`, `lean_weaker`, `different`, or `unknown`.
- Evidence level: model proposal, formal artifact, or human review.

Only say “not found in the declared formalization scope” after all manifest targets were considered. Missing sources should produce an explicit abstention. Do not treat a publisher's scope note as proof of semantic correspondence; use it to distinguish a disclosed limitation from a newly discovered discrepancy.

Acceptance: adding a sibling artifact resolves a known false coverage alarm with a cited mapping; removing that artifact yields incomplete context. Duplicate filenames across repositories remain distinct. Paper-version mismatch remains visible. Existing single-file commands still work through the adapter.

## Phase 2 Extract the dependencies that need review

Create `apology/dependencies.py`, `apology/review.py`, and a small Lean extraction adapter under `lean/`. Keep the dependency graph in JSON and render it within Marimo; adopting another frontend is unnecessary.

Start with a short compatibility spike against [Lean Atlas's implementation](https://github.com/NyxFoundation/lean-atlas). Its documented graph export is `lake exe atlas graph-data --output graph.json --pretty`. Pin an implementation revision and test against each audited repository's actual Lean toolchain. Do not change audited repositories' tracked files or assume the prompt's hardcoded Lean version matches every target. Use a disposable analysis checkout. If integration requires substantial dependency changes, implement a small extractor over Lean's elaborated environment and document the adapted algorithm.

### Extraction contract

Extract fully qualified constants, actual declaration kinds, elaborated types and available values, originating module, source mapping, and direct constant references. Record whether each reference occurs in the type, value, or both. Preserve constructor, projection, recursor, instance, and abbreviation relationships that affect the target; do not infer dependencies from identifiers appearing in comments or notation.

Mark external trusted declarations explicitly rather than silently dropping unknown imports. If an opaque body or source mapping is unavailable, expose a blocker. The current regex parser can continue supplying display excerpts, but an incomplete lexical parse cannot certify graph completeness or reconstruct the authoritative theorem type.

Implement a pure function:

`compute_review_scope(graph, target_ids, trusted_base) -> ReviewScope`

For the Compass-style semantic slice, traverse type edges and definition-value edges, excluding theorem-proof-only edges. Include project axioms and target nodes. Retain why each included node was reached. Handle cycles with a visited set; group recursive components for display. Keep a separate full proof-dependency/axiom view for proof validation. [Lean Compass algorithm](https://arxiv.org/pdf/2604.16347)

Challenge files contain placeholder proofs. Their dependency view helps identify statement meaning; it does not establish that the solution proofs passed a checker. Record solution/comparator verification as a separate artifact, or explicitly as unverified in this run.

### Review workflow

Each relevant node gets a human status: `unreviewed`, `accepted`, `mismatch`, `needs_context`, or `stale`. Model priority and explanation live in separate fields. An LLM may reorder a queue but cannot mark an item human-accepted.

Store reviewer ID, timestamp, rationale, compared paper spans, node hash, dependency fingerprint, and run identity. A change to the node, its semantic dependencies, source paper, or trusted base invalidates the applicable review. Review a reused definition once per identical context and show every affected claim.

Replace the current single trust-burden count with:

- Unique relevant declarations and source spans.
- Human-reviewed versus unreviewed items.
- Unresolved extraction or context blockers.
- Model-prioritized suggestions, clearly labeled as such.

Count unique source spans to avoid double counting shared definitions. Show the selected claim inventory beside the graph: a complete slice for one theorem is not coverage of every claim in its paper.

### Challenge and solution definitions

Use the extracted environments to improve `holes.py`: resolve imported definitions and classify proof fields by elaborated type being `Prop`, not by the presence of `by`. Compare declaration types and computational content across the challenge and solution environments.

Report `text_equal`, `definitional_equal`, `proved_equivalent`, `different`, and `unresolved` separately. Matching hashes/text are useful checks but require the same name-resolution context. A failure of definitional equality does not prove semantic inequality. General cross-environment equivalence is a stretch task; unresolved comparisons remain in the review queue.

### Acceptance fixtures

Build small Lean fixtures covering a nested definition, a theorem used only in a proof, a theorem in a dependent type, a custom instance, an abbreviation, an imported definition hole, a data field constructed with `by`, and an axiom. Verify the expected included/excluded nodes and blockers by hand. Include a graph cycle fixture. Changing a shared definition must invalidate every affected review.

Measure extraction coverage and retained nodes on both challenge files and full solution modules. Do not require an arbitrary reduction percentage for success; reliable inclusion of the necessary context is the first acceptance criterion.

## Phase 3 Target the discrepancies the current system misses

Create `apology/semantic_checks.py`; extend `prompts.py`, `probes.py`, and `restate.py`. Start with transparent rules and small Lean fixtures. Model-written mathematics remains a proposal until its specific evidence is checked.

### Structured comparison

For each paired claim, represent domains, binders, quantifier order, hypotheses, conclusion, exceptional sets, boundary strictness, constants, and referenced definitions. Lean supplies the formal side; paper extraction supplies an explicitly proposed reading with source citations. Show the comparison as a table in the app.

Avoid comparing rendered tokens alone. In particular, resolve natural/integer/real types, coercions, hidden structure assumptions, and the definitions behind notation before assigning meaning.

### First checks to implement

| Check | Example | Useful evidence |
| --- | --- | --- |
| Boundary inclusion | `x > 0` versus `x >= 0` | An endpoint satisfying one predicate but not the other. |
| Domain change | Natural division versus real division | A small typed evaluation exposing the difference. |
| Quantifier scope | `forall x, exists y` versus `exists y, forall x` | A finite witness where the predicates differ. |
| Hidden assumptions | A structure adds regularity or nonzero conditions | Expanded fields and the cited paper assumptions. |
| Changed constants | A bound inside a helper definition changes | Unfolded definitions and a concrete separating input where available. |
| Vacuity | Hypotheses cannot jointly hold | A proved inconsistency, or a positive witness for satisfiability; failed search is unknown. |
| Totalized operations | Division, integral, derivative at an exceptional input | Applicable domain hypotheses plus a Lean-checked exceptional case. |

Use bounded checks only where the domain supports them, such as small naturals or rationals. Explicitly state bounds. Failing to find a counterexample does not establish a universal claim. For analysis problems, a real endpoint may require a symbolic proof rather than numerical testing.

### Directional comparisons

For aligned predicates `P` from the paper interpretation and `Q` from the formalization, store results for `P -> Q` and `Q -> P` separately. Proving one direction does not prove that the reverse fails. Assign strict weakening only with a separating example or other justified evidence. Preserve the surrounding quantifiers: strengthening a predicate under negated existence can weaken the overall theorem.

Paper-derived `P` must carry `interpretation_status=proposed|human_reviewed`. Even a proved `P <-> Q` only certifies the relationship between those formal expressions. If `P` misreads the paper, the paper-to-code link is still wrong.

Existing certified restatements remain useful for readability. Replace fragile string reconstruction in `restate.py` with the extracted elaborated target type when available, preserving universes, implicit parameters, and section variables. Verify the generated left side against that target. Until supported, fail explicitly on unsupported syntax rather than guessing.

Treat BEq/BEq+ as evaluated comparison methods, not blanket semantic guarantees. In unrestricted logic, two independently provable propositions can be equivalent while expressing quite different content. Prefer structure-preserving transformations, definition comparisons, documented tactic restrictions, and human-reviewed references. Never infer faithfulness from an arbitrary successful `iff` proof alone. [BEq research](https://proceedings.iclr.cc/paper_files/paper/2025/hash/d630537fc4402cfa3ebbc7450a0cac91-Abstract-Conference.html), [BEq+ research](https://aclanthology.org/2025.emnlp-main.907/)

Acceptance: endpoint/domain fixtures produce appropriate witnesses; quantifier polarity is correct; malformed or unprovable probes remain inconclusive; changing a probe goal during repair cannot silently close the original finding; a paper interpretation without human review never receives a paper-faithfulness certificate.

## Phase 4 Demonstrate improvement with honest measurements

Extend `experiments/benchmark_evaluate.py` and `experiments/summarize.py`; add `experiments/ablate.py`, `experiments/review_scope.py`, and versioned evaluation manifests. Proposed filenames are new implementation work, not existing commands.

### Preserve and strengthen the baseline

Freeze the existing prompts, cached inputs, raw outputs, adjudications, model IDs, and source revisions as a historical baseline. The old 41 cases are now a regression set because their weaknesses have informed this plan. Create a new evaluation set grouped by source theorem or paper; keep all variants of a source in the same split.

Use semantic annotations that identify the actual discrepancy, not just a nearby line. Preserve the old location score as a secondary metric. Have reviewers adjudicate disputed cases without seeing which system produced the finding. Equivalent mutations need explicit exclusion reasons; compilation by itself does not establish that a mutation changed meaning.

For external validation, first select a small, fixed sample from ProofNetVerif or corrected ProofNet#, then a context-rich RLM25 sample if its toolchains are available. Verify dataset licensing, version, labels, and required imports. These datasets test related abilities; they do not substitute for real paper-to-project audits. [Dataset paper](https://aclanthology.org/2025.emnlp-main.907/)

### Ablations and metrics

Compare a frozen baseline with cumulative additions: evidence fixes, complete bundles, dependency context, and targeted probes. Also compare the same bundle with and without dependency filtering to isolate its effect. Use identical source sets, model settings, and declared budgets; report extra cost when a component adds calls. A second judge is optional and must have its own cost/accuracy ablation.

Report:

- Semantic discrepancy precision and recall, with raw counts and per-category results.
- Fraction of independent clean files receiving at least one false flag; additionally report the legacy mutation-site metric by its actual name.
- Abstention/incomplete-context rate, separate from a clean verdict.
- Probe completion and certified-witness rates, with timeout and rejection counts.
- Cost, tokens, latency, and calls per audited result; show live cost separately from cache replay.
- Extraction completeness, unique retained review nodes, and human review completion.
- Confidence intervals with the statistical unit stated. Where variants share a source, use source-group resampling rather than assuming every mutation is independent.

Do not advertise a guaranteed accuracy target from this plan. Predeclare the fresh-test scoring rule and budget, then publish the resulting tradeoff. The 12 textbook controls are useful regression checks but too few to establish a small real-world false-positive rate.

If claiming reduced human effort, run a small counterbalanced review exercise: reviewers examine comparable cases with the old cards and the new view, recording time and correctness. Node reduction alone does not support a review-time claim.

### Reproducibility

Add `--offline` behavior that refuses API calls on cache misses, including automatic retries. Record exact prompts, source/document hashes, model configuration, schema/extractor versions, toolchain, resource limits, and actual usage in each run manifest. Existing prompt-keyed caching is worth retaining, but source provenance must also identify which Lean execution produced each artifact. [Current cache implementation](https://github.com/johnemmanueljen-boop/An-Automaton-s-Apology/blob/main/apology/llm.py)

Give each frozen experiment its actual prompt; do not replay old results under current prompts. The repository already documents several exceptions to exact replay. Keep these exceptions visible rather than presenting an ad-hoc historical comparison as a fully reproducible experiment. [Experiment notes](https://github.com/johnemmanueljen-boop/An-Automaton-s-Apology/blob/main/experiments/README.md)

## Shared data contracts

Use versioned JSON and explicit validation. The following is a field contract, not a requirement to introduce a database.

| Object | Fields and invariants |
| --- | --- |
| `SourceSpan` | Source ID, immutable hash, path/document version, one-based start/end line, optional page, declaration ID; all bounds validated. Preserve PDF form feeds consistently. |
| `DependencyNode` | Environment-qualified ID, fully qualified name, kind, type/body fingerprints, source span, trusted-base status, extraction completeness. |
| `DependencyEdge` | Source/target IDs and site `type|value|both`; never merge away type relevance. |
| `Finding` | Stable ID, bundle/claim IDs, category, severity, hypothesis, Lean/paper spans, location validation, proposed relation, evidence IDs, human decision. |
| `ProbeEvidence` | Requested proposition, generated theorem identity, exact Lean artifact/hash, status, axiom dependencies, runtime result, claim it supports, interpretation status. |
| `HumanReview` | Reviewer, time, decision, rationale, source and dependency fingerprints; accepted reviews become stale when those inputs change. |
| `RunManifest` | Code/tool/model versions, input hashes, exact request IDs, budgets/actual cost, timestamps, output paths, offline status. |

Maintain these invariants across the pipeline:

1. A model cannot emit its own human-review decision or checked-proof status.
2. Missing evidence, incomplete extraction, and failed proof attempts remain explicit unknowns.
3. Location validity, mathematical evidence, and semantic judgment are different properties.
4. Machine-readable claims have immutable source identity and an evidence trail.
5. Historical outputs are retained and loaded through an adapter, not retroactively upgraded.

## Hackathon interface and demonstration

Extend `app.py` with a result bundle selector and one main claim view. Show the paper passage next to the formal claim and expanded assumptions. Below it, list relevant definitions, proposed discrepancies, and checked evidence. A small dependency graph should answer why a definition is present; a table is sufficient for the first version.

Use explicit labels such as “Model concern,” “Source location checked,” “Lean-checked witness,” “Human-confirmed mismatch,” and “Context incomplete.” Show unresolved items and source versions. Let a local reviewer record a decision and export a JSON/Markdown audit report with evidence links. Use simple local JSON review storage for the hackathon; a multi-user service can wait.

Prepare three reproducible examples:

1. A clean or disclosed-partial result whose apparent coverage alarm disappears when the sibling artifact is included.
2. A small synthetic boundary/definition mismatch with a checked separating witness and a clear dependency path. Label it synthetic.
3. The existing Navier–Stokes Lemma 8.6 reproduction, crediting the original experts and distinguishing the supplied lemma pairing from end-to-end discovery. Preserve the recorded miss rather than implying all expert issues were found.

The useful demo story is that a reviewer can trace a concern to sources and see exactly what remains uncertain. Do not imply that a supplied pair found quickly is equivalent to independently auditing an entire research paper.

## Delivery sequence and effort assumptions

Estimates are engineering planning ranges for someone comfortable with Python and Lean, with working toolchains and existing fixtures. They exclude large dependency downloads, expert annotation, and training models.

| Milestone | Deliverable | Approximate effort | Dependency |
| --- | --- | --- | --- |
| M0 | Baseline snapshot, strict citations/probe statuses, regression fixtures, honest labels | 4–6 hours | Existing repository |
| M1 | Bundle manifest, complete-context audit, legacy adapter, one coverage regression | 4–6 hours | M0 |
| M2 | Lean extractor spike, graph contract, review scope and invalidation | 8–12 hours | M0; integrates with M1 |
| M3 | Targeted boundary/definition checks and witnessed demo | 4–8 hours | M0 and M1; uses M2 when available |
| M4 | Evaluation report, app integration, offline demo and export | 4–6 hours | Available completed milestones |

For a single-day deadline, ship M0, a narrow M1, and a reduced M4 with cached examples. For two to three focused development days, aim for the full 24–38 hour path. If the extractor compatibility spike exceeds two hours, keep it as an optional subsystem and continue with bundles and evidence correctness; incomplete extraction must stay visible.

Defer model fine-tuning, a universal paper-to-Lean translator, a full React rewrite, automated public accusations, a multi-user backend, and rebuilding every upstream proof. These would consume the hackathon without directly resolving the demonstrated weaknesses.

## Instructions to the implementing model

Implement the plan incrementally in the existing repository. First read the current README, repository instructions, `docs/trust.md`, `docs/validation.md`, and the named functions; capture the checkout SHA and inspect worktree changes. Treat this handoff's source observations as hypotheses to revalidate against that checkout.

Start with M0 and add focused regression tests for the identified evidence failures. Preserve historical results and prompts. Introduce versioned output schemas and compatibility adapters before changing consumers. Keep cached browsing usable without an API key or Lean, and make new paid experiments explicit, bounded operations. Do not silently regenerate all results after changing a prompt.

Then implement M1 and attempt the time-boxed M2 compatibility spike. Prefer exact Lean/environment data over expanding regex parsing. Keep proposed modules small and use the existing Marimo interface. Use the target repository's pinned toolchain; do not upgrade upstream mathematics as a side effect.

For checks, start with the existing `python -m experiments.summarize` and `marimo run app.py` baseline, then run the focused Python regressions and Lean fixtures appropriate to each milestone. Add documented commands for new experiments only when they exist. Ensure offline mode makes zero provider calls even on cache miss. Do not present inability to run Lean as a passing integration check.

Deliver the implemented changes, passing checks, a versioned sample bundle/card, reproducible demo instructions, and a concise list of limitations or deferred milestones. Update headline metrics only from a saved evaluation run. Never promote a model judgment, an unvalidated citation, or a failed Lean invocation into a semantic correctness certificate.
