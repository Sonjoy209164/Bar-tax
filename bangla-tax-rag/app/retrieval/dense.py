import json
import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np

from app.core.schemas import ChunkRecord, RetrievalHit
from app.core.settings import get_settings
from app.core.utils import ensure_directory
from app.core.utils import extract_definition_target, extract_informative_query_terms, preprocess_query, tokenize_for_bm25
from app.retrieval.filters import (
    authority_value,
    chunk_has_rate_value_language,
    chunk_navigation_noise_score,
    chunk_quality_score,
    filter_chunk_records,
    hit_has_amount_language,
    hit_has_date_language,
    hit_has_duration_language,
    hit_supports_eligibility,
    hit_looks_list_like,
    infer_chunk_tax_year,
)
from app.retrieval.sparse import build_weighted_search_text, load_chunk_records_from_jsonl

logger = logging.getLogger(__name__)

DEFAULT_DENSE_INDEX_DIR = Path("indexes/dense")
DEFAULT_TRANSFORMER_BATCH_SIZE = 8
DEFAULT_TRANSFORMER_MAX_LENGTH = 1024

try:  # pragma: no cover - depends on optional runtime extras
    import faiss
except Exception:  # pragma: no cover - exercised through graceful fallback
    faiss = None

try:  # pragma: no cover - depends on optional runtime extras
    import torch
    import torch.nn.functional as F
    from transformers import AutoModel, AutoTokenizer
except Exception:  # pragma: no cover - exercised through graceful fallback
    torch = None
    F = None
    AutoModel = None
    AutoTokenizer = None


def _resolve_local_hf_snapshot(model_name: str) -> str | None:
    cache_root = Path(os.environ.get("HF_HUB_CACHE", Path.home() / ".cache" / "huggingface" / "hub"))
    model_cache_dir = cache_root / f"models--{model_name.replace('/', '--')}"
    snapshots_dir = model_cache_dir / "snapshots"
    if not snapshots_dir.exists():
        return None
    candidate_snapshots = sorted(path for path in snapshots_dir.iterdir() if path.is_dir())
    if not candidate_snapshots:
        return None
    required_files = ("config.json", "tokenizer.json")
    model_files = ("model.safetensors", "pytorch_model.bin")
    for snapshot_path in reversed(candidate_snapshots):
        if all((snapshot_path / filename).exists() for filename in required_files) and any(
            (snapshot_path / filename).exists() for filename in model_files
        ):
            return str(snapshot_path)
    return None


@lru_cache(maxsize=2)
def _load_embedding_bundle(model_name: str) -> tuple[Any, Any, str]:
    if torch is None or AutoTokenizer is None or AutoModel is None or F is None:
        raise RuntimeError("Transformers embedding dependencies are not installed.")

    local_model_path = _resolve_local_hf_snapshot(model_name)
    try:
        load_target = local_model_path or model_name
        tokenizer = AutoTokenizer.from_pretrained(load_target, local_files_only=True)
        model = AutoModel.from_pretrained(load_target, local_files_only=True)
    except Exception:
        tokenizer = AutoTokenizer.from_pretrained(model_name)
        model = AutoModel.from_pretrained(model_name)
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model.to(device)
    model.eval()
    return tokenizer, model, device


def _mean_pool(last_hidden_state: Any, attention_mask: Any) -> Any:
    mask = attention_mask.unsqueeze(-1).expand(last_hidden_state.size()).float()
    masked_sum = (last_hidden_state * mask).sum(dim=1)
    mask_sum = mask.sum(dim=1).clamp(min=1e-9)
    return masked_sum / mask_sum


def _encode_texts_with_transformers(
    texts: list[str],
    *,
    model_name: str,
    batch_size: int = DEFAULT_TRANSFORMER_BATCH_SIZE,
    max_length: int = DEFAULT_TRANSFORMER_MAX_LENGTH,
) -> np.ndarray:
    if not texts:
        return np.zeros((0, 0), dtype=np.float32)

    tokenizer, model, device = _load_embedding_bundle(model_name)
    batches: list[np.ndarray] = []
    for start in range(0, len(texts), batch_size):
        batch_texts = texts[start : start + batch_size]
        with torch.inference_mode():
            inputs = tokenizer(
                batch_texts,
                padding=True,
                truncation=True,
                max_length=max_length,
                return_tensors="pt",
            )
            inputs = {key: value.to(device) for key, value in inputs.items()}
            outputs = model(**inputs, return_dict=True)
            pooled = _mean_pool(outputs.last_hidden_state, inputs["attention_mask"])
            normalized = F.normalize(pooled, p=2, dim=1)
            batches.append(normalized.cpu().numpy().astype("float32"))
    return np.vstack(batches) if batches else np.zeros((0, 0), dtype=np.float32)


def _save_chunk_records(chunk_records: list[ChunkRecord], output_path: Path) -> None:
    chunks_output_path = output_path / "chunks.jsonl"
    with chunks_output_path.open("w", encoding="utf-8") as handle:
        for chunk in chunk_records:
            handle.write(json.dumps(chunk.model_dump(), ensure_ascii=False) + "\n")


def build_dense_index_artifacts(
    chunk_jsonl_path: str | Path,
    output_dir: str | Path,
    *,
    provider: str | None = None,
    model_name: str | None = None,
    use_faiss: bool | None = None,
) -> tuple[Path, int]:
    settings = get_settings()
    effective_provider = (provider or settings.embedding_provider or "mock").lower()
    effective_model_name = model_name or settings.embedding_model_name
    use_faiss_backend = bool(faiss is not None) if use_faiss is None else use_faiss

    chunk_records = load_chunk_records_from_jsonl(chunk_jsonl_path)
    output_path = ensure_directory(str(output_dir))
    _save_chunk_records(chunk_records, output_path)
    search_texts = [build_weighted_search_text(chunk) for chunk in chunk_records]

    metadata: dict[str, Any] = {
        "status": "ready",
        "chunk_count": len(chunk_records),
        "provider": effective_provider,
        "model_name": effective_model_name,
    }

    if effective_provider in {"", "mock", "overlap"}:
        metadata.update(
            {
                "index_type": "dense_overlap_placeholder",
                "index_backend": "none",
            }
        )
    elif effective_provider == "transformers":
        embeddings = _encode_texts_with_transformers(
            search_texts,
            model_name=effective_model_name,
        )
        np.save(output_path / "embeddings.npy", embeddings)
        metadata.update(
            {
                "index_type": "dense_transformers",
                "index_backend": "numpy",
                "embedding_dim": int(embeddings.shape[1]) if embeddings.size else 0,
                "normalized_embeddings": True,
                "max_length": DEFAULT_TRANSFORMER_MAX_LENGTH,
            }
        )
        if use_faiss_backend and embeddings.size and faiss is not None:
            faiss_index = faiss.IndexFlatIP(int(embeddings.shape[1]))
            faiss_index.add(embeddings.astype("float32"))
            faiss.write_index(faiss_index, str(output_path / "index.faiss"))
            metadata["index_backend"] = "faiss"
    else:
        raise ValueError(f"Unsupported embedding provider: {effective_provider}")

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
        tax_year=infer_chunk_tax_year(chunk),
        original_text=chunk.original_text,
        normalized_text=chunk.normalized_text,
        heading_path=chunk.heading_path,
        content=chunk.original_text,
        score=round(score, 4),
        intermediate_scores={},
    )


def _apply_dense_query_boosts(
    *,
    chunk: ChunkRecord,
    analyzed_query: Any,
    base_score: float,
    similarity_score: float,
) -> RetrievalHit | None:
    weighted_text = " ".join([chunk.doc_title, " ".join(chunk.heading_path), chunk.normalized_text])
    searchable_text = weighted_text.lower()
    chunk_tokens = set(tokenize_for_bm25(weighted_text))
    score = base_score
    score += chunk_quality_score(chunk.normalized_text) * 0.8
    navigation_noise_score = chunk_navigation_noise_score(chunk)
    if navigation_noise_score:
        score -= navigation_noise_score * 3.2
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
        if chunk_has_rate_value_language(chunk):
            score += 1.4
        elif chunk.page_no <= 5 and chunk.chunk_type in {"section", "text"}:
            score -= 2.8
        if any(phrase in searchable_text for phrase in ("করহার", "কর হার", "tax rate", "rate of tax", "tax payable")):
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

    pseudo_hit = _to_retrieval_hit(chunk, score)
    informative_terms = extract_informative_query_terms(analyzed_query.normalized_query, analyzed_query.query_intent)
    informative_overlap = len(informative_terms & chunk_tokens)
    if analyzed_query.query_intent == "eligibility":
        normalized_query = analyzed_query.normalized_query.lower()
        if hit_supports_eligibility(pseudo_hit, analyzed_query):
            score += 1.5
        else:
            score -= 1.2
        if any(term in normalized_query for term in ("labour", "labor", "worker")):
            if any(term in searchable_text for term in ("day labourer", "day laborer", "worker")):
                score += 1.8
            elif any(term in searchable_text for term in ("employee", "employment")):
                score += 0.6
            else:
                score -= 0.7
        if any(term in normalized_query for term in ("salary", "salaried", "employee")):
            if any(term in searchable_text for term in ("salary", "employee", "employment", "income from employment")):
                score += 1.0
            else:
                score -= 0.8
        if informative_terms:
            score += min(informative_overlap * 0.9, 3.0)
            if informative_overlap == 0 and all(
                phrase not in searchable_text
                for phrase in ("chargeable to tax", "day labourer", "day laborer", "income from employment", "tax exemption")
            ):
                score -= 2.8
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
        return None

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
        intermediate_scores={
            "dense_score": round(score, 6),
            "dense_similarity": round(similarity_score, 6),
            "appendix_id": chunk.appendix_id or "",
            "sro_id": chunk.sro_id or "",
        },
    )


def _dense_overlap_search_records(
    *,
    query: str,
    top_k: int,
    tax_year: str | None,
    doc_type: str | None,
    authority_level_min: str | None,
    chunk_type: str | None,
    chunk_records: list[ChunkRecord],
) -> list[dict[str, str | float | int | list[str] | None | dict[str, float | int | None]]]:
    analyzed_query = preprocess_query(query)
    effective_tax_year = tax_year or analyzed_query.tax_year
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
        hit = _apply_dense_query_boosts(
            chunk=chunk,
            analyzed_query=analyzed_query,
            base_score=score,
            similarity_score=score,
        )
        if hit is not None:
            scored_hits.append(hit)
    ranked_hits = sorted(scored_hits, key=lambda hit: hit.score, reverse=True)[:top_k]
    return [hit.model_dump() for hit in ranked_hits]


def _load_dense_embeddings(index_dir: str | Path) -> np.ndarray:
    embeddings_path = Path(index_dir) / "embeddings.npy"
    if not embeddings_path.exists():
        raise FileNotFoundError(f"Dense embeddings not found at {embeddings_path}")
    return np.load(embeddings_path)


@lru_cache(maxsize=4)
def _load_faiss_index(index_path: str) -> Any:
    if faiss is None:
        raise RuntimeError("faiss is not installed.")
    return faiss.read_index(index_path)


def _search_dense_vectors(
    *,
    query_embedding: np.ndarray,
    index_dir: str | Path,
    metadata: dict[str, Any],
    embeddings: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    search_k = embeddings.shape[0]
    if metadata.get("index_backend") == "faiss" and faiss is not None:
        index_path = Path(index_dir) / "index.faiss"
        if index_path.exists():
            faiss_index = _load_faiss_index(str(index_path))
            scores, indices = faiss_index.search(query_embedding.reshape(1, -1).astype("float32"), search_k)
            return scores[0], indices[0]

    similarities = embeddings @ query_embedding.reshape(-1, 1)
    similarities = similarities.reshape(-1)
    indices = np.argsort(-similarities)
    return similarities[indices], indices


def dense_search(
    query: str,
    top_k: int,
    *,
    tax_year: str | None = None,
    doc_type: str | None = None,
    authority_level_min: str | None = None,
    chunk_type: str | None = None,
    index_dir: str | Path = DEFAULT_DENSE_INDEX_DIR,
) -> list[dict[str, str | float | int | list[str] | None | dict[str, float | int | None]]]:
    metadata = load_dense_index_metadata(index_dir)
    chunk_records = load_chunk_records_from_jsonl(Path(index_dir) / "chunks.jsonl")
    if metadata.get("index_type") == "dense_overlap_placeholder":
        return _dense_overlap_search_records(
            query=query,
            top_k=top_k,
            tax_year=tax_year,
            doc_type=doc_type,
            authority_level_min=authority_level_min,
            chunk_type=chunk_type,
            chunk_records=chunk_records,
        )

    if metadata.get("index_type") != "dense_transformers":
        raise ValueError(f"Unsupported dense index type: {metadata.get('index_type')}")

    analyzed_query = preprocess_query(query)
    effective_tax_year = tax_year or analyzed_query.tax_year
    filtered_records = filter_chunk_records(
        chunk_records,
        tax_year=effective_tax_year,
        doc_type=doc_type,
        authority_level_min=authority_level_min,
        chunk_type=chunk_type,
    )
    if not filtered_records:
        return []

    embeddings = _load_dense_embeddings(index_dir)
    query_embedding = _encode_texts_with_transformers(
        [analyzed_query.rewritten_query or analyzed_query.normalized_query],
        model_name=metadata.get("model_name") or get_settings().embedding_model_name,
    )[0]
    similarities, indices = _search_dense_vectors(
        query_embedding=query_embedding,
        index_dir=index_dir,
        metadata=metadata,
        embeddings=embeddings,
    )

    allowed_chunk_ids = {chunk.chunk_id for chunk in filtered_records}
    chunk_by_id = {chunk.chunk_id: chunk for chunk in filtered_records}
    scored_hits: list[RetrievalHit] = []
    for similarity, index_position in zip(similarities.tolist(), indices.tolist(), strict=False):
        if index_position < 0 or index_position >= len(chunk_records):
            continue
        chunk = chunk_records[index_position]
        if chunk.chunk_id not in allowed_chunk_ids:
            continue
        hit = _apply_dense_query_boosts(
            chunk=chunk_by_id[chunk.chunk_id],
            analyzed_query=analyzed_query,
            base_score=float(similarity) * 8.0,
            similarity_score=float(similarity),
        )
        if hit is not None:
            hit.intermediate_scores["dense_backend"] = metadata.get("index_backend", "numpy")
            hit.intermediate_scores["embedding_model_name"] = metadata.get("model_name", "")
            scored_hits.append(hit)
        if len(scored_hits) >= max(top_k * 4, 20):
            break

    ranked_hits = sorted(scored_hits, key=lambda hit: hit.score, reverse=True)[:top_k]
    return [hit.model_dump() for hit in ranked_hits]
