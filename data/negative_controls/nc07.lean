import Mathlib

open Filter Topology Bornology
variable {X : Type*} [PseudoMetricSpace X] [ProperSpace X] {s : Set X}

theorem stmt (hs : IsBounded s) {x : ℕ → X} (hx : ∀ n, x n ∈ s) :
    ∃ a ∈ closure s, ∃ φ : ℕ → ℕ, StrictMono φ ∧ Tendsto (x ∘ φ) atTop (𝓝 a) := by
  sorry
