from app.core.schemas import ChunkRecord, RetrievalHit


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
