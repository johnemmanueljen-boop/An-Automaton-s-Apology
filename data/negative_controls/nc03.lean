import Mathlib

open Set
variable {α : Type*} [ConditionallyCompleteLinearOrder α] [TopologicalSpace α] [OrderTopology α] [DenselyOrdered α]
variable {δ : Type*} [LinearOrder δ] [TopologicalSpace δ] [OrderClosedTopology δ]

theorem stmt {a b : α} (hab : a ≤ b) {f : α → δ} (hf : ContinuousOn f (Icc a b)) :
    Icc (f a) (f b) ⊆ f '' Icc a b := by
  sorry
