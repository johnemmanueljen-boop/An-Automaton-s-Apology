# Why you can trust a label

Each label on an audit card rests on a different foundation, and the card says which. Only one kind is a
mathematical guarantee; the others are measured or need a human.

| Label | What it guarantees | Rests on | Can it be wrong? |
|---|---|---|---|
| Lean-certified restatement or probe | A theorem holds, e.g. OpenAI's exact statement ⟺ our readable version | Lean's kernel, Mathlib, three standard axioms, ~170 lines of our guard code | Only if Lean's kernel or Mathlib has a bug |
| Deterministic finding (citation label, definition hole, lint) | A fact about the files, which anyone can reproduce | Simple code reading the files | Only through a bug in that code; anyone can re-run it |
| AI flag (sticky note) | Nothing; it says where to look | The model's reading, with its accuracy measured | Yes: it missed about 1 in 4 planted errors and raised 2% false alarms |
| Coverage verdict (equivalent, weaker, different) | Nothing until a human confirms it | The model's reading | Yes; confirm before publishing |

## Why a Lean-certified label is sound

A certified restatement is a theorem *original ⟺ restated*, checked by Lean's kernel
(`apology/restate.py`):

1. **The AI does not write the original side.** Our code copies OpenAI's statement verbatim, or applies
   OpenAI's definition to all of its parameters, so the AI cannot narrow it to a special case.
2. **No shortcuts.** Before Lean runs, the guard rejects `sorry`, new axioms, `native_decide`, new
   definitions or instances, options and metaprograms, any of which could fake or change a proof.
3. **Axioms are checked afterwards.** The result may use only the three standard axioms Mathlib uses.
4. **Trivial restatements are refused.** The restated side may not mention the original, so "A ⟺ A" fails.
5. **Failures are tested.** A deliberately wrong restatement (dropping a lower bound) was refused by Lean;
   a `sorry` cheat was refused by the guard (`results/demo/restatements.json`).

## What a certified label does not guarantee

- **That OpenAI's statement matches the paper.** Certification links our version to OpenAI's code, not to
  the paper. That link is what the AI flags and human review are for.
- **That OpenAI's proof is correct.** That is Lean's job on OpenAI's side: OpenAI's checker ties each
  statement file to its proof, and independent re-checks (e.g. ten-slops) confirmed the ten-proofs kernels.
- **That the English is perfect.** The sentence describing a restatement is AI-written; the Lean formula
  is the guarantee.

## The trusted base

To believe a certified label you trust Lean's kernel, Mathlib's definitions, the three standard axioms,
and about 170 lines of guard code you can read (`FORBIDDEN` and `assemble` in `restate.py`, `FORBIDDEN`
and the axiom check in `probes.py`). That is the base OpenAI's own results rely on, plus those 170 lines.

## Why AI flags are still useful

The AI never certifies anything. It proposes where to look, and we report how often it is right
([validation.md](validation.md)). A flag is a reason to look, not a verdict.
