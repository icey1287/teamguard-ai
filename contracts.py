"""Shared application contracts. These are not database models."""

from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Rule(Contract):
    id: str
    text: str = Field(min_length=1)


class Rulebook(Contract):
    project_id: str
    project_name: str
    version: int = Field(ge=1)
    schema_sql: str = Field(min_length=1)
    rules: tuple[Rule, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_rules(self):
        if len({r.id for r in self.rules}) != len(self.rules):
            raise ValueError("Rule IDs must be unique within a version.")
        return self


class ReviewRequest(Contract):
    sql: str = Field(min_length=1, max_length=30000)
    rulebook: Rulebook


class Issue(Contract):
    severity: Literal["high", "medium", "low"]
    category: Literal["syntax", "safety", "schema", "metric"]
    message: str = Field(min_length=1)
    evidence: str = Field(min_length=1)
    suggestion: str = Field(min_length=1)
    rule_id: str | None = None
    rule_quote: str | None = None


class SemanticIssue(Contract):
    severity: Literal["high", "medium", "low"]
    category: Literal["metric"]
    message: str = Field(min_length=1)
    evidence: str = Field(min_length=1)
    suggestion: str = Field(min_length=1)
    rule_id: str
    rule_quote: str = Field(min_length=1)


class SemanticResult(Contract):
    issues: tuple[SemanticIssue, ...]
    revised_sql: str | None


class Usage(Contract):
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    cached_tokens: int = Field(default=0, ge=0)
    estimated_cost: float | None = None


class ReviewReport(Contract):
    id: str = Field(default_factory=lambda: str(uuid4()))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    request: ReviewRequest
    status: Literal["passed", "needs_review", "incomplete"]
    issues: tuple[Issue, ...]
    semantic_status: Literal["completed", "skipped", "failed", "not_configured"]
    note: str
    revised_sql: str | None = None
    usage: Usage | None = None
    model: str | None = None
    elapsed_seconds: float
    parent_report_id: str | None = None
    prompt_version: str = "policy-v2"
    model_parameters: dict = Field(default_factory=dict)


class Decision(Contract):
    id: str = Field(default_factory=lambda: str(uuid4()))
    report_id: str
    action: Literal["accept", "reject"]
    note: str = ""
    reviewer: str = Field(min_length=1, max_length=80)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
