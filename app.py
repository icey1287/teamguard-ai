"""Run from the repository root: uv run streamlit run app.py"""

import difflib
import json
import sqlite3
from uuid import uuid4

import streamlit as st
from pydantic import ValidationError

from checks import read_schema
from contracts import Decision, ReviewRequest, Rule, Rulebook
from benchmarks import benchmark_cases
from evaluation import ARMS, evaluate_case, new_run, summarize
from model_client import ModelClient, ModelSettings, load_settings
from review import review_sql
from storage import Store

st.set_page_config(page_title="TeamGuard AI · SQL Review", page_icon="◈", layout="wide")
st.markdown("""<style>
    .stApp { background: #f6f8f7; }
    .block-container { max-width: 1180px; padding-top: 2.8rem; padding-bottom: 4rem; }
    [data-testid="stSidebar"] { background: #102b2b; }
    [data-testid="stSidebar"] * { color: #e4efec; }
    [data-testid="stSidebar"] [data-testid="stCaptionContainer"] { opacity: .72; }
    h1 { letter-spacing: -.045em; font-weight: 750; }
    h2, h3 { letter-spacing: -.025em; }
    [data-testid="stMetric"] { background: white; border: 1px solid #dce5df;
        border-radius: 14px; padding: 18px 20px; }
    [data-testid="stMetricValue"] { font-size: 1.85rem; }
    [data-testid="stVerticalBlockBorderWrapper"] { border-radius: 14px; }
</style>""", unsafe_allow_html=True)

try:
    store = Store()
    projects = store.projects()
    reports = store.reports()
    decisions = store.decisions()
except (sqlite3.Error, OSError, ValueError):
    st.error("The local workspace could not be opened. Check its file permissions and restart the app.")
    st.stop()

try:
    settings = load_settings()
    configuration_error = False
except (ValidationError, OSError, ValueError):
    # Do not render validation exceptions: they may include configuration values.
    settings, configuration_error = ModelSettings(), True
client = ModelClient(settings)
PAGES = ["Overview", "Project & rules", "Submit SQL", "Review report", "History", "Evaluation"]


def navigate(page, report_id=None):
    st.session_state["navigation"] = page
    if report_id:
        st.session_state["active_report"] = report_id
        st.session_state["report_picker"] = report_id


with st.sidebar:
    st.title("◈ TeamGuard AI")
    st.caption("POLICY-AWARE SQL REVIEW")
    st.divider()
    page = st.radio("Workspace", PAGES, key="navigation", label_visibility="collapsed")
    st.divider()
    st.caption("WORKSPACE")
    st.write(f"{len(projects)} projects · {len(reports)} reviews")
    st.caption("Saved locally · available after restart")
    st.divider()
    st.caption("MODEL CONNECTION")
    st.write("Configured" if client.configured else "Setup required")
    st.caption(settings.model or "No model selected")
    st.caption("Connection is verified when a review runs.")
    if configuration_error:
        st.warning("Check the model settings in your environment file.")
    st.divider()
    st.caption("SQL review only · queries are never executed")


def project_label(project_id):
    return projects[project_id][-1].project_name


def decode_upload(upload):
    if upload is None:
        raise ValueError("Choose a file first.")
    if upload.size > 100_000:
        raise ValueError("Use a UTF-8 file smaller than 100 KB.")
    try:
        return upload.getvalue().decode("utf-8-sig")
    except UnicodeDecodeError:
        raise ValueError("The uploaded file must use UTF-8 encoding.") from None


def save_review(request, parent=None):
    with st.status("Reviewing your query…", expanded=True) as status:
        st.write("1 · Parse MySQL and resolve references against the approved schema.")
        st.write("2 · If structural checks pass, review business definitions with the model.")
        report = review_sql(request, client, parent_report_id=parent)
        store.save_report(report)
        st.write("3 · Save the report, its evidence and the exact rulebook version.")
        status.update(label="Review saved" if report.status != "incomplete" else "Incomplete review saved",
                      state="complete" if report.status != "incomplete" else "error", expanded=False)
    st.session_state.active_report = report.id
    return report


def render_report(report, allow_decision=True, prefix="report"):
    labels = {"passed": "Passed completed checks", "needs_review": "Needs review", "incomplete": "Review incomplete"}
    colors = {"passed": "green", "needs_review": "orange", "incomplete": "red"}
    st.badge(labels[report.status], color=colors[report.status])
    book = report.request.rulebook
    st.caption(f"{book.project_name} · Rulebook v{book.version} · {report.created_at:%Y-%m-%d %H:%M UTC} · {report.id[:8]}")
    if report.parent_report_id:
        st.caption(f"Follow-up to review {report.parent_report_id[:8]} · Original remains in history")
    if report.status == "incomplete":
        st.warning(report.note)
    else:
        st.info(report.note)
    st.caption(f"Business-rule review: {report.semantic_status.replace('_', ' ')}. Passing does not guarantee SQL correctness or safety.")
    cols = st.columns(3)
    cols[0].metric("Findings", len(report.issues))
    cols[1].metric("Review time", f"{report.elapsed_seconds:.1f} s")
    cols[2].metric("Total tokens", f"{report.usage.input_tokens + report.usage.output_tokens:,}" if report.usage
                   else ("0" if report.semantic_status in {"skipped", "not_configured"} else "Not reported"))
    if report.usage and report.usage.estimated_cost is not None:
        st.caption(f"Estimated model cost: {report.usage.estimated_cost:.6f} (configured pricing currency).")
    findings_tab, sql_tab, context_tab = st.tabs(["Findings & decisions", "SQL & revision", "Rulebook & provenance"])
    with findings_tab:
        if not report.issues:
            if report.status == "passed":
                st.success("No issues identified against this schema and rulebook.")
            else:
                st.write("No findings from the completed checks. Business-rule review is still incomplete.")
        for index, issue in enumerate(report.issues, 1):
            with st.container(border=True):
                st.badge(f"{issue.severity.upper()} · {issue.category}", color="red" if issue.severity == "high" else "orange")
                st.write(f"**{index}. {issue.message}**")
                st.caption("QUERY EVIDENCE")
                st.code(issue.evidence, language="sql" if issue.category != "schema" else None)
                if issue.rule_id:
                    st.caption(f"RULE EVIDENCE · {issue.rule_id}")
                    st.write(issue.rule_quote or next((r.text for r in book.rules if r.id == issue.rule_id), ""))
                st.caption("SUGGESTED FIX")
                st.write(issue.suggestion)
        report_decisions = [d for d in decisions if d.report_id == report.id]
        if report_decisions:
            st.subheader("Human decisions")
            for decision in report_decisions:
                st.write(f"**{decision.action.title()}** · {decision.reviewer} · {decision.created_at:%Y-%m-%d %H:%M UTC}")
                if decision.note:
                    st.write(decision.note)
        if allow_decision and report.semantic_status == "completed" and report.issues:
            st.subheader("Your review decision")
            st.caption("Record your judgment of the suggestions. Acceptance never executes SQL or changes the original report.")
            with st.form(f"{prefix}_decision_{report.id}"):
                reviewer = st.text_input("Reviewer", max_chars=80)
                action = st.radio("Decision", ["Accept suggestions", "Reject suggestions"], horizontal=True)
                note = st.text_area("Reason or comment", height=90, max_chars=2000)
                if st.form_submit_button("Record decision", type="primary"):
                    if not reviewer.strip():
                        st.error("Enter a reviewer name.")
                    else:
                        store.save_decision(Decision(report_id=report.id,
                            action="accept" if action == "Accept suggestions" else "reject",
                            reviewer=reviewer.strip(), note=note.strip()))
                        st.rerun()
    with sql_tab:
        st.subheader("Submitted SQL")
        st.code(report.request.sql, language="sql")
        if report.revised_sql:
            st.subheader("Proposed revision")
            st.code(report.revised_sql, language="sql")
            st.caption("The revision passed structural checks. Review its meaning before use.")
            with st.expander("See what changed"):
                st.code("\n".join(difflib.unified_diff(report.request.sql.splitlines(), report.revised_sql.splitlines(),
                    fromfile="submitted.sql", tofile="proposed.sql", lineterm="")), language="diff")
            if allow_decision and st.button("Review proposed SQL again", key=f"{prefix}_recheck_{report.id}"):
                revised = save_review(ReviewRequest(sql=report.revised_sql, rulebook=book), report.id)
                st.session_state.pending_report = revised.id
                st.rerun()
            st.download_button("Download proposed SQL", report.revised_sql, "proposed.sql", "text/plain", key=f"{prefix}_sql_{report.id}")
        elif report.issues:
            st.write("No validated revision is available. Edit the query using the findings and submit it again.")
    with context_tab:
        st.write(f"**{book.project_name} · Version {book.version}**")
        st.code(book.schema_sql, language="sql")
        for rule in book.rules:
            st.write(f"**{rule.id}** · {rule.text}")
        st.caption(f"Model: {report.model or 'Not configured'} · Prompt: {report.prompt_version}")
        st.json(report.model_parameters, expanded=False)
        st.caption("The saved snapshot is used even if the current project rules change.")
    export = {"report": report.model_dump(mode="json"),
              "decisions": [d.model_dump(mode="json") for d in decisions if d.report_id == report.id]}
    st.download_button("Download review JSON", json.dumps(export, ensure_ascii=False, indent=2),
                       f"review-{report.id[:8]}.json", "application/json", key=f"{prefix}_json_{report.id}")


if page == "Overview":
    st.title("Workspace")
    if not client.configured:
        st.info("Set MODEL_API_KEY in your .env file to enable business-rule review.")
    if not projects:
        st.write("Create a project with your MySQL schema and business rules to review SQL.")
        st.button("Create project", type="primary", on_click=navigate, args=("Project & rules",))
    else:
        left, right = st.columns([3, 1])
        left.subheader("Projects")
        right.button("New project", on_click=navigate, args=("Project & rules",))
        for project_id, versions in projects.items():
            book = versions[-1]
            with st.container(border=True):
                st.write(f"**{book.project_name}**")
                st.caption(f"Version {book.version} · {len(read_schema(book.schema_sql))} tables · {len(book.rules)} rules")
        st.button("Submit SQL", type="primary", on_click=navigate, args=("Submit SQL",))
    if reports:
        st.subheader("Recent reviews")
        for report in reversed(reports[-3:]):
            a, b = st.columns([4, 1])
            a.write(f"**{report.request.rulebook.project_name}** · {report.status.replace('_', ' ')} · {report.created_at:%m-%d %H:%M UTC}")
            b.button("Open report", key=f"recent_{report.id}", on_click=navigate, args=("Review report", report.id))

elif page == "Project & rules":
    st.title("Project & rules")
    st.write("Give every reviewer the same schema and business definitions.")
    selected = st.selectbox("Project", [None, *projects], format_func=lambda p: "Create a project" if p is None else project_label(p))
    current = projects[selected][-1] if selected else None
    with st.form(f"project_{selected or 'new'}"):
        name = st.text_input("Project name", value=current.project_name if current else "", max_chars=100)
        st.caption("Schema: MySQL CREATE TABLE statements with explicit columns. Nothing is executed.")
        schema_sql = st.text_area("Approved schema", value=current.schema_sql if current else "", height=220)
        schema_upload = st.file_uploader("Or upload a schema (.sql); replaces the text for this save", type=["sql"])
        rule_text = st.text_area("Business rules — one rule per line", value="\n".join(r.text for r in current.rules) if current else "", height=180)
        rules_upload = st.file_uploader("Or upload rules (.txt); replaces the text for this save", type=["txt"])
        saved = st.form_submit_button("Save new version" if current else "Create project", type="primary")
    if saved:
        try:
            if not name.strip():
                raise ValueError("Enter a project name.")
            schema = decode_upload(schema_upload) if schema_upload else schema_sql
            raw_rules = decode_upload(rules_upload) if rules_upload else rule_text
            if len(schema) > 30000 or len(raw_rules) > 20000:
                raise ValueError("Use a schema up to 30,000 characters and rules up to 20,000 characters.")
            read_schema(schema)
            rules = tuple(Rule(id=f"R{i:03d}", text=line.strip()) for i, line in enumerate(
                (line for line in raw_rules.splitlines() if line.strip()), 1))
            if not rules:
                raise ValueError("Add at least one business rule.")
            if current and current.project_name == name.strip() and current.schema_sql == schema and current.rules == rules:
                raise ValueError("No changes to save. The current version is already available.")
            book = Rulebook(project_id=selected or str(uuid4()), project_name=name.strip(),
                            version=(current.version + 1) if current else 1, schema_sql=schema, rules=rules)
            store.save_rulebook(book)
            st.success(f"Saved {book.project_name}, version {book.version}.")
            st.button("Continue to SQL review", on_click=navigate, args=("Submit SQL",))
        except ValueError as error:
            st.error(str(error))
    if selected:
        st.subheader("Saved versions")
        st.caption("New versions never change an existing review's context.")
        for book in reversed(store.projects()[selected]):
            with st.expander(f"Version {book.version} · {book.project_name}"):
                st.code(book.schema_sql, language="sql")
                for rule in book.rules:
                    st.write(f"**{rule.id}** · {rule.text}")

elif page == "Submit SQL":
    st.title("Submit SQL")
    st.write("Review a query before it becomes a shared business result.")
    if not projects:
        st.info("Create a project with its schema and rules before submitting SQL.")
        st.button("Create project", on_click=navigate, args=("Project & rules",))
    else:
        left, right = st.columns([2, 1])
        project_id = left.selectbox("Project", list(projects), format_func=project_label)
        versions = projects[project_id]
        version = right.selectbox("Rule version", list(reversed(range(len(versions)))), format_func=lambda i: f"Version {versions[i].version}")
        book = versions[version]
        with st.expander(f"Review context · {len(book.rules)} rules · {len(read_schema(book.schema_sql))} tables"):
            st.code(book.schema_sql, language="sql")
            for rule in book.rules:
                st.write(f"**{rule.id}** · {rule.text}")
        source = st.radio("Input method", ["Paste SQL", "Upload SQL"], horizontal=True)
        with st.form("submit_sql"):
            sql_text = st.text_area("MySQL query", height=260, key="sql_editor") if source == "Paste SQL" else ""
            upload = st.file_uploader("SQL file", type=["sql"]) if source == "Upload SQL" else None
            st.caption("One read-only query · SQL and approved context are sent to the configured model after structural checks pass.")
            submitted = st.form_submit_button("Run review", type="primary")
        if submitted:
            try:
                sql = decode_upload(upload) if source == "Upload SQL" else sql_text
                if not sql.strip():
                    raise ValueError("Enter a query before submitting.")
                if len(sql) > 30000:
                    raise ValueError("Use a query shorter than 30,000 characters.")
                report = save_review(ReviewRequest(sql=sql, rulebook=book))
                st.session_state.submission_report = report.id
            except ValueError as error:
                st.error(str(error))
        last_id = st.session_state.get("submission_report")
        last = next((r for r in store.reports() if r.id == last_id), None)
        if last:
            st.divider()
            render_report(last, allow_decision=False, prefix="submission")
            st.button("Open report & record decision", on_click=navigate, args=("Review report", last.id), type="primary")

elif page == "Review report":
    st.title("Review report")
    st.write("Inspect the evidence. Review the proposed change. Record your judgment.")
    if not reports:
        st.info("Submit a SQL query to create your first report.")
        st.button("Submit SQL", on_click=navigate, args=("Submit SQL",))
    else:
        ordered = list(reversed(reports))
        # Follow-up reviews select their new ID on the next rerun, before widget creation.
        pending = st.session_state.pop("pending_report", None)
        if pending:
            st.session_state.report_picker = pending
        report_id = st.selectbox("Submission", [r.id for r in ordered], key="report_picker",
            format_func=lambda rid: next(f"{r.request.rulebook.project_name} · {r.created_at:%m-%d %H:%M:%S UTC} · {r.id[:8]}" for r in ordered if r.id == rid))
        report = next(r for r in reports if r.id == report_id)
        render_report(report)
        if report.status == "incomplete" and st.button("Retry review with the same rule version"):
            retried = save_review(report.request, report.id)
            st.session_state.pending_report = retried.id
            st.rerun()

elif page == "History":
    st.title("Review history")
    st.write("Find previous submissions with their original rules and reviewer decisions.")
    a, b, c = st.columns([2, 1, 1])
    query = a.text_input("Search project or SQL")
    status = b.selectbox("Status", ["All", "passed", "needs_review", "incomplete"])
    project_filter = c.selectbox("Project filter", [None, *projects], format_func=lambda p: "All projects" if p is None else project_label(p))
    decision_filter = st.selectbox("Human decision", ["All", "Not recorded", "Accepted", "Rejected"])
    latest_decisions = {d.report_id: d.action for d in decisions}
    found = [r for r in reversed(reports)
             if (status == "All" or r.status == status)
             and (project_filter is None or r.request.rulebook.project_id == project_filter)
             and query.casefold() in (r.request.rulebook.project_name + " " + r.request.sql).casefold()
             and (decision_filter == "All" or latest_decisions.get(r.id) == {"Not recorded": None, "Accepted": "accept", "Rejected": "reject"}[decision_filter])]
    st.caption(f"{len(found)} matching reviews")
    if not found:
        st.info("No matching reviews. Try a different filter or submit a query.")
    for report in found:
        with st.container(border=True):
            a, b = st.columns([4, 1])
            a.write(f"**{report.request.rulebook.project_name}** · v{report.request.rulebook.version}")
            a.caption(f"{report.created_at:%Y-%m-%d %H:%M UTC} · {report.status.replace('_', ' ')} · {len(report.issues)} findings · Decision: {latest_decisions.get(report.id, 'not recorded')}")
            a.code(report.request.sql[:240] + ("…" if len(report.request.sql) > 240 else ""), language="sql")
            b.button("Open review", key=f"history_{report.id}", on_click=navigate, args=("Review report", report.id))

else:
    st.title("Evaluation")
    st.write("Run a benchmark comparison of structural checks, generic model review and policy-aware review.")
    st.caption("48 synthetic development cases · commerce-v1 · developer-authored labels awaiting independent human validation")
    with st.expander("Methods, targets & limitations", expanded=False):
        st.write("**A** runs the parser and schema checks. **B** asks the same model to review SQL with schema but no business rules. **C** runs structural checks, then the model with the approved rulebook.")
        st.write("Targets set before testing: severe-risk recall ≥85%, precision ≥80%, median review time ≤15 seconds.")
        st.write("Automated scores match distinct error categories per case, not the correctness of every natural-language finding. Failures count as missed expected findings and reduce completion. False-positive rate must be read together with clean-case completion. Exact rule citations are retained for manual inspection.")
        st.write("For C, the detailed metrics also match each business finding to its expected rule ID. Generic review has no rulebook, so this rule-level score is not applicable to B.")
        st.write("Structural fix validity checks parsing, safety and schema only. Human-checked fix validity and external user feedback are not measured here. These development examples are not an independent held-out test set.")
        st.write("Inputs, rules, labels, model, prompt version and dataset hash are saved with every run.")
    cases = benchmark_cases()
    with st.expander("Inspect frozen inputs and expected labels"):
        st.dataframe([{"Case": c["id"], "Input": c["sql"], "Expected": ", ".join(c["expected"]) or "No issue"} for c in cases], hide_index=True, width="stretch")
    arms = st.multiselect("Strategies", list(ARMS), default=["A"], format_func=ARMS.get)
    groups = st.multiselect("Case groups", ["clean", "syntax", "schema", "safety", "metric"], default=["clean", "syntax", "schema", "safety", "metric"])
    selected_cases = [c for c in cases if c["group"] in groups]
    st.caption(f"{len(selected_cases)} cases × {len(arms)} strategies. Model strategies make real API calls and may take several minutes.")
    if st.button("Run evaluation", type="primary", disabled=not arms or not selected_cases):
        if any(a != "A" for a in arms) and not client.configured:
            st.error("Configure a model before running strategies B or C.")
        else:
            run = new_run(arms, selected_cases, settings.model, settings.public_parameters())
            store.save_evaluation(run)
            progress = st.progress(0, text="Starting evaluation…")
            total = len(arms) * len(selected_cases)
            for arm in arms:
                for case in selected_cases:
                    row = evaluate_case(case, arm, client)
                    run["rows"].append(row)
                    store.update_evaluation(run)
                    progress.progress(len(run["rows"]) / total, text=f"{ARMS[arm]} · {case['id']} · {len(run['rows'])}/{total}")
            run["complete"] = True
            store.update_evaluation(run)
            st.success("Evaluation saved. Failed model calls remain visible in the results.")
    runs = store.evaluations()
    if runs:
        selected_run = st.selectbox("Saved evaluation", range(len(runs)), format_func=lambda i: f"{runs[i]['created_at'][:19]} UTC · {', '.join(runs[i]['arms'])} · {len(runs[i]['rows'])} results")
        run = runs[selected_run]
        if not run["complete"]:
            st.warning("This run is not complete. Results include only attempts saved so far, not the full selected set.")
        st.caption(f"{len(run['rows'])} / {len(run['arms']) * len(run['frozen_dataset']['cases'])} attempts saved")
        st.caption(f"Model: {run['model'] or 'Not configured'} · Dataset: {run['dataset_version']} · SHA256 {run['dataset_sha256'][:16]}")
        summary = summarize(run["rows"])
        def percent(value):
            return f"{value:.1%}" if value is not None else "Not measured"
        st.dataframe([{"Strategy": s["arm"], "Cases": s["cases"], "Completed": percent(s["completion_rate"]),
                       "Precision": percent(s["label_precision"]), "Recall": percent(s["label_recall"]),
                       "F1": percent(s["label_f1"]), "Severe recall": percent(s["severe_recall"]),
                       "Median (s)": round(s["median_seconds"], 2)} for s in summary], hide_index=True, width="stretch")
        with st.expander("All metrics, fix validation & cost coverage"):
            st.dataframe(summary, hide_index=True, width="stretch")
        st.caption("Detailed rates use fractions from 0 to 1. Empty values mean not measured or unavailable, never zero. Cost uses configured pricing; missing usage is not treated as free.")
        only_failures = st.checkbox("Show mismatches and failed calls only", value=True)
        visible = [r for r in run["rows"] if not only_failures or not r["matched"]]
        st.dataframe([{"Case": r["case_id"], "Strategy": r["arm"], "Expected": ", ".join(r["expected"]) or "No issue",
                       "Actual": ", ".join(r["predicted"]) or "No issue", "Complete": r["complete"], "Match": r["matched"],
                       "Seconds": round(r["elapsed_seconds"], 2), "Note": r["note"]} for r in visible], hide_index=True, width="stretch")
        if run["rows"]:
            detail = st.selectbox("Inspect a result", range(len(run["rows"])), format_func=lambda i: f"{run['rows'][i]['arm']} · {run['rows'][i]['case_id']} · {run['rows'][i]['title']}")
            row = run["rows"][detail]
            st.code(next(c["sql"] for c in run["frozen_dataset"]["cases"] if c["id"] == row["case_id"]), language="sql")
            st.json({k: v for k, v in row.items() if k != "report"}, expanded=False)
            if row["revised_sql"] and run["complete"]:
                st.code(row["revised_sql"], language="sql")
                with st.form(f"fix_validation_{run['id']}_{detail}"):
                    st.caption("Human validation: check whether the proposed SQL preserves the intended task and satisfies the frozen rules.")
                    verdict = st.selectbox("Fix validity", ["Not reviewed", "Valid", "Invalid"],
                        index=0 if row["human_fix_valid"] is None else (1 if row["human_fix_valid"] else 2))
                    reviewer = st.text_input("Reviewer name or alias", value=row.get("fix_reviewer", ""))
                    reason = st.text_area("Validation reason", value=row.get("fix_reason", ""))
                    if st.form_submit_button("Save fix validation"):
                        if not reviewer.strip() or not reason.strip():
                            st.error("Enter a reviewer and reason so this judgment is traceable.")
                        else:
                            row["human_fix_valid"] = {"Not reviewed": None, "Valid": True, "Invalid": False}[verdict]
                            row["fix_reviewer"], row["fix_reason"] = reviewer.strip(), reason.strip()
                            store.update_evaluation(run)
                            st.rerun()
        st.download_button("Download evaluation JSON", json.dumps(run, ensure_ascii=False, indent=2), f"evaluation-{run['id'][:8]}.json", "application/json")
    else:
        st.info("No evaluation has run yet. Start with deterministic checks, then compare the model strategies.")
