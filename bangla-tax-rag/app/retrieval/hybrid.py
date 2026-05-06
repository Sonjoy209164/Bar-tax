import logging
import re
from pathlib import Path

from app.core.schemas import HybridRetrievalResponse, QuerySignals, RetrievalHit
from app.core.utils import (
    extract_informative_query_terms,
    extract_salient_query_terms,
    normalize_text,
    preprocess_query,
    tokenize_for_bm25,
)
from app.retrieval.dense import dense_search
from app.retrieval.filters import (
    authority_value,
    deduplicate_retrieval_hits,
    filter_supportive_hits,
    has_exact_section_heading_match,
    hit_has_amount_language,
    hit_supports_comparison,
    hit_has_date_language,
    hit_has_duration_language,
    hit_matches_definition_target_exactly,
    hit_supports_definition,
    hit_supports_eligibility,
    infer_chunk_tax_year,
    hit_looks_list_like,
    hit_supports_query,
    looks_like_late_reference_material,
    query_requests_reference_material,
)
from app.retrieval.reranker import rerank_retrieval_hits
from app.retrieval.sparse import DEFAULT_INDEX_DIR, load_sparse_index, sparse_search
from app.retrieval.sparse import load_chunk_records_from_jsonl

logger = logging.getLogger(__name__)


COMPANY_QUERY_PATTERN = re.compile(r"(কোম্প|কম্প|মকাম্প|ককাম্প|company)", re.IGNORECASE)
STRICT_SUPPORT_INTENTS = {"amount_lookup", "count_lookup", "duration_lookup", "date_lookup", "list_lookup"}
GENERIC_HEADING_TERMS = {
    "act",
    "income",
    "tax",
    "section",
    "chapter",
    "part",
    "under",
    "the",
    "and",
    "of",
    "for",
    "to",
    "in",
}
LIST_CONTINUATION_PATTERN = re.compile(r"^(?:\([a-z0-9ivxlcdm]+\)|[a-z]\)|\d+\.)\s+", re.IGNORECASE)


def _chunk_number(hit: RetrievalHit) -> int | None:
    chunk_match = re.search(r"-c(\d+)$", hit.chunk_id)
    return int(chunk_match.group(1)) if chunk_match else None


def _load_dense_hits_for_hybrid(
    *,
    query: str,
    top_k: int,
    effective_tax_year: str | None,
    doc_type: str | None,
    authority_level_min: str | None,
    chunk_type: str | None,
    dense_index_dir: str | Path,
) -> list[RetrievalHit]:
    try:
        return [
            RetrievalHit(**hit)
            for hit in dense_search(
                query,
                top_k=top_k,
                tax_year=effective_tax_year,
                doc_type=doc_type,
                authority_level_min=authority_level_min,
                chunk_type=chunk_type,
                index_dir=dense_index_dir,
            )
        ]
    except FileNotFoundError as exc:
        logger.warning("Dense index missing for hybrid retrieval; continuing with sparse hits only.", extra={"error": str(exc)})
        return []
    except Exception as exc:  # pragma: no cover - runtime fallback
        logger.warning("Dense retrieval failed inside hybrid pipeline; continuing with sparse hits only.", extra={"error": str(exc)})
        return []


def _heading_signature(hit: RetrievalHit) -> str | None:
    if not hit.heading_path:
        return None
    return normalize_text(hit.heading_path[-1]).lower()


def _primary_legal_heading_signature(hit: RetrievalHit) -> str | None:
    normalized_headings = [normalize_text(heading).lower() for heading in hit.heading_path if normalize_text(heading)]
    if not normalized_headings:
        return None
    for heading in reversed(normalized_headings):
        if re.match(r"^\d+[a-z]?(?:\.\d+)?(?:[.)]|(?:\s*[—:-]))", heading):
            return heading
    return normalized_headings[-1]


def _heading_content_terms(text: str | None) -> set[str]:
    if not text:
        return set()
    return {
        token
        for token in tokenize_for_bm25(text.lower())
        if token not in GENERIC_HEADING_TERMS and not token.isdigit()
    }


def _heading_term_overlap(anchor_hit: RetrievalHit, candidate_hit: RetrievalHit) -> int:
    anchor_heading = _primary_legal_heading_signature(anchor_hit) or _heading_signature(anchor_hit)
    candidate_heading = _primary_legal_heading_signature(candidate_hit) or _heading_signature(candidate_hit)
    anchor_terms = _heading_content_terms(anchor_heading)
    candidate_terms = _heading_content_terms(candidate_heading)
    return len(anchor_terms & candidate_terms)


def _looks_like_list_continuation(hit: RetrievalHit) -> bool:
    first_line = next((normalize_text(line) for line in hit.original_text.splitlines() if normalize_text(line)), "")
    return bool(
        LIST_CONTINUATION_PATTERN.match(first_line)
        or "namely" in hit.normalized_text.lower()
    )


def _same_logical_unit(anchor_hit: RetrievalHit, candidate_hit: RetrievalHit, analyzed_query: QuerySignals) -> bool:
    if anchor_hit.doc_id != candidate_hit.doc_id:
        return False
    if anchor_hit.chunk_id == candidate_hit.chunk_id:
        return True
    page_distance = abs(anchor_hit.page_no - candidate_hit.page_no)

    anchor_heading = _heading_signature(anchor_hit)
    candidate_heading = _heading_signature(candidate_hit)
    anchor_primary_heading = _primary_legal_heading_signature(anchor_hit)
    candidate_primary_heading = _primary_legal_heading_signature(candidate_hit)
    if anchor_primary_heading and candidate_primary_heading and anchor_primary_heading == candidate_primary_heading:
        return page_distance <= 2
    if anchor_heading and candidate_heading and anchor_heading == candidate_heading:
        return page_distance <= 1

    if anchor_hit.subsection_id and candidate_hit.subsection_id and anchor_hit.subsection_id == candidate_hit.subsection_id:
        return True

    anchor_chunk_number = _chunk_number(anchor_hit)
    candidate_chunk_number = _chunk_number(candidate_hit)
    if (
        page_distance == 0
        and anchor_chunk_number is not None
        and candidate_chunk_number is not None
        and abs(anchor_chunk_number - candidate_chunk_number) <= 2
        and analyzed_query.query_intent
        in {"amount_lookup", "rate_lookup", "date_lookup", "example", "calculation", "procedure"}
        and (
            anchor_hit.chunk_type == candidate_hit.chunk_type
            or _informative_overlap(candidate_hit, analyzed_query) > 0
            or _informative_overlap(anchor_hit, analyzed_query) > 0
        )
    ):
        return True

    heading_overlap = _heading_term_overlap(anchor_hit, candidate_hit)
    if anchor_hit.section_id and candidate_hit.section_id and anchor_hit.section_id == candidate_hit.section_id:
        if page_distance <= 1 and heading_overlap >= 1:
            return True
        if page_distance <= 1 and (_looks_like_list_continuation(anchor_hit) or _looks_like_list_continuation(candidate_hit)):
            return True

    if analyzed_query.section_reference:
        anchor_has_section_heading = has_exact_section_heading_match(anchor_hit, analyzed_query.section_reference)
        candidate_has_section_heading = has_exact_section_heading_match(candidate_hit, analyzed_query.section_reference)
        if anchor_has_section_heading and candidate_has_section_heading:
            return page_distance <= 2
        if (
            anchor_has_section_heading
            and anchor_hit.section_id
            and candidate_hit.section_id == anchor_hit.section_id
            and page_distance <= 1
            and _looks_like_list_continuation(candidate_hit)
        ):
            return True

    return False


def _logical_unit_sort_key(anchor_hit: RetrievalHit, candidate_hit: RetrievalHit) -> tuple[int, int, int, int, int, int, float, str]:
    same_primary_heading = int(
        (_primary_legal_heading_signature(anchor_hit) or "") == (_primary_legal_heading_signature(candidate_hit) or "")
    )
    same_heading = int((_heading_signature(anchor_hit) or "") == (_heading_signature(candidate_hit) or ""))
    page_distance = abs(anchor_hit.page_no - candidate_hit.page_no)
    heading_overlap = _heading_term_overlap(anchor_hit, candidate_hit)
    from_corpus_pool = int(bool(candidate_hit.intermediate_scores.get("from_corpus_pool")))
    return (
        0 if candidate_hit.chunk_id == anchor_hit.chunk_id else 1,
        -same_primary_heading,
        -same_heading,
        page_distance,
        -heading_overlap,
        from_corpus_pool,
        -candidate_hit.score,
        candidate_hit.chunk_id,
    )


def _expand_logical_unit_hits(
    candidate_hits: list[RetrievalHit],
    all_hits: list[RetrievalHit],
    analyzed_query: QuerySignals,
    *,
    final_top_k: int,
    candidate_pool: list[RetrievalHit] | None = None,
) -> list[RetrievalHit]:
    should_expand = bool(analyzed_query.section_reference) or analyzed_query.query_intent in {
        "eligibility",
        "count_lookup",
        "list_lookup",
        "date_lookup",
        "amount_lookup",
        "duration_lookup",
        "rate_lookup",
        "definition",
        "example",
        "calculation",
        "procedure",
    }
    if not should_expand or not candidate_hits:
        return candidate_hits

    anchor_count = 2 if analyzed_query.query_intent in {"eligibility", "count_lookup", "list_lookup"} else 1
    anchors = candidate_hits[:anchor_count]
    expanded_hits: list[RetrievalHit] = []
    seen_chunk_ids: set[str] = set()

    pool = list(all_hits)
    if candidate_pool:
        seen_pool_chunk_ids = {hit.chunk_id for hit in pool}
        pool.extend(hit for hit in candidate_pool if hit.chunk_id not in seen_pool_chunk_ids)

    for anchor_hit in anchors:
        related_hits = [
            hit
            for hit in pool
            if _same_logical_unit(anchor_hit, hit, analyzed_query)
        ]
        related_hits.sort(key=lambda hit: _logical_unit_sort_key(anchor_hit, hit))
        for hit in related_hits:
            if hit.chunk_id in seen_chunk_ids:
                continue
            expanded_hits.append(hit)
            seen_chunk_ids.add(hit.chunk_id)

    if not expanded_hits:
        return candidate_hits

    # Keep more same-unit chunks for list/count queries where legal lists often spill over multiple chunks.
    if analyzed_query.query_intent in {"count_lookup", "list_lookup"}:
        max_hits = max(final_top_k, 3)
    else:
        max_hits = min(final_top_k, 3)
    return expanded_hits[:max_hits]


def _document_order_key(hit: RetrievalHit) -> tuple[int, int, str]:
    chunk_match = re.search(r"-c(\d+)$", hit.chunk_id)
    chunk_number = int(chunk_match.group(1)) if chunk_match else 0
    return hit.page_no, chunk_number, hit.chunk_id


def _unique_hits_preserving_order(hits: list[RetrievalHit]) -> list[RetrievalHit]:
    seen_chunk_ids: set[str] = set()
    unique_hits: list[RetrievalHit] = []
    for hit in hits:
        if hit.chunk_id in seen_chunk_ids:
            continue
        seen_chunk_ids.add(hit.chunk_id)
        unique_hits.append(hit)
    return unique_hits


def _looks_like_navigation_noise(hit: RetrievalHit) -> bool:
    if hit.page_no > 6:
        return False
    searchable_text = normalize_text(f"{' '.join(hit.heading_path)} {hit.normalized_text}").lower()
    return any(term in searchable_text for term in ("সূচিপত্র", "সূচীপত্র", "ক্রমিক", "বিষয়", "পৃষ্ঠ", "শিরোনাম"))


def _informative_overlap(hit: RetrievalHit, analyzed_query: QuerySignals) -> int:
    informative_terms = extract_informative_query_terms(
        analyzed_query.original_query or analyzed_query.normalized_query,
        analyzed_query.query_intent,
    )
    if not informative_terms:
        return 0
    searchable_terms = set(tokenize_for_bm25(f"{' '.join(hit.heading_path)} {hit.normalized_text}".lower()))
    return len(informative_terms & searchable_terms)


def _comparison_side_groups(analyzed_query: QuerySignals) -> list[tuple[str, ...]]:
    normalized_query = normalize_text(analyzed_query.original_query or analyzed_query.normalized_query).lower()
    side_groups: list[tuple[str, ...]] = []
    if "company" in normalized_query:
        side_groups.append(("company",))
    if (
        "other than a company" in normalized_query
        or "person other than a company" in normalized_query
        or "assessee other than a company" in normalized_query
        or "assesse other than a company" in normalized_query
    ):
        side_groups.append(
            (
                "other than a company",
                "person other than a company",
                "assessee other than a company",
                "assesse other than a company",
            )
        )
    if "between july 1, 2017 and june 30, 2023" in normalized_query:
        side_groups.append(("between july 1, 2017 and june 30, 2023",))
    if "on or after july 1, 2023" in normalized_query:
        side_groups.append(("on or after july 1, 2023",))

    unique_groups: list[tuple[str, ...]] = []
    seen_groups: set[tuple[str, ...]] = set()
    for group in side_groups:
        if group in seen_groups:
            continue
        seen_groups.add(group)
        unique_groups.append(group)
    return unique_groups


def _comparison_group_matched(searchable_text: str, group: tuple[str, ...]) -> bool:
    if group == ("company",):
        stripped_text = re.sub(
            r"(?:person\s+|assessee\s+|assesse\s+)?other than a company",
            "",
            searchable_text,
        )
        return bool(re.search(r"\bcompany\b", stripped_text))
    return any(phrase in searchable_text for phrase in group)


def _comparison_focus_coverage(hit: RetrievalHit, analyzed_query: QuerySignals) -> int:
    searchable_text = normalize_text(f"{' '.join(hit.heading_path)} {hit.normalized_text}").lower()
    coverage = 0
    for group in _comparison_side_groups(analyzed_query):
        if _comparison_group_matched(searchable_text, group):
            coverage += 1
    return coverage


def _build_definition_evidence_hits(
    candidate_hits: list[RetrievalHit],
    all_hits: list[RetrievalHit],
    analyzed_query: QuerySignals,
    *,
    final_top_k: int,
    candidate_pool: list[RetrievalHit] | None,
) -> list[RetrievalHit]:
    if not candidate_hits:
        return []
    exact_hits = [hit for hit in candidate_hits if hit_matches_definition_target_exactly(hit, analyzed_query)]
    anchor = exact_hits[0] if exact_hits else candidate_hits[0]
    expanded_hits = _expand_logical_unit_hits(
        [anchor],
        all_hits,
        analyzed_query,
        final_top_k=max(final_top_k, 3),
        candidate_pool=candidate_pool,
    )
    exact_expanded_hits = [hit for hit in expanded_hits if hit_matches_definition_target_exactly(hit, analyzed_query)]
    supportive_hits = [hit for hit in expanded_hits if hit_supports_definition(hit, analyzed_query)]
    ordered_hits = _unique_hits_preserving_order(exact_expanded_hits + supportive_hits)
    ordered_hits.sort(
        key=lambda hit: (
            0 if hit_matches_definition_target_exactly(hit, analyzed_query) else 1,
            0 if hit_supports_definition(hit, analyzed_query) else 1,
            -hit.score,
            *_document_order_key(hit),
        )
    )
    return ordered_hits[: min(final_top_k, 2)]


def _build_contextual_evidence_hits(
    candidate_hits: list[RetrievalHit],
    all_hits: list[RetrievalHit],
    analyzed_query: QuerySignals,
    *,
    final_top_k: int,
    candidate_pool: list[RetrievalHit] | None,
) -> list[RetrievalHit]:
    if not candidate_hits:
        return []
    anchor = candidate_hits[0]
    expanded_hits = _expand_logical_unit_hits(
        [anchor],
        all_hits,
        analyzed_query,
        final_top_k=max(final_top_k, 3),
        candidate_pool=candidate_pool,
    )
    contextual_hits = [
        hit
        for hit in expanded_hits
        if hit.chunk_id == anchor.chunk_id
        or hit_supports_query(hit, analyzed_query)
        or _same_logical_unit(anchor, hit, analyzed_query)
    ]
    contextual_hits = _unique_hits_preserving_order(contextual_hits)
    if not contextual_hits:
        return [anchor]
    anchor_and_context = [anchor]
    trailing_hits = sorted(
        [hit for hit in contextual_hits if hit.chunk_id != anchor.chunk_id],
        key=_document_order_key,
    )
    anchor_and_context.extend(trailing_hits)
    if len(anchor_and_context) < final_top_k:
        seen_chunk_ids = {hit.chunk_id for hit in anchor_and_context}
        for hit in candidate_hits:
            if hit.chunk_id in seen_chunk_ids:
                continue
            anchor_and_context.append(hit)
            seen_chunk_ids.add(hit.chunk_id)
            if len(anchor_and_context) >= final_top_k:
                break
    return anchor_and_context[:final_top_k]


def _build_list_evidence_hits(
    candidate_hits: list[RetrievalHit],
    all_hits: list[RetrievalHit],
    analyzed_query: QuerySignals,
    *,
    final_top_k: int,
    candidate_pool: list[RetrievalHit] | None,
) -> list[RetrievalHit]:
    if not candidate_hits:
        return []
    anchors = candidate_hits[:2]
    expanded_hits = _expand_logical_unit_hits(
        anchors,
        all_hits,
        analyzed_query,
        final_top_k=max(final_top_k, 4),
        candidate_pool=candidate_pool,
    )
    selected_hits = [
        hit
        for hit in expanded_hits
        if hit_supports_query(hit, analyzed_query)
        or any(_same_logical_unit(anchor, hit, analyzed_query) for anchor in anchors)
    ]
    selected_hits = _unique_hits_preserving_order(selected_hits)
    selected_hits.sort(key=_document_order_key)
    return selected_hits[: max(final_top_k, min(4, len(selected_hits)))]


def _build_section_evidence_hits(
    candidate_hits: list[RetrievalHit],
    all_hits: list[RetrievalHit],
    analyzed_query: QuerySignals,
    *,
    final_top_k: int,
    candidate_pool: list[RetrievalHit] | None,
) -> list[RetrievalHit]:
    if not candidate_hits:
        return []
    exact_heading_hits = [
        hit for hit in candidate_hits
        if analyzed_query.section_reference and has_exact_section_heading_match(hit, analyzed_query.section_reference)
    ]
    anchor_pool = exact_heading_hits if exact_heading_hits else candidate_hits
    anchor_pool = sorted(
        anchor_pool,
        key=lambda hit: (-hit.score, -authority_value(hit.authority_level), *_document_order_key(hit)),
    )
    anchor = anchor_pool[0]
    expanded_hits = _expand_logical_unit_hits(
        [anchor],
        all_hits,
        analyzed_query,
        final_top_k=max(final_top_k, 3),
        candidate_pool=candidate_pool,
    )
    selected_hits = [
        hit
        for hit in expanded_hits
        if hit.chunk_id == anchor.chunk_id
        or (analyzed_query.section_reference and has_exact_section_heading_match(hit, analyzed_query.section_reference))
        or _same_logical_unit(anchor, hit, analyzed_query)
    ]
    selected_hits = _unique_hits_preserving_order(selected_hits)
    selected_hits.sort(
        key=lambda hit: (
            0 if hit.chunk_id == anchor.chunk_id else 1,
            0 if analyzed_query.section_reference and has_exact_section_heading_match(hit, analyzed_query.section_reference) else 1,
            -hit.score,
            -authority_value(hit.authority_level),
            *_document_order_key(hit),
        )
    )
    return selected_hits[:final_top_k]


def _build_comparison_evidence_hits(
    candidate_hits: list[RetrievalHit],
    all_hits: list[RetrievalHit],
    analyzed_query: QuerySignals,
    *,
    final_top_k: int,
    candidate_pool: list[RetrievalHit] | None,
) -> list[RetrievalHit]:
    if not candidate_hits:
        return []
    side_groups = _comparison_side_groups(analyzed_query)
    self_contained_hits = [
        hit
        for hit in candidate_hits
        if len(side_groups) >= 2 and _comparison_focus_coverage(hit, analyzed_query) >= len(side_groups)
    ]
    if self_contained_hits:
        self_contained_hits.sort(
            key=lambda hit: (
                -_comparison_focus_coverage(hit, analyzed_query),
                -_informative_overlap(hit, analyzed_query),
                -(1 if hit_has_date_language(hit) else 0),
                -hit.score,
                *_document_order_key(hit),
            )
        )
        best_hit = self_contained_hits[0]
        expanded_hits = _expand_logical_unit_hits(
            [best_hit],
            all_hits,
            analyzed_query,
            final_top_k=max(final_top_k, 3),
            candidate_pool=candidate_pool,
        )
        selected_hits = [
            hit
            for hit in expanded_hits
            if _same_logical_unit(best_hit, hit, analyzed_query) or hit.chunk_id == best_hit.chunk_id
        ]
        selected_hits = _unique_hits_preserving_order(selected_hits)
        selected_hits.sort(
            key=lambda hit: (
                0 if hit.chunk_id == best_hit.chunk_id else 1,
                -_comparison_focus_coverage(hit, analyzed_query),
                -_informative_overlap(hit, analyzed_query),
                *_document_order_key(hit),
            )
        )
        return selected_hits[: min(max(final_top_k, 1), max(1, len(selected_hits)))]

    ranked_candidates = sorted(
        candidate_hits,
        key=lambda hit: (
            -_informative_overlap(hit, analyzed_query),
            -(1 if hit_has_date_language(hit) else 0),
            -hit.score,
            *_document_order_key(hit),
        ),
    )
    primary_anchor = ranked_candidates[0]
    primary_unit_hits = _expand_logical_unit_hits(
        [primary_anchor],
        all_hits,
        analyzed_query,
        final_top_k=max(final_top_k, 4),
        candidate_pool=candidate_pool,
    )
    primary_unit_hits = [
        hit
        for hit in primary_unit_hits
        if hit_supports_comparison(hit, analyzed_query) or _same_logical_unit(primary_anchor, hit, analyzed_query)
    ]
    primary_unit_hits = _unique_hits_preserving_order(primary_unit_hits)
    if len(primary_unit_hits) >= 2:
        primary_unit_hits.sort(
            key=lambda hit: (
                0 if hit.chunk_id == primary_anchor.chunk_id else 1,
                -_informative_overlap(hit, analyzed_query),
                -(1 if hit_has_date_language(hit) else 0),
                *_document_order_key(hit),
            )
        )
        return primary_unit_hits[: max(final_top_k, min(3, len(primary_unit_hits)))]

    anchors = ranked_candidates[:2] if len(ranked_candidates) >= 2 else ranked_candidates[:1]
    expanded_hits = _expand_logical_unit_hits(
        anchors,
        all_hits,
        analyzed_query,
        final_top_k=max(final_top_k, 4),
        candidate_pool=candidate_pool,
    )
    selected_hits = _unique_hits_preserving_order(anchors + expanded_hits)
    selected_hits.sort(
        key=lambda hit: (
            -_informative_overlap(hit, analyzed_query),
            -(1 if hit_has_date_language(hit) else 0),
            -hit.score,
            *_document_order_key(hit),
        )
    )
    return selected_hits[: max(final_top_k, min(3, len(selected_hits)))]


def _build_default_evidence_hits(
    candidate_hits: list[RetrievalHit],
    analyzed_query: QuerySignals,
    *,
    final_top_k: int,
) -> list[RetrievalHit]:
    selected_hits: list[RetrievalHit] = []
    seen_chunk_types: set[str] = set()
    for hit in candidate_hits:
        if len(selected_hits) >= final_top_k:
            break
        if hit.chunk_type not in seen_chunk_types or len(selected_hits) < 2:
            selected_hits.append(hit)
            seen_chunk_types.add(hit.chunk_type)
            continue
        selected_hits.append(hit)
    selected_hits.sort(key=lambda hit: (authority_value(hit.authority_level), hit.score), reverse=True)
    return selected_hits[:final_top_k]


def _select_evidence_hits_by_query_type(
    candidate_hits: list[RetrievalHit],
    all_hits: list[RetrievalHit],
    analyzed_query: QuerySignals,
    *,
    final_top_k: int,
    candidate_pool: list[RetrievalHit] | None,
) -> list[RetrievalHit]:
    if analyzed_query.query_intent == "definition":
        return _build_definition_evidence_hits(
            candidate_hits,
            all_hits,
            analyzed_query,
            final_top_k=final_top_k,
            candidate_pool=candidate_pool,
        )
    if analyzed_query.query_intent in {
        "amount_lookup",
        "rate_lookup",
        "duration_lookup",
        "date_lookup",
        "eligibility",
        "example",
        "calculation",
        "procedure",
    }:
        return _build_contextual_evidence_hits(
            candidate_hits,
            all_hits,
            analyzed_query,
            final_top_k=final_top_k,
            candidate_pool=candidate_pool,
        )
    if analyzed_query.query_intent in {"count_lookup", "list_lookup"}:
        return _build_list_evidence_hits(
            candidate_hits,
            all_hits,
            analyzed_query,
            final_top_k=final_top_k,
            candidate_pool=candidate_pool,
        )
    if analyzed_query.query_intent == "comparison":
        return _build_comparison_evidence_hits(
            candidate_hits,
            all_hits,
            analyzed_query,
            final_top_k=final_top_k,
            candidate_pool=candidate_pool,
        )
    if analyzed_query.section_reference:
        return _build_section_evidence_hits(
            candidate_hits,
            all_hits,
            analyzed_query,
            final_top_k=final_top_k,
            candidate_pool=candidate_pool,
        )
    return _build_default_evidence_hits(candidate_hits, analyzed_query, final_top_k=final_top_k)


def reciprocal_rank_fusion(
    *,
    sparse_hits: list[RetrievalHit],
    dense_hits: list[RetrievalHit],
    rrf_k: int = 60,
) -> list[RetrievalHit]:
    fused_by_chunk_id: dict[str, RetrievalHit] = {}
    for source_name, hits in (("sparse", sparse_hits), ("dense", dense_hits)):
        for rank, hit in enumerate(hits, start=1):
            fusion_gain = 1.0 / (rrf_k + rank)
            existing_hit = fused_by_chunk_id.get(hit.chunk_id)
            if existing_hit is None:
                existing_hit = hit.model_copy(deep=True)
                existing_hit.score = 0.0
                existing_hit.intermediate_scores = dict(hit.intermediate_scores)
                fused_by_chunk_id[hit.chunk_id] = existing_hit
            existing_hit.score += fusion_gain
            existing_hit.intermediate_scores[f"{source_name}_rank"] = rank
            existing_hit.intermediate_scores[f"{source_name}_score"] = hit.score
            existing_hit.intermediate_scores["rrf_score"] = round(existing_hit.score, 6)
    return sorted(fused_by_chunk_id.values(), key=lambda hit: hit.score, reverse=True)


def apply_hybrid_post_ranking(hit: RetrievalHit, analyzed_query: QuerySignals) -> RetrievalHit:
    adjusted_hit = hit.model_copy(deep=True)
    adjusted_score = adjusted_hit.score
    sparse_source_score = float(adjusted_hit.intermediate_scores.get("sparse_score", 0.0) or 0.0)
    dense_source_score = float(adjusted_hit.intermediate_scores.get("dense_score", 0.0) or 0.0)
    adjusted_score += min(sparse_source_score, 20.0) * 0.12
    adjusted_score += min(dense_source_score, 10.0) * 0.04
    if analyzed_query.tax_year and adjusted_hit.tax_year == analyzed_query.tax_year:
        adjusted_score += 1.4
    if analyzed_query.section_id and adjusted_hit.section_id == analyzed_query.section_id:
        adjusted_score += 1.8
    elif analyzed_query.section_id and adjusted_hit.section_id:
        adjusted_score -= 1.2
    if analyzed_query.subsection_id and adjusted_hit.subsection_id == analyzed_query.subsection_id:
        adjusted_score += 2.6
    elif analyzed_query.subsection_id:
        adjusted_score -= 2.2
    if analyzed_query.appendix_id and adjusted_hit.intermediate_scores.get("appendix_id") == analyzed_query.appendix_id:
        adjusted_score += 1.2
    if analyzed_query.sro_id and adjusted_hit.intermediate_scores.get("sro_id") == analyzed_query.sro_id:
        adjusted_score += 1.4
    if _looks_like_navigation_noise(adjusted_hit):
        adjusted_score -= 4.5
    if looks_like_late_reference_material(
        doc_title=adjusted_hit.doc_title,
        page_no=adjusted_hit.page_no,
        heading_path=adjusted_hit.heading_path,
        normalized_text=adjusted_hit.normalized_text,
        chunk_type=adjusted_hit.chunk_type,
        appendix_id=str(adjusted_hit.intermediate_scores.get("appendix_id") or "") or None,
    ):
        if query_requests_reference_material(analyzed_query.normalized_query):
            adjusted_score += 0.5
        else:
            adjusted_score -= 4.2
    query_terms = set(tokenize_for_bm25(analyzed_query.normalized_query))
    heading_terms = set(tokenize_for_bm25(" ".join(adjusted_hit.heading_path)))
    heading_overlap = len(query_terms & heading_terms)
    adjusted_score += min(heading_overlap * 0.25, 1.0)
    adjusted_score += authority_value(adjusted_hit.authority_level) * 0.18
    preferred_chunk_types = {
        "rate_lookup": "table",
        "example": "example",
        "procedure": "procedure",
        "calculation": "example",
    }
    preferred_chunk_type = preferred_chunk_types.get(analyzed_query.query_intent)
    if preferred_chunk_type and adjusted_hit.chunk_type == preferred_chunk_type:
        adjusted_score += 1.1
    if analyzed_query.query_intent == "rate_lookup":
        normalized_text = adjusted_hit.normalized_text
        if "করহার" not in normalized_text and "কর হার" not in normalized_text:
            adjusted_score -= 1.0
    searchable_text = f"{' '.join(adjusted_hit.heading_path)} {adjusted_hit.normalized_text}"
    if COMPANY_QUERY_PATTERN.search(analyzed_query.normalized_query):
        if COMPANY_QUERY_PATTERN.search(searchable_text):
            adjusted_score += 1.1
        else:
            adjusted_score -= 0.6
    if analyzed_query.query_intent == "mention_lookup":
        salient_terms = extract_salient_query_terms(analyzed_query.normalized_query)
        searchable_terms = set(tokenize_for_bm25(searchable_text.lower()))
        adjusted_score += min(len(salient_terms & searchable_terms) * 0.9, 4.5)
        if "software" in analyzed_query.normalized_query.lower():
            if "software" in searchable_text.lower():
                adjusted_score += 2.8
            else:
                adjusted_score -= 2.6
        if "service" in analyzed_query.normalized_query.lower():
            if "service" in searchable_text.lower():
                adjusted_score += 1.6
            else:
                adjusted_score -= 1.4
        if "software" in searchable_text.lower() and "service" in searchable_text.lower():
            adjusted_score += 1.5
    informative_terms = extract_informative_query_terms(analyzed_query.normalized_query, analyzed_query.query_intent)
    searchable_terms = set(tokenize_for_bm25(searchable_text.lower()))
    informative_overlap = len(informative_terms & searchable_terms)
    if analyzed_query.query_intent == "eligibility":
        normalized_query = analyzed_query.normalized_query.lower()
        if hit_supports_eligibility(adjusted_hit, analyzed_query):
            adjusted_score += 1.8
        else:
            adjusted_score -= 1.4
        if any(term in normalized_query for term in ("labour", "labor", "worker")):
            if any(term in searchable_text.lower() for term in ("day labourer", "day laborer", "worker")):
                adjusted_score += 2.1
            elif any(term in searchable_text.lower() for term in ("employee", "employment")):
                adjusted_score += 0.7
            else:
                adjusted_score -= 0.8
        if any(term in normalized_query for term in ("salary", "salaried", "employee")):
            if any(term in searchable_text.lower() for term in ("salary", "employee", "employment", "income from employment")):
                adjusted_score += 1.1
            else:
                adjusted_score -= 0.9
        if informative_terms:
            adjusted_score += min(informative_overlap * 0.9, 3.5)
            if informative_overlap == 0 and all(
                phrase not in searchable_text.lower()
                for phrase in ("chargeable to tax", "day labourer", "day laborer", "income from employment", "tax exemption")
            ):
                adjusted_score -= 3.2
    if analyzed_query.query_intent == "amount_lookup":
        if hit_has_amount_language(adjusted_hit):
            adjusted_score += 2.0
        else:
            adjusted_score -= 1.6
        if informative_terms:
            adjusted_score += min(informative_overlap * 1.0, 4.0)
            if informative_overlap == 0:
                adjusted_score -= 4.0
    if analyzed_query.query_intent == "count_lookup":
        if hit_looks_list_like(adjusted_hit) or any(token.isdigit() for token in searchable_terms):
            adjusted_score += 1.8
        if informative_terms:
            adjusted_score += min(informative_overlap * 1.0, 4.0)
            if informative_overlap == 0:
                adjusted_score -= 4.0
    if analyzed_query.query_intent == "duration_lookup":
        if hit_has_duration_language(adjusted_hit):
            adjusted_score += 2.0
        else:
            adjusted_score -= 1.5
        if informative_terms:
            adjusted_score += min(informative_overlap * 1.0, 4.0)
            if informative_overlap == 0:
                adjusted_score -= 4.0
    if analyzed_query.query_intent == "date_lookup":
        if hit_has_date_language(adjusted_hit):
            adjusted_score += 1.8
        else:
            adjusted_score -= 1.4
        if informative_terms:
            adjusted_score += min(informative_overlap * 0.9, 3.5)
            if informative_overlap == 0:
                adjusted_score -= 3.5
    if analyzed_query.query_intent == "list_lookup":
        if hit_looks_list_like(adjusted_hit):
            adjusted_score += 1.9
        else:
            adjusted_score -= 1.2
        if informative_terms:
            adjusted_score += min(informative_overlap * 0.9, 3.5)
            if informative_overlap == 0:
                adjusted_score -= 3.2
    if analyzed_query.query_intent == "comparison":
        if hit_supports_comparison(adjusted_hit, analyzed_query):
            adjusted_score += 2.2
        else:
            adjusted_score -= 2.2
        if informative_terms:
            adjusted_score += min(informative_overlap * 0.9, 3.5)
            if informative_overlap == 0:
                adjusted_score -= 3.8
    adjusted_hit.score = round(adjusted_score, 6)
    adjusted_hit.intermediate_scores["postrank_score"] = adjusted_hit.score
    return adjusted_hit


def detect_conflicts(hits: list[RetrievalHit]) -> list[str]:
    conflict_notes: list[str] = []
    for index, left_hit in enumerate(hits):
        for right_hit in hits[index + 1:]:
            same_heading = left_hit.heading_path and left_hit.heading_path == right_hit.heading_path
            same_section = left_hit.section_id and left_hit.section_id == right_hit.section_id
            if (same_heading or same_section) and left_hit.tax_year != right_hit.tax_year and left_hit.tax_year and right_hit.tax_year:
                conflict_notes.append(
                    f"Potential tax-year conflict between {left_hit.chunk_id} ({left_hit.tax_year}) and {right_hit.chunk_id} ({right_hit.tax_year})."
                )
            if (same_heading or same_section) and left_hit.authority_level != right_hit.authority_level:
                conflict_notes.append(
                    f"Potential authority conflict between {left_hit.chunk_id} ({left_hit.authority_level}) and {right_hit.chunk_id} ({right_hit.authority_level})."
                )
    return list(dict.fromkeys(conflict_notes))


def build_evidence_pack(
    fused_hits: list[RetrievalHit],
    analyzed_query: QuerySignals,
    *,
    final_top_k: int = 5,
    query_text: str | None = None,
    candidate_pool: list[RetrievalHit] | None = None,
) -> tuple[list[RetrievalHit], str, list[str], list[str]]:
    reranked_hits = [apply_hybrid_post_ranking(hit, analyzed_query) for hit in fused_hits]
    reranked_hits.sort(key=lambda hit: hit.score, reverse=True)
    reranked_hits = rerank_retrieval_hits(
        query_text=query_text or analyzed_query.original_query,
        analyzed_query=analyzed_query,
        hits=reranked_hits,
        top_n=max(final_top_k * 4, 12),
    )
    conflict_notes = detect_conflicts(reranked_hits[: max(final_top_k + 2, 4)])
    deduplicated_hits, dropped_duplicates = deduplicate_retrieval_hits(reranked_hits)
    supportive_hits = filter_supportive_hits(deduplicated_hits, analyzed_query)
    if analyzed_query.section_reference and not analyzed_query.subsection_id:
        exact_heading_hits = [
            hit for hit in supportive_hits
            if has_exact_section_heading_match(hit, analyzed_query.section_reference)
        ]
        if exact_heading_hits:
            salient_terms = extract_salient_query_terms(analyzed_query.normalized_query)
            generic_terms = {"section", "tax", "income", "act", "under", "what", "are", analyzed_query.section_reference or ""}
            informative_terms = {term for term in salient_terms if term not in generic_terms}
            semantically_aligned_hits = []
            for hit in exact_heading_hits:
                searchable_text = f"{' '.join(hit.heading_path)} {hit.normalized_text}".lower()
                searchable_terms = set(tokenize_for_bm25(searchable_text))
                if informative_terms:
                    if any(term in searchable_text for term in informative_terms):
                        semantically_aligned_hits.append(hit)
                elif len(salient_terms & searchable_terms) >= 2:
                    semantically_aligned_hits.append(hit)
            supportive_hits = semantically_aligned_hits or exact_heading_hits
    requires_exact_support = (
        bool(analyzed_query.subsection_id)
        or (analyzed_query.query_intent == "rate_lookup" and bool(analyzed_query.section_id))
        or analyzed_query.query_intent in STRICT_SUPPORT_INTENTS
    )
    if requires_exact_support and not supportive_hits:
        conflict_notes.append("No final evidence directly supports the requested section or subsection.")
        candidate_hits: list[RetrievalHit] = []
    else:
        candidate_hits = supportive_hits if supportive_hits else deduplicated_hits
    selected_hits = _select_evidence_hits_by_query_type(
        candidate_hits,
        deduplicated_hits,
        analyzed_query,
        final_top_k=final_top_k,
        candidate_pool=candidate_pool,
    )
    evidence_summary = (
        "; ".join(f"{hit.chunk_id} p.{hit.page_no} {hit.chunk_type} {hit.authority_level}" for hit in selected_hits)
        if selected_hits
        else "No evidence passed the final support checks."
    )
    return selected_hits, evidence_summary, conflict_notes, dropped_duplicates


def run_hybrid_retrieval(
    *,
    query: str,
    sparse_top_k: int = 10,
    dense_top_k: int = 10,
    final_top_k: int = 5,
    rrf_k: int = 60,
    tax_year: str | None = None,
    doc_type: str | None = None,
    authority_level_min: str | None = None,
    chunk_type: str | None = None,
    index_dir: str | Path = DEFAULT_INDEX_DIR,
    dense_index_dir: str | Path | None = None,
    sparse_hits_override: list[RetrievalHit] | None = None,
    dense_hits_override: list[RetrievalHit] | None = None,
) -> HybridRetrievalResponse:
    analyzed_query = preprocess_query(query)
    effective_tax_year = tax_year or analyzed_query.tax_year
    sparse_hits = (
        sparse_hits_override
        if sparse_hits_override is not None
        else [
            RetrievalHit(**hit)
            for hit in sparse_search(
                query,
                top_k=sparse_top_k,
                tax_year=effective_tax_year,
                doc_type=doc_type,
                authority_level_min=authority_level_min,
                chunk_type=chunk_type,
                index_dir=index_dir,
            )
        ]
    )
    dense_hits = (
        dense_hits_override
        if dense_hits_override is not None
        else _load_dense_hits_for_hybrid(
            query=query,
            top_k=dense_top_k,
            effective_tax_year=effective_tax_year,
            doc_type=doc_type,
            authority_level_min=authority_level_min,
            chunk_type=chunk_type,
            dense_index_dir=dense_index_dir or index_dir,
        )
    )
    fused_hits = reciprocal_rank_fusion(sparse_hits=sparse_hits, dense_hits=dense_hits, rrf_k=rrf_k)
    candidate_pool: list[RetrievalHit] | None = None
    if sparse_hits_override is None and dense_hits_override is None:
        try:
            chunk_records = load_chunk_records_from_jsonl(Path(index_dir) / "chunks.jsonl")
        except FileNotFoundError:
            chunk_records = []
        candidate_pool = [
            RetrievalHit(
                chunk_id=chunk.chunk_id,
                doc_id=chunk.doc_id,
                doc_title=chunk.doc_title,
                page_no=chunk.page_no,
                section_id=chunk.section_id,
                subsection_id=chunk.subsection_id,
                chunk_type=chunk.chunk_type,
                authority_level=chunk.authority_level,
                tax_year=infer_chunk_tax_year(chunk),
                original_text=chunk.original_text,
                normalized_text=chunk.normalized_text,
                heading_path=chunk.heading_path,
                content=chunk.original_text,
                score=0.0,
                intermediate_scores={"from_corpus_pool": 1},
            )
            for chunk in chunk_records
        ]
    final_hits, evidence_summary, conflict_notes, dropped_duplicates = build_evidence_pack(
        fused_hits,
        analyzed_query,
        final_top_k=final_top_k,
        query_text=query,
        candidate_pool=candidate_pool,
    )
    return HybridRetrievalResponse(
        query_text=query,
        analyzed_query=analyzed_query,
        sparse_hits=sparse_hits,
        dense_hits=dense_hits,
        fused_hits=fused_hits,
        final_hits=final_hits,
        conflict_notes=conflict_notes,
        evidence_summary=evidence_summary,
        dropped_duplicates=dropped_duplicates,
    )


def hybrid_search(
    query: str,
    top_k: int = 5,
    *,
    tax_year: str | None = None,
    doc_type: str | None = None,
    authority_level_min: str | None = None,
    chunk_type: str | None = None,
    sparse_top_k: int | None = None,
    dense_top_k: int | None = None,
    final_top_k: int | None = None,
    rrf_k: int = 60,
    index_dir: str | Path = DEFAULT_INDEX_DIR,
    dense_index_dir: str | Path | None = None,
) -> list[dict[str, str | float | int | list[str] | None | dict[str, float | int | None]]]:
    response = run_hybrid_retrieval(
        query=query,
        sparse_top_k=sparse_top_k or max(top_k * 2, 10),
        dense_top_k=dense_top_k or max(top_k * 2, 10),
        final_top_k=final_top_k or top_k,
        rrf_k=rrf_k,
        tax_year=tax_year,
        doc_type=doc_type,
        authority_level_min=authority_level_min,
        chunk_type=chunk_type,
        index_dir=index_dir,
        dense_index_dir=dense_index_dir,
    )
    logger.info(
        "Hybrid retrieval complete",
        extra={
            "query": query,
            "sparse_hits": len(response.sparse_hits),
            "dense_hits": len(response.dense_hits),
            "final_hits": len(response.final_hits),
        },
    )
    return [hit.model_dump() for hit in response.final_hits]
