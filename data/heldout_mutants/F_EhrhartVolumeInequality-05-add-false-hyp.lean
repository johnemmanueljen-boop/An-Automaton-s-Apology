import Mathlib

noncomputable section

open Set MeasureTheory
open scoped BigOperators ENNReal

namespace Ehrhart

abbrev Space (n : ℕ) := Fin n → ℝ

def integerPoint (n : ℕ) (z : Fin n → ℤ) : Space n :=
  fun i => (z i : ℝ)

def standardSimplex (n : ℕ) : Set (Space n) :=
  {x | (∀ i, 0 ≤ x i) ∧ (∑ i, x i) ≤ 1}

def simplexDilation (n : ℕ) (x : Space n) : Space n :=
  fun i => ((n : ℝ) + 1) * x i - 1

def centeredSimplex (n : ℕ) : Set (Space n) :=
  simplexDilation n '' standardSimplex n

def normalizedVolume {n : ℕ} (K : Set (Space n)) : ℝ :=
  ((volume : Measure (Space n)) K).toReal

def barycenter {n : ℕ} (K : Set (Space n)) : Space n :=
  (normalizedVolume K)⁻¹ • ∫ x in K, x ∂(volume : Measure (Space n))

def interiorLatticePoints {n : ℕ} (K : Set (Space n)) : Set (Fin n → ℤ) :=
  {z | integerPoint n z ∈ interior K}

structure CenteredBody (n : ℕ) where
  carrier : Set (Space n)
  convex : Convex ℝ carrier
  compact : IsCompact carrier
  fullDimensional : (interior carrier).Nonempty
  centered : barycenter carrier = 0
  uniqueInteriorLatticePoint : interiorLatticePoints carrier = {0}

def sharpConstant (n : ℕ) : ℝ :=
  ((n : ℝ) + 1) ^ n / (n.factorial : ℝ)

end Ehrhart

namespace Ehrhart.SimplexVolume

theorem barycenter_centeredSimplex (n : ℕ) :
    barycenter (centeredSimplex n) = 0 := by
  sorry

theorem normalizedVolume_centeredSimplex (n : ℕ) (_hn : 0 < n) :
    normalizedVolume (centeredSimplex n) = sharpConstant n := by
  sorry

theorem exists_centeredBody_sharp (n : ℕ) (hn : 0 < n) :
    ∃ K : CenteredBody n,
      normalizedVolume K.carrier = sharpConstant n := by
  sorry

end Ehrhart.SimplexVolume

namespace Ehrhart.Volume

theorem ehrhart_volume_inequality_for_sets (hbase : (1 : ℕ) = 0) {n : ℕ} (hn : 0 < n) (S : Set (Space n))
    (hconvex : Convex ℝ S)
    (hcompact : IsCompact S)
    (hinterior : (interior S).Nonempty)
    (hcentered : barycenter S = 0)
    (hlattice : interiorLatticePoints S = {0}) :
    normalizedVolume S ≤
      ((n : ℝ) + 1) ^ n / (n.factorial : ℝ) := by
  sorry

end Ehrhart.Volume

end
