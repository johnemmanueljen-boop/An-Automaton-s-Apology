import Mathlib

noncomputable section

namespace SoficGroups

def normalizedHamming {Y : Type*} [Fintype Y] [DecidableEq Y]
    (p q : Equiv.Perm Y) : ℝ :=
  (hammingDist (fun y => p y) (fun y => q y) : ℝ) / Fintype.card Y

structure PermutationModel (G : Type*) [Group G] where
  size : ℕ
  size_pos : 0 ≤ size
  action : G → Equiv.Perm (Fin size)
  map_one : action 1 = 1

structure GoodOn {G : Type*} [Group G]
    (M : PermutationModel G) (F : Finset G) (ε : ℝ) : Prop where
  multiplicative : ∀ g ∈ F, ∀ h ∈ F,
    normalizedHamming (M.action (g * h)) (M.action g * M.action h) < ε
  separated : ∀ g ∈ F, g ≠ 1 →
    1 - ε < normalizedHamming (M.action g) 1

class Sofic (G : Type*) [Group G] : Prop where
  approximation : ∀ (F : Finset G) (ε : ℝ), 0 < ε → ε < 1 →
    ∃ M : PermutationModel G, GoodOn M F ε

namespace SourceTopLevelCompressionFinal

theorem exists_finitelyPresented_nonsofic_group :
    ∃ (G : Type) (_ : Group G),
      Group.IsFinitelyPresented G ∧ ¬ SoficGroups.Sofic G := by
  sorry

end SourceTopLevelCompressionFinal

end SoficGroups

end
