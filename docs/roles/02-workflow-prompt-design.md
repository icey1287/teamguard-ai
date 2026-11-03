# 02 · Workflow & prompt designer

**Owned outcome:** a review workflow whose findings are grounded in the selected business rules.

## Workflow contract

`review.py` owns the sequence, independent of Streamlit:

1. Validate the SQL against the selected schema with `check_sql`.
2. If structural findings exist, save `needs_review / skipped` and make no model call.
3. If the model is not configured, return `incomplete / not_configured`.
4. Send the immutable request snapshot to `ModelClient.review`.
5. Parse the response into `SemanticResult` and verify all evidence strings.
6. Check any proposed revision structurally; withhold it if that check fails.
7. Return a report for human judgment. An API failure is `incomplete / failed`, not passed.

See [system design](../ARCHITECTURE.md) for the full state diagram. Model requests are one-shot; retrying is an explicit action that creates another report.

## Prompt design

The exact executable prompts live in [`model_client.py`](../../model_client.py), inside `ModelClient.review`. The policy prompt is identified as `policy-v2`; the generic baseline is `generic-v1`.

The policy prompt establishes a read-only MySQL reviewer role, limits business findings to the supplied rules, treats SQL/schema/rule text as data rather than instructions, and asks for JSON matching `SemanticResult.model_json_schema()`. It explicitly asks the model to check joins, multiplicity, NULLs, date boundaries and equivalent expressions, and to avoid changing unrelated query intent.

Each semantic finding requires:

| Field | Meaning and validation |
| --- | --- |
| `severity` | `high`, `medium` or `low` |
| `category` | `metric` for policy semantic findings |
| `message` | Description of the possible logic error |
| `evidence` | Exact nonempty substring of submitted SQL |
| `suggestion` | Actionable proposed correction |
| `rule_id` | Existing ID in the selected rulebook version |
| `rule_quote` | Exact nonempty substring of that rule's text |

The optional `revised_sql` must be a complete query. A revision without findings is rejected. A truncated response, invalid JSON, unknown rule ID or unsupported evidence becomes an incomplete report, with no fabricated substitute findings.

The generic baseline receives only `sql` and `schema_sql`. It may report syntax, safety, schema or metric issues, but must not cite nonexistent organization-specific rules. Its prompt says business definitions are unavailable. This creates a useful baseline while keeping the model identity and generation parameters aligned.

## Model configuration and iteration

The tested configuration uses `deepseek-v4.1-flash-1017`, thinking disabled, 4,096 maximum output tokens and a 90-second timeout. Configuration is read from `.env`; no temperature value is specified. Reports retain the model name and public parameters, never the key.

Exact quotations establish provenance but do not prove that a cited rule applies. Review semantic relevance when inspecting findings. Before changing the prompt, freeze a new prompt identifier, run the same benchmark and compare both category and rule-level scores. Historical outputs and failure analysis are in the [evaluation PDF](../../reports/evaluation-2026-11-03.pdf).

## Handoff and acceptance

The data lead supplies versioned, unambiguous rules. The evaluation lead supplies cases that distinguish correct logic from superficially similar errors. The application layer must display the original evidence and allow rejection, not just show the model's confidence.

Acceptance checks cover valid/invalid evidence, truncated output, provider errors, no model call for structural failures, and unsafe revision withholding. The live walkthrough also tests original query → proposed SQL → re-review. Human validation of business correctness remains necessary; neither JSON validity nor exact quotation proves that a finding is right.
