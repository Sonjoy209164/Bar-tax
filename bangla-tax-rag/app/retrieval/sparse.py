




import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path

from rank_bm25 import BM25Okapi

from app.core.schemas import ChunkRecord, QuerySignals, RetrievalHit, RetrievalResponse
from app.core.utils import (
    extract_definition_target,
    extract_informative_query_terms,
    extract_salient_query_terms,
    extract_tax_years,
    extract_tax_years_near_marker,
    preprocess_query,
    tokenize_for_bm25,
)
from app.retrieval.filters import (
    authority_value,
    chunk_has_rate_value_language,
    chunk_navigation_noise_score,
    chunk_quality_score,
    filter_chunk_records,
    hit_has_amount_language,
    hit_supports_comparison,
    hit_has_date_language,
    hit_has_duration_language,
    hit_supports_eligibility,
    hit_looks_list_like,
    infer_chunk_tax_year,
)

logger = logging.getLogger(__name__)
DEFAULT_INDEX_DIR = Path("indexes/sparse")
COMPANY_QUERY_TOKENS = {"company", "কোম্পানি", "কম্পানি", "software", "software company"}


@dataclass
class SparseIndex:
    chunk_records: list[ChunkRecord]
    search_texts: list[str]
    tokenized_corpus: list[list[str]]
    bm25: BM25Okapi
    body_texts: list[str]
    heading_texts: list[str]
    structure_texts: list[str]
    body_tokenized_corpus: list[list[str]]
    heading_tokenized_corpus: list[list[str]]
    structure_tokenized_corpus: list[list[str]]
    body_bm25: BM25Okapi
    heading_bm25: BM25Okapi
    structure_bm25: BM25Okapi


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


def build_body_search_text(chunk: ChunkRecord) -> str:
    return chunk.normalized_text


def build_heading_search_text(chunk: ChunkRecord) -> str:
    return " ".join(chunk.heading_path)


def build_structure_search_text(chunk: ChunkRecord) -> str:
    parts = [
        chunk.doc_title,
        chunk.doc_type,
        chunk.authority_level,
        chunk.chunk_type,
    ]
    if chunk.tax_year:
        parts.extend([chunk.tax_year, f"tax year {chunk.tax_year}"])
    if chunk.section_id:
        parts.extend([chunk.section_id, f"section {chunk.section_id}", f"section_{chunk.section_id}"])
    if chunk.subsection_id:
        parts.extend(
            [
                chunk.subsection_id,
                f"subsection {chunk.subsection_id}",
                f"subsection_{chunk.subsection_id}",
                f"section {chunk.subsection_id}",
            ]
        )
    if chunk.appendix_id:
        parts.extend([chunk.appendix_id, f"appendix {chunk.appendix_id}"])
    if chunk.sro_id:
        parts.extend(["sro", chunk.sro_id])
    return " ".join(part for part in parts if part)


def _field_score_weights(query_signals: QuerySignals) -> dict[str, float]:
    if query_signals.query_intent == "definition":
        return {"body": 0.4, "heading": 0.35, "structure": 0.25}
    if query_signals.query_intent in {"amount_lookup", "duration_lookup", "date_lookup"}:
        return {"body": 0.55, "heading": 0.15, "structure": 0.3}
    if query_signals.query_intent in {"count_lookup", "list_lookup"}:
        return {"body": 0.4, "heading": 0.25, "structure": 0.35}
    if query_signals.query_intent == "comparison":
        return {"body": 0.45, "heading": 0.2, "structure": 0.35}
    if query_signals.query_intent == "eligibility":
        return {"body": 0.5, "heading": 0.15, "structure": 0.35}
    if query_signals.section_reference:
        return {"body": 0.35, "heading": 0.25, "structure": 0.4}
    if query_signals.query_intent == "mention_lookup":
        return {"body": 0.65, "heading": 0.25, "structure": 0.1}
    return {"body": 0.55, "heading": 0.25, "structure": 0.2}


def _normalize_field_scores(scores: list[float]) -> list[float]:
    positive_scores = [score for score in scores if score > 0]
    if not positive_scores:
        return [0.0 for _ in scores]
    max_score = max(positive_scores)
    if max_score <= 0:
        return [0.0 for _ in scores]
    return [score / max_score if score > 0 else 0.0 for score in scores]


def _tokenize_sparse_field(text: str) -> list[str]:
    tokens = tokenize_for_bm25(text)
    return tokens if tokens else ["__empty__"]


def _has_exact_section_heading_match(chunk: ChunkRecord, section_reference: str) -> bool:
    heading_pattern = re.compile(rf"^{re.escape(section_reference)}(?:[.)]|(?:\s*[—:-]))")
    if heading_pattern.match(chunk.normalized_text):
        return True
    return any(heading_pattern.match(heading) for heading in chunk.heading_path)


def build_sparse_index(chunk_records: list[ChunkRecord]) -> SparseIndex:
    search_texts = [build_weighted_search_text(chunk) for chunk in chunk_records]
    body_texts = [build_body_search_text(chunk) for chunk in chunk_records]
    heading_texts = [build_heading_search_text(chunk) for chunk in chunk_records]
    structure_texts = [build_structure_search_text(chunk) for chunk in chunk_records]
    tokenized_corpus = [_tokenize_sparse_field(text) for text in search_texts]
    body_tokenized_corpus = [_tokenize_sparse_field(text) for text in body_texts]
    heading_tokenized_corpus = [_tokenize_sparse_field(text) for text in heading_texts]
    structure_tokenized_corpus = [_tokenize_sparse_field(text) for text in structure_texts]
    bm25 = BM25Okapi(tokenized_corpus)
    body_bm25 = BM25Okapi(body_tokenized_corpus)
    heading_bm25 = BM25Okapi(heading_tokenized_corpus)
    structure_bm25 = BM25Okapi(structure_tokenized_corpus)
    return SparseIndex(
        chunk_records=chunk_records,
        search_texts=search_texts,
        tokenized_corpus=tokenized_corpus,
        bm25=bm25,
        body_texts=body_texts,
        heading_texts=heading_texts,
        structure_texts=structure_texts,
        body_tokenized_corpus=body_tokenized_corpus,
        heading_tokenized_corpus=heading_tokenized_corpus,
        structure_tokenized_corpus=structure_tokenized_corpus,
        body_bm25=body_bm25,
        heading_bm25=heading_bm25,
        structure_bm25=structure_bm25,
    )


def save_sparse_index(index: SparseIndex, output_dir: str | Path = DEFAULT_INDEX_DIR) -> Path:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    chunks_path = output_path / "chunks.jsonl"
    with chunks_path.open("w", encoding="utf-8") as handle:
        for chunk in index.chunk_records:
            handle.write(json.dumps(chunk.model_dump(), ensure_ascii=False) + "\n")
    metadata_path = output_path / "metadata.json"
    metadata = {
        "chunk_count": len(index.chunk_records),
        "index_type": "field_aware_bm25",
        "fields": ["body", "heading", "structure"],
    }
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
    navigation_noise_score = chunk_navigation_noise_score(chunk)
    if navigation_noise_score:
        boosted_score -= navigation_noise_score * 4.0
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
    searchable_terms = set(tokenize_for_bm25(searchable_text))
    informative_terms = extract_informative_query_terms(query_signals.normalized_query, query_signals.query_intent)
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
    if query_signals.query_intent == "rate_lookup":
        if chunk_has_rate_value_language(chunk):
            boosted_score += 1.8
        elif chunk.page_no <= 5 and chunk.chunk_type in {"section", "text"}:
            boosted_score -= 3.2
        searchable_years = set(extract_tax_years(searchable_text))
        marked_years = set(extract_tax_years_near_marker(searchable_text))
        if query_signals.tax_year:
            if marked_years and query_signals.tax_year in marked_years:
                boosted_score += 4.5
            elif marked_years:
                boosted_score -= 5.0
            elif query_signals.tax_year in searchable_years:
                boosted_score += 3.0
            elif searchable_years:
                boosted_score -= 3.5
        normalized_query = query_signals.normalized_query.lower()
        wants_normal_person_rate = any(term in normalized_query for term in ("স্বাভাবিক ব্যক্তি", "স্বাভাবিক ব্যক্তির"))
        if wants_normal_person_rate and "স্বাভাবিক ব্যক্তি" in searchable_text:
            boosted_score += 3.0
        if wants_normal_person_rate and "স্বাভাবিক ব্যক্তি ব্যতীত" in searchable_text:
            boosted_score -= 1.5
        if "সারচাজ" not in normalized_query and "সারচার্জ" not in normalized_query:
            if "সারচাজ" in searchable_text or "সারচার্জ" in searchable_text:
                boosted_score -= 2.5
        if "উৎসে" not in normalized_query and "withholding" not in normalized_query:
            if "উৎসের নাম" in searchable_text or "পরিশোধের বর্ণনা" in searchable_text:
                boosted_score -= 3.0
    informative_overlap = len(informative_terms & searchable_terms)
    if query_signals.query_intent == "eligibility":
        pseudo_hit = _to_retrieval_hit(chunk, boosted_score)
        normalized_query = query_signals.normalized_query.lower()
        if hit_supports_eligibility(pseudo_hit, query_signals):
            boosted_score += 1.9
        else:
            boosted_score -= 1.4
        if any(term in normalized_query for term in ("labour", "labor", "worker")):
            if any(term in searchable_text for term in ("day labourer", "day laborer", "worker")):
                boosted_score += 2.4
            elif any(term in searchable_text for term in ("employee", "employment")):
                boosted_score += 0.8
            else:
                boosted_score -= 0.8
        if any(term in normalized_query for term in ("salary", "salaried", "employee")):
            if any(term in searchable_text for term in ("salary", "employee", "employment", "income from employment")):
                boosted_score += 1.2
            else:
                boosted_score -= 0.9
        if informative_terms:
            boosted_score += min(informative_overlap * 1.1, 3.8)
            if informative_overlap == 0 and all(
                phrase not in searchable_text
                for phrase in ("chargeable to tax", "day labourer", "day laborer", "income from employment", "tax exemption")
            ):
                boosted_score -= 3.0
    if query_signals.query_intent == "amount_lookup":
        pseudo_hit = _to_retrieval_hit(chunk, boosted_score)
        if hit_has_amount_language(pseudo_hit):
            boosted_score += 1.9
        else:
            boosted_score -= 1.5
        if informative_terms:
            boosted_score += min(informative_overlap * 1.2, 4.0)
            if informative_overlap == 0:
                boosted_score -= 3.5
    if query_signals.query_intent == "count_lookup":
        pseudo_hit = _to_retrieval_hit(chunk, boosted_score)
        if hit_looks_list_like(pseudo_hit) or any(token.isdigit() for token in searchable_terms):
            boosted_score += 1.6
        if informative_terms:
            boosted_score += min(informative_overlap * 1.1, 3.5)
            if informative_overlap == 0:
                boosted_score -= 3.2
    if query_signals.query_intent == "duration_lookup":
        pseudo_hit = _to_retrieval_hit(chunk, boosted_score)
        if hit_has_duration_language(pseudo_hit):
            boosted_score += 1.8
        else:
            boosted_score -= 1.4
        if informative_terms:
            boosted_score += min(informative_overlap * 1.2, 4.0)
            if informative_overlap == 0:
                boosted_score -= 3.5
    if query_signals.query_intent == "date_lookup":
        pseudo_hit = _to_retrieval_hit(chunk, boosted_score)
        if hit_has_date_language(pseudo_hit):
            boosted_score += 1.7
        else:
            boosted_score -= 1.3
        if informative_terms:
            boosted_score += min(informative_overlap * 1.1, 3.5)
            if informative_overlap == 0:
                boosted_score -= 3.0
    if query_signals.query_intent == "list_lookup":
        pseudo_hit = _to_retrieval_hit(chunk, boosted_score)
        if hit_looks_list_like(pseudo_hit):
            boosted_score += 1.7
        else:
            boosted_score -= 1.0
        if informative_terms:
            boosted_score += min(informative_overlap * 1.0, 3.0)
            if informative_overlap == 0:
                boosted_score -= 2.8
    if query_signals.query_intent == "comparison":
        pseudo_hit = _to_retrieval_hit(chunk, boosted_score)
        if hit_supports_comparison(pseudo_hit, query_signals):
            boosted_score += 2.4
        else:
            boosted_score -= 2.6
        if informative_terms:
            boosted_score += min(informative_overlap * 1.1, 3.8)
            if informative_overlap == 0:
                boosted_score -= 3.8
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


def _to_retrieval_hit(
    chunk: ChunkRecord,
    score: float,
    *,
    intermediate_scores: dict[str, float | int | str | None] | None = None,
) -> RetrievalHit:
    merged_intermediate_scores: dict[str, float | int | str | None] = {
        "sparse_score": round(score, 6),
        "appendix_id": chunk.appendix_id or "",
        "sro_id": chunk.sro_id or "",
    }
    if intermediate_scores:
        merged_intermediate_scores.update(intermediate_scores)
    return RetrievalHit(
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
        score=round(score, 4),
        intermediate_scores=merged_intermediate_scores,
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
    body_scores = index.body_bm25.get_scores(query_tokens).tolist()
    heading_scores = index.heading_bm25.get_scores(query_tokens).tolist()
    structure_scores = index.structure_bm25.get_scores(query_tokens).tolist()
    normalized_body_scores = _normalize_field_scores(body_scores)
    normalized_heading_scores = _normalize_field_scores(heading_scores)
    normalized_structure_scores = _normalize_field_scores(structure_scores)
    field_weights = _field_score_weights(query_signals)
    scored_hits: list[RetrievalHit] = []
    allowed_chunk_ids = {chunk.chunk_id for chunk in candidate_records}
    for position, chunk in enumerate(index.chunk_records):
        if chunk.chunk_id not in allowed_chunk_ids:
            continue
        base_score = 12.0 * (
            (normalized_body_scores[position] * field_weights["body"])
            + (normalized_heading_scores[position] * field_weights["heading"])
            + (normalized_structure_scores[position] * field_weights["structure"])
        )
        final_score = apply_score_boosts(chunk, query_signals, float(base_score))
        if final_score <= 0:
            continue
        searchable_text = f"{chunk.doc_title} {' '.join(chunk.heading_path)} {chunk.normalized_text}".lower()
        searchable_tokens = set(tokenize_for_bm25(searchable_text))
        salient_overlap = len(salient_terms & searchable_tokens)
        if salient_terms and query_signals.query_intent in {"rate_lookup", "definition", "mention_lookup"} and salient_overlap == 0:
            continue
        informative_terms = extract_informative_query_terms(query_signals.normalized_query, query_signals.query_intent)
        informative_overlap = len(informative_terms & searchable_tokens)
        if informative_terms and query_signals.query_intent == "eligibility" and informative_overlap == 0:
            pseudo_hit = _to_retrieval_hit(chunk, final_score)
            if not hit_supports_eligibility(pseudo_hit, query_signals):
                continue
        elif query_signals.query_intent == "comparison":
            pseudo_hit = _to_retrieval_hit(chunk, final_score)
            if not hit_supports_comparison(pseudo_hit, query_signals):
                continue
        elif informative_terms and query_signals.query_intent in {"amount_lookup", "count_lookup", "duration_lookup", "date_lookup", "list_lookup", "comparison"} and informative_overlap == 0:
            continue
        scored_hits.append(
            _to_retrieval_hit(
                chunk,
                final_score,
                intermediate_scores={
                    "sparse_base_score": round(base_score, 6),
                    "field_body_score": round(body_scores[position], 6),
                    "field_heading_score": round(heading_scores[position], 6),
                    "field_structure_score": round(structure_scores[position], 6),
                    "field_body_weight": field_weights["body"],
                    "field_heading_weight": field_weights["heading"],
                    "field_structure_weight": field_weights["structure"],
                },
            )
        )
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
