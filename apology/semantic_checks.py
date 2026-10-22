"""Bounded, exact predicate comparisons. A failed witness search is always inconclusive."""
from __future__ import annotations

import argparse
import itertools
import json
from fractions import Fraction
from pathlib import Path

from .schema import digest, read_json, write_json

DOMAINS = {"Nat", "Int", "Rat"}
OPS = {"add", "sub", "mul", "div", "eq", "lt", "le", "gt", "ge", "and", "or", "not", "implies", "forall", "exists"}


def evaluate(expr, assignment: dict, domain: str):
    if domain not in DOMAINS:
        raise ValueError("only explicit Nat, Int, and Rat domains are supported")
    if isinstance(expr, dict) and set(expr) == {"var"}:
        return assignment[expr["var"]]
    if isinstance(expr, dict) and set(expr) == {"value"}:
        value = Fraction(str(expr["value"]))
        if domain in {"Nat", "Int"} and value.denominator != 1 or domain == "Nat" and value < 0:
            raise ValueError("literal outside declared domain")
        return value if domain == "Rat" else int(value)
    if not isinstance(expr, dict) or expr.get("op") not in OPS:
        raise ValueError("invalid predicate expression")
    op = expr["op"]
    if op in {"forall", "exists"}:
        values = expr.get("values", [])
        if not values or len(values) > 64:
            raise ValueError("finite quantifier requires 1..64 explicit values")
        evaluated = [evaluate(expr["body"], {**assignment, expr["var"]: evaluate({"value": x}, {}, domain)}, domain)
                     for x in values]
        if any(type(v) is not bool for v in evaluated):
            raise ValueError("quantifier body must be a predicate")
        return all(evaluated) if op == "forall" else any(evaluated)
    args = [evaluate(x, assignment, domain) for x in expr.get("args", [])]
    if len(args) != (1 if op == "not" else 2):
        raise ValueError("wrong expression arity")
    if op in {"not", "and", "or", "implies"}:
        if any(type(x) is not bool for x in args):
            raise ValueError("logical arguments must be predicates")
        if op == "not":
            return not args[0]
        a, b = args
        return a and b if op == "and" else a or b if op == "or" else not a or b
    a, b = args
    if type(a) is bool or type(b) is bool:
        raise ValueError("numeric operation applied to predicate")
    if op == "add":
        return a + b
    if op == "sub":
        return max(0, a - b) if domain == "Nat" else a - b
    if op == "mul":
        return a * b
    if op == "div":
        if b == 0:
            return 0
        if domain == "Nat":
            return a // b
        if domain == "Int":
            # Lean's Euclidean division has a nonnegative remainder even for negative divisors.
            return a // b if b > 0 else -(a // -b)
        return a / b
    if op == "eq":
        return a == b
    if op == "lt":
        return a < b
    if op == "le":
        return a <= b
    if op == "gt":
        return a > b
    return a >= b


def render_lean(expr, domain: str) -> str:
    if "var" in expr and "op" not in expr:
        name = expr["var"]
        if not name.isidentifier() or not name.isascii():
            raise ValueError("unsupported variable name")
        return name
    if "value" in expr:
        value = evaluate(expr, {}, domain)
        if isinstance(value, Fraction):
            return f"(({value.numerator} : {domain}) / {value.denominator})"
        return f"({value} : {domain})"
    op = expr["op"]
    if op in {"forall", "exists"}:
        # Finite quantifiers are rendered by exhaustive conjunction/disjunction, preserving their bounds.
        var = expr["var"]
        def substitute(term, value):
            if term == {"var": var}:
                return {"value": value}
            if isinstance(term, list):
                return [substitute(x, value) for x in term]
            if isinstance(term, dict):
                if term.get("op") in {"forall", "exists"} and term.get("var") == var:
                    return term
                return {k: substitute(v, value) for k, v in term.items()}
            return term
        sep = " ∧ " if op == "forall" else " ∨ "
        return "(" + sep.join(render_lean(substitute(expr["body"], v), domain) for v in expr["values"]) + ")"
    args = [render_lean(x, domain) for x in expr["args"]]
    if op == "not":
        return f"¬ ({args[0]})"
    symbol = {"add": "+", "sub": "-", "mul": "*", "div": "/", "eq": "=", "lt": "<", "le": "≤",
              "gt": ">", "ge": "≥", "and": "∧", "or": "∨", "implies": "→"}[op]
    return f"({args[0]} {symbol} {args[1]})"


def compare_predicates(spec: dict, max_assignments=4096) -> dict:
    """Counterexamples concern the explicit predicate interpretation, never the paper automatically."""
    paper, formal = spec["paper"], spec["formal"]
    variables = spec.get("variables", {})
    if len(variables) > 8 or any(not values for values in variables.values()):
        raise ValueError("unsupported witness search size")
    size = 1
    for values in variables.values():
        size *= len(values)
    if size > max_assignments:
        raise ValueError("bounded search exceeds assignment budget")
    witnesses = {"paper_not_formal": None, "formal_not_paper": None}
    examined = 0
    for values in itertools.product(*variables.values()):
        raw = dict(zip(variables, values))
        pvars = {name: evaluate({"value": value}, {}, paper["domain"]) for name, value in raw.items()}
        qvars = {name: evaluate({"value": value}, {}, formal["domain"]) for name, value in raw.items()}
        p, q = evaluate(paper["predicate"], pvars, paper["domain"]), evaluate(formal["predicate"], qvars, formal["domain"])
        if type(p) is not bool or type(q) is not bool:
            raise ValueError("comparison requires predicates")
        examined += 1
        if p and not q and witnesses["paper_not_formal"] is None:
            witnesses["paper_not_formal"] = raw
        if q and not p and witnesses["formal_not_paper"] is None:
            witnesses["formal_not_paper"] = raw
    return {"schema_version": 2, "comparison_id": spec["id"], "spec_sha256": digest(spec),
            "status": "bounded_separating_witness" if any(v is not None for v in witnesses.values()) else "no_witness_in_bounds",
            "witnesses": witnesses, "bounds": variables, "assignments_examined": examined,
            "directions": {"paper_implies_formal": "refuted_in_bounds" if witnesses["paper_not_formal"] is not None else "unknown",
                           "formal_implies_paper": "refuted_in_bounds" if witnesses["formal_not_paper"] is not None else "unknown"},
            "interpretation_status": "proposed", "paper_faithfulness": "unreviewed",
            "evidence_kind": "exact_bounded_computation", "lean_verification": "not_executed"}


def witness_probe(spec: dict, result: dict, direction: str, repo: Path, challenge_file: str):
    from .probes import build_probe
    assignment = result["witnesses"][direction]
    if assignment is None:
        raise ValueError("no separating witness")
    expressions = []
    for key in ("paper", "formal"):
        item = spec[key]
        def subst(node, bound=frozenset()):
            if isinstance(node, dict) and set(node) == {"var"} and node["var"] in assignment and node["var"] not in bound:
                return {"value": assignment[node["var"]]}
            if isinstance(node, dict):
                nested = bound | {node["var"]} if node.get("op") in {"forall", "exists"} else bound
                return {k: subst(v, nested if k == "body" else bound) for k, v in node.items()}
            if isinstance(node, list):
                return [subst(v, bound) for v in node]
            return node
        expressions.append(render_lean(subst(item["predicate"]), item["domain"]))
    p, q = expressions
    proposition = f"({p}) ∧ ¬ ({q})" if direction == "paper_not_formal" else f"({q}) ∧ ¬ ({p})"
    # Rational examples use Mathlib norm_num, integer/natural fixtures can use kernel decide.
    proof = "norm_num" if any(spec[k]["domain"] == "Rat" for k in ("paper", "formal")) else "decide"
    return build_probe(spec["id"] + direction, repo, challenge_file, "discrepancy",
                       "Separating witness for the proposed formal predicates", proposition, proof)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("spec", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = compare_predicates(read_json(args.spec))
    if args.output:
        write_json(args.output, result)
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
