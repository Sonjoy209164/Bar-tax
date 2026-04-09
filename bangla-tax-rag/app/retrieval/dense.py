import json
from pathlib import Path

from app.core.schemas import RetrievalHit
from app.core.utils import ensure_directory
from app.core.utils import extract_definition_target, extract_informative_query_terms, preprocess_query, tokenize_for_bm25
from app.retrieval.filters import (
    authority_value,
    chunk_quality_score,
    filter_chunk_records,
    hit_has_amount_language,
    hit_has_date_language,
    hit_has_duration_language,
    hit_looks_list_like,
)
from app.retrieval.sparse import DEFAULT_INDEX_DIR, load_chunk_records_from_jsonl


def build_dense_index_artifacts(
    chunk_jsonl_path: str | Path,
    output_dir: str | Path,
) -> tuple[Path, int]:
    chunk_records = load_chunk_records_from_jsonl(chunk_jsonl_path)
    output_path = ensure_directory(str(output_dir))
    chunks_output_path = output_path / "chunks.jsonl"
    chunks_output_path.write_text(Path(chunk_jsonl_path).read_text(encoding="utf-8"), encoding="utf-8")
    metadata = {
        "status": "ready",
        "index_type": "dense_overlap_placeholder",
        "chunk_count": len(chunk_records),
    }
    metadata_path = output_path / "metadata.json"
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    return output_path, len(chunk_records)


def load_dense_index_metadata(index_dir: str | Path) -> dict:
    metadata_path = Path(index_dir) / "metadata.json"
    if not metadata_path.exists():
        raise FileNotFoundError(f"Dense index metadata not found at {metadata_path}")
    return json.loads(metadata_path.read_text(encoding="utf-8"))


def _dense_like_score(query_tokens: set[str], chunk_tokens: set[str], authority_level: str) -> float:
    if not query_tokens or not chunk_tokens:
        return 0.0
    overlap_count = len(query_tokens & chunk_tokens)
    containment_ratio = overlap_count / len(query_tokens)
    jaccard_ratio = overlap_count / len(query_tokens | chunk_tokens)
    return (containment_ratio * 2.0) + jaccard_ratio + (authority_value(authority_level) * 0.05)


def dense_search(
    query: str,
    top_k: int,
    *,
    tax_year: str | None = None,
    doc_type: str | None = None,
    authority_level_min: str | None = None,
    chunk_type: str | None = None,
    index_dir: str | Path = DEFAULT_INDEX_DIR,
) -> list[dict[str, str | float | int | list[str] | None | dict[str, float | int | None]]]:
    load_dense_index_metadata(index_dir)
    analyzed_query = preprocess_query(query)
    effective_tax_year = tax_year or analyzed_query.tax_year
    chunk_records = load_chunk_records_from_jsonl(Path(index_dir) / "chunks.jsonl")
    filtered_records = filter_chunk_records(
        chunk_records,
        tax_year=effective_tax_year,
        doc_type=doc_type,
        authority_level_min=authority_level_min,
        chunk_type=chunk_type,
    )
    query_tokens = set(tokenize_for_bm25(analyzed_query.normalized_query))
    informative_terms = extract_informative_query_terms(analyzed_query.normalized_query, analyzed_query.query_intent)
    scored_hits: list[RetrievalHit] = []
    for chunk in filtered_records:
        weighted_text = " ".join([chunk.doc_title, " ".join(chunk.heading_path), chunk.normalized_text])
        searchable_text = weighted_text.lower()
        chunk_tokens = set(tokenize_for_bm25(weighted_text))
        score = _dense_like_score(query_tokens, chunk_tokens, chunk.authority_level)
        score += chunk_quality_score(chunk.normalized_text) * 0.8
        exact_heading_match = False
        if analyzed_query.subsection_id:
            if chunk.subsection_id == analyzed_query.subsection_id:
                score += 1.8
            else:
                score -= 1.6
        elif analyzed_query.section_id and chunk.section_id:
            if chunk.section_id == analyzed_query.section_id:
                score += 1.0
            else:
                score -= 0.8
        if analyzed_query.section_reference:
            exact_heading_match = any(
                tokenize_for_bm25(heading.lower())[:1] == tokenize_for_bm25(analyzed_query.section_reference)
                or heading.lower().startswith(f"{analyzed_query.section_reference}.")
                or heading.lower().startswith(f"{analyzed_query.section_reference} ")
                for heading in chunk.heading_path
            )
            if exact_heading_match:
                score += 1.8
        if analyzed_query.query_intent == "rate_lookup":
            if chunk.chunk_type == "table":
                score += 1.1
            if "করহার" in chunk.normalized_text or "কর হার" in chunk.normalized_text:
                score += 0.9
            else:
                score -= 0.7
        if analyzed_query.query_intent == "definition":
            definition_target = extract_definition_target(analyzed_query.original_query or analyzed_query.normalized_query)
            has_definition_heading = any(
                keyword in heading.lower()
                for heading in chunk.heading_path
                for keyword in ("definition", "definitions", "সংজ্ঞা")
            )
            has_definition_language = any(
                phrase in searchable_text
                for phrase in (" means ", " means\n", "defined as", "definitions", "definition")
            )
            if has_definition_heading:
                score += 2.0
            if has_definition_language:
                score += 1.5
            else:
                score -= 1.0
            if definition_target:
                focus_terms = [token.lower() for token in tokenize_for_bm25(definition_target)]
                if focus_terms and all(term in searchable_text for term in focus_terms):
                    score += 2.0
                    if any(
                        phrase in searchable_text
                        for phrase in (
                            f"“{definition_target.lower()}” means",
                            f"\"{definition_target.lower()}\" means",
                            f"{definition_target.lower()} means",
                        )
                    ):
                        score += 2.5
                else:
                    score -= 1.2
        pseudo_hit = RetrievalHit(
            chunk_id=chunk.chunk_id,
            doc_id=chunk.doc_id,
            doc_title=chunk.doc_title,
            page_no=chunk.page_no,
            section_id=chunk.section_id,
            subsection_id=chunk.subsection_id,
            chunk_type=chunk.chunk_type,
            authority_level=chunk.authority_level,
            tax_year=chunk.tax_year,
            original_text=chunk.original_text,
            normalized_text=chunk.normalized_text,
            heading_path=chunk.heading_path,
            content=chunk.original_text,
            score=round(score, 4),
            intermediate_scores={},
        )
        informative_overlap = len(informative_terms & chunk_tokens)
        if analyzed_query.query_intent == "amount_lookup":
            if hit_has_amount_language(pseudo_hit):
                score += 1.4
            else:
                score -= 1.2
            if informative_terms:
                score += min(informative_overlap * 0.9, 3.0)
                if informative_overlap == 0:
                    score -= 2.8
        if analyzed_query.query_intent == "count_lookup":
            if hit_looks_list_like(pseudo_hit) or any(token.isdigit() for token in chunk_tokens):
                score += 1.2
            if informative_terms:
                score += min(informative_overlap * 0.9, 3.0)
                if informative_overlap == 0:
                    score -= 2.8
        if analyzed_query.query_intent == "duration_lookup":
            if hit_has_duration_language(pseudo_hit):
                score += 1.3
            else:
                score -= 1.1
            if informative_terms:
                score += min(informative_overlap * 0.9, 3.0)
                if informative_overlap == 0:
                    score -= 2.8
        if analyzed_query.query_intent == "date_lookup":
            if hit_has_date_language(pseudo_hit):
                score += 1.2
            else:
                score -= 1.0
            if informative_terms:
                score += min(informative_overlap * 0.8, 2.5)
                if informative_overlap == 0:
                    score -= 2.5
        if analyzed_query.query_intent == "list_lookup":
            if hit_looks_list_like(pseudo_hit):
                score += 1.3
            else:
                score -= 0.8
            if informative_terms:
                score += min(informative_overlap * 0.8, 2.5)
                if informative_overlap == 0:
                    score -= 2.3
        if score <= 0:
            continue
        scored_hits.append(
            RetrievalHit(
                chunk_id=chunk.chunk_id,
                doc_id=chunk.doc_id,
                doc_title=chunk.doc_title,
                page_no=chunk.page_no,
                section_id=chunk.section_id,
                subsection_id=chunk.subsection_id,
                chunk_type=chunk.chunk_type,
                authority_level=chunk.authority_level,
                tax_year=chunk.tax_year,
                original_text=chunk.original_text,
                normalized_text=chunk.normalized_text,
                heading_path=chunk.heading_path,
                content=chunk.original_text,
                score=round(score, 4),
                intermediate_scores={
                    "dense_score": round(score, 6),
                    "appendix_id": chunk.appendix_id or "",
                    "sro_id": chunk.sro_id or "",
                },
            )
        )
    ranked_hits = sorted(scored_hits, key=lambda hit: hit.score, reverse=True)[:top_k]
    return [hit.model_dump() for hit in ranked_hits]
