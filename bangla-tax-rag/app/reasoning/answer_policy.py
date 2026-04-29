from __future__ import annotations

import re

from pydantic import BaseModel, Field

from app.reasoning.nli_guardrail import GuardrailVerificationResult, REFUSAL_TEXT
from app.reasoning.prompt_strategies import NON_CLAIM_PREFIXES


class AnswerPolicyDecision(BaseModel):
    final_draft: str
    removed_claims: list[str] = Field(default_factory=list)
    appended_notice: str | None = None
    refused: bool = False


class GuardrailedAnswerPolicy:
    def apply(self, draft_answer: str, verification: GuardrailVerificationResult) -> AnswerPolicyDecision:
        unsupported_claims = {claim.claim_text for claim in verification.unsupported_claims}
        if not unsupported_claims:
            return AnswerPolicyDecision(final_draft=draft_answer)

        filtered_lines: list[str] = []
        removed_claims: list[str] = []
        for line in [line for line in draft_answer.splitlines() if line.strip()]:
            if line.startswith(NON_CLAIM_PREFIXES):
                filtered_lines.append(line)
                continue
            kept_sentences: list[str] = []
            for sentence in _split_claim_sentences(line):
                if sentence in unsupported_claims:
                    removed_claims.append(sentence)
                    continue
                kept_sentences.append(sentence)
            if kept_sentences:
                filtered_lines.append(" ".join(kept_sentences))

        if not any(
            line for line in filtered_lines if not line.startswith(NON_CLAIM_PREFIXES)
        ):
            return AnswerPolicyDecision(
                final_draft=REFUSAL_TEXT,
                removed_claims=removed_claims,
                appended_notice=REFUSAL_TEXT,
                refused=True,
            )

        appended_notice = None
        if removed_claims:
            appended_notice = "Information not found in retrieved evidence."
            filtered_lines.append(f"Verification: {appended_notice}")

        return AnswerPolicyDecision(
            final_draft="\n\n".join(filtered_lines),
            removed_claims=removed_claims,
            appended_notice=appended_notice,
            refused=False,
        )


def apply_answer_policy(draft_answer: str, verification: GuardrailVerificationResult) -> AnswerPolicyDecision:
    return GuardrailedAnswerPolicy().apply(draft_answer, verification)


def _split_claim_sentences(line: str) -> list[str]:
    return [
        sentence.strip()
        for sentence in re.split(r"(?<=[.!?।])\s+|\s*;\s*", line)
        if sentence.strip()
    ]
