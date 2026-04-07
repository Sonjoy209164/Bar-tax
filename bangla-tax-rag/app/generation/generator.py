import json
import logging
from dataclasses import dataclass

import httpx

from app.core.schemas import (
    AbstentionDecision,
    AnswerSentence,
    CitationRecord,
    GeneratedAnswer,
    GenerationOptions,
    QuerySignals,
    RetrievalHit,
)
from app.core.settings import get_settings
from app.core.utils import clamp_score, detect_text_language, split_sentences, truncate_text
from app.generation.citations import (
    build_citation_records,
    extract_citation_markers,
    map_markers_to_citations,
    render_inline_cited_answer,
)
from app.retrieval.filters import authority_value

logger = logging.getLogger(__name__)


@dataclass
class ChatMessage:
    role: str
    content: str


class ChatCompletionClient:
    def complete(
        self,
        *,
        messages: list[ChatMessage],
        model_name: str,
        temperature: float,
        max_tokens: int,
    ) -> str:
        raise NotImplementedError


class OpenAICompatibleChatClient(ChatCompletionClient):
    def __init__(self, *, base_url: str, api_key: str | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key

    def complete(
        self,
        *,
        messages: list[ChatMessage],
        model_name: str,
        temperature: float,
        max_tokens: int,
    ) -> str:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        payload = {
            "model": model_name,
            "messages": [{"role": message.role, "content": message.content} for message in messages],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        response = httpx.post(f"{self.base_url}/chat/completions", headers=headers, json=payload, timeout=30.0)
        response.raise_for_status()
        response_json = response.json()
        return response_json["choices"][0]["message"]["content"]


class MockChatCompletionClient(ChatCompletionClient):
    def __init__(self, mocked_response: str | None = None) -> None:
        self.mocked_response = mocked_response

    def complete(
        self,
        *,
        messages: list[ChatMessage],
        model_name: str,
        temperature: float,
        max_tokens: int,
    ) -> str:
        if self.mocked_response is not None:
            return self.mocked_response
        return f'{{"answer_sentences":[{{"sentence":"উপলব্ধ প্রমাণ অনুযায়ী নির্ধারিত তথ্য পাওয়া গেছে।","citations":["[C1]"]}}]}}'


def build_generation_options(
    *,
    provider: str | None = None,
    model_name: str | None = None,
    base_url: str | None = None,
    api_key: str | None = None,
) -> GenerationOptions:
    settings = get_settings()
    return GenerationOptions(
        provider=provider or settings.generator_provider,
        model_name=model_name or settings.generator_model_name,
        base_url=base_url or settings.generator_base_url,
        api_key=api_key or settings.generator_api_key,
        max_generation_tokens=settings.max_generation_tokens,
        temperature=settings.temperature,
        abstention_score_threshold=settings.abstention_score_threshold,
        verification_enabled=settings.verification_enabled,
    )


def get_chat_client(options: GenerationOptions, mocked_response: str | None = None) -> ChatCompletionClient:
    if options.provider == "openai_compatible" and options.base_url and options.api_key:
        return OpenAICompatibleChatClient(base_url=options.base_url, api_key=options.api_key)
    return MockChatCompletionClient(mocked_response=mocked_response)


def build_prompt(
    question_text: str,
    evidence_hits: list[RetrievalHit],
    analyzed_query: QuerySignals,
    citations: list[CitationRecord],
) -> list[ChatMessage]:
    evidence_lines = []
    for citation, hit in zip(citations, evidence_hits, strict=False):
        evidence_lines.append(
            f"{citation.marker} chunk_id={hit.chunk_id} doc={hit.doc_title} page={hit.page_no} "
            f"section={hit.section_id or '-'} subsection={hit.subsection_id or '-'}\n"
            f"Evidence: {truncate_text(hit.original_text, max_length=500)}"
        )
    answer_language = "Bangla" if detect_text_language(question_text) == "bangla" else "the same language as the question"
    system_prompt = (
        "You are a grounded legal-tax answer generator. "
        "Answer only from provided evidence. Do not invent facts. "
        "Every factual sentence must include one or more citation markers like [C1]. "
        "If evidence conflicts, explicitly mention the conflict. "
        "If evidence is insufficient, respond with JSON that marks abstention."
    )
    user_prompt = (
        f"Question:\n{question_text}\n\n"
        f"Analyzed Query:\n{analyzed_query.model_dump_json(indent=2)}\n\n"
        f"Answer language: {answer_language}\n\n"
        "Evidence:\n"
        + "\n\n".join(evidence_lines)
        + "\n\n"
        "Return strict JSON with this shape:\n"
        '{"answer_sentences":[{"sentence":"...", "citations":["[C1]"]}], "conflict_notes":["..."]}'
    )
    return [ChatMessage(role="system", content=system_prompt), ChatMessage(role="user", content=user_prompt)]


def detect_unresolved_conflict(evidence_hits: list[RetrievalHit], conflict_notes: list[str]) -> bool:
    if not conflict_notes:
        return False
    authority_levels = {hit.authority_level for hit in evidence_hits}
    if len(authority_levels) <= 1:
        return True
    max_authority = max(authority_value(hit.authority_level) for hit in evidence_hits)
    winners = [hit for hit in evidence_hits if authority_value(hit.authority_level) == max_authority]
    return len(winners) != 1


def pre_generation_abstention(
    *,
    evidence_hits: list[RetrievalHit],
    options: GenerationOptions,
    conflict_notes: list[str],
) -> AbstentionDecision:
    if not evidence_hits:
        return AbstentionDecision(abstained=True, reason="No evidence hits available.", stage="pre")
    top_score = evidence_hits[0].score if evidence_hits else 0.0
    if top_score < options.abstention_score_threshold:
        return AbstentionDecision(abstained=True, reason="Top retrieval score is below threshold.", stage="pre")
    if detect_unresolved_conflict(evidence_hits, conflict_notes):
        return AbstentionDecision(abstained=True, reason="Conflicting evidence without a clear authority winner.", stage="pre")
    return AbstentionDecision(abstained=False)


def parse_model_output(raw_output: str) -> tuple[list[AnswerSentence], list[str]]:
    try:
        parsed_output = json.loads(raw_output)
    except json.JSONDecodeError:
        sentence_texts = split_sentences(raw_output)
        return ([AnswerSentence(sentence_text=text) for text in sentence_texts], [])
    answer_sentences = [
        AnswerSentence(
            sentence_text=item["sentence"].strip(),
            citation_markers=item.get("citations", []),
        )
        for item in parsed_output.get("answer_sentences", [])
        if item.get("sentence")
    ]
    conflict_notes = [str(note) for note in parsed_output.get("conflict_notes", [])]
    return answer_sentences, conflict_notes


def _sentence_overlap_score(sentence_text: str, query_text: str) -> int:
    sentence_tokens = set(sentence_text.lower().split())
    query_tokens = set(query_text.lower().split())
    return len(sentence_tokens & query_tokens)


def build_mock_grounded_answer(
    question_text: str,
    evidence_hits: list[RetrievalHit],
    citations: list[CitationRecord],
) -> tuple[list[AnswerSentence], list[str]]:
    if not evidence_hits or not citations:
        return [], []
    candidate_sentences: list[tuple[int, str, str]] = []
    for citation, hit in zip(citations, evidence_hits, strict=False):
        split_hit_sentences = split_sentences(hit.original_text)
        if not split_hit_sentences:
            continue
        for sentence in split_hit_sentences:
            candidate_sentences.append((_sentence_overlap_score(sentence, question_text), sentence.strip(), citation.marker))
    if not candidate_sentences:
        fallback_sentence = truncate_text(evidence_hits[0].original_text, max_length=220)
        return ([AnswerSentence(sentence_text=fallback_sentence, citation_markers=[citations[0].marker])], [])
    candidate_sentences.sort(key=lambda item: (item[0], len(item[1])), reverse=True)
    best_score, best_sentence, best_marker = candidate_sentences[0]
    answer_sentences = [AnswerSentence(sentence_text=best_sentence, citation_markers=[best_marker])]
    return answer_sentences, []


def repair_citations_if_easy(
    answer_sentences: list[AnswerSentence],
    citations: list[CitationRecord],
) -> list[AnswerSentence]:
    if len(citations) != 1:
        return answer_sentences
    sole_marker = citations[0].marker
    repaired_sentences: list[AnswerSentence] = []
    for sentence in answer_sentences:
        if sentence.citation_markers:
            repaired_sentences.append(sentence)
            continue
        repaired_sentences.append(
            AnswerSentence(
                sentence_text=sentence.sentence_text,
                citation_markers=[sole_marker],
                supported=sentence.supported,
                support_notes=sentence.support_notes,
            )
        )
    return repaired_sentences


def verify_generated_answer(
    answer_sentences: list[AnswerSentence],
    citations: list[CitationRecord],
) -> tuple[bool, list[AnswerSentence], str | None]:
    citation_map = map_markers_to_citations(citations)
    verified_sentences: list[AnswerSentence] = []
    unsupported_messages: list[str] = []
    for sentence in answer_sentences:
        markers = sentence.citation_markers or extract_citation_markers(sentence.sentence_text)
        cleaned_text = sentence.sentence_text.strip()
        if not markers:
            verified_sentences.append(
                AnswerSentence(
                    sentence_text=cleaned_text,
                    citation_markers=[],
                    supported=False,
                    support_notes="Sentence is missing citations.",
                )
            )
            unsupported_messages.append("Sentence missing citations.")
            continue
        invalid_markers = [marker for marker in markers if marker not in citation_map]
        if invalid_markers:
            verified_sentences.append(
                AnswerSentence(
                    sentence_text=cleaned_text,
                    citation_markers=markers,
                    supported=False,
                    support_notes=f"Invalid citation markers: {', '.join(invalid_markers)}",
                )
            )
            unsupported_messages.append("Invalid citation marker found.")
            continue
        cited_text = " ".join(citation_map[marker].evidence_snippet for marker in markers)
        sentence_tokens = set(cleaned_text.lower().split())
        evidence_tokens = set(cited_text.lower().split())
        overlap = len(sentence_tokens & evidence_tokens)
        supported = overlap > 0 or len(sentence_tokens) <= 4
        verified_sentences.append(
            AnswerSentence(
                sentence_text=cleaned_text,
                citation_markers=markers,
                supported=supported,
                support_notes=None if supported else "Sentence has weak lexical support in cited evidence.",
            )
        )
        if not supported:
            unsupported_messages.append("Unsupported sentence found.")
    return (len(unsupported_messages) == 0, verified_sentences, unsupported_messages[0] if unsupported_messages else None)


def compute_confidence_score(
    *,
    evidence_hits: list[RetrievalHit],
    conflict_notes: list[str],
    verification_passed: bool,
) -> float:
    if not evidence_hits:
        return 0.0
    top_score_strength = min(evidence_hits[0].score / 5.0, 1.0)
    support_count_score = min(len(evidence_hits) / 3.0, 1.0)
    conflict_penalty = 0.2 if conflict_notes else 0.0
    verification_bonus = 0.15 if verification_passed else -0.25
    raw_score = (top_score_strength * 0.55) + (support_count_score * 0.25) + verification_bonus - conflict_penalty
    return round(clamp_score(raw_score), 4)


def _build_abstained_answer(reason: str, conflict_notes: list[str] | None = None) -> GeneratedAnswer:
    return GeneratedAnswer(
        answer_text="",
        answer_sentences=[],
        citations=[],
        used_chunk_ids=[],
        confidence_score=0.0,
        abstained=True,
        abstention_reason=reason,
        conflict_notes=conflict_notes or [],
        verification_passed=False,
    )


def generate_answer(
    question_text: str,
    evidence_hits: list[RetrievalHit],
    analyzed_query: QuerySignals | None = None,
    options: GenerationOptions | None = None,
    *,
    mocked_response: str | None = None,
    conflict_notes: list[str] | None = None,
) -> GeneratedAnswer:
    generation_options = options or build_generation_options()
    analyzed_query = analyzed_query or QuerySignals(original_query=question_text, normalized_query=question_text)
    conflict_notes = conflict_notes or []
    abstention = pre_generation_abstention(
        evidence_hits=evidence_hits,
        options=generation_options,
        conflict_notes=conflict_notes,
    )
    if abstention.abstained:
        return _build_abstained_answer(abstention.reason or "Abstained.", conflict_notes=conflict_notes)

    citations = build_citation_records(evidence_hits)
    prompt_messages = build_prompt(question_text, evidence_hits, analyzed_query, citations)
    if generation_options.provider == "mock" and mocked_response is None:
        answer_sentences, model_conflict_notes = build_mock_grounded_answer(
            question_text,
            evidence_hits,
            citations,
        )
    else:
        chat_client = get_chat_client(generation_options, mocked_response=mocked_response)
        try:
            raw_output = chat_client.complete(
                messages=prompt_messages,
                model_name=generation_options.model_name,
                temperature=generation_options.temperature,
                max_tokens=generation_options.max_generation_tokens,
            )
        except Exception as exc:
            logger.exception("Generation call failed")
            if not generation_options.fallback_to_mock:
                return _build_abstained_answer(f"Generation failed: {exc}", conflict_notes=conflict_notes)
            answer_sentences, model_conflict_notes = build_mock_grounded_answer(
                question_text,
                evidence_hits,
                citations,
            )
        else:
            answer_sentences, model_conflict_notes = parse_model_output(raw_output)
    combined_conflict_notes = list(dict.fromkeys(conflict_notes + model_conflict_notes))
    answer_sentences = repair_citations_if_easy(answer_sentences, citations)

    verification_passed = True
    verification_reason: str | None = None
    if generation_options.verification_enabled:
        verification_passed, answer_sentences, verification_reason = verify_generated_answer(answer_sentences, citations)
    if not answer_sentences:
        return _build_abstained_answer("Model returned no usable answer sentences.", conflict_notes=combined_conflict_notes)
    if not verification_passed:
        return _build_abstained_answer(
            verification_reason or "Generated answer failed verification.",
            conflict_notes=combined_conflict_notes,
        )
    if detect_unresolved_conflict(evidence_hits, combined_conflict_notes):
        return _build_abstained_answer(
            "Conflicting evidence remained unresolved after generation.",
            conflict_notes=combined_conflict_notes,
        )

    answer_text = render_inline_cited_answer(answer_sentences)
    used_chunk_ids = [citation.chunk_id for citation in citations if citation.marker in {marker for sentence in answer_sentences for marker in sentence.citation_markers}]
    confidence_score = compute_confidence_score(
        evidence_hits=evidence_hits,
        conflict_notes=combined_conflict_notes,
        verification_passed=verification_passed,
    )
    return GeneratedAnswer(
        answer_text=answer_text,
        answer_sentences=answer_sentences,
        citations=citations,
        used_chunk_ids=list(dict.fromkeys(used_chunk_ids)),
        confidence_score=confidence_score,
        abstained=False,
        abstention_reason=None,
        conflict_notes=combined_conflict_notes,
        verification_passed=verification_passed,
    )
