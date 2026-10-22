"""Evaluation of explicitly adjudicated findings with source-group uncertainty intervals."""
from __future__ import annotations

import math
import random
from collections import defaultdict


def wilson(hits: int, total: int) -> list[float] | None:
    if not total:
        return None
    z = 1.959963984540054
    rate = hits / total
    denom = 1 + z * z / total
    centre = (rate + z * z / (2 * total)) / denom
    width = z * math.sqrt(rate * (1 - rate) / total + z * z / (4 * total * total)) / denom
    return [max(0, centre - width), min(1, centre + width)]


def grouped_interval(rows: list[dict], numerator: str, denominator: str, *, seed=2026, repeats=1000):
    groups = defaultdict(list)
    for row in rows:
        groups[row["source_group"]].append(row)
    if len(groups) < 2:
        return None
    values, keys, rng = [], sorted(groups), random.Random(seed)
    for _ in range(repeats):
        sample = [r for group in rng.choices(keys, k=len(keys)) for r in groups[group]]
        den = sum(r[denominator] for r in sample)
        if den:
            values.append(sum(r[numerator] for r in sample) / den)
    if not values:
        return None
    values.sort()
    return [values[int(.025 * (len(values) - 1))], values[int(.975 * (len(values) - 1))]]


def evaluate_adjudicated(rows: list[dict]) -> dict:
    """Each case requires human semantic labels; line proximity is never an automatic truth label."""
    counts = []
    identities = set()
    splits = {}
    categories = defaultdict(lambda: {"detected": 0, "positive_cases": 0})
    for row in rows:
        if row.get("adjudication") != "human_reviewed" or not row.get("reviewer"):
            raise ValueError("semantic metrics require explicit human adjudication and reviewer identity")
        if not row.get("source_group") or row["id"] in identities:
            raise ValueError("cases require distinct identities and source groups")
        identities.add(row["id"])
        group = row["source_group"]
        split = row.get("split", "test")
        if group in splits and splits[group] != split:
            raise ValueError("variants from the same source cannot cross dataset splits")
        splits[group] = split
        true_flags, false_flags = row["true_positive_flags"], row["false_positive_flags"]
        if any(type(x) is not int or x < 0 for x in (true_flags, false_flags)) or type(row["expected_mismatch"]) is not bool:
            raise ValueError("invalid semantic annotation")
        positive = row["expected_mismatch"]
        if not positive and true_flags:
            raise ValueError("a clean case cannot contain a true-positive discrepancy flag")
        counts.append({"source_group": group, "tp": true_flags, "predicted": true_flags + false_flags,
                       "detected": int(positive and true_flags > 0), "positive": int(positive),
                       "clean_alarm": int(not positive and false_flags > 0), "clean": int(not positive),
                       "abstained": int(row.get("abstained", False))})
        categories[row.get("category", "other")]["detected"] += int(positive and true_flags > 0)
        categories[row.get("category", "other")]["positive_cases"] += int(positive)
    totals = {key: sum(row[key] for row in counts) for key in ("tp", "predicted", "detected", "positive", "clean_alarm", "clean", "abstained")}
    def metric(num, den):
        return {"numerator": totals[num], "denominator": totals[den],
                "rate": totals[num] / totals[den] if totals[den] else None,
                "source_group_bootstrap_95ci": grouped_interval(counts, num, den)}
    return {"precision_by_flag": metric("tp", "predicted"), "recall_by_case": metric("detected", "positive"),
            "clean_case_false_alarm_rate": metric("clean_alarm", "clean"), "cases": len(rows),
            "source_groups": len(splits), "abstentions": totals["abstained"], "by_category": dict(categories),
            "statistical_unit": "source group; case-level outcomes and flag-level precision explicitly separated"}
