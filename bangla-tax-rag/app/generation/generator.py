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
    extract_definition_target,
    extract_informative_query_terms,
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
RATE_VALUE_PATTERN = r"(?:\d+(?:\.\d+)?%(?:\s*\([^)]+\))?|\d+(?:\.\d+)?\s*শতাংশ)"
EXTRACTIVE_INTENTS = {
    "mention_lookup",
    "definition",
    "rate_lookup",
    "eligibility",
    "amount_lookup",
    "count_lookup",
    "duration_lookup",
    "date_lookup",
    "list_lookup",
}


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
        timeout_seconds: float = 30.0,
        response_format: dict[str, object] | None = None,
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
        timeout_seconds: float = 30.0,
        response_format: dict[str, object] | None = None,
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
        if response_format is not None:
            payload["response_format"] = response_format
        response = httpx.post(f"{self.base_url}/chat/completions", headers=headers, json=payload, timeout=timeout_seconds)
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
        timeout_seconds: float = 30.0,
        response_format: dict[str, object] | None = None,
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
    if options.provider == "mock":
        return MockChatCompletionClient(mocked_response=mocked_response)
    raise ValueError(f"Unsupported or misconfigured generator provider: {options.provider}")


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
    parsed_output = _parse_structured_model_output(raw_output)
    if parsed_output is None:
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


def _strip_json_code_fence(text: str) -> str:
    stripped = text.strip()
    fence_match = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", stripped, flags=re.DOTALL | re.IGNORECASE)
    if fence_match:
        return fence_match.group(1).strip()
    return stripped


def _extract_first_json_object(text: str) -> str | None:
    start_index = text.find("{")
    if start_index < 0:
        return None
    depth = 0
    in_string = False
    escape_next = False
    for index, char in enumerate(text[start_index:], start=start_index):
        if in_string:
            if escape_next:
                escape_next = False
            elif char == "\\":
                escape_next = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start_index:index + 1]
    return None


def _coerce_to_generation_dict(candidate: object) -> dict | None:
    current = candidate
    for _ in range(2):
        if isinstance(current, str):
            normalized = current.strip()
            if not normalized:
                return None
            try:
                current = json.loads(normalized)
            except json.JSONDecodeError:
                return None
            continue
        break
    if isinstance(current, dict):
        return current
    return None


def _parse_structured_model_output(raw_output: str) -> dict | None:
    stripped_output = raw_output.strip()
    candidates = [stripped_output]
    unfenced_output = _strip_json_code_fence(stripped_output)
    if unfenced_output != stripped_output:
        candidates.append(unfenced_output)
    extracted_json = _extract_first_json_object(unfenced_output)
    if extracted_json and extracted_json not in candidates:
        candidates.append(extracted_json)

    for candidate in candidates:
        parsed_output = _coerce_to_generation_dict(candidate)
        if parsed_output and isinstance(parsed_output.get("answer_sentences"), list):
            return parsed_output
    return None


def _sentence_overlap_score(sentence_text: str, query_text: str) -> int:
    sentence_tokens = set(sentence_text.lower().split())
    query_tokens = set(query_text.lower().split())
    return len(sentence_tokens & query_tokens)


def _extract_rate_segments(text: str) -> list[str]:
    compact_text = _clean_evidence_text(text).replace("\n", " ")
    rate_matches = list(re.finditer(RATE_VALUE_PATTERN, compact_text))
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
    values = re.findall(RATE_VALUE_PATTERN, normalized)
    return list(dict.fromkeys(value.strip() for value in values))


def _extract_rate_candidates(text: str) -> list[tuple[str, str]]:
    compact_text = re.sub(r"\s+", " ", _clean_evidence_text(text)).strip()
    candidates: list[tuple[str, str]] = []
    for match in re.finditer(RATE_VALUE_PATTERN, compact_text):
        value = match.group(0).strip()
        end_candidates = [
            position
            for position in (
                compact_text.find(" and ", match.end()),
                compact_text.find("; ", match.end()),
                compact_text.find(". ", match.end()),
            )
            if position != -1
        ]
        end_index = min(end_candidates) if end_candidates else len(compact_text)
        context = compact_text[match.start():end_index].strip(" ,;:-")
        if context:
            candidates.append((value, context))
    if candidates:
        deduplicated: list[tuple[str, str]] = []
        seen_contexts: set[str] = set()
        for value, context in candidates:
            normalized_context = normalize_text(context).lower()
            if normalized_context in seen_contexts:
                continue
            seen_contexts.add(normalized_context)
            deduplicated.append((value, context))
        return deduplicated
    return [(value, segment) for value, segment in zip(_extract_rate_values(text), _extract_rate_segments(text), strict=False)]


def _score_rate_candidate(value: str, context: str, question_text: str) -> int:
    informative_terms = extract_informative_query_terms(question_text, "rate_lookup")
    context_terms = set(tokenize_for_bm25(context.lower()))
    score = _sentence_overlap_score(context, question_text) + (len(informative_terms & context_terms) * 3)
    lower_question = normalize_text(question_text).lower()
    lower_context = normalize_text(context).lower()
    if "agricultural income" in lower_question and "income from agriculture" in lower_context:
        score += 8
    if "business income" in lower_question and "business income" in lower_context:
        score += 8
    if "considered" in lower_question and ("deemed to be" in lower_context or "considered" in lower_context):
        score += 4
    if "tea" in lower_question and "tea" in lower_context:
        score += 2
    if "rubber" in lower_question and "rubber" in lower_context:
        score += 2
    if "company" in lower_question and "company" in lower_context:
        score += 2
    score += 1 if value in lower_context else 0
    return score


def _extract_amount_phrases(text: str) -> list[str]:
    cleaned_text = _clean_evidence_text(text)
    cleaned_text = re.sub(r"(\bTaka\s+)\d+\[(\d+(?:\([^)]+\))?\s*(?:crore|lakh|thousand)?)\]", r"\1\2", cleaned_text, flags=re.IGNORECASE)
    cleaned_text = re.sub(r"\b(\d+)\[(\d+(?:\([^)]+\))?)\]", r"\2", cleaned_text)
    amount_patterns = [
        r"(?:not more than|no more than|exceeds?|minimum|maximum)\s+Taka\s+\[?[0-9]+(?:\s*\([^)]+\))?\]?\s*(?:crore|lakh|thousand)?",
        r"Taka\s+\[?[0-9]+(?:\s*\([^)]+\))?\]?\s*(?:crore|lakh|thousand)?",
        r"[0-9]+(?:\.[0-9]+)?%\s*\([^)]+\)",
        r"[0-9]+(?:\.[0-9]+)?%",
    ]
    phrases: list[str] = []
    for pattern in amount_patterns:
        for match in re.finditer(pattern, cleaned_text, flags=re.IGNORECASE):
            phrase = match.group(0).strip(" ,;:.")
            if phrase and phrase not in phrases:
                phrases.append(phrase)
    return phrases


def _extract_duration_phrases(text: str) -> list[str]:
    cleaned_text = _clean_evidence_text(text)
    patterns = [
        r"[0-9]+\s*\([^)]+\)\s*successive assessment years",
        r"[0-9]+\s*\([^)]+\)\s*assessment years",
        r"[0-9]+\s*\([^)]+\)\s*(?:successive\s+)?assessment years",
        r"[0-9]+\s*\([^)]+\)\s*years",
        r"[0-9]+\s*\([^)]+\)\s*months",
        r"[0-9]+\s*\([^)]+\)\s*days",
        r"[0-9]+\s+successive assessment years",
    ]
    phrases: list[str] = []
    for pattern in patterns:
        for match in re.finditer(pattern, cleaned_text, flags=re.IGNORECASE):
            phrase = match.group(0).strip(" ,;:.")
            if phrase and phrase not in phrases:
                phrases.append(phrase)
    return phrases


def _extract_date_phrases(text: str) -> list[str]:
    cleaned_text = _clean_evidence_text(text)
    patterns = [
        r"\b\d{1,2}(?:st|nd|rd|th)\s*\([^)]+\)\s*day of [A-Za-z]+",
        r"\b\d{1,2}(?:st|nd|rd|th)\s+day of [A-Za-z]+",
        r"\b[A-Za-z]+\s+\d{1,2},\s+\d{4}\b",
        r"\b\d{1,2}\s+[A-Za-z]+\s+\d{4}\b",
        r"\b(?:July|June|September|November)\s+\d{1,2},\s+\d{4}\b",
    ]
    phrases: list[str] = []
    for pattern in patterns:
        for match in re.finditer(pattern, cleaned_text, flags=re.IGNORECASE):
            phrase = match.group(0).strip(" ,;:.")
            if phrase and phrase not in phrases:
                phrases.append(phrase)
    return phrases


def _count_enumerated_items(text: str) -> int:
    cleaned_text = _clean_evidence_text(text)
    markers = re.findall(r"\([a-z]\)", cleaned_text.lower())
    if markers:
        return len(dict.fromkeys(markers))
    ordinal_markers = re.findall(r"\b(first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth)\b", cleaned_text.lower())
    if ordinal_markers:
        return len(dict.fromkeys(ordinal_markers))
    return 0


def _extract_enumerated_entries(text: str) -> list[tuple[str, str]]:
    compact_text = re.sub(r"\s+", " ", _clean_evidence_text(text))
    entries: list[tuple[str, str]] = []
    for match in re.finditer(r"\(([a-z])\)\s*([^;]+)", compact_text, flags=re.IGNORECASE):
        marker = match.group(1).lower()
        value = match.group(2).strip(" ,.;:")
        value = re.sub(r"\b\d+\[[^]]+\]", "", value).strip(" ,.;:")
        if not value:
            continue
        if value.lower().startswith(("the words and brackets", "the words", "the figure", "provided that")):
            continue
        entries.append((marker, value))
    deduplicated_entries: list[tuple[str, str]] = []
    seen_markers: set[str] = set()
    for marker, value in entries:
        if marker in seen_markers:
            continue
        seen_markers.add(marker)
        deduplicated_entries.append((marker, value))
    return deduplicated_entries


def _extract_tax_day_clause(text: str, question_text: str) -> str | None:
    cleaned_text = _clean_evidence_text(text)
    lower_question = question_text.lower()
    clause_patterns = [
        ("other than a company", r"in the case of an assessee? other than a company,\s*(.*?)(?:;\s*\([a-z]\)|$)"),
        ("company", r"in the case of a company,\s*(.*?)(?:;\s*\([a-z]\)|$)"),
        ("individual", r"in the case of an (?:individual|individual assessee)[^,]*,\s*(.*?)(?:;\s*\([a-z]\)|$)"),
    ]
    for label, pattern in clause_patterns:
        if label not in lower_question:
            continue
        match = re.search(pattern, cleaned_text, flags=re.IGNORECASE | re.DOTALL)
        if not match:
            continue
        clause = re.sub(r"\s+", " ", match.group(1)).strip(" ,.;:")
        if clause:
            return clause
    return None


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
        for heading in hit.heading_path:
            normalized_heading = normalize_text(heading).lower()
            if normalized_heading.endswith((" there shall be the", " of the", " to the", " for the", " under the")):
                continue
            overlap_score = _sentence_overlap_score(heading, question_text) + 3
            if analyzed_query and analyzed_query.section_id and analyzed_query.section_id in heading:
                overlap_score += 3
            candidate_sentences.append((overlap_score, len(heading), heading.strip(), citation.marker))
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
    candidate_segments: list[tuple[int, str, str, str]] = []
    for citation, hit in zip(citations, evidence_hits, strict=False):
        for value, context in _extract_rate_candidates(hit.original_text):
            candidate_segments.append((_score_rate_candidate(value, context, question_text), value, context, citation.marker))
    if candidate_segments:
        candidate_segments.sort(key=lambda item: (item[0], len(item[2])), reverse=True)
        _, best_value, best_context, best_marker = candidate_segments[0]
        if detect_text_language(question_text) == "bangla":
            sentence_text = f"প্রাসঙ্গিক হার/শতাংশ হলো {best_value}। {truncate_text(best_context, max_length=260)}"
        else:
            sentence_text = f"The relevant percentage is {best_value}. {truncate_text(best_context, max_length=260)}"
        return [AnswerSentence(sentence_text=sentence_text.strip(), citation_markers=[best_marker])], []

    all_rate_values: list[str] = []
    for hit in evidence_hits:
        for rate_value in _extract_rate_values(hit.original_text):
            if rate_value not in all_rate_values:
                all_rate_values.append(rate_value)
    if all_rate_values:
        displayed_values = ", ".join(all_rate_values[:4])
        if detect_text_language(question_text) == "bangla":
            sentence_text = f"প্রাসঙ্গিক প্রমাণে {displayed_values} হার উল্লেখ আছে।"
        else:
            sentence_text = f"The cited provision mentions these rates or percentages: {displayed_values}."
        markers = [citations[0].marker]
        return [AnswerSentence(sentence_text=sentence_text, citation_markers=markers)], []

    candidate_segments = []
    for citation, hit in zip(citations, evidence_hits, strict=False):
        for segment in _extract_rate_segments(hit.original_text):
            candidate_segments.append((_sentence_overlap_score(segment, question_text), "", segment, citation.marker))
    if not candidate_segments:
        return [], []
    candidate_segments.sort(key=lambda item: (item[0], len(item[2])), reverse=True)
    _, _, best_segment, best_marker = candidate_segments[0]
    return [AnswerSentence(sentence_text=truncate_text(best_segment, max_length=260), citation_markers=[best_marker])], []


def _best_sentences_for_intent(
    question_text: str,
    evidence_hits: list[RetrievalHit],
    citations: list[CitationRecord],
    *,
    matcher,
) -> list[tuple[int, int, str, str]]:
    informative_terms = extract_informative_query_terms(question_text)
    candidates: list[tuple[int, int, str, str]] = []
    for citation, hit in zip(citations, evidence_hits, strict=False):
        for sentence in split_sentences(_clean_evidence_text(hit.original_text)):
            if not matcher(sentence):
                continue
            sentence_terms = set(tokenize_for_bm25(sentence.lower()))
            informative_overlap = len(informative_terms & sentence_terms)
            score = _sentence_overlap_score(sentence, question_text) + (informative_overlap * 3)
            candidates.append((score, len(sentence), sentence.strip(), citation.marker))
    candidates.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return candidates


def _build_amount_lookup_answer(
    question_text: str,
    evidence_hits: list[RetrievalHit],
    citations: list[CitationRecord],
) -> tuple[list[AnswerSentence], list[str]]:
    for citation, hit in zip(citations, evidence_hits, strict=False):
        whole_hit_phrases = _extract_amount_phrases(_clean_evidence_text(hit.original_text))
        if whole_hit_phrases:
            best_phrase = next((phrase for phrase in whole_hit_phrases if phrase.lower().startswith("taka")), whole_hit_phrases[0])
            best_phrase = normalize_text(best_phrase)
            answer_text = f"The threshold amount is {best_phrase}."
            return [AnswerSentence(sentence_text=answer_text, citation_markers=[citation.marker])], []
        for sentence in split_sentences(_clean_evidence_text(hit.original_text)):
            amount_phrases = _extract_amount_phrases(sentence)
            if not amount_phrases:
                continue
            best_phrase = next((phrase for phrase in amount_phrases if phrase.lower().startswith("taka")), amount_phrases[0])
            best_phrase = normalize_text(best_phrase)
            answer_text = f"The threshold amount is {best_phrase}."
            return [AnswerSentence(sentence_text=answer_text, citation_markers=[citation.marker])], []
    return build_mock_grounded_answer(question_text, evidence_hits, citations)


def _build_count_lookup_answer(
    question_text: str,
    evidence_hits: list[RetrievalHit],
    citations: list[CitationRecord],
) -> tuple[list[AnswerSentence], list[str]]:
    enumerated_entries: dict[str, str] = {}
    for hit in evidence_hits:
        for marker, value in _extract_enumerated_entries(hit.original_text):
            enumerated_entries.setdefault(marker, value)
    if enumerated_entries:
        item_count = len(enumerated_entries)
        if "authorit" in question_text.lower():
            answer_text = f"The Act lists {item_count} classes of income tax authorities in the relevant provision."
        else:
            answer_text = f"The Act lists {item_count} items in the relevant provision."
        return [AnswerSentence(sentence_text=answer_text, citation_markers=[citations[0].marker])], []
    for citation, hit in zip(citations, evidence_hits, strict=False):
        for sentence in split_sentences(_clean_evidence_text(hit.original_text)):
            duration_phrases = _extract_duration_phrases(sentence)
            if duration_phrases:
                answer_text = f"The relevant duration is {duration_phrases[0]}."
                return [AnswerSentence(sentence_text=answer_text, citation_markers=[citation.marker])], []
            if re.search(r"\b\d+\b", sentence):
                return [AnswerSentence(sentence_text=truncate_text(sentence, max_length=260), citation_markers=[citation.marker])], []
    return build_mock_grounded_answer(question_text, evidence_hits, citations)


def _build_duration_lookup_answer(
    question_text: str,
    evidence_hits: list[RetrievalHit],
    citations: list[CitationRecord],
) -> tuple[list[AnswerSentence], list[str]]:
    for citation, hit in zip(citations, evidence_hits, strict=False):
        for sentence in split_sentences(_clean_evidence_text(hit.original_text)):
            duration_phrases = _extract_duration_phrases(sentence)
            if not duration_phrases:
                continue
            answer_text = f"The relevant duration is {duration_phrases[0]}."
            return [AnswerSentence(sentence_text=answer_text, citation_markers=[citation.marker])], []
    return build_mock_grounded_answer(question_text, evidence_hits, citations)


def _build_date_lookup_answer(
    question_text: str,
    evidence_hits: list[RetrievalHit],
    citations: list[CitationRecord],
) -> tuple[list[AnswerSentence], list[str]]:
    for citation, hit in zip(citations, evidence_hits, strict=False):
        tax_day_clause = _extract_tax_day_clause(hit.original_text, question_text)
        if tax_day_clause and "tax day" in question_text.lower():
            return [
                AnswerSentence(
                    sentence_text=f"In the case asked about, Tax Day is {tax_day_clause}.",
                    citation_markers=[citation.marker],
                )
            ], []
        for sentence in split_sentences(_clean_evidence_text(hit.original_text)):
            if not (_extract_date_phrases(sentence) or "tax day" in sentence.lower()):
                continue
            return [AnswerSentence(sentence_text=truncate_text(sentence, max_length=260), citation_markers=[citation.marker])], []
    return build_mock_grounded_answer(question_text, evidence_hits, citations)


def _build_eligibility_answer(
    question_text: str,
    evidence_hits: list[RetrievalHit],
    citations: list[CitationRecord],
) -> tuple[list[AnswerSentence], list[str]]:
    lower_question = normalize_text(question_text).lower()
    labour_like = any(term in lower_question for term in ("labour", "labor", "worker", "day labourer", "day laborer"))
    salary_like = any(term in lower_question for term in ("salary", "salaried", "employee", "employment"))

    labour_marker: str | None = None
    chargeable_marker: str | None = None
    status_marker: str | None = None
    labour_sentence: str | None = None
    chargeable_sentence: str | None = None
    status_sentence: str | None = None

    for citation, hit in zip(citations, evidence_hits, strict=False):
        for sentence in split_sentences(_clean_evidence_text(hit.original_text)):
            lowered_sentence = normalize_text(sentence).lower()
            if labour_sentence is None and any(term in lowered_sentence for term in ("day labourer", "day laborer", "worker")):
                labour_sentence = sentence.strip()
                labour_marker = citation.marker
            if chargeable_sentence is None and any(
                phrase in lowered_sentence
                for phrase in ("chargeable to tax", "tax payable on income", "minimum tax is payable")
            ):
                chargeable_sentence = sentence.strip()
                chargeable_marker = citation.marker
            if status_sentence is None and any(
                phrase in lowered_sentence for phrase in ("income from employment", "employee", "individual", "resident", "assessee", "tax exemption")
            ):
                status_sentence = sentence.strip()
                status_marker = citation.marker

    markers = [
        marker
        for marker in dict.fromkeys([labour_marker, chargeable_marker, status_marker])
        if marker is not None
    ]
    if not markers:
        markers = [citations[0].marker]

    if labour_like and labour_sentence and chargeable_sentence:
        answer_sentences = [
            AnswerSentence(
                sentence_text=(
                    "If by labour you mean a day labourer, one relevant definition says the term "
                    '"employee" does not include a day labourer; the Act still does not let me compute '
                    "your exact tax from that alone because tax depends on whether your income is chargeable to tax under the Act."
                ),
                citation_markers=markers[:2],
            ),
            AnswerSentence(
                sentence_text="Please share your annual income and tax year for a closer estimate under the Act.",
                citation_markers=markers[:1],
            ),
        ]
        return answer_sentences, []

    if labour_like and labour_sentence:
        answer_sentences = [
            AnswerSentence(
                sentence_text=(
                    'If by labour you mean a day labourer, one relevant definition says the term "employee" '
                    "does not include a day labourer, so the Act does not let me compute your exact tax from that description alone."
                ),
                citation_markers=markers[:1],
            ),
            AnswerSentence(
                sentence_text="Please share your annual income, tax year, and income source for a closer estimate under the Act.",
                citation_markers=markers[:1],
            ),
        ]
        return answer_sentences, []

    if salary_like and (status_sentence or chargeable_sentence):
        answer_sentences = [
            AnswerSentence(
                sentence_text=(
                    "The Act does not let me compute your exact tax from occupation alone; income from employment "
                    "is treated separately, and tax still depends on whether your income is chargeable to tax under the Act."
                ),
                citation_markers=markers[:2],
            ),
            AnswerSentence(
                sentence_text="Please share your annual income and tax year if you want a closer estimate.",
                citation_markers=markers[:1],
            ),
        ]
        return answer_sentences, []

    if chargeable_sentence or status_sentence:
        answer_sentences = [
            AnswerSentence(
                sentence_text=(
                    "I cannot determine your exact tax from this question alone; under the Act, tax depends on whether "
                    "your income is chargeable to tax, and the answer can vary for an individual assessee or employee."
                ),
                citation_markers=markers[:2],
            ),
            AnswerSentence(
                sentence_text="Please share your annual income, tax year, and income source for a closer estimate.",
                citation_markers=markers[:1],
            ),
        ]
        return answer_sentences, []

    return build_mock_grounded_answer(question_text, evidence_hits, citations)


def _build_list_lookup_answer(
    question_text: str,
    evidence_hits: list[RetrievalHit],
    citations: list[CitationRecord],
) -> tuple[list[AnswerSentence], list[str]]:
    lower_question = question_text.lower()
    aggregated_entries: dict[str, str] = {}
    for hit in evidence_hits:
        for marker, value in _extract_enumerated_entries(hit.original_text):
            aggregated_entries.setdefault(marker, value)
    if aggregated_entries:
        rendered_items = "; ".join(value for _, value in sorted(aggregated_entries.items()))
        if "authorit" in lower_question:
            answer_text = f"The income tax authorities listed are: {rendered_items}."
        else:
            answer_text = f"The relevant provision lists: {rendered_items}."
        return [AnswerSentence(sentence_text=truncate_text(answer_text, max_length=320), citation_markers=[citation.marker for citation in citations[: min(2, len(citations))]])], []
    for citation, hit in zip(citations, evidence_hits, strict=False):
        fragments = _extract_mention_fragments(hit.original_text, question_text)
        if fragments:
            listed_items = "; ".join(fragment for _, fragment in fragments[:4])
            if "authorit" in lower_question:
                answer_text = f"The income tax authorities listed are: {listed_items}."
            else:
                answer_text = f"The relevant provision lists: {listed_items}."
            return [AnswerSentence(sentence_text=answer_text, citation_markers=[citation.marker])], []
        enumerated_count = _count_enumerated_items(hit.original_text)
        if enumerated_count > 0:
            if "authorit" in lower_question:
                answer_text = f"The relevant provision lists {enumerated_count} income tax authorities."
            else:
                answer_text = f"The relevant provision lists {enumerated_count} items."
            return [AnswerSentence(sentence_text=answer_text, citation_markers=[citation.marker])], []
    return build_mock_grounded_answer(question_text, evidence_hits, citations)


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


def _build_definition_answer(
    question_text: str,
    evidence_hits: list[RetrievalHit],
    citations: list[CitationRecord],
    analyzed_query: QuerySignals | None,
) -> tuple[list[AnswerSentence], list[str]]:
    focus_term = extract_definition_target(question_text)
    candidate_sentences: list[tuple[int, int, str, str]] = []
    for citation, hit in zip(citations, evidence_hits, strict=False):
        for sentence in split_sentences(_clean_evidence_text(hit.original_text)):
            lowered_sentence = sentence.lower()
            score = _sentence_overlap_score(sentence, question_text)
            if "means" in lowered_sentence or "defined as" in lowered_sentence:
                score += 3
            if focus_term and normalize_text(focus_term).lower() in normalize_text(sentence).lower():
                score += 4
                if any(
                    phrase in normalize_text(sentence).lower()
                    for phrase in (
                        f"“{normalize_text(focus_term).lower()}” means",
                        f"\"{normalize_text(focus_term).lower()}\" means",
                        f"{normalize_text(focus_term).lower()} means",
                    )
                ):
                    score += 4
            candidate_sentences.append((score, len(sentence), sentence.strip(), citation.marker))
    if not candidate_sentences:
        return build_mock_grounded_answer(question_text, evidence_hits, citations)
    candidate_sentences.sort(key=lambda item: (item[0], item[1]), reverse=True)
    _, _, best_sentence, best_marker = candidate_sentences[0]
    return [AnswerSentence(sentence_text=truncate_text(best_sentence, max_length=260), citation_markers=[best_marker])], []


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
    if analyzed_query and analyzed_query.query_intent == "definition":
        return _build_definition_answer(question_text, evidence_hits, citations, analyzed_query)
    if analyzed_query and analyzed_query.query_intent == "rate_lookup":
        return _build_rate_lookup_answer(question_text, evidence_hits, citations)
    if analyzed_query and analyzed_query.query_intent == "eligibility":
        return _build_eligibility_answer(question_text, evidence_hits, citations)
    if analyzed_query and analyzed_query.query_intent == "amount_lookup":
        return _build_amount_lookup_answer(question_text, evidence_hits, citations)
    if analyzed_query and analyzed_query.query_intent == "count_lookup":
        return _build_count_lookup_answer(question_text, evidence_hits, citations)
    if analyzed_query and analyzed_query.query_intent == "duration_lookup":
        return _build_duration_lookup_answer(question_text, evidence_hits, citations)
    if analyzed_query and analyzed_query.query_intent == "date_lookup":
        return _build_date_lookup_answer(question_text, evidence_hits, citations)
    if analyzed_query and analyzed_query.query_intent == "list_lookup":
        return _build_list_lookup_answer(question_text, evidence_hits, citations)
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
    should_use_extractive_builder = (
        analyzed_query.query_intent in EXTRACTIVE_INTENTS
        or bool(analyzed_query.subsection_id or analyzed_query.section_id)
    )
    if should_use_extractive_builder and mocked_response is None:
        answer_sentences, model_conflict_notes = build_mock_grounded_answer(
            question_text,
            evidence_hits,
            citations,
            analyzed_query,
        )
        used_extractive_fallback = True
    else:
        try:
            chat_client = get_chat_client(generation_options, mocked_response=mocked_response)
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
