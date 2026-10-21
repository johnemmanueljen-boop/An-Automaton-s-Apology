import Mathlib

set_option autoImplicit false

noncomputable section

namespace MetricCodes

instance numeralTwoAtLeast : Nat.AtLeastTwo 2 := ⟨by decide⟩

abbrev BinaryWord (n : ℕ) := Fin n → Bool

def hammingDist {n : ℕ} (x y : BinaryWord n) : ℕ :=
  (Finset.univ.filter fun i => x i ≠ y i).card

def binaryWeight {n : ℕ} (x : BinaryWord n) : ℕ :=
  (Finset.univ.filter fun i => x i = true).card

def weightShell (n w : ℕ) : Finset (BinaryWord n) :=
  Finset.univ.filter fun x => binaryWeight x = w

def IsBinaryCode {n : ℕ} (d : ℕ) (C : Finset (BinaryWord n)) : Prop :=
  ∀ ⦃x⦄, x ∈ C → ∀ ⦃y⦄, y ∈ C → x ≠ y → d ≤ hammingDist x y

def binaryEntropy (u : ℝ) : ℝ :=
  -(u * Real.logb 2 u) -
    (1 - u) * Real.logb 2 (1 - u)

def hammingGamma (a b : ℝ) : ℝ :=
  (2 * (a - b) * (1 - a - b)) /
    Real.sqrt (a * (1 - a))

namespace Hamming

noncomputable def validCodes (n d : ℕ) : Finset (Finset (BinaryWord n)) := by
  classical
  exact Finset.univ.filter (MetricCodes.IsBinaryCode d)

noncomputable def codeNumber (n d : ℕ) : ℕ :=
  (validCodes n d).sup fun C => C.card

def classicalParameter (δ : ℝ) : ℝ :=
  (1 : ℝ) / 2 - Real.sqrt (δ * (1 - δ))

def classicalRate (δ : ℝ) : ℝ :=
  MetricCodes.binaryEntropy (classicalParameter δ)

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

theorem binaryRate_lt_classicalRate {δ : ℝ}
    (hδ : 0 < δ) (hδ' : δ < (1 : ℝ) / 2) :
    binaryRate δ < classicalRate δ := by
  sorry

theorem exists_binaryRate_improvement {δ : ℝ}
    (hδ : 0 < δ) (hδ' : δ < (1 : ℝ) / 2) :
    ∃ ε : ℝ, 0 < ε ∧ binaryRate δ ≤ classicalRate δ - ε := by
  sorry

end Hamming

namespace Johnson

def binaryCodeFamily (n d : ℕ) : Finset (Finset (BinaryWord n)) := by
  classical
  exact (Finset.univ : Finset (BinaryWord n)).powerset.filter
    (fun C => IsBinaryCode d C)

def binaryCodeNumber (n d : ℕ) : ℕ :=
  (binaryCodeFamily n d).sup (fun C => C.card)

def shellCodeFamily (n w d : ℕ) : Finset (Finset (BinaryWord n)) := by
  classical
  exact (weightShell n w).powerset.filter (fun C => IsBinaryCode d C)

def shellCodeNumber (n w d : ℕ) : ℕ :=
  (shellCodeFamily n w d).sup (fun C => C.card)

def centeredDegree (u : ℝ) : ℝ := 1 - 2 * u

def centeredWeight (α : ℝ) : ℝ := 1 - 2 * α

def centeredSigma (β γ : ℝ) : ℝ := 1 - 2 * β - 2 * γ

def centeredEta (α β γ : ℝ) : ℝ :=
  1 - 2 * α + 2 * β - 2 * γ

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
  1 + mrrwG (r ^ 2) -
    mrrwG (r ^ 2 + 2 * δ * r + 2 * δ)

def mrrwRateSet (δ : ℝ) : Set ℝ :=
  {t | ∃ r : ℝ, 0 ≤ r ∧ r ≤ 1 - 2 * δ ∧
    t = mrrwObjective δ r}

def mrrwRate (δ : ℝ) : ℝ :=
  sInf (mrrwRateSet δ)

theorem binaryRate_le_combinedVariationalRate
    {d : ℝ} (hd : 0 < d) (hdhalf : d < (1 : ℝ) / 2) :
    MetricCodes.Hamming.binaryRate d ≤ combinedVariationalRate d := by
  sorry

theorem binaryRate_lt_mrrw
    {d : ℝ} (hd : 0 < d) (hdhalf : d < (1 : ℝ) / 2) :
    MetricCodes.Hamming.binaryRate d < mrrwRate d := by
  sorry

theorem exists_binaryRate_mrrw_improvement
    {d : ℝ} (hd : 0 < d) (hdhalf : d < (1 : ℝ) / 3) :
    ∃ e : ℝ, 0 < e ∧ MetricCodes.Hamming.binaryRate d ≤ mrrwRate d - e := by
  sorry

end Johnson

namespace MRRW

theorem strict_mrrw2
    {δ : ℝ} (hδ : 0 < δ) (hhalf : δ < (1 : ℝ) / 2) :
    MetricCodes.Johnson.combinedVariationalRate δ <
      MetricCodes.Johnson.mrrwRate δ := by
  sorry

end MRRW

end MetricCodes

end
