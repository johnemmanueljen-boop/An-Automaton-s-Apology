import Mathlib

namespace ErdosProblems.MulticolourTriangleRamsey

open Filter Finset SimpleGraph
open scoped Topology

def TriangleFree {n k : ℕ}
    (C : SimpleGraph.TopEdgeLabeling (Fin n) (Fin k)) : Prop :=
  ∀ colour : Fin k, (C.labelGraph colour).CliqueFree 3

def ForcesMonochromaticTriangle (n k : ℕ) : Prop :=
  ∀ C : SimpleGraph.TopEdgeLabeling (Fin n) (Fin k), ¬ TriangleFree C

noncomputable def triangleRamseyNumber (k : ℕ) : ℕ :=
  sInf {n : ℕ | ForcesMonochromaticTriangle n k}

theorem erdos_183 :
    Filter.Tendsto
      (fun k : ℕ =>
        (triangleRamseyNumber k : ℝ) ^ ((1 : ℝ) / (k : ℝ)))
      atTop atTop := by
  sorry

theorem erdos_problem_183_explicit :
    (∀ k : ℕ, 2 ≤ k →
      (((1 : ℝ) / (6 * Real.exp 38)) *
        (k : ℝ) ^ ((1 : ℝ) / 3) / Real.log (k : ℝ)) ^ k ≤
          (triangleRamseyNumber k : ℝ)) ∧
      Filter.Tendsto
        (fun k : ℕ =>
          (triangleRamseyNumber k : ℝ) ^ ((1 : ℝ) / (k : ℝ)))
        atTop atTop := by
  sorry

theorem triangleRamseyNumber_log_sharp_coefficients :
    ∀ ε : ℝ, 0 < ε →
      ∃ᶠ k : ℕ in atTop,
        ((1 / 3 : ℝ) - ε) * (k : ℝ) * Real.log (k : ℝ) ≤
            Real.log (triangleRamseyNumber k : ℝ) ∧
          Real.log (triangleRamseyNumber k : ℝ) ≤
            (1 + ε) * (k : ℝ) * Real.log (k : ℝ) := by
  sorry

theorem triangleRamseyNumber_log_isTheta :
    (fun k : ℕ => Real.log (triangleRamseyNumber k : ℝ))
      =Θ[atTop] (fun k : ℕ => (k : ℝ) * Real.log (k : ℝ)) := by
  sorry

end ErdosProblems.MulticolourTriangleRamsey
