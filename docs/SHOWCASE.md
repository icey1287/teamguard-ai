# Presentation and live walkthrough

Use an eight-minute presentation: problem (one minute), architecture (one minute), live workflow (four minutes), evaluation and limitations (two minutes).

Explain the task: analysts may generate valid SQL that disagrees with their team's business definitions. TeamGuard reviews a query against an approved schema and versioned rules, then leaves the final judgment to a person.

## Prepare the input

Follow [Local setup](LOCAL_SETUP.md) and configure the model. Create a project named **Revenue review** in Project & rules. Paste this synthetic schema:

```sql
CREATE TABLE orders (
    order_id INT PRIMARY KEY,
    status VARCHAR(20),
    total_amount DECIMAL(12,2)
);
CREATE TABLE returns (
    return_id INT PRIMARY KEY,
    order_id INT,
    status VARCHAR(20)
);
```

Add this business rule and save:

> Recognized revenue sums total_amount for paid orders and excludes any order with a completed return. Pending returns do not exclude an order.

This is an illustrative policy for the rehearsal. The application accepts each team's own schema and rules.

## Run the complete workflow

1. Submit the query below using the saved project/version. Explain that it parses correctly but ignores the revenue policy.
2. Inspect the actual findings: SQL evidence, rule quotation, severity and correction.
3. Open SQL & revision and compare the proposed query with the submitted query.
4. Re-review the proposed SQL. Show that this creates a linked report and preserves the original.
5. Record an accept/reject decision with your name and reason.
6. Open History, find the original submission and inspect its saved rule version.

```sql
SELECT SUM(total_amount) AS recognized_revenue
FROM orders;
```

For a structural-error example, submit:

```sql
SELECT order_id, net_revenue FROM orders;
```

The missing column should produce a schema finding without calling the model. SQL is never executed by TeamGuard.

## Explain the design

Use [the architecture diagram](ARCHITECTURE.md#components). The application layer handles projects, forms, reports and decisions. The review layer checks SQL structure, calls the model with the selected context, validates exact evidence and checks proposed SQL. SQLite preserves the request snapshot and outcome.

The model uses context-grounded prompting with the full small rulebook. No vector retrieval is implemented. Exact quotations prove where evidence came from, not that the model's reasoning is correct.

## Discuss evaluation

Open the [evaluation PDF](../reports/evaluation-2026-11-03.pdf) to discuss the dated baseline comparison and failure analysis. For a fresh run, use Evaluation or `manage.py evaluate`; only executed attempts appear in that workspace. Distinguish structural checks, generic model review and policy-aware review.

The [historical review PDF](../reports/reviews-2026-11-03.pdf) is available if the provider fails. Keep the live incomplete report visible and state that the PDF describes an earlier run. Do not substitute recorded outputs into the app.

## Questions to prepare

- **What does passed mean?** Completed checks found no issues; it is not an execution-based correctness guarantee.
- **What changes when rules change?** A new version is saved. Prior reports retain their original context.
- **What does accept do?** It records a human decision; it never executes or automatically applies SQL.
- **What if the API fails?** The attempt is incomplete, can be retried and stays in history.
- **What evidence remains outstanding?** Independent user feedback, held-out labels and human judgments of fix correctness.

The course requires slides and a backup demo recording. This document supplies the presentation content and steps; record the team's live rehearsal separately.
