from __future__ import annotations

from pydantic import BaseModel, Field

from app.services.query_service import QueryRequest, QueryResponse, QueryService


class EvaluationCase(BaseModel):
    case_id: str
    question: str
    expected_sections: list[str] = Field(default_factory=list)
    required_substrings: list[str] = Field(default_factory=list)
    expected_refusal: bool = False


class EvaluationResult(BaseModel):
    case_id: str
    passed: bool
    answer: str
    matched_sections: list[str] = Field(default_factory=list)
    matched_substrings: list[str] = Field(default_factory=list)
    refused: bool = False
    trace_id: str


class EvaluationSummary(BaseModel):
    total_cases: int
    passed_cases: int
    accuracy: float
    results: list[EvaluationResult] = Field(default_factory=list)


class EvaluationService:
    def __init__(self, *, query_service: QueryService) -> None:
        self.query_service = query_service

    def evaluate(self, cases: list[EvaluationCase]) -> EvaluationSummary:
        results: list[EvaluationResult] = []
        for case in cases:
            response = self.query_service.run(QueryRequest(question=case.question))
            results.append(self._evaluate_case(case, response))

        passed_cases = sum(1 for result in results if result.passed)
        total_cases = len(results)
        return EvaluationSummary(
            total_cases=total_cases,
            passed_cases=passed_cases,
            accuracy=round((passed_cases / total_cases) if total_cases else 0.0, 4),
            results=results,
        )

    def _evaluate_case(self, case: EvaluationCase, response: QueryResponse) -> EvaluationResult:
        answer_lower = response.answer.lower()
        citation_sections = {payload.section for payload in response.citations if payload.section}
        matched_sections = [section for section in case.expected_sections if section in citation_sections]
        matched_substrings = [
            substring
            for substring in case.required_substrings
            if substring.lower() in answer_lower
        ]
        refused = "information not found in retrieved evidence" in answer_lower

        passed = True
        if case.expected_sections:
            passed = passed and len(matched_sections) == len(case.expected_sections)
        if case.required_substrings:
            passed = passed and len(matched_substrings) == len(case.required_substrings)
        if case.expected_refusal:
            passed = passed and refused
        elif not case.expected_refusal and case.required_substrings:
            passed = passed and not refused

        return EvaluationResult(
            case_id=case.case_id,
            passed=passed,
            answer=response.answer,
            matched_sections=matched_sections,
            matched_substrings=matched_substrings,
            refused=refused,
            trace_id=response.trace_id,
        )
