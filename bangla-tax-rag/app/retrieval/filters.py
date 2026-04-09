import re

from app.core.schemas import ChunkRecord, QuerySignals, RetrievalHit
from app.core.utils import extract_definition_target, normalize_text


AUTHORITY_RANK = {
    "unknown": 0,
    "local": 1,
    "regional": 2,
    "national": 3,
    "statute": 4,
    "constitutional": 5,
}


def deduplicate_results(results: list[dict[str, str | float]]) -> list[dict[str, str | float]]:
    seen_chunk_ids: set[str] = set()
    unique_results: list[dict[str, str | float]] = []
    for result in results:
        chunk_id = str(result["chunk_id"])
        if chunk_id in seen_chunk_ids:
            continue
        seen_chunk_ids.add(chunk_id)
        unique_results.append(result)
    return unique_results


def authority_value(authority_level: str | None) -> int:
    if authority_level is None:
        return AUTHORITY_RANK["unknown"]
    return AUTHORITY_RANK.get(authority_level.lower(), AUTHORITY_RANK["unknown"])


def chunk_quality_score(text: str) -> float:
    stripped_text = text.strip()
    if not stripped_text:
        return 0.0
    bangla_char_count = len(re.findall(r"[\u0980-\u09ff]", stripped_text))
    digit_count = sum(character.isdigit() for character in stripped_text)
    alpha_count = sum(character.isalpha() for character in stripped_text)
    length_score = min(len(stripped_text) / 120.0, 1.0)
    bangla_score = min(bangla_char_count / 25.0, 1.0)
    digit_penalty = min(digit_count / max(len(stripped_text), 1), 1.0)
    alpha_score = min(alpha_count / max(len(stripped_text), 1), 1.0)
    score = (length_score * 0.35) + (bangla_score * 0.45) + (alpha_score * 0.35) - (digit_penalty * 0.35)
    if re.fullmatch(r"[0-9 .:/()%\-]+", stripped_text):
        score -= 0.7
    return max(0.0, min(1.0, score))


def is_low_quality_chunk(text: str) -> bool:
    return chunk_quality_score(text) < 0.22


def passes_metadata_filters(
    chunk: ChunkRecord,
    *,
    tax_year: str | None = None,
    doc_type: str | None = None,
    authority_level_min: str | None = None,
    chunk_type: str | None = None,
) -> bool:
    if tax_year and chunk.tax_year != tax_year:
        return False
    if doc_type and chunk.doc_type != doc_type:
        return False
    if chunk_type and chunk.chunk_type != chunk_type:
        return False
    if authority_level_min and authority_value(chunk.authority_level) < authority_value(authority_level_min):
        return False
    return True


def filter_chunk_records(
    chunk_records: list[ChunkRecord],
    *,
    tax_year: str | None = None,
    doc_type: str | None = None,
    authority_level_min: str | None = None,
    chunk_type: str | None = None,
) -> list[ChunkRecord]:
    return [
        chunk
        for chunk in chunk_records
        if passes_metadata_filters(
            chunk,
            tax_year=tax_year,
            doc_type=doc_type,
            authority_level_min=authority_level_min,
            chunk_type=chunk_type,
        )
        and not is_low_quality_chunk(chunk.normalized_text)
    ]


def text_overlap_ratio(left_text: str, right_text: str) -> float:
    left_tokens = set(left_text.split())
    right_tokens = set(right_text.split())
    if not left_tokens or not right_tokens:
        return 0.0
    intersection_size = len(left_tokens & right_tokens)
    union_size = len(left_tokens | right_tokens)
    return intersection_size / union_size if union_size else 0.0


def deduplicate_retrieval_hits(
    hits: list[RetrievalHit],
    *,
    overlap_threshold: float = 0.82,
) -> tuple[list[RetrievalHit], list[str]]:
    deduplicated_hits: list[RetrievalHit] = []
    dropped_duplicates: list[str] = []
    for hit in hits:
        should_drop = False
        for kept_hit in deduplicated_hits:
            same_chunk = hit.chunk_id == kept_hit.chunk_id
            highly_overlapping = (
                hit.doc_id == kept_hit.doc_id
                and text_overlap_ratio(hit.normalized_text, kept_hit.normalized_text) >= overlap_threshold
            )
            if same_chunk or highly_overlapping:
                dropped_duplicates.append(hit.chunk_id)
                should_drop = True
                break
        if not should_drop:
            deduplicated_hits.append(hit)
    return deduplicated_hits, dropped_duplicates


def has_exact_section_heading_match(hit: RetrievalHit, section_reference: str) -> bool:
    heading_pattern = re.compile(rf"^{re.escape(section_reference)}(?:[.)]|(?:\s*[—:-]))")
    if heading_pattern.match(normalize_text(hit.normalized_text)):
        return True
    return any(heading_pattern.match(normalize_text(heading)) for heading in hit.heading_path)


def hit_matches_definition_target_exactly(hit: RetrievalHit, analyzed_query: QuerySignals) -> bool:
    focus_term = extract_definition_target(analyzed_query.original_query or analyzed_query.normalized_query)
    if not focus_term:
        return False
    searchable_text = normalize_text(f"{' '.join(hit.heading_path)} {hit.normalized_text}").lower()
    normalized_focus = normalize_text(focus_term).lower()
    patterns = [
        f"“{normalized_focus}” means",
        f"\"{normalized_focus}\" means",
        f"{normalized_focus} means",
    ]
    return any(pattern in searchable_text for pattern in patterns)


def hit_supports_definition(hit: RetrievalHit, analyzed_query: QuerySignals) -> bool:
    searchable_text = f"{' '.join(hit.heading_path)} {hit.normalized_text}".lower()
    has_definition_heading = "definition" in searchable_text or "definitions" in searchable_text or "সংজ্ঞা" in searchable_text
    has_definition_language = " means " in searchable_text or " means\n" in searchable_text or "defined as" in searchable_text or "সংজ্ঞা" in searchable_text
    focus_term = extract_definition_target(analyzed_query.original_query or analyzed_query.normalized_query)
    if focus_term:
        focus_tokens = [token.lower() for token in focus_term.split() if token.strip()]
        focus_match = all(token in searchable_text for token in focus_tokens)
    else:
        focus_match = True
    return focus_match and (has_definition_heading or has_definition_language)


def hit_supports_query(hit: RetrievalHit, analyzed_query: QuerySignals) -> bool:
    normalized_text = hit.normalized_text.lower()
    is_rate_lookup = analyzed_query.query_intent == "rate_lookup"
    has_rate_language = "করহার" in normalized_text or "কর হার" in normalized_text or "tax rate" in normalized_text
    if analyzed_query.subsection_id:
        if hit.subsection_id == analyzed_query.subsection_id:
            return has_rate_language if is_rate_lookup else True
        if analyzed_query.subsection_id in normalized_text and analyzed_query.query_intent != "rate_lookup":
            return True
        return False
    if analyzed_query.section_id and hit.section_id:
        section_matches = hit.section_id == analyzed_query.section_id or analyzed_query.section_id in normalized_text
        if not section_matches:
            return False
        return has_rate_language if is_rate_lookup else True
    if is_rate_lookup:
        return has_rate_language
    return True


def filter_supportive_hits(hits: list[RetrievalHit], analyzed_query: QuerySignals) -> list[RetrievalHit]:
    if analyzed_query.query_intent == "definition":
        definition_hits = [hit for hit in hits if hit_supports_definition(hit, analyzed_query)]
        exact_target_hits = [hit for hit in definition_hits if hit_matches_definition_target_exactly(hit, analyzed_query)]
        if exact_target_hits:
            return exact_target_hits
        if definition_hits:
            return definition_hits
    if not analyzed_query.section_id and not analyzed_query.subsection_id:
        return hits
    supportive_hits = [hit for hit in hits if hit_supports_query(hit, analyzed_query)]
    return supportive_hits
