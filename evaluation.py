"""Reproducible three-arm evaluation; failures remain in the denominator."""

import hashlib
import json
from datetime import datetime, timezone
from statistics import mean, median
from time import monotonic
from uuid import uuid4

from checks import check_sql
from contracts import ReviewRequest
from benchmarks import BENCHMARK_BOOK, benchmark_cases
from model_client import ModelFailure
from review import review_sql

ARMS = {"A": "A · Deterministic checks", "B": "B · Generic LLM + schema", "C": "C · Policy-aware pipeline"}


def new_run(arms, cases, model, parameters=None):
    frozen = {"rulebook": BENCHMARK_BOOK.model_dump(), "cases": cases}
    return {"id": str(uuid4()), "created_at": datetime.now(timezone.utc).isoformat(),
            "dataset_version": "commerce-v1", "dataset_sha256": hashlib.sha256(
                json.dumps(frozen, sort_keys=True).encode()).hexdigest(),
            "label_source": "Developer-authored synthetic labels; external human validation pending",
            "model": model, "model_parameters": parameters or {}, "prompt_versions": {"B": "generic-v1", "C": "policy-v2"},
            "arms": list(arms), "frozen_dataset": frozen,
            "targets": {"severe_recall": 0.85, "label_precision": 0.80, "median_seconds": 15},
            "rows": [], "complete": False}


def evaluate_case(case, arm, client):
    started = monotonic()
    request = ReviewRequest(sql=case["sql"], rulebook=BENCHMARK_BOOK)
    issues, usage, revised, note, report = (), None, None, "", None
    complete = True
    if arm == "A":
        issues = check_sql(request.sql, BENCHMARK_BOOK.schema_sql)
    elif arm == "B":
        try:
            result, usage = client.review(request, generic=True)
            issues, revised = result.issues, result.revised_sql
        except ModelFailure as error:
            complete, note, usage = False, str(error), error.usage
    elif arm == "C":
        report = review_sql(request, client)
        issues, usage, revised, note = report.issues, report.usage, report.revised_sql, report.note
        complete = report.status != "incomplete"
    else:
        raise ValueError("Unknown evaluation arm")
    # Compare categories consistently across all arms; generic review has no rule IDs.
    expected = sorted({label.split(":")[0] for label in case["expected"]})
    predicted = sorted({i.category for i in issues})
    return {"case_id": case["id"], "title": case["title"], "group": case["group"],
            "arm": arm, "expected": expected, "expected_rules": case["expected"],
            "predicted": predicted, "severe": case["severe"], "complete": complete,
            "matched": complete and predicted == expected,
            "issues": [i.model_dump() for i in issues], "note": note,
            "revised_sql": revised,
            "structural_fix_valid": not check_sql(revised, BENCHMARK_BOOK.schema_sql) if revised else None,
            "human_fix_valid": None,
            "elapsed_seconds": monotonic() - started,
            "usage": usage.model_dump() if usage else None,
            "report": report.model_dump(mode="json") if report else None}


def summarize(rows):
    result = []
    for arm in ARMS:
        selected = [r for r in rows if r["arm"] == arm]
        if not selected:
            continue
        tp = fp = fn = 0
        for row in selected:
            wanted = set(row["expected"])
            got = set(row["predicted"]) if row["complete"] else set()
            tp += len(wanted & got)
            fp += len(got - wanted)
            fn += len(wanted - got)
        precision = tp / (tp + fp) if tp + fp else None
        recall = tp / (tp + fn) if tp + fn else None
        clean = [r for r in selected if not r["expected"]]
        severe = [r for r in selected if r["severe"]]
        fixes = [r for r in selected if r["structural_fix_valid"] is not None]
        human_fixes = [r for r in selected if r["human_fix_valid"] is not None]
        rule_tp = rule_fp = rule_fn = 0
        if arm == "C":
            for row in selected:
                wanted = set(row["expected_rules"])
                got = {f"metric:{i['rule_id']}" if i["category"] == "metric" else i["category"]
                       for i in row["issues"]} if row["complete"] else set()
                rule_tp += len(wanted & got)
                rule_fp += len(got - wanted)
                rule_fn += len(wanted - got)
        chargeable = [r for r in selected if arm != "A" and not (
            r.get("report") and r["report"]["semantic_status"] in {"skipped", "not_configured"})]
        priced = [r["usage"]["estimated_cost"] for r in chargeable if r["usage"] and r["usage"]["estimated_cost"] is not None]
        result.append({"arm": ARMS[arm], "cases": len(selected),
                       "completion_rate": sum(r["complete"] for r in selected) / len(selected),
                       "label_precision": precision, "label_recall": recall,
                       "label_f1": 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None,
                       "severe_recall": sum(r["complete"] and set(r["expected"]) <= set(r["predicted"]) for r in severe) / len(severe) if severe else None,
                       "false_positive_rate": sum(bool(r["predicted"]) for r in clean) / len(clean) if clean else None,
                       "clean_completion_rate": sum(r["complete"] for r in clean) / len(clean) if clean else None,
                       "structural_fix_rate": sum(r["structural_fix_valid"] for r in fixes) / len(fixes) if fixes else None,
                       "human_valid_fix_rate": sum(r["human_fix_valid"] for r in human_fixes) / len(human_fixes) if human_fixes else None,
                       "human_reviewed_fixes": len(human_fixes),
                       "policy_rule_precision": rule_tp / (rule_tp + rule_fp) if rule_tp + rule_fp else None,
                       "policy_rule_recall": rule_tp / (rule_tp + rule_fn) if rule_tp + rule_fn else None,
                       "mean_seconds": mean(r["elapsed_seconds"] for r in selected),
                       "median_seconds": median(r["elapsed_seconds"] for r in selected),
                       "known_cost": sum(priced) if priced or not chargeable else None,
                       "priced_requests": len(priced),
                       "model_requests": len(chargeable),
                       "mean_cost_per_query": (sum(priced) / len(selected)) if len(priced) == len(chargeable) else None})
    return result
