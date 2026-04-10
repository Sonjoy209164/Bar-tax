import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from app.core.schemas import ChunkRecord, QuerySignals, RetrievalHit
from app.retrieval import dense, reranker


def _write_chunks(path: Path, chunks: list[ChunkRecord]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for chunk in chunks:
            handle.write(json.dumps(chunk.model_dump(), ensure_ascii=False) + "\n")


def _make_chunk(*, chunk_id: str, text: str, heading: str, page_no: int) -> ChunkRecord:
    return ChunkRecord(
        chunk_id=chunk_id,
        doc_id="income-tax-act-2023",
        doc_title="Income Tax Act 2023",
        doc_type="statute",
        authority_level="national",
        page_no=page_no,
        section_id="2",
        subsection_id=None,
        chunk_type="text",
        heading_path=[heading],
        original_text=text,
        normalized_text=text,
    )


def test_build_dense_index_transformers_materializes_artifacts(monkeypatch, tmp_path: Path) -> None:
    chunks = [
        _make_chunk(chunk_id="c1", text="Commissioner means Commissioner of Taxes.", heading="2. Definitions", page_no=6),
        _make_chunk(chunk_id="c2", text="Tax Day means 30 November.", heading="2. Definitions", page_no=7),
    ]
    chunk_path = tmp_path / "chunks.jsonl"
    _write_chunks(chunk_path, chunks)

    monkeypatch.setattr(
        dense,
        "_encode_texts_with_transformers",
        lambda texts, **_: np.array([[1.0, 0.0], [0.0, 1.0]], dtype="float32"),
    )

    output_dir, chunk_count = dense.build_dense_index_artifacts(
        chunk_path,
        tmp_path / "dense",
        provider="transformers",
        model_name="demo/bge-m3",
        use_faiss=True,
    )
    metadata = dense.load_dense_index_metadata(output_dir)

    assert chunk_count == 2
    assert metadata["index_type"] == "dense_transformers"
    assert metadata["model_name"] == "demo/bge-m3"
    assert (output_dir / "embeddings.npy").exists()
    if dense.faiss is not None:
        assert metadata["index_backend"] == "faiss"
        assert (output_dir / "index.faiss").exists()
    else:
        assert metadata["index_backend"] == "numpy"


def test_dense_search_ranks_semantic_match_first(monkeypatch, tmp_path: Path) -> None:
    chunks = [
        _make_chunk(chunk_id="c1", text="Commissioner means Commissioner of Taxes.", heading="2. Definitions", page_no=6),
        _make_chunk(chunk_id="c2", text="Tax Day means 30 November.", heading="2. Definitions", page_no=7),
    ]
    chunk_path = tmp_path / "chunks.jsonl"
    _write_chunks(chunk_path, chunks)

    def fake_encode(texts, **_):  # type: ignore[no-untyped-def]
        vectors = []
        for text in texts:
            normalized = text.lower()
            if "commissioner" in normalized:
                vectors.append([1.0, 0.0])
            else:
                vectors.append([0.0, 1.0])
        return np.array(vectors, dtype="float32")

    monkeypatch.setattr(dense, "_encode_texts_with_transformers", fake_encode)
    dense.build_dense_index_artifacts(
        chunk_path,
        tmp_path / "dense",
        provider="transformers",
        model_name="demo/bge-m3",
        use_faiss=False,
    )

    hits = dense.dense_search(
        "What is the definition of Commissioner?",
        top_k=2,
        index_dir=tmp_path / "dense",
    )

    assert hits[0]["chunk_id"] == "c1"
    assert hits[0]["intermediate_scores"]["dense_similarity"] >= hits[1]["intermediate_scores"]["dense_similarity"]


def test_model_reranker_can_reorder_hits(monkeypatch) -> None:
    analyzed_query = QuerySignals(
        original_query="What is the definition of Commissioner?",
        normalized_query="What is the definition of Commissioner?",
        query_type="definition",
        query_intent="definition",
    )
    hits = [
        RetrievalHit(
            chunk_id="c1",
            doc_id="doc",
            doc_title="Doc",
            page_no=1,
            section_id="2",
            subsection_id=None,
            chunk_type="text",
            authority_level="national",
            tax_year=None,
            original_text="Tax Day means 30 November.",
            normalized_text="Tax Day means 30 November.",
            heading_path=["2. Definitions"],
            content="Tax Day means 30 November.",
            score=5.0,
            intermediate_scores={},
        ),
        RetrievalHit(
            chunk_id="c2",
            doc_id="doc",
            doc_title="Doc",
            page_no=2,
            section_id="2",
            subsection_id=None,
            chunk_type="text",
            authority_level="national",
            tax_year=None,
            original_text="Commissioner means Commissioner of Taxes.",
            normalized_text="Commissioner means Commissioner of Taxes.",
            heading_path=["2. Definitions"],
            content="Commissioner means Commissioner of Taxes.",
            score=4.0,
            intermediate_scores={},
        ),
    ]

    monkeypatch.setattr(
        reranker,
        "get_settings",
        lambda: SimpleNamespace(reranker_provider="transformers", reranker_model_name="demo/reranker"),
    )
    monkeypatch.setattr(reranker, "_score_pairs_with_transformers", lambda *_, **__: [0.1, 0.95])

    reranked_hits = reranker.rerank_retrieval_hits(
        query_text=analyzed_query.original_query,
        analyzed_query=analyzed_query,
        hits=hits,
        top_n=2,
    )

    assert reranked_hits[0].chunk_id == "c2"
    assert reranked_hits[0].intermediate_scores["model_reranker_score"] == 0.95
