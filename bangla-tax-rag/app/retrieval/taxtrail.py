import re
from functools import lru_cache
from pathlib import Path

from app.core.schemas import ChunkRecord, RetrievalHit
from app.core.utils import (
    extract_informative_query_terms,
    extract_salient_query_terms,
    normalize_text,
    preprocess_query,
    tokenize_for_bm25,
)
from app.retrieval.filters import (
    authority_value,
    chunk_has_rate_value_language,
    chunk_matches_tax_year,
    chunk_navigation_noise_score,
    infer_chunk_tax_year,
    looks_like_late_reference_material,
    query_requests_reference_material,
)
from app.retrieval.hybrid import run_hybrid_retrieval
from app.retrieval.sparse import load_chunk_records_from_jsonl


CHUNK_NUMBER_PATTERN = re.compile(r"-c(\d+)$")
NUMBER_PATTERN = re.compile(r"\d+(?:[.,]\d+)*%?")
GUARDED_HYBRID_PREFIX = 4
STRUCTURE_REPLACEMENT_SCORE_FLOOR = 12.0


def _chunk_number(chunk_id: str) -> int:
    match = CHUNK_NUMBER_PATTERN.search(chunk_id)
    return int(match.group(1)) if match else 0


def _heading_signature(value: list[str] | None) -> str:
    if not value:
        return ""
    return normalize_text(value[-1]).lower()


def _chunk_to_hit(chunk: ChunkRecord, *, score: float = 0.0, reason: str = "structure_candidate") -> RetrievalHit:
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
        score=score,
        intermediate_scores={"taxtrail_reason": reason},
    )


def _hit_key(hit: RetrievalHit) -> tuple[int, str]:
    return hit.page_no, hit.chunk_id


class TaxTrailCorpus:
    def __init__(self, chunks: list[ChunkRecord]) -> None:
        self.chunks = chunks
        self.by_id = {chunk.chunk_id: chunk for chunk in chunks}
        self.by_doc_page: dict[tuple[str, int], list[ChunkRecord]] = {}
        self.by_doc_section: dict[tuple[str, str], list[ChunkRecord]] = {}
        self.by_doc_heading: dict[tuple[str, str], list[ChunkRecord]] = {}
        self.by_doc: dict[str, list[ChunkRecord]] = {}
        for chunk in chunks:
            self.by_doc.setdefault(chunk.doc_id, []).append(chunk)
            self.by_doc_page.setdefault((chunk.doc_id, chunk.page_no), []).append(chunk)
            if chunk.section_id:
                self.by_doc_section.setdefault((chunk.doc_id, chunk.section_id), []).append(chunk)
            heading = _heading_signature(chunk.heading_path)
            if heading:
                self.by_doc_heading.setdefault((chunk.doc_id, heading), []).append(chunk)
        for bucket in [*self.by_doc_page.values(), *self.by_doc_section.values(), *self.by_doc_heading.values(), *self.by_doc.values()]:
            bucket.sort(key=lambda item: (item.page_no, _chunk_number(item.chunk_id), item.chunk_id))


@lru_cache(maxsize=8)
def _load_taxtrail_corpus(index_dir: str) -> TaxTrailCorpus:
    return TaxTrailCorpus(load_chunk_records_from_jsonl(Path(index_dir) / "chunks.jsonl"))


def _query_terms(query: str, query_intent: str) -> tuple[set[str], set[str], set[str]]:
    informative_terms = extract_informative_query_terms(query, query_intent)
    salient_terms = extract_salient_query_terms(query)
    query_numbers = set(NUMBER_PATTERN.findall(normalize_text(query)))
    return informative_terms, salient_terms, query_numbers


def _text_terms(chunk: ChunkRecord) -> set[str]:
    return set(tokenize_for_bm25(f"{' '.join(chunk.heading_path)} {chunk.normalized_text}"))


def _overlap_count(chunk: ChunkRecord, terms: set[str]) -> int:
    if not terms:
        return 0
    return len(_text_terms(chunk) & terms)


def _number_overlap(chunk: ChunkRecord, query_numbers: set[str]) -> int:
    if not query_numbers:
        return 0
    chunk_numbers = set(NUMBER_PATTERN.findall(normalize_text(chunk.normalized_text)))
    return len(query_numbers & chunk_numbers)


def _passes_temporal_constraint(chunk: ChunkRecord, tax_year: str | None) -> bool:
    return chunk_matches_tax_year(chunk, tax_year)


def _candidate_reason_score(
    *,
    chunk: ChunkRecord,
    anchor: RetrievalHit,
    reason: str,
    informative_terms: set[str],
    salient_terms: set[str],
    query_numbers: set[str],
    query_intent: str,
    query_text: str,
    base_rank: int,
) -> float:
    score = 4.5 / max(base_rank, 1)
    if chunk.chunk_id == anchor.chunk_id:
        score += 4.0
    if chunk.doc_id == anchor.doc_id:
        score += 0.6
    page_distance = abs(chunk.page_no - anchor.page_no)
    if page_distance == 0:
        score += 1.1
    elif page_distance == 1:
        score += 0.65
    if chunk.section_id and chunk.section_id == anchor.section_id:
        score += 0.9
    if _heading_signature(chunk.heading_path) and _heading_signature(chunk.heading_path) == _heading_signature(anchor.heading_path):
        score += 0.75

    informative_overlap = _overlap_count(chunk, informative_terms)
    salient_overlap = _overlap_count(chunk, salient_terms)
    numeric_overlap = _number_overlap(chunk, query_numbers)
    score += informative_overlap * 0.42
    score += salient_overlap * 0.25
    score += numeric_overlap * 0.55

    if query_intent == "rate_lookup" and chunk_has_rate_value_language(chunk):
        score += 0.9
    if query_intent == "definition" and any(term in chunk.normalized_text for term in ("সংজ্ঞা", "অর্থ", "means")):
        score += 0.55
    if query_intent in {"procedure", "eligibility"} and any(term in chunk.normalized_text for term in ("শর্ত", "দাখিল", "পরিশোধ", "প্রযোজ্য", "কর্তন")):
        score += 0.45
    if query_intent == "calculation" and numeric_overlap:
        score += 0.5

    if reason == "doc_term_fallback":
        score += 0.35
    if reason == "same_page":
        score += 0.25
    if reason == "same_section":
        score += 0.45

    score += authority_value(chunk.authority_level) * 0.05
    score -= chunk_navigation_noise_score(chunk) * 1.4
    if not query_requests_reference_material(query_text) and looks_like_late_reference_material(
        doc_title=chunk.doc_title,
        page_no=chunk.page_no,
        heading_path=chunk.heading_path,
        normalized_text=chunk.normalized_text,
        chunk_type=chunk.chunk_type,
        appendix_id=chunk.appendix_id,
    ):
        score -= 0.55
    return score


def _add_candidate(
    candidates: dict[str, tuple[ChunkRecord, RetrievalHit, str, int]],
    chunk: ChunkRecord,
    anchor: RetrievalHit,
    reason: str,
    rank: int,
    tax_year: str | None,
) -> None:
    if not _passes_temporal_constraint(chunk, tax_year):
        return
    current = candidates.get(chunk.chunk_id)
    if current is None or rank < current[3]:
        candidates[chunk.chunk_id] = (chunk, anchor, reason, rank)


def _expand_candidates(
    corpus: TaxTrailCorpus,
    base_hits: list[RetrievalHit],
    *,
    tax_year: str | None,
    query_text: str,
    query_intent: str,
) -> dict[str, tuple[ChunkRecord, RetrievalHit, str, int]]:
    candidates: dict[str, tuple[ChunkRecord, RetrievalHit, str, int]] = {}
    informative_terms, salient_terms, query_numbers = _query_terms(query_text, query_intent)
    term_floor = 2 if query_intent in {"definition", "procedure", "rate_lookup"} else 1

    for rank, anchor in enumerate(base_hits, start=1):
        anchor_chunk = corpus.by_id.get(anchor.chunk_id)
        if anchor_chunk:
            _add_candidate(candidates, anchor_chunk, anchor, "hybrid_seed", rank, tax_year)

        anchor_number = _chunk_number(anchor.chunk_id)
        for page_no in range(anchor.page_no - 1, anchor.page_no + 2):
            for chunk in corpus.by_doc_page.get((anchor.doc_id, page_no), []):
                if page_no == anchor.page_no and abs(_chunk_number(chunk.chunk_id) - anchor_number) > 4:
                    continue
                reason = "same_page" if page_no == anchor.page_no else "adjacent_page"
                _add_candidate(candidates, chunk, anchor, reason, rank, tax_year)

        if anchor.section_id:
            for chunk in corpus.by_doc_section.get((anchor.doc_id, anchor.section_id), [])[:40]:
                _add_candidate(candidates, chunk, anchor, "same_section", rank, tax_year)

        heading = _heading_signature(anchor.heading_path)
        if heading:
            for chunk in corpus.by_doc_heading.get((anchor.doc_id, heading), [])[:30]:
                _add_candidate(candidates, chunk, anchor, "same_heading", rank, tax_year)

        doc_candidates = []
        for chunk in corpus.by_doc.get(anchor.doc_id, []):
            if not _passes_temporal_constraint(chunk, tax_year):
                continue
            informative_overlap = _overlap_count(chunk, informative_terms)
            salient_overlap = _overlap_count(chunk, salient_terms)
            numeric_overlap = _number_overlap(chunk, query_numbers)
            if informative_overlap >= term_floor or (informative_overlap >= 1 and numeric_overlap >= 1):
                doc_candidates.append((informative_overlap, salient_overlap, numeric_overlap, chunk))
        doc_candidates.sort(key=lambda item: (-item[0], -item[1], -item[2], item[3].page_no, item[3].chunk_id))
        for _, _, _, chunk in doc_candidates[:25]:
            _add_candidate(candidates, chunk, anchor, "doc_term_fallback", rank, tax_year)

    return candidates


def taxtrail_search(
    query: str,
    top_k: int = 5,
    *,
    index_dir: str | Path,
    dense_index_dir: str | Path,
    tax_year: str | None = None,
) -> list[RetrievalHit]:
    analyzed_query = preprocess_query(query)
    effective_tax_year = tax_year or analyzed_query.tax_year
    candidate_k = max(top_k * 4, 20)
    hybrid_response = run_hybrid_retrieval(
        query=query,
        sparse_top_k=max(top_k * 10, 50),
        dense_top_k=max(top_k * 10, 50),
        final_top_k=candidate_k,
        tax_year=effective_tax_year,
        index_dir=index_dir,
        dense_index_dir=dense_index_dir,
    )
    corpus = _load_taxtrail_corpus(str(index_dir))
    base_hits = [
        hit
        for hit in hybrid_response.final_hits
        if (chunk := corpus.by_id.get(hit.chunk_id)) is None
        or _passes_temporal_constraint(chunk, effective_tax_year)
    ]
    candidates = _expand_candidates(
        corpus,
        base_hits,
        tax_year=effective_tax_year,
        query_text=query,
        query_intent=str(analyzed_query.query_intent),
    )
    informative_terms, salient_terms, query_numbers = _query_terms(query, str(analyzed_query.query_intent))
    scored_hits: list[RetrievalHit] = []
    for chunk, anchor, reason, rank in candidates.values():
        score = _candidate_reason_score(
            chunk=chunk,
            anchor=anchor,
            reason=reason,
            informative_terms=informative_terms,
            salient_terms=salient_terms,
            query_numbers=query_numbers,
            query_intent=str(analyzed_query.query_intent),
            query_text=query,
            base_rank=rank,
        )
        hit = _chunk_to_hit(chunk, score=score, reason=reason)
        hit.intermediate_scores.update(
            {
                "anchor_chunk_id": anchor.chunk_id,
                "anchor_rank": rank,
                "informative_overlap": _overlap_count(chunk, informative_terms),
                "salient_overlap": _overlap_count(chunk, salient_terms),
                "numeric_overlap": _number_overlap(chunk, query_numbers),
            }
        )
        scored_hits.append(hit)

    scored_hits.sort(key=lambda hit: (-hit.score, _hit_key(hit)))
    if top_k <= GUARDED_HYBRID_PREFIX:
        return base_hits[:top_k]

    guarded_hits = list(base_hits[:GUARDED_HYBRID_PREFIX])
    seen_chunk_ids = {hit.chunk_id for hit in guarded_hits}

    for hit in scored_hits:
        if len(guarded_hits) >= top_k:
            break
        if hit.chunk_id in seen_chunk_ids:
            continue
        if len(base_hits) >= top_k and hit.score < STRUCTURE_REPLACEMENT_SCORE_FLOOR:
            continue
        guarded_hits.append(hit)
        seen_chunk_ids.add(hit.chunk_id)

    for hit in base_hits[GUARDED_HYBRID_PREFIX:]:
        if len(guarded_hits) >= top_k:
            break
        if hit.chunk_id in seen_chunk_ids:
            continue
        guarded_hits.append(hit)
        seen_chunk_ids.add(hit.chunk_id)

    return guarded_hits[:top_k]
