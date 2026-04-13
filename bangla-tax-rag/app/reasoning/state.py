from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, Field, computed_field, field_validator, model_validator

from app.domain import EvidenceItem, LegalCitation, QueryExecutionPath, QueryType


class QueryPlanStep(BaseModel):
    goal: str
    sub_query: str
    rationale: str | None = None
    preferred_node_types: list[str] = Field(default_factory=list)
    metadata_filters: dict[str, str | int | float | bool | None] = Field(default_factory=dict)

    @field_validator("goal", "sub_query")
    @classmethod
    def validate_non_empty_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("query plan text fields must not be empty")
        return stripped


class RetrievalAttempt(BaseModel):
    attempt_number: int = Field(..., ge=1)
    query_text: str
    retrieval_mode: str = "hybrid"
    candidate_evidence_ids: list[str] = Field(default_factory=list)
    selected_evidence_ids: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    requires_more_retrieval: bool = False

    @field_validator("query_text")
    @classmethod
    def validate_query_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("query_text must not be empty")
        return stripped


class VerificationFailure(BaseModel):
    claim_text: str
    reason: str
    severity: Literal["warning", "error"] = "error"
    evidence_ids: list[str] = Field(default_factory=list)
    replacement_text: str | None = None

    @field_validator("claim_text", "reason")
    @classmethod
    def validate_failure_fields(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("verification failure fields must not be empty")
        return stripped


class AgentState(BaseModel):
    trace_id: str = Field(default_factory=lambda: uuid4().hex)
    question: str
    normalized_question: str | None = None
    query_type: QueryType = QueryType.GENERAL
    execution_path: QueryExecutionPath = QueryExecutionPath.FAST_PATH
    planned_steps: list[QueryPlanStep] = Field(default_factory=list)
    facts_from_user: list[str] = Field(default_factory=list)
    facts_found: list[str] = Field(default_factory=list)
    missing_facts: list[str] = Field(default_factory=list)
    rules_found: list[str] = Field(default_factory=list)
    exceptions_found: list[str] = Field(default_factory=list)
    open_issues: list[str] = Field(default_factory=list)
    retrieved_evidence: list[EvidenceItem] = Field(default_factory=list)
    retrieval_attempts: list[RetrievalAttempt] = Field(default_factory=list)
    verification_failures: list[VerificationFailure] = Field(default_factory=list)
    reasoning_summary: list[str] = Field(default_factory=list)
    citations: list[LegalCitation] = Field(default_factory=list)
    completed_nodes: list[str] = Field(default_factory=list)
    needs_more_retrieval: bool = False
    draft_answer: str | None = None
    final_answer: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    current_step: int = Field(default=0, ge=0)
    max_reasoning_steps: int = Field(default=4, ge=1, le=12)

    @field_validator("question")
    @classmethod
    def validate_question(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("question must not be empty")
        return stripped

    @model_validator(mode="after")
    def validate_step_budget(self) -> "AgentState":
        if self.current_step > self.max_reasoning_steps:
            raise ValueError("current_step cannot exceed max_reasoning_steps")
        return self

    @computed_field  # type: ignore[prop-decorator]
    @property
    def remaining_steps(self) -> int:
        return max(self.max_reasoning_steps - self.current_step, 0)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def exhausted_reasoning_budget(self) -> bool:
        return self.current_step >= self.max_reasoning_steps

    @computed_field  # type: ignore[prop-decorator]
    @property
    def has_verification_errors(self) -> bool:
        return any(issue.severity == "error" for issue in self.verification_failures)

    @computed_field  # type: ignore[prop-decorator]
    @property
    def should_enter_agent_loop(self) -> bool:
        return self.execution_path is QueryExecutionPath.AGENTIC

    @computed_field  # type: ignore[prop-decorator]
    @property
    def ready_for_compose(self) -> bool:
        return bool(self.draft_answer) and not self.needs_more_retrieval

    def advance_step(self, node_name: str) -> None:
        node_name = node_name.strip()
        if not node_name:
            raise ValueError("node_name must not be empty")
        if self.exhausted_reasoning_budget:
            raise ValueError("reasoning budget exhausted")
        self.current_step += 1
        self.completed_nodes.append(node_name)

    def add_reasoning_note(self, note: str) -> None:
        note = note.strip()
        if note and note not in self.reasoning_summary:
            self.reasoning_summary.append(note)

    def add_fact_found(self, fact: str) -> None:
        fact = fact.strip()
        if fact and fact not in self.facts_found:
            self.facts_found.append(fact)

    def add_missing_fact(self, fact: str) -> None:
        fact = fact.strip()
        if fact and fact not in self.missing_facts:
            self.missing_facts.append(fact)

    def add_rule_found(self, rule: str) -> None:
        rule = rule.strip()
        if rule and rule not in self.rules_found:
            self.rules_found.append(rule)

    def add_exception_found(self, exception: str) -> None:
        exception = exception.strip()
        if exception and exception not in self.exceptions_found:
            self.exceptions_found.append(exception)

    def add_open_issue(self, issue: str) -> None:
        issue = issue.strip()
        if issue and issue not in self.open_issues:
            self.open_issues.append(issue)

    def add_retrieval_attempt(self, attempt: RetrievalAttempt) -> None:
        self.retrieval_attempts.append(attempt)
        self.needs_more_retrieval = attempt.requires_more_retrieval

    def add_verification_failure(self, failure: VerificationFailure) -> None:
        self.verification_failures.append(failure)

    def add_evidence(self, evidence_items: list[EvidenceItem]) -> None:
        seen_evidence_ids = {item.evidence_id for item in self.retrieved_evidence}
        seen_citations = {
            (
                citation.node_id,
                citation.relation,
                citation.section_number,
                citation.subsection_number,
                citation.clause_number,
            )
            for citation in self.citations
        }
        for item in evidence_items:
            if item.evidence_id not in seen_evidence_ids:
                self.retrieved_evidence.append(item)
                seen_evidence_ids.add(item.evidence_id)
            citation_key = (
                item.citation.node_id,
                item.citation.relation,
                item.citation.section_number,
                item.citation.subsection_number,
                item.citation.clause_number,
            )
            if citation_key not in seen_citations:
                self.citations.append(item.citation)
                seen_citations.add(citation_key)
