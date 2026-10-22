import Lean

/- Integration fixtures for the native extractor. These require an installed Lean toolchain.
   The Python graph tests separately exercise hand-authored graph fixtures.
   No fixture here is evidence of a new error in an external mathematical project. -/
namespace ApologyFixture

def nested : Nat := 2
def threshold : Nat := nested + 1
abbrev aliasThreshold := threshold
theorem helper : nested = 2 := rfl
theorem main : threshold = 3 := by
  exact congrArg (fun n : Nat => n + 1) helper

structure DataAndProof where
  value : Nat
  proof : value = 5

def dataBy : DataAndProof where
  value := by exact 5
  proof := by rfl

class Bound where
  bound : Nat
instance : Bound := ⟨threshold⟩
def viaInstance [b : Bound] := b.bound

axiom projectAssumption : True
def theoremInType : { p : True // p = projectAssumption } := ⟨projectAssumption, rfl⟩
theorem probe_endpoint : (0 : Int) >= 0 ∧ ¬ ((0 : Int) > 0) := by decide

end ApologyFixture
