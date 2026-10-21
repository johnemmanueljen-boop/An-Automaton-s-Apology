import Mathlib

open Nat

theorem stmt (p : ℕ) [Fact p.Prime] : ((p - 1)! : ZMod p) = -1 := by
  sorry
