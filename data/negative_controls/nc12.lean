import Mathlib

variable {F : Type*} [NormedAddCommGroup F] [InnerProductSpace ℝ F]

theorem stmt (x y : F) : |inner ℝ x y| ≤ ‖x‖ * ‖y‖ := by
  sorry
