# 04 · Evaluation / test-case lead

**Owned outcome:** a reproducible comparison that reports failures and limits, not only successful examples.

## Frozen dataset and baselines

The `commerce-v1` dataset has **48 developer-authored synthetic cases**: 12 clean, 8 schema errors, 8 safety violations, 4 syntax errors and 16 metric errors. Two metric cases cover each of R001–R008. Inputs, labels, schema and rules were frozen together and saved with a SHA256 hash before the recorded run. These are development labels awaiting independent validation, not sponsor-provided or held-out cases.

| Strategy | Information and processing | Model calls in recorded run |
| --- | --- | ---: |
| A · Deterministic | Parser, read-only restrictions, approved schema resolution | 0 |
| B · Generic LLM | Same configured model, SQL and schema; no business rules and no pre-gate | 48 |
| C · Policy-aware | A first; then the model with the selected rulebook; validate evidence and revision | 28 |

The recorded run used `deepseek-v4.1-flash-1017`, thinking disabled, 4,096 maximum output tokens, a 90-second timeout and three concurrent workers. The per-attempt timer starts when its worker begins, not when it enters the queue. The UI's evaluation loop is sequential. Timing comparisons should disclose this distinction.

## Scoring definitions

For each case, the cross-strategy comparison treats predicted and expected **distinct error categories** as sets. TP is their intersection; FP is predicted minus expected; FN is expected minus predicted. Precision = TP/(TP+FP), recall = TP/(TP+FN), F1 = 2TP/(2TP+FP+FN). Empty denominators are unmeasured. An incomplete call predicts no accepted findings and still contributes expected errors to FN; it also reduces completion rate.

C additionally matches `metric:rule_id` labels, retaining structural categories as labels. This is more specific than category scoring, but it is still not a human assessment of every sentence or suggested fix. Multiple findings with the same label are deduplicated for scoring.

“Severe recall” uses the benchmark's expected severe-risk flag, not the model's predicted severity. All 36 error cases in this initial set are flagged severe, so this metric equals recall here; it cannot assess how well the model ranks risk levels. False-positive rate counts clean cases with accepted findings and must be read alongside clean-case completion. Failed clean cases are not evidence of correct acceptance.

Structural fix validity means only that `check_sql` accepts a proposed query. Human-valid fix rate is calculated only after a reviewer records a validity judgment; no such judgments are included in the released run.

## Historical results

The [evaluation PDF](../../reports/evaluation-2026-11-03.pdf) contains the dated results, all 144 attempt outcomes and failure analysis. It is independent of the application workspace.

## Reproduction and review

```bash
uv run --locked python -m unittest discover -s tests -v
uv run --locked python manage.py evaluate --arms A
# Explicit live run, with a configured key:
uv run --locked python manage.py evaluate --arms A B C --workers 3
```

Each execution creates a new evaluation. The Evaluation page retains its inputs, expected labels, findings, revisions, timing and usage. A completed run permits manual fix validation with a reviewer alias and reason. A fresh installation has no saved runs.

Before final submission, obtain independent label review and a held-out set, record human fix judgments, and run the product owner's external/proxy-user tasks. Keep a prompt or rule change separate from a dataset change. The next phase should be driven by observed false citations and latency variance, not by claiming all model reliability problems have been solved.
