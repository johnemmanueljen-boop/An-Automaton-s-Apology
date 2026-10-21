import Mathlib

variable {K : Type*} [GroupWithZero K] [Fintype K]

theorem stmt (a : K) (ha : a ≠ 0) : a ^ (Fintype.card K - 1) = 1 := by
  sorry
