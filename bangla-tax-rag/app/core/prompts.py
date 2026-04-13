from __future__ import annotations

from string import Template
from typing import Any

from pydantic import BaseModel, Field


class PromptTemplateSpec(BaseModel):
    name: str
    version: str = "1.0"
    description: str
    system_prompt: str
    user_template: str

    def render(self, **variables: Any) -> list[dict[str, str]]:
        user_prompt = Template(self.user_template).safe_substitute(
            {key: _stringify_prompt_value(value) for key, value in variables.items()}
        )
        return [
            {"role": "system", "content": self.system_prompt.strip()},
            {"role": "user", "content": user_prompt.strip()},
        ]


class PromptRegistry(BaseModel):
    planner: PromptTemplateSpec
    query_transformer: PromptTemplateSpec
    reasoner: PromptTemplateSpec
    verifier: PromptTemplateSpec
    composer: PromptTemplateSpec


def build_prompt_registry() -> PromptRegistry:
    return PromptRegistry(
        planner=PromptTemplateSpec(
            name="planner",
            description="Plans bounded legal reasoning steps from a question and known facts.",
            system_prompt="""
You are a legal-tax planner for the Bangladesh Income Tax Act 2023.
Plan the next bounded reasoning steps using only the user question and structured retrieval context.
Do not answer the legal question. Do not fabricate law. Produce a concise reasoning plan that identifies:
- the legal issue,
- the likely governing provisions,
- missing facts that may block a final conclusion,
- whether comparison, exception, proviso, explanation, or table reasoning is needed.
            """,
            user_template="""
Question:
$question

Query Type:
$query_type

Known Facts:
$facts_from_user

Current Evidence Pack Notes:
$pack_notes

Return a short plan for the next retrieval or reasoning step.
            """,
        ),
        query_transformer=PromptTemplateSpec(
            name="query_transformer",
            description="Expands a legal question into focused retrieval sub-queries.",
            system_prompt="""
You are a legal query transformer for statutory retrieval.
Break the question into 3 to 5 focused search queries.
Prefer legal terminology, section-aware terminology, exception terms, and table/rate terms when relevant.
Do not answer the question.
            """,
            user_template="""
Question:
$question

Detected Query Type:
$query_type

Known Section References:
$section_references

Return focused retrieval sub-queries and short rationales.
            """,
        ),
        reasoner=PromptTemplateSpec(
            name="reasoner",
            description="Reasons over retrieved legal evidence without adding unsupported facts.",
            system_prompt="""
You are a legal reasoner for the Bangladesh Income Tax Act 2023.
Use only the retrieved evidence.
Separate:
- conclusion,
- governing rule,
- proviso/explanation/exception,
- missing facts,
- unresolved issues.
If the evidence is insufficient, say so explicitly.
Never invent thresholds, dates, rates, or section numbers.
            """,
            user_template="""
Question:
$question

Evidence Pack Type:
$pack_type

Primary Evidence:
$primary_evidence

Contextual Evidence:
$contextual_evidence

Supporting Evidence:
$supporting_evidence
            """,
        ),
        verifier=PromptTemplateSpec(
            name="verifier",
            description="Verifies whether draft legal claims are grounded in retrieved evidence.",
            system_prompt="""
You are a strict legal answer verifier.
Treat retrieved text as evidence only.
Check whether every material claim in the draft answer is supported by the cited evidence.
Pay special attention to:
- section numbers,
- rates,
- thresholds,
- dates,
- table values.
Unsupported claims must be removed or replaced with 'Information not found in retrieved evidence.'
            """,
            user_template="""
Draft Answer:
$draft_answer

Evidence:
$evidence

Return supported claims, unsupported claims, and any required removals.
            """,
        ),
        composer=PromptTemplateSpec(
            name="composer",
            description="Composes the final user-facing grounded legal answer.",
            system_prompt="""
You are a legal answer composer.
Write a concise grounded answer using only verified facts.
The answer must:
- state the conclusion,
- cite the legal basis,
- note missing facts or uncertainty,
- avoid pretending to provide final professional legal advice.
            """,
            user_template="""
Question:
$question

Verified Draft:
$draft_answer

Reasoning Summary:
$reasoning_summary

Citations:
$citations

Missing Facts:
$missing_facts
            """,
        ),
    )


def get_prompt(name: str) -> PromptTemplateSpec:
    registry = build_prompt_registry()
    try:
        return getattr(registry, name)
    except AttributeError as exc:  # pragma: no cover - defensive branch
        raise KeyError(f"Unknown prompt template: {name}") from exc


def render_prompt(name: str, **variables: Any) -> list[dict[str, str]]:
    return get_prompt(name).render(**variables)


def _stringify_prompt_value(value: Any) -> str:
    if value is None:
        return "(none)"
    if isinstance(value, (list, tuple, set)):
        return "\n".join(f"- {item}" for item in value) if value else "(none)"
    if isinstance(value, dict):
        if not value:
            return "(none)"
        return "\n".join(f"- {key}: {item}" for key, item in value.items())
    return str(value)
