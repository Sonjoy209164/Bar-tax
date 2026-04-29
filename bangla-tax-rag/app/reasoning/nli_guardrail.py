from __future__ import annotations

import re
from typing import Iterable

from pydantic import BaseModel, Field

from app.domain import EvidenceItem, QueryType, canonicalize_query_type
from app.reasoning.prompt_strategies import NON_CLAIM_PREFIXES
from app.reasoning.state import VerificationFailure

REFUSAL_TEXT = "Information not found in retrieved evidence."

NUMERIC_CLAIM_PATTERN = re.compile(r"\b\d+(?:\.\d+)?(?:\s*%| percent)?\b", re.IGNORECASE)
DATE_CLAIM_PATTERN = re.compile(
    r"\b(?:\d{1,2}\s+)?(?:january|february|march|april|may|june|july|august|september|october|november|december)\b|\b\d{1,2}\s+(?:day|month|year|years)\b",
    re.IGNORECASE,
)
SECTION_CLAIM_PATTERN = re.compile(r"\bsection\s+(\d+[A-Za-z]?)\b", re.IGNORECASE)
THRESHOLD_CLAIM_PATTERN = re.compile(r"\b(?:taka|tk\.?|lakh|crore)\b", re.IGNORECASE)
TOKEN_PATTERN = re.compile(r"[\w\u0980-\u09FF]+", re.UNICODE)

STOPWORDS = {
    "the",
    "a",
    "an",
    "and",
    "or",
    "of",
    "to",
    "for",
    "is",
    "are",
    "be",
    "under",
    "this",
    "that",
    "these",
    "those",
    "with",
    "from",
    "in",
    "on",
    "by",
    "it",
    "as",
    "at",
    "than",
    "other",
    "company",
    "retrieved",
    "evidence",
    "legal",
    "basis",
    "short",
    "answer",
    "reasoning",
    "missing",
    "facts",
    "citations",
    "rule",
    "rules",
    "table",
    "indicate",
    "indicates",
    "based",
    "provision",
    "provisions",
    "states",
    "leading",
    "according",
    "retrieved",
    "উদ্ধার",
    "করা",
    "প্রমাণ",
    "অনুযায়ী",
    "অনুযায়ী",
    "হিসেবে",
    "জন্য",
    "এর",
    "এবং",
    "অথবা",
    "উপর",
    "হবে",
    "হয়",
    "হয়",
    "সংক্ষিপ্ত",
    "উত্তর",
    "প্রযোজ্য",
    "বিধান",
    "যুক্তির",
    "সারাংশ",
    "অপূর্ণ",
    "তথ্য",
    "উৎস",
    "যাচাই",
    "সীমাবদ্ধতা",
}


class GuardrailClaimResult(BaseModel):
    claim_text: str
    supported: bool
    support_score: float = Field(default=0.0, ge=0.0, le=1.0)
    evidence_ids: list[str] = Field(default_factory=list)
    failure_reasons: list[str] = Field(default_factory=list)


class GuardrailVerificationResult(BaseModel):
    supported_claims: list[GuardrailClaimResult] = Field(default_factory=list)
    unsupported_claims: list[GuardrailClaimResult] = Field(default_factory=list)
    failures: list[VerificationFailure] = Field(default_factory=list)
    backend: str = "deterministic_nli"

    @property
    def has_errors(self) -> bool:
        return any(failure.severity == "error" for failure in self.failures)


class DeterministicNliGuardrail:
    def verify(
        self,
        draft_answer: str,
        *,
        evidence_items: list[EvidenceItem],
        query_type: str | QueryType,
        missing_coverage: list[str] | None = None,
    ) -> GuardrailVerificationResult:
        canonical_query_type = canonicalize_query_type(query_type)
        claims = _extract_claims(draft_answer)
        evidence_text = " ".join(item.source_text.lower() for item in evidence_items)
        evidence_sections = {item.citation.section_number for item in evidence_items if item.citation.section_number}
        evidence_ids = [item.evidence_id for item in evidence_items]

        supported_claims: list[GuardrailClaimResult] = []
        unsupported_claims: list[GuardrailClaimResult] = []
        failures: list[VerificationFailure] = []

        for claim in claims:
            result = _verify_claim(
                claim,
                evidence_items=evidence_items,
                evidence_text=evidence_text,
                evidence_sections=evidence_sections,
                query_type=canonical_query_type,
            )
            if result.supported:
                supported_claims.append(result)
            else:
                unsupported_claims.append(result)
                failures.append(
                    VerificationFailure(
                        claim_text=result.claim_text,
                        reason="; ".join(result.failure_reasons) or "Claim is not sufficiently supported by retrieved evidence.",
                        severity="error",
                        evidence_ids=result.evidence_ids or evidence_ids,
                        replacement_text=REFUSAL_TEXT,
                    )
                )

        for issue in missing_coverage or []:
            failures.append(
                VerificationFailure(
                    claim_text=issue,
                    reason="Evidence coverage is incomplete for this reasoning path.",
                    severity="warning",
                    evidence_ids=evidence_ids,
                )
            )

        return GuardrailVerificationResult(
            supported_claims=supported_claims,
            unsupported_claims=unsupported_claims,
            failures=failures,
        )


def verify_draft_answer(
    draft_answer: str,
    *,
    evidence_items: list[EvidenceItem],
    query_type: str | QueryType,
    missing_coverage: list[str] | None = None,
) -> GuardrailVerificationResult:
    return DeterministicNliGuardrail().verify(
        draft_answer,
        evidence_items=evidence_items,
        query_type=query_type,
        missing_coverage=missing_coverage,
    )


def _verify_claim(
    claim: str,
    *,
    evidence_items: list[EvidenceItem],
    evidence_text: str,
    evidence_sections: set[str],
    query_type: QueryType,
) -> GuardrailClaimResult:
    normalized_claim = claim.strip()
    claim_tokens = _informative_tokens(normalized_claim)
    matched_evidence_ids = [item.evidence_id for item in evidence_items if _claim_matches_item(normalized_claim, item)]
    overlap_score = _support_overlap_score(normalized_claim, evidence_items)
    failure_reasons: list[str] = []

    numeric_claims = NUMERIC_CLAIM_PATTERN.findall(normalized_claim)
    for numeric in numeric_claims:
        if numeric.lower() not in evidence_text:
            failure_reasons.append(f"Numeric claim {numeric!r} does not appear in retrieved evidence.")

    section_claims = SECTION_CLAIM_PATTERN.findall(normalized_claim)
    for section_number in section_claims:
        if section_number not in evidence_sections:
            failure_reasons.append(f"Section {section_number} is not supported by the retrieved citations.")

    if DATE_CLAIM_PATTERN.search(normalized_claim):
        for date_token in DATE_CLAIM_PATTERN.findall(normalized_claim):
            if date_token.lower() not in evidence_text:
                failure_reasons.append(f"Date or duration token {date_token!r} does not appear in retrieved evidence.")

    if THRESHOLD_CLAIM_PATTERN.search(normalized_claim) and not any(token.lower() in evidence_text for token in THRESHOLD_CLAIM_PATTERN.findall(normalized_claim)):
        failure_reasons.append("Threshold terminology is not grounded in the retrieved evidence.")

    minimum_overlap = _minimum_overlap_for_query_type(query_type, has_numbers=bool(numeric_claims))
    if claim_tokens and overlap_score < minimum_overlap:
        failure_reasons.append(
            f"Claim token overlap score {overlap_score:.2f} is below the required support threshold {minimum_overlap:.2f}."
        )

    supported = not failure_reasons
    return GuardrailClaimResult(
        claim_text=normalized_claim,
        supported=supported,
        support_score=round(overlap_score, 3),
        evidence_ids=matched_evidence_ids,
        failure_reasons=failure_reasons,
    )


def _extract_claims(draft_answer: str) -> list[str]:
    lines = [line.strip() for line in draft_answer.splitlines() if line.strip()]
    claims: list[str] = []
    for line in lines:
        if line.startswith(NON_CLAIM_PREFIXES):
            continue
        claims.extend(
            sentence.strip()
            for sentence in re.split(r"(?<=[.!?।])\s+|\s*;\s*", line)
            if sentence.strip()
        )
    return claims or [draft_answer.strip()]


def _support_overlap_score(claim: str, evidence_items: Iterable[EvidenceItem]) -> float:
    claim_tokens = _informative_tokens(claim)
    if not claim_tokens:
        return 1.0
    best = 0.0
    for item in evidence_items:
        evidence_tokens = _informative_tokens(item.source_text)
        if not evidence_tokens:
            continue
        overlap = len(claim_tokens & evidence_tokens) / max(len(claim_tokens), 1)
        if overlap > best:
            best = overlap
    return best


def _claim_matches_item(claim: str, item: EvidenceItem) -> bool:
    claim_tokens = _informative_tokens(claim)
    if not claim_tokens:
        return False
    evidence_tokens = _informative_tokens(item.source_text)
    return len(claim_tokens & evidence_tokens) >= min(2, len(claim_tokens))


def _informative_tokens(text: str) -> set[str]:
    return {
        token.lower()
        for token in TOKEN_PATTERN.findall(text)
        if token and token.lower() not in STOPWORDS and len(token) > 1
    }


def _minimum_overlap_for_query_type(query_type: QueryType, *, has_numbers: bool) -> float:
    if query_type in {QueryType.RATE_LOOKUP, QueryType.TABLE_LOOKUP, QueryType.AMOUNT_LOOKUP, QueryType.DATE_LOOKUP, QueryType.DURATION_LOOKUP}:
        return 0.45 if has_numbers else 0.35
    if query_type in {QueryType.SCENARIO_REASONING, QueryType.CROSS_SECTION_REASONING, QueryType.COMPARISON, QueryType.ELIGIBILITY}:
        return 0.25
    return 0.3
