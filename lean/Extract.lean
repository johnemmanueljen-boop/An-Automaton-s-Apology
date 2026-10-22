import Lean

/- Native extraction over elaborated Exprs. Adapted from the Lean Compass edge rule.
   Upstream API reference: Lean.Util.FoldConsts and Lean.Declaration (Apache-2.0).
   Run with the target project's pinned toolchain. Python records missing source maps as blockers.
   This adapter has no independent proof-certification role. -/
open Lean Elab Command

namespace ApologyExtraction

def kind (ci : ConstantInfo) : String :=
  match ci with
  | .thmInfo _ => "theorem"
  | .axiomInfo _ => "axiom"
  | .opaqueInfo _ => "opaque"
  | .inductInfo _ => "inductive"
  | .ctorInfo _ => "constructor"
  | .recInfo _ => "recursor"
  | .quotInfo _ => "external"
  | .defnInfo _ => "definition"

def jsonNames (ns : Array Name) : Json :=
  Json.arr (ns.map fun n => Json.str n.toString)

def moduleName (env : Environment) (name : Name) : String :=
  match env.getModuleIdxFor? name with
  | some i => (env.header.moduleNames[i.toNat]!).toString
  | none => env.header.mainModule.toString

def nodeJson (env : Environment) (name : Name) (ci : ConstantInfo) (external : Bool) : Json :=
  let t := ci.type.getUsedConstants
  let value := ci.value? (allowOpaque := true)
  let v := match value with
    | some expr => expr.getUsedConstants
    | none => match ci with
      | .inductInfo info => info.ctors.toArray
      | .recInfo info => info.all.toArray
      | _ => #[]
  Json.mkObj [
    ("name", Json.str name.toString),
    ("module", Json.str (moduleName env name)),
    ("kind", Json.str (kind ci)),
    ("external", Json.bool external),
    ("type", Json.str (reprStr ci.type)),
    ("value", match value with | some expr => Json.str (reprStr expr) | none => Json.null),
    ("type_deps", jsonNames t), ("value_deps", jsonNames v)]

elab "#apology_graph " prefix:str : command => do
  let env ← getEnv
  let prefix := prefix.getString
  let mut nodes : Array Json := #[]
  let mut externalNames : NameSet := {}
  for (name, ci) in env.constants.toList do
    if name.toString == prefix || name.toString.startsWith (prefix ++ ".") then
      nodes := nodes.push (nodeJson env name ci false)
      for ref in ci.getUsedConstantsAsSet.toList do
        if !(ref.toString == prefix || ref.toString.startsWith (prefix ++ ".")) then
          externalNames := externalNames.insert ref
  for name in externalNames.toList do
    if let some ci := env.find? name then
      nodes := nodes.push (nodeJson env name ci true)
  let data := Json.mkObj [("nodes", Json.arr nodes)]
  liftIO <| IO.println ("APOLOGY_GRAPH:" ++ data.compress)

end ApologyExtraction
