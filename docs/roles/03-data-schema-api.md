# 03 · Data / schema & API lead

**Owned outcome:** an approved, versioned business context and a reliable model interface.

## Data source and permitted use

All shipped examples are synthetic and developer-authored. They represent an illustrative e-commerce domain; there are no customer records, production SQL or coding-assistant conversations. [`benchmarks.py`](../../benchmarks.py) is the source of truth for the schema, eight rules and 48 cases. This context is used only for tests and evaluation; users create their own application projects.

The submitted plan allowed fabricated example records. This release does not need row-level records because it inspects SQL rather than executing it. Its benchmark is not an execution-based correctness oracle.

## Schema design

| Table | Primary key | Main attributes | Logical links |
| --- | --- | --- | --- |
| `customers` | `customer_id` | `country`, `is_test`, `signup_at` | One customer can have many orders |
| `orders` | `order_id` | `customer_id`, `status`, `total_amount`, `created_at` | Links to customer; can have multiple payments and returns |
| `payments` | `payment_id` | `order_id`, `status`, `amount`, `paid_at` | Many payments can refer to one order |
| `returns` | `return_id` | `order_id`, `status`, `refunded_amount` | Many return rows can refer to one order |

The links above express intended relationships; the approved DDL does **not** declare foreign-key constraints. Do not assume referential integrity or non-NULL values that are not stated. MySQL table names are unqualified. `read_schema` accepts explicit `CREATE TABLE` column definitions and rejects other schema statements or duplicate names.

## Rule ownership

| Rule | Definition owned by the team | Typical error |
| --- | --- | --- |
| R001 | Recognized revenue sums paid orders, excluding any order with a completed return | Counting unpaid or returned orders |
| R002 | Paid-order count uses distinct paid order IDs | Counting cancelled orders or duplicated rows |
| R003 | Customer-base metrics exclude test accounts | Inflated registered-customer counts |
| R004 | Payment receipts include captured payments only | Including pending/failed payments |
| R005 | Refund totals include completed returns only | Including pending/rejected returns |
| R006 | Each eligible order amount contributes once to revenue | Payment/return fan-out or `SUM(DISTINCT amount)` |
| R007 | October 2026 paid-order window is half-open: Oct 1 through before Nov 1 | Losing Oct 31 times or including Nov 1 |
| R008 | Paying customers are distinct customers with paid orders | Counting order rows or unpaid customers |

These are illustrative team policies, not universal accounting definitions. For example, R001 excludes the entire order when there is any completed return, even if another business would treat partial returns differently. Do not “correct” this policy using a generic assumption. Agree on a changed definition with the product owner, save a new version and update test labels before rerunning evaluation.

## Model API boundary

`ModelSettings` reads the project `.env` or an explicitly selected file, then applies process-environment overrides. It never silently borrows another course project's credentials. `ModelClient` posts a bearer-authenticated Chat Completions-compatible request containing the model, messages and configured generation options. Redirects are disabled; no business database is contacted.

The response must finish with `stop`, contain valid structured content and meet all evidence checks. HTTP 401/403/404/429 have specific user guidance. Timeouts and malformed responses become incomplete reports. Automatic retry loops are not used, preventing hidden duplicate requests and untracked costs.

Usage parsing accepts prompt/completion token counts and compatible cached-token fields. Costs are estimated only when sufficient rate information is provided. Missing usage or unknown rates are not treated as zero. The request credential is a `SecretStr` and is not stored in a report, evaluation export or Git.

## Data change and handoff protocol

1. Check uploaded schema/rules with the owner; use UTF-8 `.sql`/`.txt` files.
2. Keep each business rule on one line. The UI assigns R001, R002, etc. in that version.
3. Treat a rule ID together with its project and version; the same ID in a later version can have changed text.
4. Save a new version rather than overwriting an old review's context.
5. Give the evaluation lead positive and negative examples of each revised definition.
6. Keep the frozen benchmark unchanged when measuring a prompt-only change.

Historical model-call results are in the separate PDF reports. Availability, quota and pricing must be checked with the actual provider before a new live demonstration. Keys are supplied separately by each authorized member; see [local setup](../LOCAL_SETUP.md).
