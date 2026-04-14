import re

from app.core.schemas import ChunkRecord, QuerySignals, RetrievalHit
from app.core.utils import extract_definition_target, extract_informative_query_terms, normalize_text, tokenize_for_bm25


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
    lines = [line.strip() for line in stripped_text.splitlines() if line.strip()]
    word_count = len(re.findall(r"\b[\w\u0980-\u09ff]+\b", stripped_text))
    bangla_char_count = len(re.findall(r"[\u0980-\u09ff]", stripped_text))
    latin_char_count = len(re.findall(r"[A-Za-z]", stripped_text))
    digit_count = sum(character.isdigit() for character in stripped_text)
    alpha_count = sum(character.isalpha() for character in stripped_text)
    length_score = min(len(stripped_text) / 180.0, 1.0)
    alpha_density = alpha_count / max(len(stripped_text), 1)
    alpha_score = min(alpha_density / 0.45, 1.0)
    lexical_score = min(word_count / 28.0, 1.0)
    script_presence_score = 1.0 if max(bangla_char_count, latin_char_count) >= 18 else min((bangla_char_count + latin_char_count) / 18.0, 1.0)
    digit_penalty = min(digit_count / max(len(stripped_text), 1), 1.0)
    structural_line_count = sum(
        1 for line in lines if re.fullmatch(r"[0-9 .:/()%\-|]+", line)
    )
    structural_penalty = structural_line_count / max(len(lines), 1)
    score = (
        (length_score * 0.25)
        + (alpha_score * 0.35)
        + (lexical_score * 0.2)
        + (script_presence_score * 0.25)
        - (digit_penalty * 0.2)
        - (structural_penalty * 0.35)
    )
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


AMOUNT_PATTERN = re.compile(
    r"(taka|crore|lakh|percent|%|threshold|limit|not more than|no more than|exceeds?|minimum|maximum)",
    re.IGNORECASE,
)
DURATION_PATTERN = re.compile(
    r"(\b\d+\s*\((?:[^)]*)\)\s*(?:successive\s+)?(?:assessment\s+)?(?:years?|months?|days?)|\b\d+\s+(?:successive\s+)?(?:assessment\s+)?years?\b|carry(?:ied)?\s+forward|period of|from .* to .*)",
    re.IGNORECASE,
)
DATE_PATTERN = re.compile(
    r"(\b(?:january|february|march|april|may|june|july|august|september|october|november|december)\b|\b\d{1,2}(?:st|nd|rd|th)\b|effective from|deadline|due date|tax day|by june|by july|by september|by november)",
    re.IGNORECASE,
)
LIST_PATTERN = re.compile(r"(\([a-z]\)|\([ivx]+\)|namely|following classes|following items|following incomes|first year|second year)", re.IGNORECASE)
ELIGIBILITY_PATTERN = re.compile(
    r"(chargeable to tax|taxable income|tax exemption|employee|employment|income from employment|salary|salaried|individual|resident|assessee|day labourer|day laborer|worker|labour|labor|wage|wages)",
    re.IGNORECASE,
)


def _build_searchable_text(hit: RetrievalHit) -> str:
    return normalize_text(f"{' '.join(hit.heading_path)} {hit.normalized_text}").lower()


def _satisfies_query_phrase_constraints(hit: RetrievalHit, analyzed_query: QuerySignals) -> bool:
    normalized_query = normalize_text(analyzed_query.original_query or analyzed_query.normalized_query).lower()
    searchable_text = _build_searchable_text(hit)
    required_phrases = [
        "tax day",
        "charitable purpose",
        "income tax authorities",
        "startup",
    ]
    for phrase in required_phrases:
        if phrase in normalized_query and phrase not in searchable_text:
            return False
    if "carried forward" in normalized_query and "carried forward" not in searchable_text and "set off" not in searchable_text:
        return False
    return True


def _informative_overlap_count(hit: RetrievalHit, analyzed_query: QuerySignals) -> int:
    informative_terms = extract_informative_query_terms(
        analyzed_query.original_query or analyzed_query.normalized_query,
        analyzed_query.query_intent,
    )
    if not informative_terms:
        return 0
    searchable_terms = set(tokenize_for_bm25(_build_searchable_text(hit)))
    return len(informative_terms & searchable_terms)


def hit_has_amount_language(hit: RetrievalHit) -> bool:
    return bool(AMOUNT_PATTERN.search(_build_searchable_text(hit)))


def hit_has_duration_language(hit: RetrievalHit) -> bool:
    return bool(DURATION_PATTERN.search(_build_searchable_text(hit)))


def hit_has_date_language(hit: RetrievalHit) -> bool:
    return bool(DATE_PATTERN.search(_build_searchable_text(hit)))


def hit_looks_list_like(hit: RetrievalHit) -> bool:
    return bool(LIST_PATTERN.search(_build_searchable_text(hit)))


def hit_supports_amount(hit: RetrievalHit, analyzed_query: QuerySignals) -> bool:
    return (
        _satisfies_query_phrase_constraints(hit, analyzed_query)
        and _informative_overlap_count(hit, analyzed_query) > 0
        and hit_has_amount_language(hit)
    )


def hit_supports_count(hit: RetrievalHit, analyzed_query: QuerySignals) -> bool:
    searchable_text = _build_searchable_text(hit)
    has_numeric_phrase = bool(re.search(r"\b\d+\b", searchable_text))
    return (
        _satisfies_query_phrase_constraints(hit, analyzed_query)
        and _informative_overlap_count(hit, analyzed_query) > 0
        and (hit_looks_list_like(hit) or has_numeric_phrase)
    )


def hit_supports_duration(hit: RetrievalHit, analyzed_query: QuerySignals) -> bool:
    return (
        _satisfies_query_phrase_constraints(hit, analyzed_query)
        and _informative_overlap_count(hit, analyzed_query) > 0
        and hit_has_duration_language(hit)
    )


def hit_supports_date(hit: RetrievalHit, analyzed_query: QuerySignals) -> bool:
    return (
        _satisfies_query_phrase_constraints(hit, analyzed_query)
        and _informative_overlap_count(hit, analyzed_query) > 0
        and hit_has_date_language(hit)
    )


def hit_supports_list(hit: RetrievalHit, analyzed_query: QuerySignals) -> bool:
    return (
        _satisfies_query_phrase_constraints(hit, analyzed_query)
        and _informative_overlap_count(hit, analyzed_query) > 0
        and hit_looks_list_like(hit)
    )


def hit_supports_comparison(hit: RetrievalHit, analyzed_query: QuerySignals) -> bool:
    searchable_text = _build_searchable_text(hit)
    normalized_query = normalize_text(analyzed_query.original_query or analyzed_query.normalized_query).lower()
    if not _satisfies_query_phrase_constraints(hit, analyzed_query):
        return False
    if "tax day" in normalized_query and not hit_has_date_language(hit):
        return False
    informative_overlap = _informative_overlap_count(hit, analyzed_query)
    comparison_focus_phrases = [
        "company",
        "other than a company",
        "assessee",
        "startup",
        "dividend",
    ]
    focus_match = any(phrase in normalized_query and phrase in searchable_text for phrase in comparison_focus_phrases)
    return informative_overlap > 0 or focus_match


def hit_supports_eligibility(hit: RetrievalHit, analyzed_query: QuerySignals) -> bool:
    searchable_text = _build_searchable_text(hit)
    normalized_query = normalize_text(analyzed_query.original_query or analyzed_query.normalized_query).lower()
    informative_overlap = _informative_overlap_count(hit, analyzed_query)
    has_eligibility_language = bool(ELIGIBILITY_PATTERN.search(searchable_text))
    if not has_eligibility_language:
        return False

    role_terms_by_query = {
        "labour": ("day labourer", "day laborer", "worker", "employee", "employment"),
        "labor": ("day labourer", "day laborer", "worker", "employee", "employment"),
        "worker": ("day labourer", "day laborer", "worker", "employee", "employment"),
        "salary": ("salary", "employee", "employment", "income from employment"),
        "salaried": ("salary", "employee", "employment", "income from employment"),
        "employee": ("employee", "employment", "income from employment"),
        "resident": ("resident", "individual", "assessee"),
        "individual": ("individual", "resident", "assessee"),
    }
    has_general_taxability_anchor = any(
        phrase in searchable_text for phrase in ("chargeable to tax", "tax exemption", "taxable income")
    )
    for trigger, expected_terms in role_terms_by_query.items():
        if trigger in normalized_query and not any(term in searchable_text for term in expected_terms) and not has_general_taxability_anchor:
            return False

    return _satisfies_query_phrase_constraints(hit, analyzed_query) and (
        informative_overlap > 0
        or any(
            phrase in searchable_text
            for phrase in ("chargeable to tax", "day labourer", "day laborer", "income from employment", "tax exemption")
        )
    )


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
    if analyzed_query.query_intent == "eligibility":
        return hit_supports_eligibility(hit, analyzed_query)
    if analyzed_query.query_intent == "amount_lookup":
        return hit_supports_amount(hit, analyzed_query)
    if analyzed_query.query_intent == "count_lookup":
        return hit_supports_count(hit, analyzed_query)
    if analyzed_query.query_intent == "duration_lookup":
        return hit_supports_duration(hit, analyzed_query)
    if analyzed_query.query_intent == "date_lookup":
        return hit_supports_date(hit, analyzed_query)
    if analyzed_query.query_intent == "list_lookup":
        return hit_supports_list(hit, analyzed_query)
    if analyzed_query.query_intent == "comparison":
        return hit_supports_comparison(hit, analyzed_query)
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
    if analyzed_query.query_intent == "eligibility":
        eligibility_hits = [hit for hit in hits if hit_supports_eligibility(hit, analyzed_query)]
        if eligibility_hits:
            return eligibility_hits
    if analyzed_query.query_intent == "definition":
        definition_hits = [hit for hit in hits if hit_supports_definition(hit, analyzed_query)]
        exact_target_hits = [hit for hit in definition_hits if hit_matches_definition_target_exactly(hit, analyzed_query)]
        if exact_target_hits:
            return exact_target_hits
        if definition_hits:
            return definition_hits
    if analyzed_query.query_intent == "amount_lookup":
        amount_hits = [hit for hit in hits if hit_supports_amount(hit, analyzed_query)]
        if amount_hits:
            return amount_hits
    if analyzed_query.query_intent == "count_lookup":
        count_hits = [hit for hit in hits if hit_supports_count(hit, analyzed_query)]
        if count_hits:
            return count_hits
    if analyzed_query.query_intent == "duration_lookup":
        duration_hits = [hit for hit in hits if hit_supports_duration(hit, analyzed_query)]
        if duration_hits:
            return duration_hits
    if analyzed_query.query_intent == "date_lookup":
        date_hits = [hit for hit in hits if hit_supports_date(hit, analyzed_query)]
        if date_hits:
            return date_hits
    if analyzed_query.query_intent == "list_lookup":
        list_hits = [hit for hit in hits if hit_supports_list(hit, analyzed_query)]
        if list_hits:
            return list_hits
    if analyzed_query.query_intent == "comparison":
        comparison_hits = [hit for hit in hits if hit_supports_comparison(hit, analyzed_query)]
        if comparison_hits:
            return comparison_hits
    if not analyzed_query.section_id and not analyzed_query.subsection_id:
        return hits
    supportive_hits = [hit for hit in hits if hit_supports_query(hit, analyzed_query)]
    return supportive_hits
