from __future__ import annotations

import json
import sys
from typing import Any
from pathlib import Path
from collections import defaultdict

import requests
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.core.settings import get_settings

try:
    import fitz
except Exception:  # pragma: no cover - optional UI dependency
    fitz = None

try:  # pragma: no cover - optional inspection dependency
    import numpy as np
except Exception:  # pragma: no cover - defensive UI fallback
    np = None

try:  # pragma: no cover - optional inspection dependency
    import faiss
except Exception:  # pragma: no cover - defensive UI fallback
    faiss = None

REQUEST_TIMEOUT_SECONDS = 30
INGEST_TIMEOUT_SECONDS = 300
INDEX_BUILD_TIMEOUT_SECONDS = 120
QUERY_TIMEOUT_SECONDS = 90
OLLAMA_GENERATOR_MODEL_PRESETS = [
    "deepseek-r1:7b",
    "llama3.1:8b",
    "gemma2:9b",
    "mixtral:8x7b",
    "Custom...",
]
GENERATION_TEST_QUESTIONS = [
    "What are the income tax authorities under section 4?",
    "What is the definition of Commissioner?",
    "What does section 32 say about income from employment?",
    "Is software service mentioned in the Act?",
    "What does the Act say about software test lab service?",
    "What is the tax day for a company?",
    "I am a labour, what will be my tax?",
]
COMPARISON_TEST_QUESTIONS = [
    "What is the definition of Commissioner?",
    "What are the income tax authorities under section 4?",
    "What is the tax day for a company?",
    "Is software service mentioned in the Act?",
    "What does the Act say about software test lab service?",
    "For how many successive assessment years can startup losses be carried forward?",
    "I am a labour, what will be my tax?",
]
COMPARISON_REFERENCE_CASES = [
    {
        "category": "What",
        "question": "What is the definition of Commissioner?",
        "expected": "“Commissioner” means Commissioner of Taxes or Commissioner of Taxes (Large Assessee Unit), as referred to in section 4.",
        "source": "income-tax-act-2023.jsonl (line 14)",
    },
    {
        "category": "What",
        "question": "What is the Tax Day for a company?",
        "expected": "The 15th day of the seventh month following the end of the income year, or 15 September if that date falls earlier.",
        "source": "income-tax-act-2023.jsonl (line 17)",
    },
    {
        "category": "What",
        "question": "What is the threshold amount in the charitable purpose clause for services in exchange for consideration?",
        "expected": "Taka 1(one) crore.",
        "source": "income-tax-act-2023.jsonl (line 27), income-tax-act-2023.jsonl (line 28)",
    },
    {
        "category": "What",
        "question": "What tax rate applies to stock dividend under section 23?",
        "expected": "10% (ten percent).",
        "source": "income-tax-act-2023.jsonl (line 85)",
    },
    {
        "category": "What",
        "question": "What is the minimum tax rate for growth years of a registered startup?",
        "expected": "0.1% (zero point one percent).",
        "source": "income-tax-act-2023.jsonl (line 1078)",
    },
    {
        "category": "What",
        "question": "What does the Act say about software test lab service?",
        "expected": "It is explicitly listed among software-related services, along with website development/service and IT assistance/software maintenance service.",
        "source": "income-tax-act-2023.jsonl (line 1023)",
    },
    {
        "category": "How",
        "question": "How many classes of income tax authorities are listed under section 4?",
        "expected": "15 classes, from (a) to (o).",
        "source": "income-tax-act-2023.jsonl (line 56), income-tax-act-2023.jsonl (line 57), income-tax-act-2023.jsonl (line 58)",
    },
    {
        "category": "How",
        "question": "How many successive assessment years can startup losses be carried forward?",
        "expected": "9 successive assessment years.",
        "source": "income-tax-act-2023.jsonl (line 1077)",
    },
    {
        "category": "How",
        "question": "How many days make an individual a resident under clause 45?",
        "expected": "183 days, or 90 days with the prior-presence condition.",
        "source": "income-tax-act-2023.jsonl (line 28)",
    },
    {
        "category": "How",
        "question": "How many growth years are given to startups incorporated on or after July 1, 2023?",
        "expected": "5 years from the year of incorporation.",
        "source": "income-tax-act-2023.jsonl (line 1082)",
    },
    {
        "category": "Comparison",
        "question": "Compare the Tax Day for a company and for an assessee other than a company.",
        "expected": "Company: 15th day of the seventh month, or 15 September if earlier. Other than company: 30 November.",
        "source": "income-tax-act-2023.jsonl (line 17)",
    },
    {
        "category": "Comparison",
        "question": "Compare startup growth years for startups incorporated between July 1, 2017 and June 30, 2023 versus startups incorporated on or after July 1, 2023.",
        "expected": "Earlier group: 3 years from July 1, 2023 to June 30, 2027. Later group: 5 years from the year of incorporation.",
        "source": "income-tax-act-2023.jsonl (line 1082)",
    },
    {
        "category": "Comparison",
        "question": "Compare the tax treatment of dividend income for a company and for a person other than a company.",
        "expected": "Company: 20%. Other than a company: included in total income and taxed at the applicable rate.",
        "source": "income-tax-act-2023.jsonl (line 1051)",
    },
    {
        "category": "Reasoning-Style",
        "question": "Why would an organization fail to qualify as charitable purpose under clause 43 in the services-for-consideration case?",
        "expected": "Because improvement or advancement of general public utility is not treated as charitable purpose if it renders services for consideration and the aggregate value exceeds Taka 1(one) crore, and it also requires approval by the Commissioner of Taxes.",
        "source": "income-tax-act-2023.jsonl (line 27), income-tax-act-2023.jsonl (line 28)",
    },
    {
        "category": "Reasoning-Style",
        "question": "Why is a startup incorporated before July 1, 2017 not eligible for sandbox registration?",
        "expected": "Because the Act expressly says a startup is not eligible if it was incorporated prior to the first day of July 2017.",
        "source": "income-tax-act-2023.jsonl (line 1081)",
    },
    {
        "category": "Reasoning-Style",
        "question": "Why can software-related businesses under the listed exemption not freely use cash transactions after July 1, 2024?",
        "expected": "Because the Act requires all income, expenditure, and investment of that business to be performed wholly through bank transfer from July 1, 2024.",
        "source": "income-tax-act-2023.jsonl (line 1023)",
    },
    {
        "category": "Eligibility",
        "question": "I am a labour, what will be my tax?",
        "expected": "A careful answer should not guess a personal tax number. It should explain that the Act does not let us compute an exact tax from occupation alone, that a day labourer is excluded from the definition of employee, and that tax still depends on whether income is chargeable to tax under the Act.",
        "source": "income-tax-act-2023.jsonl (line 19), income-tax-act-2023.jsonl (line 11), income-tax-act-2023.jsonl (line 16)",
    },
]
COMPARISON_BEST_FIRST_QUESTIONS = [
    "What is the definition of Commissioner?",
    "How many classes of income tax authorities are listed under section 4?",
    "Compare the Tax Day for a company and for an assessee other than a company.",
    "Why would an organization fail to qualify as charitable purpose under clause 43 in the services-for-consideration case?",
    "I am a labour, what will be my tax?",
]
UI_PIPELINE_MODES = ["agentic", "legacy"]
AGENTIC_QUERY_TYPE_OPTIONS = [
    "auto",
    "general",
    "section_lookup",
    "definition",
    "table_lookup",
    "rate_lookup",
    "amount_lookup",
    "date_lookup",
    "duration_lookup",
    "count_lookup",
    "list_lookup",
    "mention_lookup",
    "comparison",
    "scenario_reasoning",
    "cross_section_reasoning",
    "eligibility",
    "amendment",
    "example",
    "procedure",
    "calculation",
    "unsupported_or_underspecified",
]


def initialize_session_state() -> None:
    settings = get_settings()
    defaults: dict[str, Any] = {
        "ui_pipeline_mode": "agentic",
        "backend_base_url": settings.ui_backend_base_url,
        "last_query_response": None,
        "last_ingest_response": None,
        "last_build_index_response": None,
        "last_trace_response": None,
        "last_retrieval_inspector_response": None,
        "last_comparison_responses": None,
        "question_preset": GENERATION_TEST_QUESTIONS[0],
        "comparison_question_preset": COMPARISON_TEST_QUESTIONS[0],
        "question_text": "২০২৫-২০২৬ করবর্ষে কোম্পানির করহার কী?",
        "comparison_question_text": COMPARISON_TEST_QUESTIONS[0],
        "retrieval_mode": settings.retrieval_mode,
        "agentic_query_type": "auto",
        "agentic_max_reasoning_steps": 6,
        "tax_year": "",
        "top_k": settings.top_k,
        "final_evidence_k": settings.final_evidence_k,
        "include_intermediate_hits": False,
        "generate_answer": True,
        "comparison_generate_answer": True,
        "query_generator_model_preset": settings.generator_model_name if settings.generator_model_name in OLLAMA_GENERATOR_MODEL_PRESETS else "Custom...",
        "query_custom_generator_model": settings.generator_model_name if settings.generator_model_name not in OLLAMA_GENERATOR_MODEL_PRESETS else "",
        "comparison_generator_model_preset": settings.generator_model_name if settings.generator_model_name in OLLAMA_GENERATOR_MODEL_PRESETS else "Custom...",
        "comparison_custom_generator_model": settings.generator_model_name if settings.generator_model_name not in OLLAMA_GENERATOR_MODEL_PRESETS else "",
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


def resolve_selected_generator_model(*, preset_key: str, custom_key: str) -> str | None:
    preset_value = st.session_state.get(preset_key)
    if preset_value == "Custom...":
        custom_value = str(st.session_state.get(custom_key) or "").strip()
        return custom_value or None
    return str(preset_value).strip() or None


def load_chunk_records(chunk_jsonl_path: str, *, max_chunks: int = 100) -> tuple[list[dict[str, Any]], str | None]:
    path = Path(chunk_jsonl_path)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    if not path.exists():
        return [], f"Chunk file not found: {path}"

    chunk_records: list[dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8") as chunk_file:
            for line_number, line in enumerate(chunk_file, start=1):
                stripped_line = line.strip()
                if not stripped_line:
                    continue
                try:
                    chunk_records.append(json.loads(stripped_line))
                except json.JSONDecodeError as exc:
                    return [], f"Invalid JSONL at line {line_number}: {exc}"
                if len(chunk_records) >= max_chunks:
                    break
    except OSError as exc:
        return [], str(exc)
    return chunk_records, None


@st.cache_data(show_spinner=False)
def load_index_artifacts(
    index_dir: str,
    *,
    max_chunks: int = 100,
) -> tuple[dict[str, Any], list[dict[str, Any]], str | None]:
    path = Path(index_dir)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    if not path.exists():
        return {}, [], f"Index directory not found: {path}"
    metadata_path = path / "metadata.json"
    chunks_path = path / "chunks.jsonl"
    if not chunks_path.exists():
        return {}, [], f"Index chunks file not found: {chunks_path}"

    metadata: dict[str, Any] = {}
    if metadata_path.exists():
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            return {}, [], f"Invalid metadata.json: {exc}"

    chunk_records, error_message = load_chunk_records(str(chunks_path), max_chunks=max_chunks)
    if error_message:
        return {}, [], error_message
    return metadata, chunk_records, None


@st.cache_data(show_spinner=False)
def load_dense_index_artifacts(
    index_dir: str,
    *,
    max_chunks: int = 100,
    vector_preview_dims: int = 12,
) -> tuple[dict[str, Any], list[dict[str, Any]], str | None]:
    path = Path(index_dir)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    if not path.exists():
        return {}, [], f"Dense index directory not found: {path}"

    metadata_path = path / "metadata.json"
    chunks_path = path / "chunks.jsonl"
    embeddings_path = path / "embeddings.npy"
    faiss_path = path / "index.faiss"

    metadata: dict[str, Any] = {}
    if metadata_path.exists():
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            return {}, [], f"Invalid metadata.json: {exc}"

    chunk_records, error_message = load_chunk_records(str(chunks_path), max_chunks=max_chunks)
    if error_message:
        return {}, [], error_message

    summary: dict[str, Any] = {
        "index_dir": str(path),
        "metadata": metadata,
        "files": {
            "metadata_json": metadata_path.exists(),
            "chunks_jsonl": chunks_path.exists(),
            "embeddings_npy": embeddings_path.exists(),
            "index_faiss": faiss_path.exists(),
        },
    }

    if embeddings_path.exists():
        if np is None:
            summary["embedding_error"] = "numpy is not available for embedding inspection."
        else:
            try:
                embeddings = np.load(embeddings_path, mmap_mode="r")
                sample_count = min(10, int(embeddings.shape[0]))
                sample_norms = (
                    np.linalg.norm(np.asarray(embeddings[:sample_count]), axis=1).round(6).tolist()
                    if sample_count
                    else []
                )
                summary["embedding_matrix"] = {
                    "shape": [int(dim) for dim in embeddings.shape],
                    "dtype": str(embeddings.dtype),
                    "sample_vector_preview": (
                        np.asarray(embeddings[0][:vector_preview_dims]).round(6).tolist()
                        if embeddings.shape[0]
                        else []
                    ),
                    "sample_norms": sample_norms,
                }
            except Exception as exc:  # pragma: no cover - defensive UI handling
                summary["embedding_error"] = str(exc)

    if faiss_path.exists():
        if faiss is None:
            summary["faiss_error"] = "faiss is not available for index inspection."
        else:
            try:
                faiss_index = faiss.read_index(str(faiss_path))
                summary["faiss_index"] = {
                    "type": type(faiss_index).__name__,
                    "ntotal": int(faiss_index.ntotal),
                    "dimension": int(faiss_index.d),
                }
            except Exception as exc:  # pragma: no cover - defensive UI handling
                summary["faiss_error"] = str(exc)

    inferred_provider = metadata.get("provider") or "unknown"
    inferred_backend = metadata.get("index_backend") or "unknown"
    inferred_type = metadata.get("index_type") or "unknown"
    if embeddings_path.exists():
        inferred_provider = "transformers"
        inferred_type = "dense_transformers"
        inferred_backend = "faiss" if faiss_path.exists() else "numpy"
    summary["inferred_runtime"] = {
        "provider": inferred_provider,
        "index_type": inferred_type,
        "index_backend": inferred_backend,
    }
    summary["metadata_mismatch"] = bool(
        embeddings_path.exists() and metadata.get("index_type") == "dense_overlap_placeholder"
    )
    return summary, chunk_records, None


@st.cache_data(show_spinner=False)
def load_dense_vector_neighbors(
    index_dir: str,
    *,
    vector_index: int,
    top_k: int = 5,
) -> tuple[list[dict[str, Any]], str | None]:
    if np is None:
        return [], "numpy is not available for dense vector inspection."
    path = Path(index_dir)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    embeddings_path = path / "embeddings.npy"
    chunks_path = path / "chunks.jsonl"
    if not embeddings_path.exists():
        return [], f"Embeddings file not found: {embeddings_path}"
    if not chunks_path.exists():
        return [], f"Chunk file not found: {chunks_path}"

    embeddings = np.load(embeddings_path)
    if vector_index < 0 or vector_index >= embeddings.shape[0]:
        return [], f"Vector index {vector_index} is out of range."

    chunk_records = load_chunk_records(str(chunks_path), max_chunks=max(int(embeddings.shape[0]), 1))[0]
    anchor = embeddings[vector_index]
    similarities = embeddings @ anchor
    ranked_indices = np.argsort(-similarities)[:top_k]

    neighbors: list[dict[str, Any]] = []
    for neighbor_index in ranked_indices.tolist():
        chunk = chunk_records[neighbor_index] if neighbor_index < len(chunk_records) else {}
        neighbors.append(
            {
                "vector_index": int(neighbor_index),
                "similarity": float(similarities[neighbor_index]),
                "chunk_id": chunk.get("chunk_id"),
                "page_no": chunk.get("page_no"),
                "section_id": chunk.get("section_id"),
                "subsection_id": chunk.get("subsection_id"),
                "chunk_type": chunk.get("chunk_type"),
                "heading_path": chunk.get("heading_path") or [],
                "original_text": chunk.get("original_text") or "",
            }
        )
    return neighbors, None


@st.cache_data(show_spinner=False)
def load_dense_vector_slice(
    index_dir: str,
    *,
    vector_index: int,
    dim_start: int = 0,
    dim_count: int = 32,
    compare_indices: tuple[int, ...] = (),
) -> tuple[dict[str, Any], str | None]:
    if np is None:
        return {}, "numpy is not available for embedding inspection."
    path = Path(index_dir)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    embeddings_path = path / "embeddings.npy"
    if not embeddings_path.exists():
        return {}, f"Embeddings file not found: {embeddings_path}"

    embeddings = np.load(embeddings_path)
    if vector_index < 0 or vector_index >= embeddings.shape[0]:
        return {}, f"Vector index {vector_index} is out of range."

    total_dims = int(embeddings.shape[1]) if embeddings.ndim > 1 else 0
    safe_start = max(0, min(int(dim_start), max(total_dims - 1, 0)))
    safe_count = max(1, min(int(dim_count), max(total_dims - safe_start, 1)))
    safe_end = min(safe_start + safe_count, total_dims)

    selected_vector = np.asarray(embeddings[vector_index], dtype=np.float32)
    compare_vectors: dict[int, np.ndarray] = {}
    for neighbor_index in compare_indices:
        if 0 <= int(neighbor_index) < embeddings.shape[0]:
            compare_vectors[int(neighbor_index)] = np.asarray(embeddings[int(neighbor_index)], dtype=np.float32)

    rows: list[dict[str, Any]] = []
    for dim_index in range(safe_start, safe_end):
        row = {
            "dim": int(dim_index),
            "selected": round(float(selected_vector[dim_index]), 6),
        }
        for neighbor_index, neighbor_vector in compare_vectors.items():
            row[f"neighbor_{neighbor_index}"] = round(float(neighbor_vector[dim_index]), 6)
            row[f"delta_{neighbor_index}"] = round(
                float(selected_vector[dim_index] - neighbor_vector[dim_index]),
                6,
            )
        rows.append(row)

    stats = {
        "vector_index": int(vector_index),
        "dimension_count": total_dims,
        "slice_start": safe_start,
        "slice_end_exclusive": safe_end,
        "min": round(float(selected_vector.min()), 6),
        "max": round(float(selected_vector.max()), 6),
        "mean": round(float(selected_vector.mean()), 6),
        "std": round(float(selected_vector.std()), 6),
        "norm": round(float(np.linalg.norm(selected_vector)), 6),
    }
    return {"stats": stats, "rows": rows}, None


@st.cache_data(show_spinner=False)
def load_dense_similarity_matrix(
    index_dir: str,
    *,
    vector_indices: tuple[int, ...],
) -> tuple[dict[str, Any], str | None]:
    if np is None:
        return {}, "numpy is not available for similarity inspection."
    path = Path(index_dir)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    embeddings_path = path / "embeddings.npy"
    chunks_path = path / "chunks.jsonl"
    if not embeddings_path.exists():
        return {}, f"Embeddings file not found: {embeddings_path}"
    if not chunks_path.exists():
        return {}, f"Chunk file not found: {chunks_path}"

    embeddings = np.load(embeddings_path)
    chunk_records = load_chunk_records(str(chunks_path), max_chunks=max(int(embeddings.shape[0]), 1))[0]

    valid_indices = [index for index in vector_indices if 0 <= int(index) < embeddings.shape[0]]
    if not valid_indices:
        return {}, "No valid vector indices were supplied."

    selected = np.asarray(embeddings[valid_indices], dtype=np.float32)
    similarities = selected @ selected.T

    labels: dict[int, str] = {}
    for index in valid_indices:
        chunk = chunk_records[index] if index < len(chunk_records) else {}
        labels[index] = (
            f"{index} | p.{chunk.get('page_no', '-')}"
            f" | {(chunk.get('heading_path') or ['-'])[-1]}"
        )

    rows: list[dict[str, Any]] = []
    for source_offset, source_index in enumerate(valid_indices):
        for target_offset, target_index in enumerate(valid_indices):
            rows.append(
                {
                    "source": labels[source_index],
                    "target": labels[target_index],
                    "similarity": round(float(similarities[source_offset, target_offset]), 6),
                }
            )

    return {"rows": rows, "labels": labels, "size": len(valid_indices)}, None


@st.cache_data(show_spinner=False)
def load_dense_projection(
    index_dir: str,
    *,
    focus_indices: tuple[int, ...] = (),
    max_points: int = 250,
) -> tuple[list[dict[str, Any]], str | None]:
    if np is None:
        return [], "numpy is not available for projection inspection."
    path = Path(index_dir)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    embeddings_path = path / "embeddings.npy"
    chunks_path = path / "chunks.jsonl"
    if not embeddings_path.exists():
        return [], f"Embeddings file not found: {embeddings_path}"
    if not chunks_path.exists():
        return [], f"Chunk file not found: {chunks_path}"

    embeddings = np.load(embeddings_path)
    total_vectors = int(embeddings.shape[0])
    if total_vectors == 0:
        return [], None

    if total_vectors <= max_points:
        sampled_indices = list(range(total_vectors))
    else:
        sampled_indices = np.linspace(0, total_vectors - 1, num=max_points, dtype=int).tolist()

    for focus_index in focus_indices:
        if 0 <= int(focus_index) < total_vectors:
            sampled_indices.append(int(focus_index))

    sampled_indices = sorted(set(sampled_indices))
    sampled_embeddings = np.asarray(embeddings[sampled_indices], dtype=np.float32)
    centered = sampled_embeddings - sampled_embeddings.mean(axis=0, keepdims=True)

    if centered.shape[1] >= 2:
        _, _, vt = np.linalg.svd(centered, full_matrices=False)
        components = vt[:2]
        coords = centered @ components.T
    elif centered.shape[1] == 1:
        coords = np.hstack([centered, np.zeros((centered.shape[0], 1), dtype=np.float32)])
    else:
        coords = np.zeros((centered.shape[0], 2), dtype=np.float32)

    chunk_records = load_chunk_records(str(chunks_path), max_chunks=max(total_vectors, 1))[0]
    focus_set = {int(index) for index in focus_indices}
    points: list[dict[str, Any]] = []
    for row_offset, vector_index in enumerate(sampled_indices):
        chunk = chunk_records[vector_index] if vector_index < len(chunk_records) else {}
        role = "focus" if vector_index in focus_set else "sample"
        points.append(
            {
                "vector_index": int(vector_index),
                "x": round(float(coords[row_offset, 0]), 6),
                "y": round(float(coords[row_offset, 1]), 6),
                "role": role,
                "chunk_id": chunk.get("chunk_id"),
                "page_no": chunk.get("page_no"),
                "section_id": chunk.get("section_id"),
                "heading": (chunk.get("heading_path") or ["-"])[-1],
            }
        )
    return points, None


@st.cache_data(show_spinner=False)
def load_query_embedding_comparison(
    index_dir: str,
    *,
    query_text: str,
    compare_indices: tuple[int, ...],
    dim_start: int = 0,
    dim_count: int = 24,
    top_k: int = 5,
) -> tuple[dict[str, Any], str | None]:
    if np is None:
        return {}, "numpy is not available for query embedding inspection."
    if not query_text.strip():
        return {}, None

    path = Path(index_dir)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    metadata_path = path / "metadata.json"
    chunks_path = path / "chunks.jsonl"
    embeddings_path = path / "embeddings.npy"
    if not metadata_path.exists():
        return {}, f"Dense metadata not found: {metadata_path}"
    if not chunks_path.exists():
        return {}, f"Chunk file not found: {chunks_path}"
    if not embeddings_path.exists():
        return {}, f"Embeddings file not found: {embeddings_path}"

    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    if metadata.get("index_type") != "dense_transformers":
        return {}, "Query embedding comparison requires a real transformers-based dense index."

    from app.retrieval.dense import (
        _encode_texts_with_transformers,
        _search_dense_vectors,
        load_dense_index_metadata,
    )

    dense_metadata = load_dense_index_metadata(path)
    embeddings = np.load(embeddings_path)
    chunk_records = load_chunk_records(str(chunks_path), max_chunks=max(int(embeddings.shape[0]), 1))[0]

    query_vector = _encode_texts_with_transformers(
        [query_text],
        model_name=dense_metadata.get("model_name") or get_settings().embedding_model_name,
    )[0]
    scores, indices = _search_dense_vectors(
        query_embedding=query_vector,
        index_dir=path,
        metadata=dense_metadata,
        embeddings=embeddings,
    )

    total_dims = int(query_vector.shape[0]) if query_vector.ndim == 1 else 0
    safe_start = max(0, min(int(dim_start), max(total_dims - 1, 0)))
    safe_count = max(1, min(int(dim_count), max(total_dims - safe_start, 1)))
    safe_end = min(safe_start + safe_count, total_dims)

    compare_vectors: dict[int, np.ndarray] = {}
    for vector_index in compare_indices:
        if 0 <= int(vector_index) < embeddings.shape[0]:
            compare_vectors[int(vector_index)] = np.asarray(embeddings[int(vector_index)], dtype=np.float32)

    rows: list[dict[str, Any]] = []
    for dim_index in range(safe_start, safe_end):
        row = {
            "dim": int(dim_index),
            "query": round(float(query_vector[dim_index]), 6),
        }
        for vector_index, vector in compare_vectors.items():
            row[f"chunk_{vector_index}"] = round(float(vector[dim_index]), 6)
            row[f"delta_{vector_index}"] = round(float(query_vector[dim_index] - vector[dim_index]), 6)
        rows.append(row)

    nearest_hits: list[dict[str, Any]] = []
    for similarity, vector_index in zip(scores.tolist()[:top_k], indices.tolist()[:top_k], strict=False):
        if vector_index < 0 or vector_index >= len(chunk_records):
            continue
        chunk = chunk_records[vector_index]
        nearest_hits.append(
            {
                "vector_index": int(vector_index),
                "similarity": round(float(similarity), 6),
                "chunk_id": chunk.get("chunk_id"),
                "page_no": chunk.get("page_no"),
                "section_id": chunk.get("section_id"),
                "heading": (chunk.get("heading_path") or ["-"])[-1],
                "text_preview": (chunk.get("original_text") or "")[:400],
            }
        )

    return {
        "stats": {
            "dimension_count": total_dims,
            "slice_start": safe_start,
            "slice_end_exclusive": safe_end,
            "norm": round(float(np.linalg.norm(query_vector)), 6),
            "min": round(float(query_vector.min()), 6),
            "max": round(float(query_vector.max()), 6),
            "mean": round(float(query_vector.mean()), 6),
            "std": round(float(query_vector.std()), 6),
        },
        "rows": rows,
        "nearest_hits": nearest_hits,
    }, None


@st.cache_data(show_spinner=False)
def load_parsed_pages(pdf_path: str) -> tuple[list[dict[str, Any]], str | None]:
    path = Path(pdf_path)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    if not path.exists():
        return [], f"PDF file not found: {path}"
    try:
        from app.ingest.parser import parse_document

        parsed_pages = parse_document(str(path))
    except Exception as exc:  # pragma: no cover - defensive UI handling
        return [], str(exc)
    return [page.model_dump() for page in parsed_pages], None


@st.cache_data(show_spinner=False)
def load_pdf_page_snapshot(pdf_path: str, page_no: int, zoom_factor: float = 1.2) -> tuple[bytes | None, str | None]:
    if fitz is None:
        return None, "PyMuPDF is not available for PDF snapshots."
    path = Path(pdf_path)
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    if not path.exists():
        return None, f"PDF file not found: {path}"
    try:
        with fitz.open(path) as pdf_document:
            if page_no < 1 or page_no > pdf_document.page_count:
                return None, f"Page {page_no} is out of range."
            page = pdf_document.load_page(page_no - 1)
            matrix = fitz.Matrix(zoom_factor, zoom_factor)
            pixmap = page.get_pixmap(matrix=matrix, alpha=False)
            return pixmap.tobytes("png"), None
    except Exception as exc:  # pragma: no cover - defensive UI handling
        return None, str(exc)


@st.cache_data(show_spinner=False)
def run_local_retrieval_inspection(
    *,
    query_text: str,
    retrieval_mode: str,
    index_dir: str,
    tax_year: str | None,
    top_k: int,
    final_evidence_k: int,
) -> dict[str, Any]:
    from app.core.utils import extract_salient_query_terms, preprocess_query, tokenize_for_bm25
    from app.core.settings import get_settings
    from app.retrieval.dense import dense_search
    from app.retrieval.hybrid import run_hybrid_retrieval
    from app.retrieval.sparse import sparse_search

    settings = get_settings()
    analyzed_query = preprocess_query(query_text)
    search_query = analyzed_query.rewritten_query or analyzed_query.normalized_query
    query_tokens = tokenize_for_bm25(search_query)
    salient_terms = sorted(extract_salient_query_terms(search_query))
    effective_tax_year = tax_year or analyzed_query.tax_year

    payload: dict[str, Any] = {
        "query_text": query_text,
        "retrieval_mode": retrieval_mode,
        "index_dir": index_dir,
        "analyzed_query": analyzed_query.model_dump(),
        "search_query": search_query,
        "query_tokens": query_tokens,
        "salient_terms": salient_terms,
        "tax_year": effective_tax_year,
        "top_k": top_k,
        "final_evidence_k": final_evidence_k,
        "sparse_hits": [],
        "dense_hits": [],
        "fused_hits": [],
        "final_hits": [],
        "conflict_notes": [],
        "evidence_summary": "",
    }

    if retrieval_mode == "sparse":
        sparse_hits = sparse_search(
            query_text,
            top_k=top_k,
            tax_year=effective_tax_year,
            index_dir=index_dir,
        )
        payload["sparse_hits"] = sparse_hits
        payload["final_hits"] = sparse_hits
        return payload

    if retrieval_mode == "dense":
        dense_hits = dense_search(
            query_text,
            top_k=top_k,
            tax_year=effective_tax_year,
            index_dir=settings.dense_index_dir,
        )
        payload["dense_hits"] = dense_hits
        payload["final_hits"] = dense_hits
        return payload

    hybrid_response = run_hybrid_retrieval(
        query=query_text,
        sparse_top_k=max(top_k * 2, 10),
        dense_top_k=max(top_k * 2, 10),
        final_top_k=final_evidence_k,
        tax_year=effective_tax_year,
        index_dir=index_dir,
        dense_index_dir=settings.dense_index_dir,
    )
    payload["sparse_hits"] = [hit.model_dump() for hit in hybrid_response.sparse_hits]
    payload["dense_hits"] = [hit.model_dump() for hit in hybrid_response.dense_hits]
    payload["fused_hits"] = [hit.model_dump() for hit in hybrid_response.fused_hits]
    payload["final_hits"] = [hit.model_dump() for hit in hybrid_response.final_hits]
    payload["conflict_notes"] = hybrid_response.conflict_notes
    payload["evidence_summary"] = hybrid_response.evidence_summary
    return payload


def api_get(base_url: str, endpoint: str) -> tuple[bool, dict[str, Any] | None, str | None]:
    try:
        response = requests.get(f"{base_url.rstrip('/')}{endpoint}", timeout=REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
        return True, response.json(), None
    except requests.RequestException as exc:
        return False, None, str(exc)


def api_post(
    base_url: str,
    endpoint: str,
    payload: dict[str, Any],
    *,
    timeout_seconds: int = REQUEST_TIMEOUT_SECONDS,
) -> tuple[bool, dict[str, Any] | None, str | None]:
    try:
        response = requests.post(
            f"{base_url.rstrip('/')}{endpoint}",
            json=payload,
            timeout=timeout_seconds,
        )
        response.raise_for_status()
        return True, response.json(), None
    except requests.RequestException as exc:
        message = str(exc)
        if exc.response is not None:
            try:
                message = str(exc.response.json())
            except ValueError:
                message = exc.response.text or message
        return False, None, message


def is_agentic_response(payload: dict[str, Any] | None) -> bool:
    if not isinstance(payload, dict):
        return False
    if payload.get("_ui_pipeline_mode") == "agentic":
        return True
    return "trace_id" in payload and "execution_path" in payload


def derive_chunk_browser_default_path(last_ingest_response: dict[str, Any] | None) -> str:
    if not isinstance(last_ingest_response, dict):
        return "data/processed/income-tax-act-2023.jsonl"
    if last_ingest_response.get("_ui_pipeline_mode") == "agentic":
        graph_path = last_ingest_response.get("graph_path")
        if isinstance(graph_path, str) and graph_path.strip():
            graph = Path(graph_path)
            return str(graph.parent.parent / "chunks" / "retrieval_chunks.jsonl")
    return str(last_ingest_response.get("output_jsonl_path") or "data/processed/income-tax-act-2023.jsonl")


def render_api_connection_panel(base_url: str) -> tuple[dict[str, Any] | None, bool]:
    selected_pipeline = st.sidebar.selectbox(
        "Workspace Pipeline",
        options=UI_PIPELINE_MODES,
        key="ui_pipeline_mode",
        help="Use agentic for the new graph-based runtime. Legacy keeps the original ingest/build-index/query flow.",
    )
    st.sidebar.header("API Connection")
    backend_base_url = st.sidebar.text_input(
        "Backend Base URL",
        key="backend_base_url",
        help="Expected local default: http://127.0.0.1:4893",
    )
    check_connection = st.sidebar.button("Check API Health", use_container_width=True)
    config_payload: dict[str, Any] | None = None
    api_reachable = False
    if check_connection or backend_base_url:
        health_ok, health_payload, health_error = api_get(backend_base_url, "/health")
        if health_ok:
            api_reachable = True
            st.sidebar.success(f"API reachable: {health_payload.get('service', 'unknown service')}")
            config_ok, config_payload, config_error = api_get(backend_base_url, "/config")
            if config_ok and config_payload is not None:
                st.sidebar.caption(f"Mode: {config_payload.get('retrieval_mode')} | Top K: {config_payload.get('top_k')}")
            elif config_error:
                st.sidebar.warning(f"Config unavailable: {config_error}")
            if selected_pipeline == "agentic":
                agentic_ok, agentic_payload, agentic_error = api_get(backend_base_url, "/agentic/status")
                if agentic_ok and agentic_payload is not None:
                    runtime_status = "ready" if agentic_payload.get("ready") else "empty"
                    loaded_documents = len(agentic_payload.get("loaded_documents") or [])
                    st.sidebar.caption(
                        f"Agentic runtime: {runtime_status} | docs={loaded_documents} | vectors={agentic_payload.get('vector_record_count', 0)}"
                    )
                elif check_connection:
                    st.sidebar.warning(f"Agentic runtime unavailable: {agentic_error}")
        elif check_connection:
            st.sidebar.warning(f"API unreachable: {health_error}")
    return config_payload, api_reachable


def render_ingestion_panel(base_url: str) -> None:
    st.subheader("PDF Ingestion")
    if st.session_state.get("ui_pipeline_mode") == "agentic":
        st.caption("Agentic ingest builds the legal graph, chunk artifacts, BM25 index, and vector store in one step.")
        with st.form("agentic_ingest_form", clear_on_submit=False):
            source_path = st.text_input("Source PDF Path", value="/home/sonjoy/Bar tax/Income_tax_act_2023.pdf")
            document_id = st.text_input("Document ID", value="income-tax-act-2023")
            act_title = st.text_input("Act Title", value="Income Tax Act 2023")
            submitted = st.form_submit_button("Ingest Into Agentic Runtime", use_container_width=True)

        if submitted:
            payload = {
                "source_path": source_path,
                "document_id": document_id or None,
                "act_title": act_title or None,
            }
            success, response_payload, error_message = api_post(
                base_url,
                "/agentic/ingest",
                payload,
                timeout_seconds=INGEST_TIMEOUT_SECONDS,
            )
            if success and response_payload is not None:
                response_payload["_ui_pipeline_mode"] = "agentic"
                st.session_state["last_ingest_response"] = response_payload
                st.success("Agentic ingest completed.")
            else:
                st.error(f"Agentic ingest failed: {error_message}")
                st.caption("For the full Act PDF, expect parsing and OCR-related steps to take longer than the small demo files.")

        if st.session_state.get("last_ingest_response"):
            ingest_response = st.session_state["last_ingest_response"]
            if ingest_response.get("_ui_pipeline_mode") == "agentic":
                st.json(
                    {
                        "status": ingest_response.get("status"),
                        "document_id": ingest_response.get("document_id"),
                        "act_title": ingest_response.get("act_title"),
                        "parser_provider": ingest_response.get("parser_provider"),
                        "graph_path": ingest_response.get("graph_path"),
                        "bm25_index_dir": ingest_response.get("bm25_index_dir"),
                        "retrieval_chunk_count": ingest_response.get("retrieval_chunk_count"),
                        "reasoning_chunk_count": ingest_response.get("reasoning_chunk_count"),
                        "vector_record_count": ingest_response.get("vector_record_count"),
                    }
                )
        return

    with st.form("ingest_form", clear_on_submit=False):
        input_pdf_path = st.text_input("Input PDF Path", value="/home/sonjoy/Bar tax/Income_tax_act_2023.pdf")
        doc_id = st.text_input("Document ID", value="income-tax-act-2023")
        doc_title = st.text_input("Document Title", value="Income Tax Act 2023")
        column_left, column_right = st.columns(2)
        with column_left:
            doc_type = st.text_input("Document Type", value="statute")
            authority_level = st.selectbox("Authority Level", options=["unknown", "local", "regional", "national", "statute", "constitutional"], index=3)
        with column_right:
            chunking_mode = st.selectbox("Chunking Mode", options=["section_aware", "naive", "example_aware", "table_aware"], index=0)
            output_jsonl_path = st.text_input("Output JSONL Path", value="data/processed/income-tax-act-2023.jsonl")
        ocr_column_left, ocr_column_right = st.columns(2)
        with ocr_column_left:
            ocr_enabled = st.checkbox("Enable OCR For Bangla PDF", value=False)
            ocr_force = st.checkbox("Force OCR Even If Text Exists", value=True)
        with ocr_column_right:
            ocr_language = st.text_input("OCR Language", value="ben+eng")
            ocr_output_pdf_path = st.text_input(
                "OCR Output PDF Path",
                value="data/processed/income-tax-act-2023.ocr.pdf",
            )
        submitted = st.form_submit_button("Ingest PDF", use_container_width=True)

    if submitted:
        payload = {
            "input_pdf_path": input_pdf_path,
            "doc_id": doc_id,
            "doc_title": doc_title,
            "doc_type": doc_type,
            "authority_level": authority_level,
            "chunking_mode": chunking_mode,
            "output_jsonl_path": output_jsonl_path or None,
            "ocr_enabled": ocr_enabled,
            "ocr_language": ocr_language,
            "ocr_force": ocr_force,
            "ocr_output_pdf_path": ocr_output_pdf_path or None,
        }
        success, response_payload, error_message = api_post(
            base_url,
            "/ingest",
            payload,
            timeout_seconds=INGEST_TIMEOUT_SECONDS,
        )
        if success and response_payload is not None:
            response_payload["_ui_pipeline_mode"] = "legacy"
            st.session_state["last_ingest_response"] = response_payload
            st.success("PDF ingestion completed.")
        else:
            st.error(f"Ingestion failed: {error_message}")
            st.caption("Large or messy Bangla PDFs can take longer to parse. If this keeps happening, try the CLI ingestion command first.")

    if st.session_state.get("last_ingest_response"):
        ingest_response = st.session_state["last_ingest_response"]
        st.json(
            {
                "status": ingest_response.get("status"),
                "number_of_pages": ingest_response.get("number_of_pages"),
                "number_of_chunks": ingest_response.get("number_of_chunks"),
                "output_jsonl_path": ingest_response.get("output_jsonl_path"),
                "chunking_mode": ingest_response.get("chunking_mode"),
                "ocr_applied": ingest_response.get("ocr_applied"),
                "ocr_output_pdf_path": ingest_response.get("ocr_output_pdf_path"),
            }
        )


def render_index_building_panel(base_url: str) -> None:
    st.subheader("Index Building")
    if st.session_state.get("ui_pipeline_mode") == "agentic":
        st.info("Agentic mode builds BM25 and vector artifacts during ingest. No separate /build-index step is required.")
        last_ingest_response = st.session_state.get("last_ingest_response") or {}
        if isinstance(last_ingest_response, dict) and last_ingest_response.get("_ui_pipeline_mode") == "agentic":
            st.json(
                {
                    "document_id": last_ingest_response.get("document_id"),
                    "graph_path": last_ingest_response.get("graph_path"),
                    "bm25_index_dir": last_ingest_response.get("bm25_index_dir"),
                    "retrieval_chunk_count": last_ingest_response.get("retrieval_chunk_count"),
                    "vector_record_count": last_ingest_response.get("vector_record_count"),
                }
            )
        return

    with st.form("build_index_form", clear_on_submit=False):
        chunk_jsonl_path = st.text_input("Chunk JSONL Path", value="data/processed/income-tax-act-2023.jsonl")
        build_sparse = st.checkbox("Build Sparse Index", value=True)
        build_dense = st.checkbox("Build Dense Index", value=False)
        submitted = st.form_submit_button("Build Index", use_container_width=True)

    if submitted:
        payload = {
            "chunk_jsonl_path": chunk_jsonl_path,
            "build_sparse": build_sparse,
            "build_dense": build_dense,
        }
        success, response_payload, error_message = api_post(
            base_url,
            "/build-index",
            payload,
            timeout_seconds=INDEX_BUILD_TIMEOUT_SECONDS,
        )
        if success and response_payload is not None:
            response_payload["_ui_pipeline_mode"] = "legacy"
            st.session_state["last_build_index_response"] = response_payload
            st.success("Index build completed.")
        else:
            st.error(f"Index build failed: {error_message}")

    if st.session_state.get("last_build_index_response"):
        build_response = st.session_state["last_build_index_response"]
        st.json(
            {
                "status": build_response.get("status"),
                "sparse_index_path": build_response.get("sparse_index_path"),
                "dense_index_path": build_response.get("dense_index_path"),
                "number_of_chunks_indexed": build_response.get("number_of_chunks_indexed"),
            }
        )


def render_query_panel(base_url: str) -> None:
    st.subheader("Query")
    with st.expander("Suggested Questions For Generation", expanded=False):
        st.caption("Load one of these into the query box to test grounded answer generation quickly.")
        preset_column, action_column = st.columns([3, 1])
        with preset_column:
            selected_question = st.selectbox(
                "Question Preset",
                options=GENERATION_TEST_QUESTIONS,
                key="question_preset",
            )
        with action_column:
            st.write("")
            if st.button("Use Question", use_container_width=True):
                st.session_state["question_text"] = selected_question
                st.session_state["last_query_response"] = None
        st.markdown("**Preset List**")
        for question in GENERATION_TEST_QUESTIONS:
            st.code(question, language="text")

    if st.session_state.get("ui_pipeline_mode") == "agentic":
        with st.form("agentic_query_form", clear_on_submit=False):
            question_text = st.text_area(
                "Question Text",
                key="question_text",
                height=100,
                placeholder="Ask in Bangla or English.",
            )
            selection_left, selection_right = st.columns(2)
            with selection_left:
                st.selectbox(
                    "Query Type Override",
                    options=AGENTIC_QUERY_TYPE_OPTIONS,
                    key="agentic_query_type",
                    help="Use auto unless you are intentionally forcing a query path for debugging.",
                )
            with selection_right:
                st.number_input(
                    "Max Reasoning Steps",
                    min_value=1,
                    max_value=12,
                    step=1,
                    key="agentic_max_reasoning_steps",
                )
            submitted = st.form_submit_button("Run Agentic Query", use_container_width=True)

        if submitted:
            payload = {
                "question": question_text,
                "max_reasoning_steps": int(st.session_state.get("agentic_max_reasoning_steps") or 6),
            }
            selected_query_type = str(st.session_state.get("agentic_query_type") or "auto").strip()
            if selected_query_type and selected_query_type != "auto":
                payload["query_type"] = selected_query_type
            success, response_payload, error_message = api_post(
                base_url,
                "/agentic/query",
                payload,
                timeout_seconds=QUERY_TIMEOUT_SECONDS,
            )
            if success and response_payload is not None:
                response_payload["_ui_pipeline_mode"] = "agentic"
                st.session_state["last_query_response"] = response_payload
                trace_id = response_payload.get("trace_id")
                if isinstance(trace_id, str) and trace_id:
                    trace_ok, trace_payload, _ = api_get(base_url, f"/trace/{trace_id}")
                    st.session_state["last_trace_response"] = trace_payload if trace_ok else None
                else:
                    st.session_state["last_trace_response"] = None
                st.success("Agentic query completed.")
            else:
                st.error(f"Agentic query failed: {error_message}")
        return

    with st.form("query_form", clear_on_submit=False):
        question_text = st.text_area(
            "Question Text",
            key="question_text",
            height=100,
            placeholder="Ask in Bangla or English.",
        )
        selection_left, selection_right = st.columns(2)
        with selection_left:
            retrieval_mode = st.selectbox("Retrieval Mode", options=["sparse", "dense", "hybrid"], key="retrieval_mode")
            tax_year = st.text_input("Tax Year (optional)", key="tax_year", placeholder="2025-2026")
            top_k = st.number_input("Top K", min_value=1, max_value=20, step=1, key="top_k")
        with selection_right:
            final_evidence_k = st.number_input("Final Evidence K", min_value=1, max_value=20, step=1, key="final_evidence_k")
            include_intermediate_hits = st.checkbox("Include Intermediate Hits", key="include_intermediate_hits")
            generate_answer = st.checkbox("Generate Grounded Answer", key="generate_answer")
        model_left, model_right = st.columns([2, 3])
        with model_left:
            st.selectbox(
                "Generator Model",
                options=OLLAMA_GENERATOR_MODEL_PRESETS,
                key="query_generator_model_preset",
                help="Uses the Ollama/OpenAI-compatible backend configured in the API.",
            )
        with model_right:
            if st.session_state.get("query_generator_model_preset") == "Custom...":
                st.text_input(
                    "Custom Generator Model",
                    key="query_custom_generator_model",
                    placeholder="e.g. qwen2.5:7b-instruct",
                )
        submitted = st.form_submit_button("Run Query", use_container_width=True)

    if submitted:
        selected_generator_model = resolve_selected_generator_model(
            preset_key="query_generator_model_preset",
            custom_key="query_custom_generator_model",
        )
        payload = {
            "question_text": question_text,
            "retrieval_mode": retrieval_mode,
            "tax_year": tax_year or None,
            "top_k": int(top_k),
            "final_evidence_k": int(final_evidence_k),
            "include_intermediate_hits": include_intermediate_hits,
            "generate_answer": generate_answer,
            "generator_model_name": selected_generator_model if generate_answer else None,
        }
        success, response_payload, error_message = api_post(
            base_url,
            "/query",
            payload,
            timeout_seconds=QUERY_TIMEOUT_SECONDS,
        )
        if success and response_payload is not None:
            response_payload["_ui_pipeline_mode"] = "legacy"
            st.session_state["last_query_response"] = response_payload
            st.session_state["last_trace_response"] = None
            st.success("Query completed.")
        else:
            st.error(f"Query failed: {error_message}")


def render_citations(citations: list[dict[str, Any]]) -> None:
    if not citations:
        return
    st.markdown("**Citations**")
    for citation in citations:
        with st.container(border=True):
            if citation.get("marker"):
                st.markdown(f"`{citation.get('marker')}` {citation.get('doc_title')} | page {citation.get('page_no')}")
                st.caption(
                    f"chunk_id={citation.get('chunk_id')} | section={citation.get('section_id') or '-'} | "
                    f"subsection={citation.get('subsection_id') or '-'}"
                )
                st.write(citation.get("evidence_snippet", ""))
                continue

            label = citation.get("label") or citation.get("node_id") or "citation"
            relation = citation.get("relation") or "support"
            page_start = citation.get("page_start")
            page_end = citation.get("page_end")
            page_label = str(page_start) if page_start == page_end else f"{page_start}-{page_end}"
            st.markdown(f"`{relation}` {label}")
            st.caption(
                f"section={citation.get('section') or '-'} | subsection={citation.get('subsection') or '-'} | "
                f"clause={citation.get('clause') or '-'} | pages={page_label}"
            )
            st.write(citation.get("snippet", ""))


def render_hit_card(
    hit: dict[str, Any],
    heading: str | None = None,
    *,
    show_intermediate_scores: bool = False,
) -> None:
    title = heading or f"{hit.get('doc_title', 'Untitled Document')} | page {hit.get('page_no', '-')}"
    with st.expander(title, expanded=False):
        metadata_columns = st.columns(4)
        metadata_columns[0].metric("Score", f"{hit.get('score', 0):.4f}" if isinstance(hit.get("score"), (int, float)) else hit.get("score", "-"))
        metadata_columns[1].metric("Chunk Type", str(hit.get("chunk_type", "-")))
        metadata_columns[2].metric("Authority", str(hit.get("authority_level", "-")))
        metadata_columns[3].metric("Tax Year", str(hit.get("tax_year", "-")))
        st.caption(
            f"chunk_id={hit.get('chunk_id')} | section={hit.get('section_id') or '-'} | "
            f"subsection={hit.get('subsection_id') or '-'}"
        )
        heading_path = hit.get("heading_path") or []
        if heading_path:
            st.markdown(f"**Heading Path:** {' > '.join(heading_path)}")
        if show_intermediate_scores and hit.get("intermediate_scores"):
            st.markdown("**Intermediate Scores**")
            st.json(hit.get("intermediate_scores"))
        snippet = hit.get("original_text") or hit.get("content") or hit.get("normalized_text") or ""
        st.write(snippet)


def render_hit_compact_card(
    hit: dict[str, Any],
    *,
    show_intermediate_scores: bool = False,
) -> None:
    with st.container(border=True):
        st.caption(
            f"{hit.get('doc_title', 'Untitled Document')} | "
            f"page {hit.get('page_no', '-')} | "
            f"{hit.get('chunk_id', 'unknown-chunk')}"
        )
        metadata_columns = st.columns(4)
        metadata_columns[0].metric(
            "Score",
            f"{hit.get('score', 0):.4f}" if isinstance(hit.get("score"), (int, float)) else hit.get("score", "-"),
        )
        metadata_columns[1].metric("Chunk Type", str(hit.get("chunk_type", "-")))
        metadata_columns[2].metric("Authority", str(hit.get("authority_level", "-")))
        metadata_columns[3].metric("Tax Year", str(hit.get("tax_year", "-")))
        st.caption(
            f"section={hit.get('section_id') or '-'} | "
            f"subsection={hit.get('subsection_id') or '-'}"
        )
        heading_path = hit.get("heading_path") or []
        if heading_path:
            st.markdown(f"**Heading Path:** {' > '.join(heading_path)}")
        if show_intermediate_scores and hit.get("intermediate_scores"):
            st.markdown("**Intermediate Scores**")
            st.json(hit.get("intermediate_scores"))
        snippet = hit.get("original_text") or hit.get("content") or hit.get("normalized_text") or ""
        st.code(snippet[:900], language="text")


def render_chunk_card(chunk: dict[str, Any]) -> None:
    title = (
        f"{chunk.get('chunk_id', 'unknown-chunk')} | "
        f"page {chunk.get('page_no', '-')} | "
        f"{chunk.get('chunk_type', '-')}"
    )
    with st.expander(title, expanded=False):
        metadata_columns = st.columns(4)
        metadata_columns[0].metric("Section", str(chunk.get("section_id") or "-"))
        metadata_columns[1].metric("Subsection", str(chunk.get("subsection_id") or "-"))
        metadata_columns[2].metric("Authority", str(chunk.get("authority_level") or "-"))
        metadata_columns[3].metric("Tax Year", str(chunk.get("tax_year") or "-"))
        heading_path = chunk.get("heading_path") or []
        if heading_path:
            st.markdown(f"**Heading Path:** {' > '.join(heading_path)}")
        st.markdown("**Original Text**")
        st.code(chunk.get("original_text") or "", language="text")
        normalized_text = chunk.get("normalized_text") or ""
        if normalized_text and normalized_text != chunk.get("original_text"):
            st.markdown("**Normalized Text**")
            st.code(normalized_text, language="text")


def render_parsed_page_card(page: dict[str, Any], *, pdf_path: str, show_snapshot: bool) -> None:
    title = f"page {page.get('page_no', '-')} | lines {page.get('line_count', '-')}"
    with st.expander(title, expanded=False):
        if show_snapshot:
            snapshot_column, detail_column = st.columns([1, 1.4])
        else:
            snapshot_column, detail_column = None, st.container()

        if show_snapshot and snapshot_column is not None:
            with snapshot_column:
                snapshot_bytes, snapshot_error = load_pdf_page_snapshot(pdf_path, int(page.get("page_no") or 0))
                if snapshot_bytes is not None:
                    st.image(snapshot_bytes, caption=f"PDF snapshot: page {page.get('page_no')}", use_container_width=True)
                else:
                    st.caption(f"Snapshot unavailable: {snapshot_error}")

        with detail_column:
            metadata_columns = st.columns(4)
            metadata_columns[0].metric("Appendix", "Yes" if page.get("is_appendix") else "No")
            metadata_columns[1].metric("Example", "Yes" if page.get("is_example") else "No")
            metadata_columns[2].metric("Table Like", "Yes" if page.get("is_table_like") else "No")
            metadata_columns[3].metric("Line Count", str(page.get("line_count") or 0))
            if page.get("headings"):
                st.markdown(f"**Headings:** {' | '.join(page.get('headings') or [])}")
            st.markdown(f"**Section Markers:** {page.get('section_markers') or []}")
            st.markdown(f"**Tax Years:** {page.get('tax_years') or []}")
            st.markdown(f"**SRO IDs:** {page.get('sro_ids') or []}")
            st.markdown("**Raw Text**")
            st.code(page.get("raw_text") or "", language="text")
            normalized_text = page.get("normalized_text") or ""
            raw_text = page.get("raw_text") or ""
            if normalized_text and normalized_text != raw_text:
                st.markdown("**Normalized Text**")
                st.code(normalized_text, language="text")


def render_chunk_browser() -> None:
    st.subheader("Chunk Browser")
    last_ingest_response = st.session_state.get("last_ingest_response")
    if not isinstance(last_ingest_response, dict):
        last_ingest_response = {}
    default_chunk_path = derive_chunk_browser_default_path(last_ingest_response)
    browser_left, browser_right = st.columns([3, 1])
    with browser_left:
        chunk_jsonl_path = st.text_input(
            "Chunk JSONL Path For Preview",
            value=default_chunk_path,
            help="Browse locally generated chunk records without calling the API.",
        )
    with browser_right:
        max_chunks = st.number_input("Preview Count", min_value=10, max_value=500, value=50, step=10)

    chunk_records, error_message = load_chunk_records(chunk_jsonl_path, max_chunks=int(max_chunks))
    if error_message:
        st.warning(error_message)
        return
    if not chunk_records:
        st.info("No chunks found in the selected file.")
        return

    available_chunk_types = sorted({str(chunk.get("chunk_type") or "unknown") for chunk in chunk_records})
    filter_left, filter_right = st.columns(2)
    with filter_left:
        chunk_type_filter = st.multiselect(
            "Filter Chunk Types",
            options=available_chunk_types,
            default=[],
        )
    with filter_right:
        page_filter = st.text_input(
            "Filter Page Number",
            value="",
            placeholder="Example: 17",
        ).strip()

    filtered_chunks = chunk_records
    if chunk_type_filter:
        filtered_chunks = [chunk for chunk in filtered_chunks if chunk.get("chunk_type") in chunk_type_filter]
    if page_filter.isdigit():
        filtered_chunks = [chunk for chunk in filtered_chunks if int(chunk.get("page_no", -1)) == int(page_filter)]

    st.caption(f"Showing {len(filtered_chunks)} of {len(chunk_records)} loaded chunks")
    for chunk in filtered_chunks:
        render_chunk_card(chunk)


def render_parser_inspector() -> None:
    st.subheader("Parser Inspector")
    st.caption("Inspect page-level parser output before chunking. This runs locally and does not call the API.")
    parser_left, parser_right = st.columns([3, 1])
    with parser_left:
        parser_input_path = st.text_input(
            "PDF Path For Parser Inspection",
            value="/home/sonjoy/Bar tax/Income_tax_act_2023.pdf",
            help="Use a local PDF path. The parser will extract page text, headings, section markers, and page flags.",
        )
    with parser_right:
        preview_limit = st.number_input("Preview Pages", min_value=5, max_value=200, value=20, step=5)
    show_snapshot = st.checkbox("Show PDF snapshots beside parsed output", value=True)

    parsed_pages, error_message = load_parsed_pages(parser_input_path)
    if error_message:
        st.warning(f"Error loading pages: {error_message}")
        return
    if not parsed_pages:
        st.info("No parsed pages available for the selected PDF.")
        return

    filter_left, filter_right = st.columns(2)
    with filter_left:
        page_filter = st.text_input("Filter Single Page Number", value="", placeholder="Example: 24").strip()
    with filter_right:
        parser_view = st.selectbox(
            "Parser View",
            options=["all", "headings only", "table-like only", "appendix only"],
            index=0,
        )

    filtered_pages = parsed_pages
    if page_filter.isdigit():
        filtered_pages = [page for page in filtered_pages if int(page.get("page_no", -1)) == int(page_filter)]
    if parser_view == "headings only":
        filtered_pages = [page for page in filtered_pages if page.get("headings")]
    elif parser_view == "table-like only":
        filtered_pages = [page for page in filtered_pages if page.get("is_table_like")]
    elif parser_view == "appendix only":
        filtered_pages = [page for page in filtered_pages if page.get("is_appendix")]

    limited_pages = filtered_pages[: int(preview_limit)]
    st.json(
        {
            "total_pages_parsed": len(parsed_pages),
            "pages_shown": len(limited_pages),
            "pages_with_headings": sum(1 for page in parsed_pages if page.get("headings")),
            "table_like_pages": sum(1 for page in parsed_pages if page.get("is_table_like")),
            "appendix_pages": sum(1 for page in parsed_pages if page.get("is_appendix")),
        }
    )
    for page in limited_pages:
        render_parsed_page_card(page, pdf_path=parser_input_path, show_snapshot=show_snapshot)


def render_indexed_chunk_card(chunk: dict[str, Any], *, weighted_search_text: str, tokenized_terms: list[str]) -> None:
    title = (
        f"{chunk.get('chunk_id', 'unknown-chunk')} | "
        f"page {chunk.get('page_no', '-')} | "
        f"{chunk.get('chunk_type', '-')}"
    )
    with st.expander(title, expanded=False):
        metadata_columns = st.columns(4)
        metadata_columns[0].metric("Section", str(chunk.get("section_id") or "-"))
        metadata_columns[1].metric("Subsection", str(chunk.get("subsection_id") or "-"))
        metadata_columns[2].metric("Authority", str(chunk.get("authority_level") or "-"))
        metadata_columns[3].metric("Tax Year", str(chunk.get("tax_year") or "-"))
        heading_path = chunk.get("heading_path") or []
        if heading_path:
            st.markdown(f"**Heading Path:** {' > '.join(heading_path)}")
        st.markdown("**Indexed Search Text**")
        st.code(weighted_search_text, language="text")
        st.markdown("**BM25 Tokens**")
        st.code(" ".join(tokenized_terms), language="text")
        st.markdown("**Original Chunk Text**")
        st.code(chunk.get("original_text") or "", language="text")


def _build_index_tree(
    chunk_records: list[dict[str, Any]],
) -> dict[str, dict[int, dict[str, list[dict[str, Any]]]]]:
    tree: dict[str, dict[int, dict[str, list[dict[str, Any]]]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(list))
    )
    for chunk in chunk_records:
        doc_label = f"{chunk.get('doc_title') or chunk.get('doc_id') or 'unknown document'} [{chunk.get('doc_id') or '-'}]"
        page_no = int(chunk.get("page_no") or -1)
        section_label = (
            chunk.get("subsection_id")
            or chunk.get("section_id")
            or "unlabeled-section"
        )
        tree[doc_label][page_no][str(section_label)].append(chunk)
    return {
        doc_label: {
            page_no: dict(section_map)
            for page_no, section_map in sorted(page_map.items())
        }
        for doc_label, page_map in sorted(tree.items())
    }


def render_index_tree(chunk_records: list[dict[str, Any]]) -> None:
    tree = _build_index_tree(chunk_records)
    st.markdown("**Index Tree**")
    for doc_label, page_map in tree.items():
        doc_chunk_count = sum(
            len(chunks)
            for section_map in page_map.values()
            for chunks in section_map.values()
        )
        with st.container(border=True):
            st.markdown(f"### {doc_label}")
            st.caption(f"{len(page_map)} pages | {doc_chunk_count} chunks")
            for page_no, section_map in page_map.items():
                page_chunk_count = sum(len(chunks) for chunks in section_map.values())
                with st.container(border=True):
                    st.markdown(f"**page {page_no}**")
                    st.caption(f"{len(section_map)} sections | {page_chunk_count} chunks")
                    for section_label, chunks in section_map.items():
                        chunk_type_summary = sorted({str(chunk.get('chunk_type') or 'unknown') for chunk in chunks})
                        st.markdown(
                            f"- **section {section_label}** | {len(chunks)} chunks | {', '.join(chunk_type_summary)}"
                        )
                        for chunk in chunks:
                            chunk_label = (
                                f"{chunk.get('chunk_id', 'unknown-chunk')} | "
                                f"{chunk.get('chunk_type', '-')} | "
                                f"{(chunk.get('heading_path') or ['-'])[-1]}"
                            )
                            with st.container(border=True):
                                st.caption(chunk_label)
                                metadata_columns = st.columns(4)
                                metadata_columns[0].metric("Section", str(chunk.get("section_id") or "-"))
                                metadata_columns[1].metric("Subsection", str(chunk.get("subsection_id") or "-"))
                                metadata_columns[2].metric("Authority", str(chunk.get("authority_level") or "-"))
                                metadata_columns[3].metric("Tax Year", str(chunk.get("tax_year") or "-"))
                                st.code(chunk.get("original_text") or "", language="text")


def render_index_inspector() -> None:
    st.subheader("Index Inspector")
    st.caption("Inspect saved index artifacts after chunking and before retrieval. This reads local index files directly.")

    last_build_index_response = st.session_state.get("last_build_index_response")
    if not isinstance(last_build_index_response, dict):
        last_build_index_response = {}
    default_index_dir = (
        last_build_index_response.get("sparse_index_path")
        or last_build_index_response.get("dense_index_path")
        or "indexes/sparse-english"
    )

    inspector_left, inspector_right = st.columns([3, 1])
    with inspector_left:
        index_dir = st.text_input(
            "Index Directory",
            value=default_index_dir,
            help="Point this to an index directory containing metadata.json and chunks.jsonl.",
        )
    with inspector_right:
        preview_limit = st.number_input("Preview Chunks", min_value=5, max_value=500, value=50, step=5)

    metadata, chunk_records, error_message = load_index_artifacts(index_dir, max_chunks=int(preview_limit))
    if error_message:
        st.warning(f"Error loading index: {error_message}")
        return
    if not chunk_records:
        st.info("No indexed chunks available in the selected index directory.")
        return

    inferred_index_type = "dense" if "dense" in index_dir.lower() else "sparse"
    st.json(
        {
            "index_dir": index_dir,
            "index_type": inferred_index_type,
            "chunk_count_in_metadata": metadata.get("chunk_count"),
            "chunks_loaded_for_preview": len(chunk_records),
            "available_files": ["metadata.json", "chunks.jsonl"],
        }
    )

    available_chunk_types = sorted({str(chunk.get("chunk_type") or "unknown") for chunk in chunk_records})
    filter_left, filter_right = st.columns(2)
    with filter_left:
        chunk_type_filter = st.multiselect(
            "Filter Indexed Chunk Types",
            options=available_chunk_types,
            default=[],
        )
    with filter_right:
        page_filter = st.text_input(
            "Filter Indexed Page Number",
            value="",
            placeholder="Example: 24",
        ).strip()
    view_mode = st.radio(
        "Index View Mode",
        options=["tree", "flat", "both"],
        horizontal=True,
        index=0,
    )

    filtered_chunks = chunk_records
    if chunk_type_filter:
        filtered_chunks = [chunk for chunk in filtered_chunks if chunk.get("chunk_type") in chunk_type_filter]
    if page_filter.isdigit():
        filtered_chunks = [chunk for chunk in filtered_chunks if int(chunk.get("page_no", -1)) == int(page_filter)]

    st.caption(f"Showing {len(filtered_chunks)} of {len(chunk_records)} loaded index chunks")

    if view_mode in {"tree", "both"}:
        render_index_tree(filtered_chunks)

    from app.core.utils import tokenize_for_bm25
    from app.core.schemas import ChunkRecord
    from app.retrieval.sparse import build_weighted_search_text

    if view_mode in {"flat", "both"}:
        st.markdown("**Indexed Chunk Cards**")
        for chunk in filtered_chunks:
            chunk_record = ChunkRecord.model_validate(chunk)
            weighted_search_text = build_weighted_search_text(chunk_record)
            tokenized_terms = tokenize_for_bm25(weighted_search_text)
            render_indexed_chunk_card(
                chunk,
                weighted_search_text=weighted_search_text,
                tokenized_terms=tokenized_terms,
            )


def render_dense_vector_inspector() -> None:
    st.subheader("Dense Vector Inspector")
    st.caption("Inspect the local dense vector store, embedding matrix, FAISS index, and chunk-to-vector mapping.")

    settings = get_settings()
    last_build_index_response = st.session_state.get("last_build_index_response")
    if not isinstance(last_build_index_response, dict):
        last_build_index_response = {}
    default_index_dir = last_build_index_response.get("dense_index_path") or settings.dense_index_dir or "indexes/dense"

    config_left, config_right, config_far_right = st.columns([3, 1, 1])
    with config_left:
        index_dir = st.text_input(
            "Dense Index Directory",
            value=default_index_dir,
            help="Point this to a dense index directory containing chunks.jsonl and embeddings.npy.",
        )
    with config_right:
        preview_limit = st.number_input("Preview Chunks", min_value=5, max_value=500, value=50, step=5)
    with config_far_right:
        preview_dims = st.number_input("Preview Dims", min_value=4, max_value=64, value=12, step=4)

    summary, chunk_records, error_message = load_dense_index_artifacts(
        index_dir,
        max_chunks=int(preview_limit),
        vector_preview_dims=int(preview_dims),
    )
    if error_message:
        st.warning(f"Error loading dense index: {error_message}")
        return

    if summary.get("metadata_mismatch"):
        st.warning(
            "Dense files exist on disk, but metadata.json still says placeholder/mock. "
            "The inspector is showing the inferred runtime shape from the actual files."
        )

    st.json(summary)

    if not chunk_records:
        st.info("No preview chunks were loaded from this dense index.")
        return

    embedding_matrix = summary.get("embedding_matrix") or {}
    vector_count = int((embedding_matrix.get("shape") or [0])[0]) if embedding_matrix.get("shape") else 0
    if vector_count <= 0:
        st.info("No embedding matrix was found yet. Build the dense index first to inspect stored vectors.")
        return

    chunk_options = [
        (
            index,
            f"{index} | p.{chunk.get('page_no', '-')} | {chunk.get('chunk_id', 'unknown-chunk')} | "
            f"{(chunk.get('heading_path') or ['-'])[-1]}"
        )
        for index, chunk in enumerate(chunk_records[:vector_count])
    ]
    option_labels = [label for _, label in chunk_options]
    selected_label = st.selectbox("Select Vector / Chunk", options=option_labels, index=0)
    selected_index = next(index for index, label in chunk_options if label == selected_label)
    selected_chunk = chunk_records[selected_index]

    vector_left, vector_right = st.columns([2, 3])
    with vector_left:
        st.markdown("**Selected Vector Metadata**")
        st.json(
            {
                "vector_index": selected_index,
                "chunk_id": selected_chunk.get("chunk_id"),
                "page_no": selected_chunk.get("page_no"),
                "section_id": selected_chunk.get("section_id"),
                "subsection_id": selected_chunk.get("subsection_id"),
                "chunk_type": selected_chunk.get("chunk_type"),
                "heading_path": selected_chunk.get("heading_path"),
            }
        )
    with vector_right:
        st.markdown("**Selected Chunk Text**")
        st.code(selected_chunk.get("original_text") or "", language="text")

    neighbors, neighbor_error = load_dense_vector_neighbors(index_dir, vector_index=selected_index, top_k=5)
    if neighbor_error:
        st.warning(neighbor_error)
        return

    st.markdown("**Embedding Value Browser**")
    total_dims = int((embedding_matrix.get("shape") or [0, 0])[1]) if embedding_matrix.get("shape") else 0
    browser_left, browser_mid, browser_right = st.columns([1, 1, 2])
    with browser_left:
        dim_start = st.number_input(
            "Dimension Start",
            min_value=0,
            max_value=max(total_dims - 1, 0),
            value=0,
            step=1,
            key=f"dense_dim_start::{index_dir}",
        )
    with browser_mid:
        dim_count = st.number_input(
            "Dimensions To Show",
            min_value=4,
            max_value=min(max(total_dims, 4), 256),
            value=min(24, max(total_dims, 4)),
            step=4,
            key=f"dense_dim_count::{index_dir}",
        )
    with browser_right:
        compare_neighbor_count = st.slider(
            "Compare With Nearest Neighbors",
            min_value=0,
            max_value=min(3, max(len(neighbors) - 1, 0)),
            value=min(2, max(len(neighbors) - 1, 0)),
            step=1,
            key=f"dense_neighbor_compare::{index_dir}",
            help="Adds nearest-neighbor vector values beside the selected vector for the same dimensions.",
        )

    compare_indices = tuple(neighbor["vector_index"] for neighbor in neighbors[1 : 1 + compare_neighbor_count])
    vector_slice_payload, vector_slice_error = load_dense_vector_slice(
        index_dir,
        vector_index=selected_index,
        dim_start=int(dim_start),
        dim_count=int(dim_count),
        compare_indices=compare_indices,
    )
    if vector_slice_error:
        st.warning(vector_slice_error)
        return

    st.caption("The table below shows actual stored embedding values for the selected vector slice.")
    st.json(vector_slice_payload.get("stats", {}))
    st.dataframe(vector_slice_payload.get("rows", []), use_container_width=True, hide_index=True)

    matrix_indices = (selected_index,) + tuple(neighbor["vector_index"] for neighbor in neighbors[1:4])
    similarity_matrix_payload, similarity_matrix_error = load_dense_similarity_matrix(
        index_dir,
        vector_indices=matrix_indices,
    )
    if similarity_matrix_error:
        st.warning(similarity_matrix_error)
    elif similarity_matrix_payload:
        st.markdown("**Cosine Similarity Matrix**")
        st.caption("A heatmap-like view of cosine similarity between the selected vector and its nearest neighbors.")
        st.vega_lite_chart(
            {
                "data": {"values": similarity_matrix_payload.get("rows", [])},
                "mark": {"type": "rect"},
                "encoding": {
                    "x": {"field": "source", "type": "nominal", "title": "Source Vector"},
                    "y": {"field": "target", "type": "nominal", "title": "Target Vector"},
                    "color": {
                        "field": "similarity",
                        "type": "quantitative",
                        "scale": {"scheme": "blues"},
                        "title": "Cosine Similarity",
                    },
                    "tooltip": [
                        {"field": "source", "type": "nominal"},
                        {"field": "target", "type": "nominal"},
                        {"field": "similarity", "type": "quantitative", "format": ".6f"},
                    ],
                },
                "width": "container",
                "height": 260,
            },
            use_container_width=True,
        )

    projection_point_count = st.slider(
        "Projection Sample Size",
        min_value=50,
        max_value=500,
        value=200,
        step=25,
        key=f"dense_projection_points::{index_dir}",
        help="Projects a sample of chunk embeddings into 2D using PCA for visual inspection.",
    )
    projection_points, projection_error = load_dense_projection(
        index_dir,
        focus_indices=matrix_indices,
        max_points=int(projection_point_count),
    )
    if projection_error:
        st.warning(projection_error)
    elif projection_points:
        st.markdown("**2D Embedding Projection**")
        st.caption("This PCA projection helps show where the selected chunk sits relative to the sampled dense vector space.")
        st.vega_lite_chart(
            {
                "data": {"values": projection_points},
                "mark": {"type": "circle", "filled": True, "size": 80},
                "encoding": {
                    "x": {"field": "x", "type": "quantitative", "title": "PCA-1"},
                    "y": {"field": "y", "type": "quantitative", "title": "PCA-2"},
                    "color": {
                        "field": "role",
                        "type": "nominal",
                        "scale": {"domain": ["sample", "focus"], "range": ["#4b83d1", "#d14b6c"]},
                        "title": "Role",
                    },
                    "tooltip": [
                        {"field": "vector_index", "type": "quantitative"},
                        {"field": "chunk_id", "type": "nominal"},
                        {"field": "page_no", "type": "quantitative"},
                        {"field": "section_id", "type": "nominal"},
                        {"field": "heading", "type": "nominal"},
                    ],
                },
                "width": "container",
                "height": 320,
            },
            use_container_width=True,
        )

    st.markdown("**Query Embedding Comparison**")
    st.caption("Encode a query with the same dense model and compare its embedding against the selected chunk and neighbors.")
    query_text = st.text_area(
        "Query Text For Dense Embedding Comparison",
        value="What are the income tax authorities under section 4?",
        height=80,
        key=f"dense_query_compare::{index_dir}",
    )
    query_compare_k = st.slider(
        "Query Nearest Hits",
        min_value=1,
        max_value=10,
        value=5,
        step=1,
        key=f"dense_query_compare_k::{index_dir}",
    )
    query_comparison_payload, query_comparison_error = load_query_embedding_comparison(
        index_dir,
        query_text=query_text,
        compare_indices=matrix_indices,
        dim_start=int(dim_start),
        dim_count=int(dim_count),
        top_k=int(query_compare_k),
    )
    if query_comparison_error:
        st.warning(query_comparison_error)
    elif query_comparison_payload:
        query_left, query_right = st.columns([2, 3])
        with query_left:
            st.markdown("**Query Embedding Stats**")
            st.json(query_comparison_payload.get("stats", {}))
        with query_right:
            st.markdown("**Query Embedding Slice**")
            st.dataframe(query_comparison_payload.get("rows", []), use_container_width=True, hide_index=True)

        st.markdown("**Nearest Chunks For Query Embedding**")
        for nearest_hit in query_comparison_payload.get("nearest_hits", []):
            with st.container(border=True):
                st.caption(
                    f"vector {nearest_hit['vector_index']} | sim={nearest_hit['similarity']:.4f} | "
                    f"{nearest_hit.get('chunk_id', 'unknown-chunk')}"
                )
                st.write(
                    f"page={nearest_hit.get('page_no', '-')} | "
                    f"section={nearest_hit.get('section_id', '-')}"
                )
                st.write(nearest_hit.get("heading", "-"))
                st.code(nearest_hit.get("text_preview") or "", language="text")

    st.markdown("**Nearest Neighbor Vectors**")
    for neighbor in neighbors:
        with st.container(border=True):
            st.caption(
                f"vector {neighbor['vector_index']} | sim={neighbor['similarity']:.4f} | "
                f"{neighbor.get('chunk_id', 'unknown-chunk')}"
            )
            st.write(
                f"page={neighbor.get('page_no', '-')} | "
                f"section={neighbor.get('section_id', '-')} | "
                f"subsection={neighbor.get('subsection_id', '-')}"
            )
            st.write(" > ".join(neighbor.get("heading_path") or ["-"]))
            st.code((neighbor.get("original_text") or "")[:900], language="text")


def render_retrieval_inspector() -> None:
    st.subheader("Retrieval Inspector")
    st.caption("Inspect local retrieval before generation. This runs sparse, dense, or hybrid retrieval directly against the selected index directory.")

    last_build_index_response = st.session_state.get("last_build_index_response")
    if not isinstance(last_build_index_response, dict):
        last_build_index_response = {}
    default_index_dir = (
        last_build_index_response.get("sparse_index_path")
        or last_build_index_response.get("dense_index_path")
        or "indexes/sparse-english"
    )

    with st.form("retrieval_inspector_form", clear_on_submit=False):
        question_text = st.text_area(
            "Inspector Query",
            value="What are the income tax authorities under section 4?",
            height=100,
        )
        selection_left, selection_right = st.columns(2)
        with selection_left:
            retrieval_mode = st.selectbox("Retrieval Mode", options=["sparse", "dense", "hybrid"], index=0)
            index_dir = st.text_input("Index Directory", value=default_index_dir)
            tax_year = st.text_input("Tax Year (optional)", value="", placeholder="2025-2026")
        with selection_right:
            top_k = st.number_input("Top K", min_value=1, max_value=20, value=5, step=1)
            final_evidence_k = st.number_input("Final Evidence K", min_value=1, max_value=20, value=5, step=1)
        submitted = st.form_submit_button("Run Retrieval Inspection", use_container_width=True)

    if submitted:
        try:
            response_payload = run_local_retrieval_inspection(
                query_text=question_text,
                retrieval_mode=retrieval_mode,
                index_dir=index_dir,
                tax_year=tax_year or None,
                top_k=int(top_k),
                final_evidence_k=int(final_evidence_k),
            )
        except Exception as exc:  # pragma: no cover - defensive UI handling
            st.error(f"Retrieval inspection failed: {exc}")
        else:
            st.session_state["last_retrieval_inspector_response"] = response_payload
            st.success("Retrieval inspection completed.")

    response_payload = st.session_state.get("last_retrieval_inspector_response")
    if not response_payload:
        st.info("Run a local retrieval inspection to see analyzed query signals, tokens, and hits.")
        return

    st.markdown("**Analyzed Query**")
    st.json(response_payload.get("analyzed_query") or {})
    search_query = response_payload.get("search_query")
    if search_query:
        st.markdown("**Effective Search Query**")
        st.code(search_query, language="text")

    token_left, token_right = st.columns(2)
    with token_left:
        st.markdown("**Query Tokens**")
        st.code(" ".join(response_payload.get("query_tokens") or []), language="text")
    with token_right:
        st.markdown("**Salient Terms**")
        st.code(" ".join(response_payload.get("salient_terms") or []), language="text")

    conflict_notes = response_payload.get("conflict_notes") or []
    if conflict_notes:
        st.warning("Conflicts detected during final evidence selection.")
        for note in conflict_notes:
            st.write(f"- {note}")

    evidence_summary = response_payload.get("evidence_summary")
    if evidence_summary:
        st.markdown("**Evidence Summary**")
        st.code(evidence_summary, language="text")

    retrieval_mode = response_payload.get("retrieval_mode")
    if retrieval_mode == "hybrid":
        sparse_tab, dense_tab, fused_tab, final_tab = st.tabs(["Sparse", "Dense", "Fused", "Final Evidence"])
        with sparse_tab:
            sparse_hits = response_payload.get("sparse_hits") or []
            if not sparse_hits:
                st.caption("No sparse hits returned.")
            for hit in sparse_hits:
                render_hit_card(hit, show_intermediate_scores=True)
        with dense_tab:
            dense_hits = response_payload.get("dense_hits") or []
            if not dense_hits:
                st.caption("No dense hits returned.")
            for hit in dense_hits:
                render_hit_card(hit, show_intermediate_scores=True)
        with fused_tab:
            fused_hits = response_payload.get("fused_hits") or []
            if not fused_hits:
                st.caption("No fused hits returned.")
            for hit in fused_hits:
                render_hit_card(hit, show_intermediate_scores=True)
        with final_tab:
            final_hits = response_payload.get("final_hits") or []
            if not final_hits:
                st.caption("No final evidence hits returned.")
            for hit in final_hits:
                render_hit_card(hit, show_intermediate_scores=True)
        return

    st.markdown("**Retrieved Hits**")
    hits = response_payload.get("sparse_hits") if retrieval_mode == "sparse" else response_payload.get("dense_hits")
    if not hits:
        st.info("No hits returned.")
        return
    for hit in hits:
        render_hit_card(hit, show_intermediate_scores=True)


def render_comparison_result_column(mode_name: str, payload: dict[str, Any]) -> None:
    st.markdown(f"### {mode_name.title()}")
    analyzed_query = payload.get("analyzed_query") or {}
    answer_text = payload.get("answer")
    abstained = payload.get("abstained")
    confidence_score = payload.get("confidence_score")
    final_hits = payload.get("final_hits") or []
    generation_model_name = payload.get("generation_model_name")

    metric_columns = st.columns(3)
    metric_columns[0].metric("Answer Status", "Abstained" if abstained else ("Answered" if answer_text else "No Answer"))
    metric_columns[1].metric("Confidence", f"{confidence_score:.4f}" if isinstance(confidence_score, (int, float)) else "-")
    metric_columns[2].metric("Final Hits", str(len(final_hits)))
    if generation_model_name:
        st.caption(f"Generation model: {generation_model_name}")

    rewritten_query = analyzed_query.get("rewritten_query")
    if rewritten_query and rewritten_query != analyzed_query.get("normalized_query"):
        st.caption(f"Rewritten: {rewritten_query}")

    if abstained:
        st.warning(payload.get("abstention_reason") or "Generation abstained.")
    elif answer_text:
        st.markdown("**Answer**")
        st.write(answer_text)
    else:
        st.info("No answer returned.")

    top_hit = final_hits[0] if final_hits else None
    if top_hit:
        st.markdown("**Top Evidence**")
        st.caption(
            f"{top_hit.get('chunk_id')} | page {top_hit.get('page_no')} | "
            f"section {top_hit.get('section_id') or '-'} | score {top_hit.get('score', '-')}"
        )
        st.code((top_hit.get("original_text") or "")[:900], language="text")

    with st.expander("All Final Evidence", expanded=False):
        if not final_hits:
            st.caption("No final evidence hits returned.")
        for hit in final_hits:
            render_hit_compact_card(hit)

    if payload.get("conflict_notes"):
        with st.expander("Conflict Notes", expanded=False):
            for note in payload.get("conflict_notes") or []:
                st.write(f"- {note}")


def render_method_comparison(base_url: str) -> None:
    st.subheader("Method Comparison")
    st.caption("Run the same easy question through sparse, dense, and hybrid retrieval and compare answers side by side.")

    with st.expander("Easy Comparison Questions", expanded=False):
        selector_column, action_column = st.columns([3, 1])
        with selector_column:
            selected_question = st.selectbox(
                "Comparison Question Preset",
                options=COMPARISON_TEST_QUESTIONS,
                key="comparison_question_preset",
            )
        with action_column:
            st.write("")
            if st.button("Use For Comparison", use_container_width=True):
                st.session_state["comparison_question_text"] = selected_question
                st.session_state["last_comparison_responses"] = None
        for question in COMPARISON_TEST_QUESTIONS:
            st.code(question, language="text")

    with st.expander("Reference Questions And Expected Answers", expanded=False):
        st.caption("Use this as a quick oracle while comparing sparse, dense, and hybrid outputs.")
        st.markdown("**Best First Questions**")
        for question in COMPARISON_BEST_FIRST_QUESTIONS:
            st.code(question, language="text")

        categories: dict[str, list[dict[str, str]]] = {}
        for case in COMPARISON_REFERENCE_CASES:
            categories.setdefault(case["category"], []).append(case)

        for category, cases in categories.items():
            st.markdown(f"**{category}**")
            for case in cases:
                with st.container(border=True):
                    st.markdown(f"**Question:** {case['question']}")
                    st.markdown(f"**Expected:** {case['expected']}")
                    st.caption(f"Source: {case['source']}")

    with st.form("comparison_form", clear_on_submit=False):
        question_text = st.text_area(
            "Comparison Question",
            key="comparison_question_text",
            height=90,
            placeholder="Ask one clear question and compare how each retrieval method responds.",
        )
        form_left, form_middle, form_right = st.columns(3)
        with form_left:
            tax_year = st.text_input("Tax Year (optional)", value="", placeholder="2025-2026")
        with form_middle:
            top_k = st.number_input("Top K", min_value=1, max_value=20, value=5, step=1, key="comparison_top_k")
        with form_right:
            final_evidence_k = st.number_input(
                "Final Evidence K",
                min_value=1,
                max_value=20,
                value=3,
                step=1,
                key="comparison_final_evidence_k",
            )
        selected_modes = st.multiselect(
            "Methods To Compare",
            options=["sparse", "dense", "hybrid"],
            default=["sparse", "dense", "hybrid"],
            key="comparison_modes",
        )
        generate_answer = st.checkbox("Generate Grounded Answer", key="comparison_generate_answer")
        comparison_model_left, comparison_model_right = st.columns([2, 3])
        with comparison_model_left:
            st.selectbox(
                "Generator Model",
                options=OLLAMA_GENERATOR_MODEL_PRESETS,
                key="comparison_generator_model_preset",
                help="Applies the same Ollama model across compared retrieval methods.",
            )
        with comparison_model_right:
            if st.session_state.get("comparison_generator_model_preset") == "Custom...":
                st.text_input(
                    "Custom Generator Model",
                    key="comparison_custom_generator_model",
                    placeholder="e.g. qwen2.5:7b-instruct",
                )
        submitted = st.form_submit_button("Compare Methods", use_container_width=True)

    if submitted:
        if not selected_modes:
            st.error("Select at least one method to compare.")
        else:
            comparison_results: dict[str, Any] = {}
            selected_generator_model = resolve_selected_generator_model(
                preset_key="comparison_generator_model_preset",
                custom_key="comparison_custom_generator_model",
            )
            for mode_name in selected_modes:
                payload = {
                    "question_text": question_text,
                    "retrieval_mode": mode_name,
                    "tax_year": tax_year or None,
                    "top_k": int(top_k),
                    "final_evidence_k": int(final_evidence_k),
                    "include_intermediate_hits": True,
                    "generate_answer": generate_answer,
                    "generator_model_name": selected_generator_model if generate_answer else None,
                }
                success, response_payload, error_message = api_post(
                    base_url,
                    "/query",
                    payload,
                    timeout_seconds=QUERY_TIMEOUT_SECONDS,
                )
                comparison_results[mode_name] = (
                    response_payload if success and response_payload is not None
                    else {"status": "error", "error": error_message}
                )
            st.session_state["last_comparison_responses"] = comparison_results
            st.success("Method comparison completed.")

    comparison_results = st.session_state.get("last_comparison_responses")
    if not comparison_results:
        st.info("Run a comparison to see how sparse, dense, and hybrid behave on the same question.")
        return

    successful_results = {mode_name: payload for mode_name, payload in comparison_results.items() if payload.get("status") == "success"}
    failed_results = {mode_name: payload for mode_name, payload in comparison_results.items() if payload.get("status") != "success"}

    if failed_results:
        st.warning("Some methods failed during comparison.")
        for mode_name, payload in failed_results.items():
            st.write(f"- {mode_name}: {payload.get('error') or 'unknown error'}")

    if not successful_results:
        return

    all_top_chunks = {
        mode_name: ((payload.get("final_hits") or [{}])[0].get("chunk_id") if payload.get("final_hits") else None)
        for mode_name, payload in successful_results.items()
    }
    all_answers = {
        mode_name: bool(payload.get("answer")) and not payload.get("abstained")
        for mode_name, payload in successful_results.items()
    }
    summary_columns = st.columns(3)
    summary_columns[0].metric("Methods Compared", str(len(successful_results)))
    summary_columns[1].metric("Answered", str(sum(1 for answered in all_answers.values() if answered)))
    summary_columns[2].metric("Distinct Top Hits", str(len({chunk_id for chunk_id in all_top_chunks.values() if chunk_id})))

    st.markdown("**Top-1 Evidence Comparison**")
    st.json(all_top_chunks)

    result_columns = st.columns(len(successful_results))
    for column, (mode_name, payload) in zip(result_columns, successful_results.items(), strict=False):
        with column:
            render_comparison_result_column(mode_name, payload)


def render_agentic_results_panel(base_url: str, response_payload: dict[str, Any]) -> None:
    metric_columns = st.columns(4)
    metric_columns[0].metric("Query Type", str(response_payload.get("query_type") or "-"))
    metric_columns[1].metric("Execution Path", str(response_payload.get("execution_path") or "-"))
    metric_columns[2].metric("Confidence", f"{float(response_payload.get('confidence') or 0.0):.2f}")
    metric_columns[3].metric("Citations", str(len(response_payload.get("citations") or [])))

    answer_text = response_payload.get("answer")
    if answer_text:
        st.markdown("**Answer**")
        st.write(answer_text)
    else:
        st.info("No grounded answer returned.")

    reasoning_summary = response_payload.get("reasoning_summary") or []
    if reasoning_summary:
        st.markdown("**Reasoning Summary**")
        for note in reasoning_summary:
            st.write(f"- {note}")

    missing_facts = response_payload.get("missing_facts") or []
    if missing_facts:
        st.warning("Missing facts detected.")
        for item in missing_facts:
            st.write(f"- {item}")

    verification_failures = response_payload.get("verification_failures") or []
    if verification_failures:
        st.warning("Verification flagged unsupported or incomplete claims.")
        for failure in verification_failures:
            st.write(f"- {failure}")

    trace_id = response_payload.get("trace_id")
    if trace_id:
        st.caption(f"Trace ID: {trace_id}")
    render_citations(response_payload.get("citations") or [])

    trace_payload = st.session_state.get("last_trace_response")
    if (
        not isinstance(trace_payload, dict)
        and isinstance(trace_id, str)
        and trace_id
    ):
        trace_ok, fetched_trace, _ = api_get(base_url, f"/trace/{trace_id}")
        trace_payload = fetched_trace if trace_ok else None
        st.session_state["last_trace_response"] = trace_payload

    if isinstance(trace_payload, dict):
        trace_state = trace_payload.get("state") or {}
        st.markdown("**Trace Summary**")
        trace_columns = st.columns(4)
        trace_columns[0].metric("Completed Nodes", str(len(trace_state.get("completed_nodes") or [])))
        trace_columns[1].metric("Evidence Items", str(len(trace_state.get("retrieved_evidence") or [])))
        trace_columns[2].metric("Pack Type", str(trace_state.get("latest_evidence_pack_type") or "-"))
        trace_columns[3].metric("Retrieval Attempts", str(len(trace_state.get("retrieval_attempts") or [])))
        if trace_state.get("completed_nodes"):
            st.caption(" -> ".join(trace_state.get("completed_nodes") or []))
        with st.expander("Trace Payload", expanded=False):
            st.json(trace_payload)


def render_results_panel(base_url: str) -> None:
    st.subheader("Results")
    response_payload = st.session_state.get("last_query_response")
    if not response_payload:
        st.info("Run a query to view analyzed query signals, grounded answers, and evidence hits.")
        return

    if is_agentic_response(response_payload):
        render_agentic_results_panel(base_url, response_payload)
        return

    analyzed_query = response_payload.get("analyzed_query", {})
    st.markdown("**Analyzed Query**")
    st.json(analyzed_query)
    rewritten_query = analyzed_query.get("rewritten_query")
    if rewritten_query and rewritten_query != analyzed_query.get("normalized_query"):
        st.markdown("**Rewritten Query**")
        st.code(rewritten_query, language="text")

    answer_text = response_payload.get("answer")
    abstained = response_payload.get("abstained")
    abstention_reason = response_payload.get("abstention_reason")
    confidence_score = response_payload.get("confidence_score")
    generation_model_name = response_payload.get("generation_model_name")
    if generation_model_name:
        st.caption(f"Generation model: {generation_model_name}")
    if abstained:
        st.warning(f"Generation abstained. {abstention_reason or ''}".strip())
    elif answer_text:
        st.markdown("**Answer**")
        st.write(answer_text)
    else:
        st.info("Generation disabled or no answer returned.")

    if confidence_score is not None:
        st.metric("Confidence Score", f"{confidence_score:.4f}")

    conflict_notes = response_payload.get("conflict_notes") or []
    if conflict_notes:
        st.warning("Conflicts detected in evidence.")
        for note in conflict_notes:
            st.write(f"- {note}")

    render_citations(response_payload.get("citations") or [])

    st.markdown("**Final Evidence Hits**")
    final_hits = response_payload.get("final_hits") or []
    if not final_hits:
        st.info("No final evidence hits returned.")
    for hit in final_hits:
        render_hit_card(hit)

    if (
        response_payload.get("sparse_hits")
        or response_payload.get("dense_hits")
        or response_payload.get("fused_hits")
    ):
        st.markdown("**Intermediate Retrieval Views**")
        sparse_tab, dense_tab, fused_tab = st.tabs(["Sparse", "Dense", "Fused"])
        with sparse_tab:
            sparse_hits = response_payload.get("sparse_hits") or []
            if not sparse_hits:
                st.caption("No sparse hits returned.")
            for hit in sparse_hits:
                render_hit_card(hit)
        with dense_tab:
            dense_hits = response_payload.get("dense_hits") or []
            if not dense_hits:
                st.caption("No dense hits returned.")
            for hit in dense_hits:
                render_hit_card(hit)
        with fused_tab:
            fused_hits = response_payload.get("fused_hits") or []
            if not fused_hits:
                st.caption("No fused hits returned.")
            for hit in fused_hits:
                render_hit_card(hit)


def main() -> None:
    initialize_session_state()
    st.set_page_config(page_title="Bangla Tax RAG", layout="wide")
    st.title("Bangla Tax RAG")
    st.caption("Research UI for PDF ingestion, index building, grounded retrieval, and cited answer exploration.")

    st.sidebar.header("Navigation")
    view_name = st.sidebar.radio(
        "View",
        options=[
            "Research Workspace",
            "Parser Inspector",
            "Index Inspector",
            "Dense Vector Inspector",
            "Retrieval Inspector",
            "Method Comparison",
        ],
        index=0,
    )

    config_payload, api_reachable = render_api_connection_panel(st.session_state["backend_base_url"])
    if not api_reachable:
        st.warning("Backend API is not confirmed reachable. You can still fill the forms, but actions may fail until the API is running.")
    if config_payload:
        with st.expander("Runtime Config Snapshot", expanded=False):
            st.json(config_payload)

    if view_name == "Parser Inspector":
        render_parser_inspector()
        return
    if view_name == "Index Inspector":
        render_index_inspector()
        return
    if view_name == "Dense Vector Inspector":
        render_dense_vector_inspector()
        return
    if view_name == "Retrieval Inspector":
        render_retrieval_inspector()
        return
    if view_name == "Method Comparison":
        render_method_comparison(st.session_state["backend_base_url"])
        return

    ingest_column, build_column = st.columns(2)
    with ingest_column:
        render_ingestion_panel(st.session_state["backend_base_url"])
    with build_column:
        render_index_building_panel(st.session_state["backend_base_url"])

    render_chunk_browser()
    render_query_panel(st.session_state["backend_base_url"])
    render_results_panel(st.session_state["backend_base_url"])


if __name__ == "__main__":
    main()
