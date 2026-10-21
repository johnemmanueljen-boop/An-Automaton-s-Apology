import Mathlib

set_option autoImplicit false

noncomputable section

open Filter Metric
open scoped BigOperators InnerProductSpace Topology

namespace MetricCodes

instance numeralTwoAtLeast : Nat.AtLeastTwo 2 := ⟨by decide⟩

abbrev BinaryWord (n : ℕ) := Fin n → Bool

def hammingDist {n : ℕ} (x y : BinaryWord n) : ℕ :=
  (Finset.univ.filter fun i => x i ≠ y i).card

def IsBinaryCode {n : ℕ} (d : ℕ) (C : Finset (BinaryWord n)) : Prop :=
  ∀ ⦃x⦄, x ∈ C → ∀ ⦃y⦄, y ∈ C → x ≠ y → d ≤ hammingDist x y

def binaryEntropy (u : ℝ) : ℝ :=
  -(u * Real.logb 2 u) - (1 - u) * Real.logb 2 (1 - u)

def hammingGamma (a b : ℝ) : ℝ :=
  (2 * (a - b) * (1 - a - b)) / Real.sqrt (a * (1 - a))

def sphericalEntropy (u : ℝ) : ℝ :=
  (1 + u) * Real.logb 2 (1 + u) - u * Real.logb 2 u

def Gamma (a b : ℝ) : ℝ :=
  ((a - b) * (1 + a + b)) /
    ((1 + 2 * a) * Real.sqrt (a * (1 + a)))

def classicalThreshold (s : ℝ) : ℝ :=
  (1 / Real.sqrt (1 - s ^ 2) - 1) / 2

namespace Hamming

noncomputable def validCodes (n d : ℕ) : Finset (Finset (BinaryWord n)) := by
  classical
  exact Finset.univ.filter (MetricCodes.IsBinaryCode d)

noncomputable def codeNumber (n d : ℕ) : ℕ :=
  (validCodes n d).sup fun C => C.card

def binaryRate (δ : ℝ) : ℝ :=
  Filter.limsup
    (fun n : ℕ =>
      Real.logb 2
        (codeNumber n (Nat.ceil (δ * (n : ℝ))) : ℝ) / (n : ℝ))
    Filter.atTop

def Feasible (δ a b : ℝ) : Prop :=
  0 ≤ b ∧ b < a ∧ a ≤ (1 : ℝ) / 2 ∧
    1 - 2 * δ < MetricCodes.hammingGamma a b

def rateSet (δ : ℝ) : Set ℝ :=
  {r | ∃ a b : ℝ, Feasible δ a b ∧
    r = MetricCodes.binaryEntropy a - MetricCodes.binaryEntropy b}

def variationalRate (δ : ℝ) : ℝ := sInf (rateSet δ)

end Hamming

namespace Johnson

def centeredDegree (u : ℝ) : ℝ := 1 - 2 * u

def centeredWeight (α : ℝ) : ℝ := 1 - 2 * α

def centeredSigma (β γ : ℝ) : ℝ := 1 - 2 * β - 2 * γ

def centeredEta (α β γ : ℝ) : ℝ := 1 - 2 * α + 2 * β - 2 * γ

def spectralLimit (α β γ u : ℝ) : ℝ :=
  let z := centeredDegree u
  let m := centeredWeight α
  let σ := centeredSigma β γ
  let η := centeredEta α β γ
  (σ * η - m * z ^ 2) ^ 2 /
      (z ^ 2 * (1 - m ^ 2) * (1 - z ^ 2)) +
    ((z ^ 2 - η ^ 2) * (σ ^ 2 - z ^ 2)) /
      (z ^ 2 * (1 - m ^ 2) * Real.sqrt (1 - z ^ 2))

def asymptoticThreshold (δ α : ℝ) : ℝ :=
  1 - δ / (2 * α * (1 - α))

def rankPenalty (α β γ : ℝ) : ℝ :=
  α * MetricCodes.binaryEntropy (β / α) +
    (1 - α) * MetricCodes.binaryEntropy (γ / (1 - α))

def shellRate (α β γ u : ℝ) : ℝ :=
  1 - MetricCodes.binaryEntropy α + MetricCodes.binaryEntropy u -
    rankPenalty α β γ

structure AsymptoticParameters (δ α β γ u : ℝ) : Prop where
  distance_pos : 0 < δ
  distance_lt_half : δ < (1 : ℝ) / 2
  weight_gt_distance : δ / 2 < α
  weight_lt_half : α < (1 : ℝ) / 2
  support_nonneg : 0 ≤ β
  support_lt_half : β < α / 2
  complement_nonneg : 0 ≤ γ
  complement_lt_half : γ < (1 - α) / 2
  first_lt_degree : β + γ < u
  degree_lt_weight : u < α
  degree_lt_left : u < α - β + γ
  degree_lt_right : u < 1 - α + β - γ

def IsSpectrallyFeasible (δ α β γ u : ℝ) : Prop :=
  asymptoticThreshold δ α < spectralLimit α β γ u

def Feasible (δ α β γ u : ℝ) : Prop :=
  AsymptoticParameters δ α β γ u ∧
    IsSpectrallyFeasible δ α β γ u

def rateSet (δ : ℝ) : Set ℝ :=
  {r | ∃ α β γ u : ℝ,
    Feasible δ α β γ u ∧ r = shellRate α β γ u}

def variationalRate (δ : ℝ) : ℝ := sInf (rateSet δ)

def combinedVariationalRate (δ : ℝ) : ℝ :=
  min (MetricCodes.Hamming.variationalRate δ) (variationalRate δ)

def mrrwG (v : ℝ) : ℝ :=
  MetricCodes.binaryEntropy ((1 - Real.sqrt (1 - v)) / 2)

def mrrwObjective (δ r : ℝ) : ℝ :=
  1 + mrrwG (r ^ 2) - mrrwG (r ^ 2 + 2 * δ * r + 2 * δ)

def mrrwRateSet (δ : ℝ) : Set ℝ :=
  {t | ∃ r : ℝ, 0 ≤ r ∧ r ≤ 1 - 2 * δ ∧
    t = mrrwObjective δ r}

def mrrwRate (δ : ℝ) : ℝ := sInf (mrrwRateSet δ)

theorem main_binary_theorem {δ : ℝ}
    (hδ : 0 < δ) (hhalf : δ < (1 : ℝ) / 2) :
    MetricCodes.Hamming.binaryRate δ ≤ combinedVariationalRate δ ∧
      combinedVariationalRate δ < mrrwRate δ := by
  sorry

end Johnson

end MetricCodes

namespace SpherePacking

abbrev Euclidean (n : ℕ) := EuclideanSpace ℝ (Fin n)

structure SphericalCode (n : ℕ) (s : ℝ) where
  points : Finset (Euclidean n)
  unit_norm : ∀ x ∈ points, ‖x‖ = 1
  inner_le : ∀ x ∈ points, ∀ y ∈ points, x ≠ y →
    ⟪x, y⟫_ℝ ≤ s

def sphericalCodeNumber (n : ℕ) (s : ℝ) : ℕ∞ :=
  ⨆ C : SphericalCode n s, (C.points.card : ℕ∞)

def kissingNumber (n : ℕ) : ℕ∞ :=
  sphericalCodeNumber n ((1 : ℝ) / 2)

end SpherePacking

namespace MetricCodes

namespace Spherical

def Feasible (s a b : ℝ) : Prop :=
  0 < b ∧ b < a ∧ s < 2 * MetricCodes.Gamma a b

def rateSet (s : ℝ) : Set ℝ :=
  {r | ∃ a b : ℝ, Feasible s a b ∧
    r = MetricCodes.sphericalEntropy a - MetricCodes.sphericalEntropy b}

def variationalRate (s : ℝ) : ℝ := sInf (rateSet s)

namespace SidelnikovLocalization

def sliceCost (s t : ℝ) : ℝ :=
  (1 / 2 : ℝ) * Real.logb 2 ((1 - t) / (1 - s))

def localizedEnvelope (κ : ℝ → ℝ) (s : ℝ) : ℝ :=
  sInf ((fun t => κ t + sliceCost s t) '' Set.Icc 0 s)

end SidelnikovLocalization

namespace HigherHierarchy

def quadraticCoordinate (u : ℝ) : ℝ := u * (1 + u)

def spectralAtom (u : ℝ) : ℝ :=
  Real.sqrt (quadraticCoordinate u) / (1 + 2 * u)

def Interlacing {r : ℕ}
    (a : Fin (r + 1) → ℝ) (b : Fin r → ℝ) : Prop :=
  0 ≤ a (Fin.last r) ∧
    ∀ i : Fin r, a i.castSucc > b i ∧ b i > a i.succ

def lagrangeNumerator {r : ℕ}
    (a : Fin (r + 1) → ℝ) (b : Fin r → ℝ)
    (ℓ : Fin (r + 1)) : ℝ :=
  ∏ m : Fin r, (quadraticCoordinate (a ℓ) - quadraticCoordinate (b m))

def lagrangeDenominator {r : ℕ}
    (a : Fin (r + 1) → ℝ) (ℓ : Fin (r + 1)) : ℝ :=
  ∏ m : Fin r,
    (quadraticCoordinate (a ℓ) - quadraticCoordinate (a (ℓ.succAbove m)))

def lagrangeWeight {r : ℕ}
    (a : Fin (r + 1) → ℝ) (b : Fin r → ℝ)
    (ℓ : Fin (r + 1)) : ℝ :=
  lagrangeNumerator a b ℓ / lagrangeDenominator a ℓ

def Gamma {r : ℕ}
    (a : Fin (r + 1) → ℝ) (b : Fin r → ℝ) : ℝ :=
  ∑ ℓ : Fin (r + 2), lagrangeWeight a b ℓ * spectralAtom (a ℓ)

def Phi {r : ℕ}
    (a : Fin (r + 1) → ℝ) (b : Fin r → ℝ) : ℝ :=
  (∑ ℓ : Fin (r + 1), MetricCodes.sphericalEntropy (a ℓ)) -
    ∑ m : Fin r, MetricCodes.sphericalEntropy (b m)

def hierarchyRateSet (s : ℝ) : Set ℝ :=
  {z | ∃ (r : ℕ) (a : Fin (r + 1) → ℝ) (b : Fin r → ℝ),
    Interlacing a b ∧ s < 2 * Gamma a b ∧ z = Phi a b}

def hierarchyVariationalRate (s : ℝ) : ℝ := sInf (hierarchyRateSet s)

def closedHierarchyRateSet (s : ℝ) : Set ℝ :=
  {z | ∃ (r : ℕ) (a : Fin (r + 1) → ℝ) (b : Fin r → ℝ),
    Interlacing a b ∧ s ≤ 2 * Gamma a b ∧ z = Phi a b}

def closedHierarchyVariationalRate (s : ℝ) : ℝ :=
  sInf (closedHierarchyRateSet s)

def sphericalCodeRate (s : ℝ) : ℝ :=
  Filter.limsup
    (fun n : ℕ =>
      Real.logb 2
        ((SpherePacking.sphericalCodeNumber n s).toNat : ℝ) / (n : ℝ))
    Filter.atTop

def levelRateSet (r : ℕ) (s : ℝ) : Set ℝ :=
  {R | ∃ (a : Fin (r + 1) → ℝ) (b : Fin r → ℝ),
    Interlacing a b ∧ s < 2 * Gamma a b ∧ R = Phi a b}

def levelRate (r : ℕ) (s : ℝ) : ℝ := sInf (levelRateSet r s)

def localizedLevelRate (r : ℕ) (s : ℝ) : ℝ :=
  SidelnikovLocalization.localizedEnvelope (levelRate r) s

def localizedHierarchyRate (s : ℝ) : ℝ :=
  sInf (Set.range fun r : ℕ => localizedLevelRate r s)

def localizedRowRate (s : ℝ) : ℝ :=
  SidelnikovLocalization.localizedEnvelope
    MetricCodes.Spherical.variationalRate s

def classicalLocalizedRate (s : ℝ) : ℝ :=
  SidelnikovLocalization.localizedEnvelope
    (fun t => MetricCodes.sphericalEntropy (MetricCodes.classicalThreshold t)) s

theorem main_general {s : ℝ} (hs : 0 < s) (hs' : s < 1) :
    (∀ {r : ℕ} {R : ℝ}
      (a : Fin (r + 1) → ℝ) (b : Fin r → ℝ),
      Interlacing a b → s < 2 * Gamma a b → Phi a b < R →
        ∀ᶠ n : ℕ in atTop, ∀ C : SpherePacking.SphericalCode n s,
          (C.points.card : ℝ) < (2 : ℝ) ^ (R * (n : ℝ))) ∧
      sphericalCodeRate s ≤ closedHierarchyVariationalRate s := by
  sorry

theorem strict_hierarchy {s : ℝ} (hs : 0 < s) (hs' : s < 1) :
    (∀ r : ℕ,
      levelRate (r + 1) s < levelRate r s ∧
        localizedLevelRate (r + 1) s < localizedLevelRate r s) ∧
      sphericalCodeRate s ≤ localizedHierarchyRate s ∧
      localizedHierarchyRate s < localizedLevelRate 1 s ∧
      localizedLevelRate 1 s < localizedRowRate s ∧
      localizedRowRate s < localizedLevelRate 0 s ∧
      localizedLevelRate 0 s = classicalLocalizedRate s := by
  sorry

namespace NumericalMaximum

theorem eventually_kissingNumber_lt_published :
    ∀ᶠ n : ℕ in atTop,
      ((SpherePacking.kissingNumber n).toNat : ℝ) ≤
        (2 : ℝ) ^ ((0.39661 : ℝ) * (n : ℝ)) := by
  sorry

end NumericalMaximum

end HigherHierarchy

end Spherical

end MetricCodes

end
