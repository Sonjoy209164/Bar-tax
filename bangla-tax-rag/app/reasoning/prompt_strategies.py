from __future__ import annotations

from typing import Any, Literal, TYPE_CHECKING

from app.core.utils import detect_text_language

if TYPE_CHECKING:  # pragma: no cover - imported for static typing only
    from app.domain import EvidenceItem
    from app.reasoning.state import AgentState


PromptStrategyName = Literal["zero_shot", "one_shot", "few_shot", "evidence_only"]
ReasoningTraceMode = Literal["off", "summary", "trace"]

PROMPT_STRATEGIES: tuple[PromptStrategyName, ...] = ("zero_shot", "one_shot", "few_shot", "evidence_only")
REASONING_TRACE_MODES: tuple[ReasoningTraceMode, ...] = ("off", "summary", "trace")

NON_CLAIM_PREFIXES = (
    "Legal basis:",
    "Reasoning:",
    "Missing facts:",
    "Citations:",
    "Verification:",
    "Coverage note:",
    "Short answer:",
    "সংক্ষিপ্ত উত্তর:",
    "প্রযোজ্য বিধান:",
    "যুক্তির সারাংশ:",
    "অপূর্ণ তথ্য:",
    "উৎস:",
    "যাচাই:",
    "সীমাবদ্ধতা:",
)

_PROMPT_EXAMPLES: dict[PromptStrategyName, list[dict[str, str]]] = {
    "zero_shot": [],
    "evidence_only": [],
    "one_shot": [
        {
            "id": "bangla_tax_direct_rate_lookup",
            "question": "২০২৫-২০২৬ করবর্ষে স্বাভাবিক ব্যক্তির করহার কী?",
            "answer_shape": "সংক্ষিপ্ত উত্তর + প্রযোজ্য বিধান",
        }
    ],
    "few_shot": [
        {
            "id": "bangla_tax_direct_rate_lookup",
            "question": "২০২৫-২০২৬ করবর্ষে স্বাভাবিক ব্যক্তির করহার কী?",
            "answer_shape": "সংক্ষিপ্ত উত্তর + প্রযোজ্য বিধান",
        },
        {
            "id": "bangla_tax_missing_fact_check",
            "question": "আমি শ্রমিক, আমার কর কত?",
            "answer_shape": "প্রমাণভিত্তিক উত্তর + অপূর্ণ তথ্য",
        },
        {
            "id": "bangla_tax_exception_check",
            "question": "কোন করদাতার করমুক্ত আয়সীমা বেশি?",
            "answer_shape": "উত্তর + ব্যতিক্রম বা শ্রেণি সতর্কতা",
        },
    ],
}


def normalize_prompt_strategy(value: Any) -> PromptStrategyName:
    normalized = str(value or "zero_shot").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "zero": "zero_shot",
        "zeroshot": "zero_shot",
        "one": "one_shot",
        "oneshot": "one_shot",
        "few": "few_shot",
        "fewshot": "few_shot",
        "evidence": "evidence_only",
        "evidenceonly": "evidence_only",
    }
    normalized = aliases.get(normalized, normalized)
    if normalized not in PROMPT_STRATEGIES:
        raise ValueError(f"prompt_strategy must be one of: {', '.join(PROMPT_STRATEGIES)}")
    return normalized  # type: ignore[return-value]


def normalize_reasoning_trace_mode(value: Any) -> ReasoningTraceMode:
    normalized = str(value or "summary").strip().lower().replace("-", "_").replace(" ", "_")
    aliases = {
        "none": "off",
        "disabled": "off",
        "safe_summary": "summary",
        "chain_of_thought": "trace",
        "cot": "trace",
        "safe_trace": "trace",
    }
    normalized = aliases.get(normalized, normalized)
    if normalized not in REASONING_TRACE_MODES:
        raise ValueError(f"reasoning_trace_mode must be one of: {', '.join(REASONING_TRACE_MODES)}")
    return normalized  # type: ignore[return-value]


def apply_prompt_strategy(
    answer: str,
    *,
    state: "AgentState",
    evidence_items: list["EvidenceItem"],
) -> str:
    strategy = normalize_prompt_strategy(state.prompt_strategy)
    state.prompt_strategy = strategy
    examples = _PROMPT_EXAMPLES[strategy]
    state.trace_metadata["prompt_strategy"] = strategy
    state.trace_metadata["prompt_examples_used"] = [example["id"] for example in examples]
    state.trace_metadata["prompt_example_count"] = len(examples)

    answer = answer.strip()
    if not answer or answer == "Information not found in retrieved evidence.":
        return answer
    if strategy in {"zero_shot", "evidence_only"}:
        if strategy == "evidence_only":
            state.add_reasoning_note("Evidence-only prompt strategy used; answer wording was limited to retrieved text.")
        return answer

    use_bangla_labels = _should_use_bangla_labels(answer, state)
    if use_bangla_labels:
        return _format_bangla_strategy_answer(answer, state=state, include_missing_facts=strategy == "few_shot")
    return _format_english_strategy_answer(answer, state=state, include_missing_facts=strategy == "few_shot")


def build_safe_reasoning_trace(state: "AgentState", mode: str | ReasoningTraceMode) -> dict[str, Any]:
    normalized_mode = normalize_reasoning_trace_mode(mode)
    if normalized_mode == "off":
        return {}

    trace: dict[str, Any] = {
        "mode": normalized_mode,
        "trace_id": state.trace_id,
        "prompt_strategy": state.prompt_strategy,
        "query_type": state.query_type.value,
        "execution_path": state.execution_path.value,
        "completed_nodes": list(state.completed_nodes),
        "evidence_pack_type": state.latest_evidence_pack_type,
        "selected_evidence_ids": list(state.latest_selected_evidence_ids),
        "citation_count": len(state.citations),
        "verification": {
            "error_count": sum(1 for failure in state.verification_failures if failure.severity == "error"),
            "warning_count": sum(1 for failure in state.verification_failures if failure.severity == "warning"),
        },
        "prompt_examples_used": list(state.trace_metadata.get("prompt_examples_used") or []),
    }
    if normalized_mode != "trace":
        return trace

    trace.update(
        {
            "planned_steps": [
                {
                    "goal": step.goal,
                    "sub_query": step.sub_query,
                    "preferred_node_types": list(step.preferred_node_types),
                    "metadata_filters": dict(step.metadata_filters),
                }
                for step in state.planned_steps
            ],
            "retrieval_attempts": [
                {
                    "attempt_number": attempt.attempt_number,
                    "query_text": attempt.query_text,
                    "retrieval_mode": attempt.retrieval_mode,
                    "candidate_evidence_ids": list(attempt.candidate_evidence_ids[:20]),
                    "selected_evidence_ids": list(attempt.selected_evidence_ids),
                    "requires_more_retrieval": attempt.requires_more_retrieval,
                    "notes": list(attempt.notes[:5]),
                }
                for attempt in state.retrieval_attempts
            ],
            "candidate_chunk_ids": list(state.latest_candidate_chunk_ids[:20]),
            "missing_coverage": list(state.latest_missing_coverage),
            "pack_notes": list(state.latest_pack_notes),
            "trace_metadata": _public_trace_metadata(state.trace_metadata),
        }
    )
    return trace


def _should_use_bangla_labels(answer: str, state: "AgentState") -> bool:
    return detect_text_language(answer) == "bangla" or detect_text_language(state.question) == "bangla"


def _format_bangla_strategy_answer(answer: str, *, state: "AgentState", include_missing_facts: bool) -> str:
    parts = ["সংক্ষিপ্ত উত্তর:", answer]
    basis = _basis_text(state)
    if basis:
        parts.append(f"প্রযোজ্য বিধান: {basis}")
    if include_missing_facts and state.missing_facts:
        parts.append("অপূর্ণ তথ্য: " + "; ".join(state.missing_facts[:3]))
    parts.append("সীমাবদ্ধতা: উত্তরটি শুধু উদ্ধারকৃত প্রমাণের ভিত্তিতে দেওয়া হয়েছে।")
    return "\n\n".join(parts)


def _format_english_strategy_answer(answer: str, *, state: "AgentState", include_missing_facts: bool) -> str:
    parts = ["Short answer:", answer]
    basis = _basis_text(state)
    if basis:
        parts.append(f"Legal basis: {basis}")
    if include_missing_facts and state.missing_facts:
        parts.append("Missing facts: " + "; ".join(state.missing_facts[:3]))
    parts.append("Verification: Answer limited to retrieved evidence.")
    return "\n\n".join(parts)


def _basis_text(state: "AgentState") -> str:
    if state.rules_found:
        return "; ".join(state.rules_found[:3])
    if state.citations:
        return "; ".join(
            citation.citability_label or f"Section {citation.section_number}" if citation.section_number else citation.node_id
            for citation in state.citations[:3]
        )
    return ""


def _public_trace_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    allowed_prefixes = (
        "reasoning_backend",
        "router_",
        "query_plan_",
        "latest_",
        "prompt_",
        "guardrail_",
    )
    public: dict[str, Any] = {}
    for key, value in metadata.items():
        if any(key == prefix or key.startswith(prefix) for prefix in allowed_prefixes):
            public[key] = value
    return public
