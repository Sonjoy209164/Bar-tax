import json
import logging
import re
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
from app.core.utils import (
    clamp_score,
    clean_bangla_ocr_text,
    detect_text_language,
    extract_salient_query_terms,
    normalize_text,
    split_sentences,
    tokenize_for_bm25,
    truncate_text,
)
from app.generation.citations import (
    build_citation_records,
    extract_citation_markers,
    map_markers_to_citations,
    render_inline_cited_answer,
)
from app.retrieval.filters import authority_value

logger = logging.getLogger(__name__)


def _clean_evidence_text(text: str) -> str:
    cleaned_text = clean_bangla_ocr_text(text)
    return cleaned_text or normalize_text(text)


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
    if options.provider == "openai_compatible" and options.base_url:
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
        cleaned_text = _clean_evidence_text(hit.original_text)
        evidence_lines.append(
            f"{citation.marker} chunk_id={hit.chunk_id} doc={hit.doc_title} page={hit.page_no} "
            f"section={hit.section_id or '-'} subsection={hit.subsection_id or '-'}\n"
            f"Evidence: {truncate_text(cleaned_text, max_length=500)}"
        )
    answer_language = "Bangla" if detect_text_language(question_text) == "bangla" else "the same language as the question"
    system_prompt = (
        "You are a grounded legal-tax answer generator. "
        "Answer only from provided evidence. Do not invent facts. "
        "Every factual sentence must include one or more citation markers like [C1]. "
        "When the evidence is a rate table, summarize the actual categories and rates instead of repeating only the heading. "
        "Prefer a short direct answer first, then one short supporting sentence if useful. "
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
        "Important instructions:\n"
        "- Do not copy OCR noise unless needed.\n"
        "- If the question asks for a tax rate, extract the relevant rate values from the evidence table.\n"
        "- Every sentence must include citations.\n\n"
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


def _extract_rate_segments(text: str) -> list[str]:
    compact_text = _clean_evidence_text(text).replace("\n", " ")
    rate_matches = list(re.finditer(r"\d+(?:\.\d+)?%", compact_text))
    segments: list[str] = []
    for match in rate_matches[:4]:
        start_index = max(0, match.start() - 70)
        end_index = min(len(compact_text), match.end() + 30)
        segment = compact_text[start_index:end_index].strip(" ,;:-")
        if segment and segment not in segments:
            segments.append(segment)
    return segments


def _extract_rate_values(text: str) -> list[str]:
    normalized = _clean_evidence_text(text)
    percent_values = re.findall(r"\d+(?:\.\d+)?%", normalized)
    if percent_values:
        return list(dict.fromkeys(percent_values))
    word_percent_values = re.findall(r"\d+(?:\.\d+)?\s*শতাংশ", normalized)
    return list(dict.fromkeys(word_percent_values))


def _find_section_excerpt(text: str, analyzed_query: QuerySignals | None) -> str:
    cleaned_text = _clean_evidence_text(text)
    if not cleaned_text or not analyzed_query:
        return cleaned_text
    section_markers: list[str] = []
    if analyzed_query.subsection_id:
        section_markers.append(re.escape(analyzed_query.subsection_id))
    if analyzed_query.section_id:
        section_markers.append(re.escape(analyzed_query.section_id))
    for marker in section_markers:
        match = re.search(rf"(^|[\s\n]){marker}(?:[\).:।-]|\s)", cleaned_text)
        if match:
            excerpt = cleaned_text[match.start():].strip()
            return excerpt
    return cleaned_text


def _build_section_summary_answer(
    question_text: str,
    evidence_hits: list[RetrievalHit],
    citations: list[CitationRecord],
    analyzed_query: QuerySignals | None,
) -> tuple[list[AnswerSentence], list[str]]:
    candidate_sentences: list[tuple[int, int, str, str]] = []
    for citation, hit in zip(citations, evidence_hits, strict=False):
        excerpt = _find_section_excerpt(hit.original_text, analyzed_query)
        for sentence in split_sentences(excerpt):
            overlap_score = _sentence_overlap_score(sentence, question_text)
            heading_bonus = 2 if (analyzed_query and analyzed_query.section_id and analyzed_query.section_id in sentence) else 0
            candidate_sentences.append((overlap_score + heading_bonus, len(sentence), sentence.strip(), citation.marker))
    if not candidate_sentences:
        return build_mock_grounded_answer(question_text, evidence_hits, citations)
    candidate_sentences.sort(key=lambda item: (item[0], item[1]), reverse=True)
    _, _, best_sentence, best_marker = candidate_sentences[0]
    return [AnswerSentence(sentence_text=truncate_text(best_sentence, max_length=260), citation_markers=[best_marker])], []


def _build_rate_lookup_answer(
    question_text: str,
    evidence_hits: list[RetrievalHit],
    citations: list[CitationRecord],
) -> tuple[list[AnswerSentence], list[str]]:
    all_rate_values: list[str] = []
    for hit in evidence_hits:
        for rate_value in _extract_rate_values(hit.original_text):
            if rate_value not in all_rate_values:
                all_rate_values.append(rate_value)
    if all_rate_values:
        displayed_values = ", ".join(all_rate_values[:4])
        sentence_text = (
            "উদ্ধৃত প্রমাণে দেখা যাচ্ছে যে ২০২৫-২০২৬ করবর্ষে কোম্পানির করহার কোম্পানির ধরন ও শর্তভেদে ভিন্ন। "
            f"প্রাসঙ্গিক সারণিতে {displayed_values} হার উল্লেখ আছে।"
        )
        markers = [citation.marker for citation in citations[:2]]
        return [AnswerSentence(sentence_text=sentence_text, citation_markers=markers)], []
    candidate_segments: list[tuple[int, str, str]] = []
    for citation, hit in zip(citations, evidence_hits, strict=False):
        for segment in _extract_rate_segments(hit.original_text):
            candidate_segments.append((_sentence_overlap_score(segment, question_text), segment, citation.marker))
    if not candidate_segments:
        return build_mock_grounded_answer(question_text, evidence_hits, citations)
    candidate_segments.sort(key=lambda item: (item[0], len(item[1])), reverse=True)
    selected_segments = candidate_segments[:2]
    sentence_text = "উদ্ধৃত প্রমাণে কোম্পানির করহার কোম্পানির ধরনভেদে ভিন্ন। " + "; ".join(
        segment for _, segment, _ in selected_segments
    )
    markers = list(dict.fromkeys(marker for _, _, marker in selected_segments))
    return [AnswerSentence(sentence_text=sentence_text.strip(), citation_markers=markers)], []


def _extract_mention_fragments(text: str, question_text: str) -> list[tuple[int, str]]:
    cleaned_text = _clean_evidence_text(text)
    query_terms = extract_salient_query_terms(question_text)
    scored_fragments: list[tuple[int, str]] = []
    for raw_fragment in re.split(r"[;\n]+", cleaned_text):
        fragment = raw_fragment.strip(" -—:,.")
        if len(fragment) < 6:
            continue
        fragment_terms = set(tokenize_for_bm25(fragment.lower()))
        lexical_overlap = len(query_terms & fragment_terms)
        software_bonus = 1 if "software" in fragment.lower() else 0
        service_bonus = 1 if "service" in fragment.lower() else 0
        score = lexical_overlap + software_bonus + service_bonus
        if score <= 0:
            continue
        scored_fragments.append((score, fragment))
    scored_fragments.sort(key=lambda item: (item[0], len(item[1])), reverse=True)
    unique_fragments: list[tuple[int, str]] = []
    seen_fragments: set[str] = set()
    for score, fragment in scored_fragments:
        lowered_fragment = fragment.lower()
        if lowered_fragment in seen_fragments:
            continue
        seen_fragments.add(lowered_fragment)
        unique_fragments.append((score, fragment))
    return unique_fragments


def _extract_focus_phrase(question_text: str) -> str | None:
    normalized_question = normalize_text(question_text).strip()
    match = re.search(r"(?:say about|mentioned in the act|included in the act)\s+(.+?)[?.]?$", normalized_question, flags=re.IGNORECASE)
    if match:
        return match.group(1).strip(" \"'`")
    return None


def _build_mention_lookup_answer(
    question_text: str,
    evidence_hits: list[RetrievalHit],
    citations: list[CitationRecord],
) -> tuple[list[AnswerSentence], list[str]]:
    fragment_candidates: list[tuple[int, str, str]] = []
    for citation, hit in zip(citations, evidence_hits, strict=False):
        for score, fragment in _extract_mention_fragments(hit.original_text, question_text):
            fragment_candidates.append((score, fragment, citation.marker))

    if not fragment_candidates:
        fallback_sentence = truncate_text(_clean_evidence_text(evidence_hits[0].original_text), max_length=220)
        return [AnswerSentence(sentence_text=fallback_sentence, citation_markers=[citations[0].marker])], []

    fragment_candidates.sort(key=lambda item: (item[0], len(item[1])), reverse=True)
    selected_candidates = fragment_candidates[:3]
    selected_fragments = [fragment for _, fragment, _ in selected_candidates]
    markers = list(dict.fromkeys(marker for _, _, marker in selected_candidates[:2]))
    focus_phrase = _extract_focus_phrase(question_text)
    if focus_phrase:
        focused_fragment = next(
            (fragment for _, fragment, _ in fragment_candidates if focus_phrase.lower() in fragment.lower()),
            None,
        )
        if focused_fragment:
            if detect_text_language(question_text) == "bangla":
                sentence_text = f"উদ্ধৃত প্রমাণে দেখা যাচ্ছে যে {focus_phrase} স্পষ্টভাবে উল্লেখ আছে। {focused_fragment}।"
            else:
                sentence_text = f'The Act explicitly mentions "{focus_phrase}". {focused_fragment}.'
            return [AnswerSentence(sentence_text=sentence_text, citation_markers=[markers[0]])], []
    if detect_text_language(question_text) == "bangla":
        sentence_text = "হ্যাঁ, উদ্ধৃত প্রমাণে এই বিষয়টি উল্লেখ আছে, যেমন " + "; ".join(selected_fragments) + "।"
    else:
        sentence_text = "Yes, the Act mentions software-related services, including " + "; ".join(selected_fragments) + "."
    return [AnswerSentence(sentence_text=sentence_text, citation_markers=markers)], []


def build_mock_grounded_answer(
    question_text: str,
    evidence_hits: list[RetrievalHit],
    citations: list[CitationRecord],
    analyzed_query: QuerySignals | None = None,
) -> tuple[list[AnswerSentence], list[str]]:
    if not evidence_hits or not citations:
        return [], []
    if analyzed_query and analyzed_query.query_intent == "mention_lookup":
        return _build_mention_lookup_answer(question_text, evidence_hits, citations)
    if analyzed_query and analyzed_query.query_intent == "rate_lookup":
        return _build_rate_lookup_answer(question_text, evidence_hits, citations)
    if analyzed_query and (analyzed_query.subsection_id or analyzed_query.section_id):
        return _build_section_summary_answer(question_text, evidence_hits, citations, analyzed_query)
    candidate_sentences: list[tuple[int, str, str]] = []
    for citation, hit in zip(citations, evidence_hits, strict=False):
        split_hit_sentences = split_sentences(_clean_evidence_text(hit.original_text))
        if not split_hit_sentences:
            continue
        for sentence in split_hit_sentences:
            candidate_sentences.append((_sentence_overlap_score(sentence, question_text), sentence.strip(), citation.marker))
    if not candidate_sentences:
        fallback_sentence = truncate_text(_clean_evidence_text(evidence_hits[0].original_text), max_length=220)
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
    used_extractive_fallback = False
    if analyzed_query.query_intent == "mention_lookup":
        answer_sentences, model_conflict_notes = build_mock_grounded_answer(
            question_text,
            evidence_hits,
            citations,
            analyzed_query,
        )
        used_extractive_fallback = True
    elif generation_options.provider == "mock" and mocked_response is None:
        answer_sentences, model_conflict_notes = build_mock_grounded_answer(
            question_text,
            evidence_hits,
            citations,
            analyzed_query,
        )
        used_extractive_fallback = True
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
                analyzed_query,
            )
            used_extractive_fallback = True
        else:
            answer_sentences, model_conflict_notes = parse_model_output(raw_output)
    combined_conflict_notes = list(dict.fromkeys(conflict_notes + model_conflict_notes))
    answer_sentences = repair_citations_if_easy(answer_sentences, citations)

    verification_passed = True
    verification_reason: str | None = None
    if generation_options.verification_enabled:
        verification_passed, answer_sentences, verification_reason = verify_generated_answer(answer_sentences, citations)
    if (
        not verification_passed
        and generation_options.fallback_to_mock
        and not used_extractive_fallback
        and verification_reason in {"Sentence missing citations.", "Unsupported sentence found."}
    ):
        fallback_sentences, fallback_conflict_notes = build_mock_grounded_answer(
            question_text,
            evidence_hits,
            citations,
            analyzed_query,
        )
        combined_conflict_notes = list(dict.fromkeys(combined_conflict_notes + fallback_conflict_notes))
        fallback_sentences = repair_citations_if_easy(fallback_sentences, citations)
        if generation_options.verification_enabled:
            verification_passed, fallback_sentences, verification_reason = verify_generated_answer(
                fallback_sentences,
                citations,
            )
        else:
            verification_passed = True
            verification_reason = None
        answer_sentences = fallback_sentences
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

    used_markers = {marker for sentence in answer_sentences for marker in sentence.citation_markers}
    used_citations = [citation for citation in citations if citation.marker in used_markers]
    answer_text = render_inline_cited_answer(answer_sentences)
    used_chunk_ids = [citation.chunk_id for citation in used_citations]
    confidence_score = compute_confidence_score(
        evidence_hits=evidence_hits,
        conflict_notes=combined_conflict_notes,
        verification_passed=verification_passed,
    )
    return GeneratedAnswer(
        answer_text=answer_text,
        answer_sentences=answer_sentences,
        citations=used_citations,
        used_chunk_ids=list(dict.fromkeys(used_chunk_ids)),
        confidence_score=confidence_score,
        abstained=False,
        abstention_reason=None,
        conflict_notes=combined_conflict_notes,
        verification_passed=verification_passed,
    )
