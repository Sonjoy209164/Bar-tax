import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path

from rank_bm25 import BM25Okapi

from app.core.schemas import ChunkRecord, QuerySignals, RetrievalHit, RetrievalResponse
from app.core.utils import extract_definition_target, extract_salient_query_terms, preprocess_query, tokenize_for_bm25
from app.retrieval.filters import authority_value, chunk_quality_score, filter_chunk_records

logger = logging.getLogger(__name__)
DEFAULT_INDEX_DIR = Path("indexes/sparse")
COMPANY_QUERY_TOKENS = {"company", "কোম্পানি", "কম্পানি", "software", "software company"}


@dataclass
class SparseIndex:
    chunk_records: list[ChunkRecord]
    search_texts: list[str]
    tokenized_corpus: list[list[str]]
    bm25: BM25Okapi


def build_weighted_search_text(chunk: ChunkRecord) -> str:
    heading_text = " ".join(chunk.heading_path)
    return " ".join(
        part
        for part in [
            chunk.doc_title,
            chunk.doc_title,
            heading_text,
            heading_text,
            chunk.normalized_text,
        ]
        if part
    )


def _has_exact_section_heading_match(chunk: ChunkRecord, section_reference: str) -> bool:
    heading_pattern = re.compile(rf"^{re.escape(section_reference)}(?:[.)]|(?:\s*[—:-]))")
    if heading_pattern.match(chunk.normalized_text):
        return True
    return any(heading_pattern.match(heading) for heading in chunk.heading_path)


def build_sparse_index(chunk_records: list[ChunkRecord]) -> SparseIndex:
    search_texts = [build_weighted_search_text(chunk) for chunk in chunk_records]
    tokenized_corpus = [tokenize_for_bm25(text) for text in search_texts]
    bm25 = BM25Okapi(tokenized_corpus)
    return SparseIndex(
        chunk_records=chunk_records,
        search_texts=search_texts,
        tokenized_corpus=tokenized_corpus,
        bm25=bm25,
    )


def save_sparse_index(index: SparseIndex, output_dir: str | Path = DEFAULT_INDEX_DIR) -> Path:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    chunks_path = output_path / "chunks.jsonl"
    with chunks_path.open("w", encoding="utf-8") as handle:
        for chunk in index.chunk_records:
            handle.write(json.dumps(chunk.model_dump(), ensure_ascii=False) + "\n")
    metadata_path = output_path / "metadata.json"
    metadata = {"chunk_count": len(index.chunk_records)}
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("Saved sparse index", extra={"output_dir": str(output_path), "chunk_count": len(index.chunk_records)})
    return output_path


def load_chunk_records_from_jsonl(input_path: str | Path) -> list[ChunkRecord]:
    chunk_records: list[ChunkRecord] = []
    with Path(input_path).open("r", encoding="utf-8") as handle:
        for line in handle:
            stripped_line = line.strip()
            if not stripped_line:
                continue
            chunk_records.append(ChunkRecord.model_validate_json(stripped_line))
    return chunk_records


def load_sparse_index(index_dir: str | Path = DEFAULT_INDEX_DIR) -> SparseIndex:
    chunks_path = Path(index_dir) / "chunks.jsonl"
    chunk_records = load_chunk_records_from_jsonl(chunks_path)
    return build_sparse_index(chunk_records)


def apply_score_boosts(chunk: ChunkRecord, query_signals: QuerySignals, base_score: float) -> float:
    boosted_score = base_score
    quality_score = chunk_quality_score(chunk.normalized_text)
    boosted_score += quality_score * 1.2
    searchable_text = f"{chunk.doc_title} {' '.join(chunk.heading_path)} {chunk.normalized_text}".lower()
    exact_heading_match = False
    if query_signals.section_reference:
        exact_heading_match = _has_exact_section_heading_match(chunk, query_signals.section_reference)
        if chunk.subsection_id == query_signals.section_reference:
            boosted_score += 4.0
            if exact_heading_match:
                boosted_score += 2.5
            else:
                boosted_score -= 1.0
        elif chunk.section_id == query_signals.section_reference:
            boosted_score += 2.5
            if exact_heading_match:
                boosted_score += 2.0
            else:
                boosted_score -= 1.2
        elif query_signals.subsection_id:
            boosted_score -= 2.5
        elif query_signals.section_id and chunk.section_id and chunk.section_id != query_signals.section_id:
            boosted_score -= 1.5
    if query_signals.tax_year and chunk.tax_year == query_signals.tax_year:
        boosted_score += 1.5
    if query_signals.appendix_reference and chunk.appendix_id == query_signals.appendix_reference:
        boosted_score += 1.5
    if query_signals.sro_reference and chunk.sro_id == query_signals.sro_reference:
        boosted_score += 2.0
    query_terms = set(tokenize_for_bm25(query_signals.normalized_query))
    heading_terms = set(tokenize_for_bm25(" ".join(chunk.heading_path)))
    heading_overlap = len(query_terms & heading_terms)
    boosted_score += min(heading_overlap * 0.3, 1.2)
    salient_heading_overlap = len(extract_salient_query_terms(query_signals.normalized_query) & heading_terms)
    if query_signals.section_reference:
        boosted_score += min(salient_heading_overlap * 1.5, 4.5)
        if not exact_heading_match and salient_heading_overlap == 0:
            boosted_score -= 3.0
        if salient_heading_overlap <= 1:
            boosted_score -= 2.5
    boosted_score += authority_value(chunk.authority_level) * 0.15
    if query_signals.query_type == "example" and chunk.chunk_type == "example":
        boosted_score += 1.25
    if query_signals.query_type == "rate_lookup" and chunk.chunk_type == "table":
        boosted_score += 1.75
        if (
            "করহার" in searchable_text
            or "কর হার" in searchable_text
            or "tax rate" in searchable_text
            or "rate of tax" in searchable_text
        ):
            boosted_score += 1.25
        if query_signals.subsection_id and chunk.subsection_id != query_signals.subsection_id:
            boosted_score -= 2.0
    if query_signals.query_intent == "rate_lookup" and all(
        phrase not in searchable_text for phrase in ("করহার", "কর হার", "tax rate", "rate of tax", "tax payable")
    ):
        boosted_score -= 1.0
    if query_signals.query_intent == "definition":
        definition_target = extract_definition_target(query_signals.original_query or query_signals.normalized_query)
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
            boosted_score += 3.0
        elif chunk.heading_path:
            boosted_score -= 0.8
        if has_definition_language:
            boosted_score += 2.0
        else:
            boosted_score -= 1.2
        if definition_target:
            focus_terms = [token.lower() for token in tokenize_for_bm25(definition_target)]
            if focus_terms and all(term in searchable_text for term in focus_terms):
                boosted_score += 2.4
                if any(
                    phrase in searchable_text
                    for phrase in (
                        f"“{definition_target.lower()}” means",
                        f"\"{definition_target.lower()}\" means",
                        f"{definition_target.lower()} means",
                    )
                ):
                    boosted_score += 3.0
            else:
                boosted_score -= 1.4
    if any(token in query_signals.normalized_query.lower() for token in COMPANY_QUERY_TOKENS):
        if any(token in searchable_text for token in COMPANY_QUERY_TOKENS):
            boosted_score += 1.0
        else:
            boosted_score -= 0.8
    return boosted_score


def _to_retrieval_hit(chunk: ChunkRecord, score: float) -> RetrievalHit:
    return RetrievalHit(
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
            "sparse_score": round(score, 6),
            "appendix_id": chunk.appendix_id or "",
            "sro_id": chunk.sro_id or "",
        },
    )


def search_sparse_index(
    *,
    query: str,
    index: SparseIndex,
    top_k: int = 5,
    tax_year: str | None = None,
    doc_type: str | None = None,
    authority_level_min: str | None = None,
    chunk_type: str | None = None,
) -> RetrievalResponse:
    query_signals = preprocess_query(query)
    effective_tax_year = tax_year or query_signals.tax_year
    search_query = query_signals.rewritten_query or query_signals.normalized_query
    query_tokens = tokenize_for_bm25(search_query)
    salient_terms = extract_salient_query_terms(search_query)
    if not query_tokens:
        return RetrievalResponse(status="success", query=query, signals=query_signals, hits=[])
    candidate_records = filter_chunk_records(
        index.chunk_records,
        tax_year=effective_tax_year,
        doc_type=doc_type,
        authority_level_min=authority_level_min,
        chunk_type=chunk_type,
    )
    if not candidate_records:
        logger.info("Sparse retrieval filters removed all results", extra={"query": query})
        return RetrievalResponse(status="success", query=query, signals=query_signals, hits=[])
    base_scores = index.bm25.get_scores(query_tokens)
    scored_hits: list[RetrievalHit] = []
    allowed_chunk_ids = {chunk.chunk_id for chunk in candidate_records}
    for chunk, base_score in zip(index.chunk_records, base_scores, strict=True):
        if chunk.chunk_id not in allowed_chunk_ids:
            continue
        final_score = apply_score_boosts(chunk, query_signals, float(base_score))
        if final_score <= 0:
            continue
        searchable_text = f"{chunk.doc_title} {' '.join(chunk.heading_path)} {chunk.normalized_text}".lower()
        salient_overlap = len(salient_terms & set(tokenize_for_bm25(searchable_text)))
        if salient_terms and query_signals.query_intent in {"rate_lookup", "definition", "mention_lookup"} and salient_overlap == 0:
            continue
        scored_hits.append(_to_retrieval_hit(chunk, final_score))
    ranked_hits = sorted(scored_hits, key=lambda hit: hit.score, reverse=True)[:top_k]
    return RetrievalResponse(status="success", query=query, signals=query_signals, hits=ranked_hits)


def sparse_search(
    query: str,
    top_k: int,
    *,
    tax_year: str | None = None,
    doc_type: str | None = None,
    authority_level_min: str | None = None,
    chunk_type: str | None = None,
    index_dir: str | Path = DEFAULT_INDEX_DIR,
) -> list[dict[str, str | float | int | list[str] | None]]:
    index = load_sparse_index(index_dir)
    response = search_sparse_index(
        query=query,
        index=index,
        top_k=top_k,
        tax_year=tax_year,
        doc_type=doc_type,
        authority_level_min=authority_level_min,
        chunk_type=chunk_type,
    )
    return [hit.model_dump() for hit in response.hits]
