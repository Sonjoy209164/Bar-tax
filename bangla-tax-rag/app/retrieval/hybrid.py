import logging
import re
from pathlib import Path

from app.core.schemas import HybridRetrievalResponse, QuerySignals, RetrievalHit
from app.core.utils import preprocess_query, tokenize_for_bm25
from app.retrieval.dense import dense_search
from app.retrieval.filters import authority_value, deduplicate_retrieval_hits, filter_supportive_hits
from app.retrieval.sparse import DEFAULT_INDEX_DIR, load_sparse_index, sparse_search

logger = logging.getLogger(__name__)


COMPANY_QUERY_PATTERN = re.compile(r"(কোম্প|কম্প|মকাম্প|ককাম্প|company)", re.IGNORECASE)


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
) -> tuple[list[RetrievalHit], str, list[str], list[str]]:
    reranked_hits = [apply_hybrid_post_ranking(hit, analyzed_query) for hit in fused_hits]
    reranked_hits.sort(key=lambda hit: hit.score, reverse=True)
    conflict_notes = detect_conflicts(reranked_hits[: max(final_top_k + 2, 4)])
    deduplicated_hits, dropped_duplicates = deduplicate_retrieval_hits(reranked_hits)
    supportive_hits = filter_supportive_hits(deduplicated_hits, analyzed_query)
    requires_exact_support = bool(analyzed_query.subsection_id) or (
        analyzed_query.query_intent == "rate_lookup" and bool(analyzed_query.section_id)
    )
    if requires_exact_support and not supportive_hits:
        conflict_notes.append("No final evidence directly supports the requested section or subsection.")
        candidate_hits: list[RetrievalHit] = []
    else:
        candidate_hits = supportive_hits if supportive_hits else deduplicated_hits
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
    selected_hits = selected_hits[:final_top_k]
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
        else [
            RetrievalHit(**hit)
            for hit in dense_search(
                query,
                top_k=dense_top_k,
                tax_year=effective_tax_year,
                doc_type=doc_type,
                authority_level_min=authority_level_min,
                chunk_type=chunk_type,
                index_dir=index_dir,
            )
        ]
    )
    fused_hits = reciprocal_rank_fusion(sparse_hits=sparse_hits, dense_hits=dense_hits, rrf_k=rrf_k)
    final_hits, evidence_summary, conflict_notes, dropped_duplicates = build_evidence_pack(
        fused_hits,
        analyzed_query,
        final_top_k=final_top_k,
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
