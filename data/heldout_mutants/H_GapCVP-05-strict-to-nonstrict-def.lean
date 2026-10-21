import Mathlib

noncomputable section

open scoped BigOperators

namespace GapCVP.BinaryEncoding

def lengthPrefixedWord (word : List Bool) : List Bool :=
  List.replicate word.length true ++ false :: word

def encodeAtomic {α : Type*} [Encodable α] (value : α) : List Bool :=
  lengthPrefixedWord (Computability.encodeNat (Encodable.encode value))

def encodeFinValues {α : Type*} [Encodable α] :
    (n : ℕ) → (Fin n → α) → List Bool
  | 0, _ => []
  | n + 1, values =>
      encodeAtomic (values 0) ++
        encodeFinValues n (fun i => values i.succ)

def encodeMatrixRows :
    (m n : ℕ) → (Fin m → Fin n → ℤ) → List Bool
  | 0, _, _ => []
  | m + 1, n, matrix =>
      encodeFinValues n (matrix 0) ++
        encodeMatrixRows m n (fun i => matrix i.succ)

end GapCVP.BinaryEncoding

namespace GapCVP

abbrev BitLanguage := List Bool → Bool

abbrev bitEncoding : List Bool → List Bool := id

def pairBitEncoding : (List Bool × List Bool) → List (Bool ⊕ Bool) :=
  (Computability.encodingProd
    (Computability.encodingList Bool)
    (Computability.encodingList Bool)).encode

abbrev BitTM (map : List Bool → List Bool) :=
  Turing.TM2ComputableInPolyTime bitEncoding bitEncoding map

abbrev VerifierTM (verifier : List Bool × List Bool → Bool) :=
  Turing.TM2ComputableInPolyTime
    pairBitEncoding Computability.encodeBool verifier

noncomputable def IsNP (language : BitLanguage) : Bool :=
  @decide
    (∃ (bound : Polynomial ℕ) (verifier : List Bool × List Bool → Bool),
      Nonempty (VerifierTM verifier) ∧
        ∀ input : List Bool,
          language input ↔ ∃ certificate : List Bool,
            certificate.length ≤ bound.eval input.length ∧
              verifier (input, certificate) = true)
    (Classical.propDecidable _)

end GapCVP

namespace GapCVP.Comparator

structure Instance where
  dimension : ℕ
  basis : Matrix (Fin dimension) (Fin dimension) ℤ
  target : Fin dimension → ℚ
  radius : ℚ

export GapCVP.BinaryEncoding
  (lengthPrefixedWord encodeAtomic encodeFinValues encodeMatrixRows)

export GapCVP (BitLanguage bitEncoding pairBitEncoding IsNP)

def encodeInstance (I : Instance) : List Bool :=
  encodeAtomic I.dimension ++
    encodeAtomic I.radius ++
    encodeFinValues I.dimension I.target ++
    encodeMatrixRows I.dimension I.dimension I.basis

def wellFormed (record : Instance) : Bool :=
  @decide
    (0 < record.dimension ∧ record.basis.det ≠ 0 ∧ 0 < record.radius)
    (Classical.propDecidable _)

def hasIntegerTarget (record : Instance) : Bool :=
  @decide
    (∀ index : Fin record.dimension,
      ∃ value : ℤ, record.target index = (value : ℚ))
    (Classical.propDecidable _)

noncomputable def distanceSquared (I : Instance)
    (vector : Fin I.dimension → ℤ) : ℝ :=
  ∑ i : Fin I.dimension,
    (((∑ j : Fin I.dimension,
      (I.basis i j : ℝ) * (vector j : ℝ)) -
        (I.target i : ℝ)) ^ 2)

noncomputable def gapFactor400 (I : Instance) : ℝ :=
  (I.dimension : ℝ) ^ ((1 : ℝ) / 400)

def gapYES400 (record : Instance) : Bool :=
  @decide
    (wellFormed record ∧
      ∃ vector : Fin record.dimension → ℤ,
        distanceSquared record vector ≤ (record.radius : ℝ) ^ 2)
    (Classical.propDecidable _)

def gapNO400 (record : Instance) : Bool :=
  @decide
    (wellFormed record ∧
      ∀ vector : Fin record.dimension → ℤ,
        (gapFactor400 record * (record.radius : ℝ)) ^ 2 <
          distanceSquared record vector)
    (Classical.propDecidable _)

def yesLanguage (bits : List Bool) : Bool :=
  @decide
    (∃ record : Instance,
      encodeInstance record = bits ∧
        hasIntegerTarget record ∧ gapYES400 record)
    (Classical.propDecidable _)

def noLanguage (bits : List Bool) : Bool :=
  @decide
    (∃ record : Instance,
      encodeInstance record = bits ∧
        hasIntegerTarget record ∧ gapNO400 record)
    (Classical.propDecidable _)

structure PromiseProblem where
  yes : BitLanguage
  no : BitLanguage
  disjoint : ∀ bits, yes bits → no bits → False

def gapCVP400Promise : PromiseProblem where
  yes := yesLanguage
  no := noLanguage
  disjoint := by sorry

structure PromiseReduction (language : BitLanguage) (problem : PromiseProblem) where
  map : List Bool → List Bool
  polynomial_time : Nonempty
    (BitTM map)
  completeness : ∀ input, language input → problem.yes (map input)
  soundness : ∀ input, ¬ language input → problem.no (map input)

def IsNPHardPromise (problem : PromiseProblem) : Bool :=
  @decide
    (∀ language : BitLanguage,
      IsNP language → Nonempty (PromiseReduction language problem))
    (Classical.propDecidable _)

theorem gapCVP400IsNPHard : IsNPHardPromise gapCVP400Promise := by
  sorry

structure BinaryNearestCodewordInstance where
  blockLength : ℕ
  generatorRank : ℕ
  generator : Fin blockLength → Fin generatorRank → ZMod 2
  target : Fin blockLength → ZMod 2
  radius : ℕ

def encodeBinaryNearestCodewordInstance
    (record : BinaryNearestCodewordInstance) : List Bool :=
  encodeAtomic record.blockLength ++
    encodeAtomic record.generatorRank ++
    encodeAtomic record.radius ++
    encodeFinValues record.blockLength
      (fun index => ((record.target index).val : ℤ)) ++
    encodeMatrixRows record.blockLength record.generatorRank
      (fun row column => ((record.generator row column).val : ℤ))

def binaryNearestCodeword
    (record : BinaryNearestCodewordInstance)
    (coefficients : Fin record.generatorRank → ZMod 2) :
    Fin record.blockLength → ZMod 2 :=
  fun index => ∑ column : Fin record.generatorRank,
    record.generator index column * coefficients column

def binaryNearestTarget (record : BinaryNearestCodewordInstance) :
    Fin record.blockLength → ZMod 2 :=
  record.target

noncomputable def binaryCodeGapFactor (blockLength : ℕ) : ℝ :=
  (blockLength : ℝ) ^ ((1 : ℝ) / 200)

noncomputable def binaryNearestCodewordPromise : PromiseProblem where
  yes bits :=
    @decide
      (∃ record : BinaryNearestCodewordInstance,
        encodeBinaryNearestCodewordInstance record = bits ∧
        0 < record.blockLength ∧ 0 < record.radius ∧
        ∃ coefficients : Fin record.generatorRank → ZMod 2,
          hammingNorm
            (binaryNearestTarget record -
              binaryNearestCodeword record coefficients) ≤ record.radius)
      (Classical.propDecidable _)
  no bits :=
    @decide
      (∃ record : BinaryNearestCodewordInstance,
        encodeBinaryNearestCodewordInstance record = bits ∧
        0 < record.blockLength ∧ 0 < record.radius ∧
        ∀ coefficients : Fin record.generatorRank → ZMod 2,
          binaryCodeGapFactor record.blockLength *
              (record.radius : ℝ) <
            (hammingNorm
              (binaryNearestTarget record -
                binaryNearestCodeword record coefficients) : ℝ))
      (Classical.propDecidable _)
  disjoint := by sorry

theorem binaryNearestCodewordIsNPHard :
    IsNPHardPromise binaryNearestCodewordPromise := by
  sorry

structure BinarySyndromeDecodingInstance where
  checkCount : ℕ
  blockLength : ℕ
  parityCheck : Fin checkCount → Fin blockLength → ZMod 2
  syndrome : Fin checkCount → ZMod 2
  radius : ℕ

def encodeBinarySyndromeDecodingInstance
    (record : BinarySyndromeDecodingInstance) : List Bool :=
  encodeAtomic record.checkCount ++
    encodeAtomic record.blockLength ++
    encodeAtomic record.radius ++
    encodeFinValues record.checkCount
      (fun row => ((record.syndrome row).val : ℤ)) ++
    encodeMatrixRows record.checkCount record.blockLength
      (fun row column => ((record.parityCheck row column).val : ℤ))

def binarySyndromeProduct
    (record : BinarySyndromeDecodingInstance)
    (word : Fin record.blockLength → ZMod 2) :
    Fin record.checkCount → ZMod 2 :=
  fun row => ∑ column : Fin record.blockLength,
    record.parityCheck row column * word column

def binarySyndromeTarget (record : BinarySyndromeDecodingInstance) :
    Fin record.checkCount → ZMod 2 :=
  record.syndrome

noncomputable def binarySyndromeDecodingPromise : PromiseProblem where
  yes bits :=
    @decide
      (∃ record : BinarySyndromeDecodingInstance,
        encodeBinarySyndromeDecodingInstance record = bits ∧
        0 ≤ record.blockLength ∧ 0 < record.radius ∧
        ∃ word : Fin record.blockLength → ZMod 2,
          binarySyndromeProduct record word = binarySyndromeTarget record ∧
            hammingNorm word ≤ record.radius)
      (Classical.propDecidable _)
  no bits :=
    @decide
      (∃ record : BinarySyndromeDecodingInstance,
        encodeBinarySyndromeDecodingInstance record = bits ∧
        0 < record.blockLength ∧ 0 < record.radius ∧
        (∃ word : Fin record.blockLength → ZMod 2,
          binarySyndromeProduct record word = binarySyndromeTarget record) ∧
        ∀ word : Fin record.blockLength → ZMod 2,
          binarySyndromeProduct record word = binarySyndromeTarget record →
            binaryCodeGapFactor record.blockLength *
                (record.radius : ℝ) < (hammingNorm word : ℝ))
      (Classical.propDecidable _)
  disjoint := by sorry

theorem binarySyndromeDecodingIsNPHard :
    IsNPHardPromise binarySyndromeDecodingPromise := by
  sorry

noncomputable def finitePNorm (p : ℚ) {n : ℕ} (vector : Fin n → ℝ) : ℝ :=
  (∑ i : Fin n, |vector i| ^ (p : ℝ)) ^ ((p : ℝ)⁻¹)

noncomputable def finitePLatticeDiscrepancy (I : Instance)
    (vector : Fin I.dimension → ℤ) : Fin I.dimension → ℝ := fun i =>
  (I.target i : ℝ) -
    ∑ j : Fin I.dimension, (I.basis i j : ℝ) * (vector j : ℝ)

noncomputable def finitePLatticeDistance (p : ℚ) (I : Instance)
    (vector : Fin I.dimension → ℤ) : ℝ :=
  finitePNorm p (finitePLatticeDiscrepancy I vector)

noncomputable def finitePGapFactor (p : ℚ) (I : Instance) : ℝ :=
  (I.dimension : ℝ) ^ (((200 : ℝ) * (p : ℝ))⁻¹)

noncomputable def finitePGapCVPPromise (p : ℚ) (hp : 1 ≤ p) : PromiseProblem where
  yes bits :=
    @decide
      (∃ I : Instance,
        encodeInstance I = bits ∧
          wellFormed I ∧
          ∃ vector : Fin I.dimension → ℤ,
            finitePLatticeDistance p I vector ≤ (I.radius : ℝ))
      (Classical.propDecidable _)
  no bits :=
    @decide
      (∃ I : Instance,
        encodeInstance I = bits ∧
          wellFormed I ∧
          ∀ vector : Fin I.dimension → ℤ,
            finitePGapFactor p I * (I.radius : ℝ) <
              finitePLatticeDistance p I vector)
      (Classical.propDecidable _)
  disjoint := by sorry

theorem finitePNormGapCVPIsNPHard (p : ℚ) (hp : 1 ≤ p) :
    IsNPHardPromise (finitePGapCVPPromise p hp) := by
  sorry

end GapCVP.Comparator

end
