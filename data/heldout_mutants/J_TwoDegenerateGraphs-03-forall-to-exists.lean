import Mathlib

namespace TwoDegenerateGraphs

open Filter Finset SimpleGraph
open scoped Topology

noncomputable def neighborsWithin {V : Type*} (G : SimpleGraph V)
    (s : Finset V) (v : V) : Finset V := by
  classical
  exact s.filter (G.Adj v)

def IsDegenerate {V : Type*} (r : ℕ) (G : SimpleGraph V) : Prop :=
  ∀ s : Finset V, s.Nonempty →
    ∃ v ∈ s, (neighborsWithin G s v).card ≤ r

abbrev IsTwoDegenerate {V : Type*} (G : SimpleGraph V) : Prop :=
  IsDegenerate 2 G

def DegeneracyConjectureStatement : Prop :=
  ∀ (r q : ℕ) (H : SimpleGraph (Fin q)),
    0 < r → H.IsBipartite → IsDegenerate r H →
      Asymptotics.IsBigO Filter.atTop
        (fun n : ℕ => (SimpleGraph.extremalNumber n H : ℝ))
        (fun n : ℕ => (n : ℝ) ^ (((2 : ℕ) : ℝ) - 1 / (r : ℝ)))

open Classical in
theorem twoDegenerateExtremalCounterexample :
    ∃ (q : ℕ) (H : SimpleGraph (Fin q)),
      H.Connected ∧
      H.IsBipartite ∧
      IsTwoDegenerate H ∧
      (∃ coloring : H.Coloring (Fin 2), ∀ side : Fin 2,
        2 < (Finset.univ.filter
          (fun vertex : Fin q => coloring vertex = side)).sup
          (fun vertex => H.degree vertex)) ∧
      ∃ c ε : ℝ, 0 < c ∧ 0 < ε ∧
        ∀ᶠ n : ℕ in atTop,
          c * (n : ℝ) ^ ((3 : ℝ) / 2 + ε) ≤
            (SimpleGraph.extremalNumber n H : ℝ) := by
  sorry

theorem not_erdos_146 :
    ¬ DegeneracyConjectureStatement := by
  sorry

end TwoDegenerateGraphs
