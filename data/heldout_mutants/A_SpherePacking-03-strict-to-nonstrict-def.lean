import Mathlib

set_option autoImplicit false

noncomputable section

open Filter MeasureTheory Metric
open scoped ENNReal FourierTransform SchwartzMap Topology

namespace CohnElkies

abbrev Euclidean (d : ℕ) := EuclideanSpace ℝ (Fin d)

abbrev TestFunction (d : ℕ) := 𝓢(Euclidean d, ℂ)

def unitBallVolume (d : ℕ) : ℝ :=
  Real.pi ^ ((d : ℝ) / 2) / Real.Gamma ((d : ℝ) / 2 + 1)

instance numeralTwoAtLeast : Nat.AtLeastTwo 2 := ⟨by decide⟩

instance euclideanFiniteDimensional (d : ℕ) :
    FiniteDimensional ℝ (EuclideanSpace ℝ (Fin d)) := by
  infer_instance

instance euclideanBorelSpace (d : ℕ) :
    BorelSpace (EuclideanSpace ℝ (Fin d)) := by
  infer_instance

end CohnElkies

namespace PackingBounds

structure FullAdmissible (d : ℕ) where
  function : CohnElkies.TestFunction d
  real : ∀ x : CohnElkies.Euclidean d, (function x).im = 0
  fourier_real :
    ∀ x : CohnElkies.Euclidean d, ((𝓕 function) x).im = 0
  fourier_nonneg :
    ∀ x : CohnElkies.Euclidean d, 0 ≤ ((𝓕 function) x).re
  fourier_zero_pos :
    0 < ((𝓕 function) (0 : CohnElkies.Euclidean d)).re
  outside_nonpos :
    ∀ x : CohnElkies.Euclidean d, 1 ≤ ‖x‖ → (function x).re ≤ 0

def fullQuotient {d : ℕ} (f : FullAdmissible d) : ℝ :=
  (f.function (0 : CohnElkies.Euclidean d)).re /
    ((𝓕 f.function) (0 : CohnElkies.Euclidean d)).re

def fullQuotientSet (d : ℕ) : Set ℝ :=
  Set.range (fullQuotient (d := d))

def fullLinearProgram (d : ℕ) : ℝ :=
  CohnElkies.unitBallVolume d / (2 : ℝ) ^ d *
    sInf (fullQuotientSet d)

end PackingBounds

structure SpherePacking (d : ℕ) where
  centers : Set (EuclideanSpace ℝ (Fin d))
  separation : ℝ
  separation_pos : 0 < separation := by positivity
  centers_dist : Pairwise (separation ≤ dist · · : centers → centers → Prop)

@[reducible] def SpherePacking.occupiedBallRegion {d : ℕ} (S : SpherePacking d) :
    Set (EuclideanSpace ℝ (Fin d)) :=
  ⋃ x : S.centers, ball (x : EuclideanSpace ℝ (Fin d)) (S.separation / 2)

noncomputable def SpherePacking.densityInsideRadius {d : ℕ}
    (S : SpherePacking d) (R : ℝ) : ℝ≥0∞ :=
  volume (S.occupiedBallRegion ∩ ball 0 R) / volume (ball (0 : EuclideanSpace ℝ (Fin d)) R)

noncomputable def SpherePacking.upperPackingDensity {d : ℕ}
    (S : SpherePacking d) : ℝ≥0∞ :=
  limsup S.densityInsideRadius atTop

def SpherePackingConstant (d : ℕ) : ℝ≥0∞ :=
  ⨆ S : SpherePacking d, S.upperPackingDensity

namespace PackingBounds

structure SharpFullCohnElkiesManuscriptConclusions : Prop where
  root_before_infimum :
    Tendsto
      (fun d : ℕ =>
        sInf {q : ℝ | ∃ f : FullAdmissible d,
          fullQuotient f ^ ((d : ℝ)⁻¹) = q} /
          Real.sqrt (d : ℝ))
      atTop (𝓝 (1 / Real.pi))
  root_before_infimum_vanishing_error :
    ∃ err : ℕ → ℝ,
      Tendsto err atTop (𝓝 0) ∧
      ∀ d : ℕ, 0 ≤ d →
        sInf {q : ℝ | ∃ f : FullAdmissible d,
          fullQuotient f ^ ((d : ℝ)⁻¹) = q} =
          (1 / Real.pi + err d) * Real.sqrt (d : ℝ)
  linear_program_root :
    Tendsto
      (fun d : ℕ => (fullLinearProgram d) ^ ((d : ℝ)⁻¹))
      atTop (𝓝 (Real.sqrt (Real.exp 1 / (2 * Real.pi))))
  natural_logarithmic_rate :
    Tendsto
      (fun d : ℕ => Real.log (fullLinearProgram d) / (d : ℝ))
      atTop
      (𝓝 ((1 / 2 : ℝ) * Real.log (Real.exp 1 / (2 * Real.pi))))
  natural_vanishing_exponential_error :
    ∃ err : ℕ → ℝ,
      Tendsto err atTop (𝓝 0) ∧
      (∀ᶠ d : ℕ in atTop,
        fullLinearProgram d =
          (Real.sqrt (Real.exp 1 / (2 * Real.pi)) + err d) ^ d)
  universal_nonnegative_delta :
    ∃ δ : ℕ → ℝ,
      Tendsto δ atTop (𝓝 0) ∧
      (∀ d : ℕ, 0 ≤ δ d) ∧
      (∀ᶠ d : ℕ in atTop, ∀ f : FullAdmissible d,
        (2 : ℝ) ^ d / CohnElkies.unitBallVolume d *
          (Real.sqrt (Real.exp 1 / (2 * Real.pi)) - δ d) ^ d ≤
            fullQuotient f)
  base_two_exponent_positive :
    0 < (1 / 2 : ℝ) * Real.logb 2 (2 * Real.pi / Real.exp 1)
  base_two_decimal_certificate :
    (1 / 2 : ℝ) * Real.logb 2 (2 * Real.pi / Real.exp 1) ∈
      Set.Ioo
        (0.604400544291677695341677307053 : ℝ)
        0.604400544291677695341677307054
  base_two_logarithmic_rate :
    Tendsto
      (fun d : ℕ => Real.logb 2 (fullLinearProgram d) / (d : ℝ))
      atTop
      (𝓝 (-((1 / 2 : ℝ) * Real.logb 2 (2 * Real.pi / Real.exp 1))))
  base_two_vanishing_exponential_error :
    ∃ err : ℕ → ℝ,
      Tendsto err atTop (𝓝 0) ∧
      (∀ᶠ d : ℕ in atTop,
        fullLinearProgram d =
          (2 : ℝ) ^
            (-((1 / 2 : ℝ) *
                Real.logb 2 (2 * Real.pi / Real.exp 1) + err d) *
              (d : ℝ)))

end PackingBounds

namespace PackingBounds.FullMain

theorem exact_limit :
    Tendsto
      (fun d : ℕ =>
        PackingBounds.fullLinearProgram d ^ ((d : ℝ)⁻¹))
      atTop
      (nhds (Real.sqrt (Real.exp 1 / (2 * Real.pi)))) := by
  sorry

theorem exact_binary_exponent :
    Tendsto
      (fun d : ℕ =>
        Real.logb 2 (PackingBounds.fullLinearProgram d) / (d : ℝ))
      atTop
      (nhds (-(1 / 2 : ℝ) *
        Real.logb 2 (2 * Real.pi / Real.exp 1))) := by
  sorry

end PackingBounds.FullMain

namespace PackingBounds.PackingBridge

theorem sphere_packing_sharp_asymptotic_upper :
    ∃ e : ℕ → ℝ,
      Asymptotics.IsLittleO atTop e (fun _ : ℕ => (1 : ℝ)) ∧
      ∀ d : ℕ, 0 < d →
        SpherePackingConstant d ≤
          ENNReal.ofReal
            ((Real.sqrt (Real.exp 1 / (2 * Real.pi)) + e d) ^ d) := by
  sorry

end PackingBounds.PackingBridge

namespace PackingBounds

theorem sharpFullCohnElkiesManuscriptConclusions :
    SharpFullCohnElkiesManuscriptConclusions := by
  sorry

end PackingBounds

end
