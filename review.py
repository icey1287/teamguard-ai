"""Reusable deterministic-check -> semantic-review pipeline, independent of Streamlit."""

from time import monotonic

from checks import check_sql
from contracts import Issue, ReviewReport, ReviewRequest
from model_client import ModelClient, ModelFailure


def review_sql(request: ReviewRequest, client: ModelClient, parent_report_id=None) -> ReviewReport:
    started = monotonic()
    issues = check_sql(request.sql, request.rulebook.schema_sql)
    common = {"request": request, "model": client.settings.model or None, "parent_report_id": parent_report_id,
              "model_parameters": client.settings.public_parameters()}
    if issues:
        return ReviewReport(**common, status="needs_review", issues=issues, semantic_status="skipped",
                            note="Deterministic checks found issues. Fix these before semantic review.",
                            elapsed_seconds=monotonic() - started)
    if not client.configured:
        return ReviewReport(**common, status="incomplete", issues=(), semantic_status="not_configured",
                            note="Deterministic checks completed. Configure a model to finish semantic review.",
                            elapsed_seconds=monotonic() - started)
    try:
        result, usage = client.review(request)
    except ModelFailure as error:
        return ReviewReport(**common, status="incomplete", issues=issues, semantic_status="failed",
                            note=str(error), usage=error.usage, elapsed_seconds=monotonic() - started)
    semantic_issues = tuple(Issue(severity=i.severity, category=i.category, message=i.message,
                                  evidence=i.evidence, suggestion=i.suggestion, rule_id=i.rule_id,
                                  rule_quote=i.rule_quote)
                            for i in result.issues)
    revised = result.revised_sql
    note = "Review completed. Findings and proposed changes require human judgment."
    if revised and check_sql(revised, request.rulebook.schema_sql):
        revised = None
        note += " The proposed SQL failed deterministic checks and was withheld."
    return ReviewReport(**common, status="needs_review" if semantic_issues else "passed",
                        issues=semantic_issues, semantic_status="completed", note=note,
                        revised_sql=revised, usage=usage, elapsed_seconds=monotonic() - started)
