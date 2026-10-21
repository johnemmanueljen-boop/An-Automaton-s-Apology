import Mathlib



theorem stmt {G : Type*} [Group G] [Fintype G] (p : ℕ) [hp : Fact p.Prime] (hdvd : p ∣ Fintype.card G) :
    ∃ x : G, orderOf x = p := by
  sorry
