# Why you can trust a label

Each label on an audit card rests on a different foundation. Version 2 separates execution status,
evidence type, source location, and human semantic review. Historical cards are displayed as historical
results and are not silently upgraded to the current validation contract.

| Label | What it guarantees | Rests on | Can it be wrong? |
|---|---|---|---|
| Checked formal probe or restatement | The recorded formal expression was accepted under the execution policy, with checked target identity and allowed axioms | Lean, imports, execution environment, wrapper construction and evidence validator | Validation, execution, statement construction or trusted-code errors remain possible |
| Source location checked | The exact declaration and source span exist in the recorded snapshot | Hash and range validation | Does not establish that the text supports the concern |
| Deterministic lint or text difference | A reproducible feature of the input files | Parser and rule implementation | A semantic mismatch still requires interpretation |
| AI flag (sticky note) | Nothing; it says where to look | The model's reading, with its accuracy measured | Yes: it missed about 1 in 4 planted errors and raised 2% false alarms |
| Coverage verdict (equivalent, weaker, different) | Nothing until a human confirms it | The model's reading | Yes; confirm before publishing |

## What a checked formal label establishes

A certified restatement is a theorem *original ⟺ restated*, checked by Lean's kernel
(`apology/restate.py`):

1. Python generates probe identities and theorem wrappers. Model proof repair retains the requested proposition.
2. Known unsafe constructs are rejected. These guards are not a sandbox; live execution is disabled by default.
3. Successful execution requires a zero process exit, a nonempty unique set of newly declared proof targets,
   and complete axiom evidence limited to `propext`, `Classical.choice`, and `Quot.sound`.
4. Failed proofs, timeouts, missing Lean, unsupported restatement syntax, and expected compiler failures
   remain inconclusive. Compiler rejection never establishes a mathematical negation.
5. A witness, satisfiability proof, implication and equivalence have different evidence types. A failed
   reverse implication does not establish strict weakening.

The restatement path refuses inferred definition types and section/universe variables when it cannot
reconstruct them safely. Broader support requires an elaborated target-type bridge. Historical proof
records are preserved separately; current regression tests do not independently recheck them.

## What a certified label does not guarantee

- **That OpenAI's statement matches the paper.** Certification links our version to OpenAI's code, not to
  the paper. That link is what the AI flags and human review are for.
- **That OpenAI's proof is correct.** That is Lean's job on OpenAI's side: OpenAI's checker ties each
  statement file to its proof, and independent re-checks (e.g. ten-slops) confirmed the ten-proofs kernels.
- **That the English is perfect.** The sentence describing a restatement is AI-written; the Lean formula
  is the guarantee.

## The trusted base

The trusted base includes Lean's logic/kernel, imported definitions and permitted axioms, statement
construction, subprocess and output validation, and the configured execution environment. The Docker
policy limits host access; it does not by itself prevent forged console evidence. Host-local mode is
an explicit opt-in for trusted fixtures, not isolation. Stronger hostile-input assurance requires exported
proof replay and statement-identity checks outside the generating process, as described in
[Lean's validation documentation](https://lean-lang.org/doc/reference/latest/ValidatingProofs/).

Human decisions are stored with reviewer identity, rationale and dependency/document fingerprints.
Model confidence only prioritizes work. Changing a shared definition or source document invalidates
affected human reviews. Exact bounded Python arithmetic is labeled computational evidence and never
presented as a Lean certificate or a universal equivalence result.

## Why AI flags are still useful

The AI never certifies anything. It proposes where to look, and we report how often it is right
([validation.md](validation.md)). A flag is a reason to look, not a verdict.
