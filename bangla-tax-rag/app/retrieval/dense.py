import json
from pathlib import Path

from app.core.schemas import RetrievalHit
from app.core.utils import ensure_directory
from app.core.utils import preprocess_query, tokenize_for_bm25
from app.retrieval.filters import authority_value, filter_chunk_records
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
    scored_hits: list[RetrievalHit] = []
    for chunk in filtered_records:
        weighted_text = " ".join([chunk.doc_title, " ".join(chunk.heading_path), chunk.normalized_text])
        chunk_tokens = set(tokenize_for_bm25(weighted_text))
        score = _dense_like_score(query_tokens, chunk_tokens, chunk.authority_level)
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
