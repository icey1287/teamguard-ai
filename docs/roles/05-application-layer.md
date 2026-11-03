# 05 · Application-layer developer

**Owned outcome:** an understandable, end-to-end local workflow with persistent, inspectable results.

## Page and interaction design

| Page | Primary action | Important behavior |
| --- | --- | --- |
| Overview | Create a project or start a review | Show the current projects and recent submissions |
| Project & rules | Create project or save next version | Validate name/schema/rules; retain prior versions |
| Submit SQL | Paste or upload a query | Select project/version explicitly; accept user inputs |
| Review report | Inspect findings and decide | Separate evidence, SQL diff and provenance; recheck a proposal |
| History | Find a prior submission | Filter by project, status, decision and SQL/project text |
| Evaluation | Compare strategies or inspect a saved run | Expose incomplete attempts, frozen inputs and scoring limits |

The visual system uses readable type, a dark navigation rail and light content panels. Status labels contain text in addition to color. The application adapts from a desktop presentation layout to stacked panels on a narrow window.

## State ownership

Durable objects belong in `Store`: rulebook versions, reports, decisions and evaluations. `st.session_state` holds only UI state such as navigation, the editor content, selected report and a pending follow-up selection. This prevents a browser refresh from becoming accidental data loss.

A report embeds the entire request and rulebook version. A revision or retry creates a new ID and `parent_report_id`; it does not overwrite an original finding. Saving a new rule version does not alter any historical report.

A project save uses an atomic next-version check. When a concurrent editor has already saved a version, the app asks the user to reload. Names are checked against other projects. The workspace is still shared on one local machine: reviewer aliases are not authentication, and separate computers do not synchronize automatically.

## Form and error behavior

Uploads accept UTF-8 `.sql`/`.txt`, at most 100 KB in the application decoder; Streamlit's transport limit is 1 MB. SQL is limited to 30,000 characters; schema and rule text limits are 30,000 and 20,000 respectively. Invalid encoding, empty SQL and unsupported schema definitions produce actionable errors.

A missing model or failed response yields an incomplete report with a retry action. Structural findings skip the model and are displayed immediately. Unknown token usage is shown as not reported; a known skipped call uses zero tokens. No secret-bearing configuration exception is rendered in the interface.

The report's JSON download contains the report and its recorded decisions. Proposed SQL has a separate download. Accepting a suggestion never executes it. The “Review proposed SQL again” button submits the proposal against the **same snapshot**, even if the current project has changed.

## Verified paths

Developer-operated browser verification covered a real metric review, the original/proposed SQL view, re-review to a passed result, file upload with an invented column, history and both wide/narrow layout behavior. Temporary-database tests cover persistence across new sessions, version conflict handling, snapshot retention, invalid responses and evidence validation. The regression suite runs without an API key.

The prior session-only implementation was replaced by SQLite persistence. Parser edge cases were corrected: an empty `SELECT` and a trailing projection comma are rejected, while a valid query followed by a comment is accepted. These are actual implementation changes, not merely planned enhancements.

## Handoff contract

- Use `ReviewRequest`/`ReviewReport` rather than adding model-response parsing inside UI components.
- Keep model API calls in `model_client.py` and orchestration in `review.py` so the same logic serves CLI evaluation and the app.
- Use storage methods rather than executing ad hoc SQL from forms.
- Preserve status distinctions and immutable context when changing presentation.
- Run `uv run --locked python -m unittest discover -s tests -v` after changing interaction or storage logic.

Known limitations are explicit: there is no production login, no per-person authorization and no tamper-proof audit log. Local backup is provided by `manage.py backup`. The application has no historical-result importer or preloaded projects. Future app changes should be guided by the product owner's user observations and the evaluation lead's failure cases.
