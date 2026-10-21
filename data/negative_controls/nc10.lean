import Mathlib

variable {p q : ℕ} [Fact p.Prime] [Fact q.Prime]

theorem stmt (hp : p ≠ 2) (hq : q ≠ 2) (hpq : p ≠ q) :
    legendreSym q p * legendreSym p q = (-1) ^ (p / 2 * (q / 2)) := by
  sorry
