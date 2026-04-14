import numpy as np

from app.domain import CitationRelation
from app.ingestion import (
    ParsedDocument,
    build_legal_chunks,
    build_legal_structure,
    build_parsed_page_from_text,
    link_parent_child_relationships,
    tag_legal_metadata,
)
from app.retrieval import (
    DeterministicTextEmbedder,
    EmbedderConfig,
    EmbeddingProvider,
    HybridRetriever,
    HybridSearchRequest,
    VectorRecord,
    VectorSearchMatch,
    VectorSearchResult,
    VectorStore,
    VectorStoreConfig,
    VectorStoreProvider,
    VectorStoreStats,
    build_bm25_index,
)


class InMemoryVectorStore(VectorStore):
    def __init__(self) -> None:
        super().__init__(VectorStoreConfig(provider=VectorStoreProvider.PINECONE, dimensions=32))
        self.records: dict[str, VectorRecord] = {}

    def upsert(self, records: list[VectorRecord], *, namespace: str | None = None) -> None:
        for record in records:
            effective_namespace = namespace or record.namespace
            self.records[record.record_id] = record.model_copy(update={"namespace": effective_namespace})

    def query(
        self,
        query_vector: list[float],
        *,
        top_k: int,
        filters: dict | None = None,
        namespace: str | None = None,
    ) -> VectorSearchResult:
        query_array = np.asarray(query_vector, dtype=np.float32)
        matches: list[VectorSearchMatch] = []
        for record in self.records.values():
            if namespace and record.namespace != namespace:
                continue
            if not _metadata_matches(record.metadata, filters or {}):
                continue
            score = float(np.dot(query_array, np.asarray(record.vector, dtype=np.float32)))
            matches.append(
                VectorSearchMatch(
                    record_id=record.record_id,
                    score=score,
                    metadata=record.metadata,
                    text=record.text,
                    namespace=record.namespace,
                )
            )
        ranked = sorted(matches, key=lambda item: item.score, reverse=True)[:top_k]
        return VectorSearchResult(provider=self.provider, matches=ranked, top_k=top_k, namespace=namespace)

    def delete(self, record_ids: list[str], *, namespace: str | None = None) -> None:
        for record_id in record_ids:
            self.records.pop(record_id, None)

    def describe(self, *, namespace: str | None = None) -> VectorStoreStats:
        count = sum(1 for record in self.records.values() if namespace is None or record.namespace == namespace)
        return VectorStoreStats(provider=self.provider, index_name="in-memory", total_vector_count=count, namespace=namespace)


def test_hybrid_retriever_merges_sparse_and_dense_for_definition_and_returns_parent_context() -> None:
    linked_document, chunks = _definition_fixture()
    embedder = DeterministicTextEmbedder(
        EmbedderConfig(provider=EmbeddingProvider.DETERMINISTIC, model_name="deterministic", dimensions=32)
    )
    vector_store = _vector_store_for_chunks(chunks, embedder)
    retriever = HybridRetriever(
        linked_document=linked_document,
        chunks_or_artifacts=chunks,
        embedder=embedder,
        vector_store=vector_store,
        bm25_index=build_bm25_index(chunks),
    )

    result = retriever.search(HybridSearchRequest(question="What is the definition of Commissioner?"))

    assert result.candidates
    top_candidate = result.candidates[0]
    assert top_candidate.chunk.section_number == "2"
    assert top_candidate.sparse_score is not None
    assert top_candidate.dense_score is not None
    relations = {item.citation.relation for item in top_candidate.evidence}
    assert CitationRelation.DIRECT in relations
    assert CitationRelation.PARENT_CONTEXT in relations


def test_hybrid_retriever_returns_table_candidate_with_governing_section_context() -> None:
    linked_document, chunks = _table_fixture()
    embedder = DeterministicTextEmbedder(
        EmbedderConfig(provider=EmbeddingProvider.DETERMINISTIC, model_name="deterministic", dimensions=32)
    )
    vector_store = _vector_store_for_chunks(chunks, embedder)
    retriever = HybridRetriever(
        linked_document=linked_document,
        chunks_or_artifacts=chunks,
        embedder=embedder,
        vector_store=vector_store,
        bm25_index=build_bm25_index(chunks),
    )

    result = retriever.search(
        HybridSearchRequest(
            question="What tax rate applies to stock dividend under section 23?",
        )
    )

    assert result.candidates
    top_candidate = result.candidates[0]
    assert top_candidate.chunk.section_number == "23"
    relations = {item.citation.relation for item in top_candidate.evidence}
    assert CitationRelation.DIRECT in relations
    assert CitationRelation.PARENT_CONTEXT in relations or CitationRelation.ATTACHED_TABLE in relations


def test_hybrid_retriever_applies_filters_before_sparse_dense_merge() -> None:
    linked_document, chunks = _table_fixture()
    target_chunk = next(chunk for chunk in chunks if chunk.chunk_variant == "table_row")
    older_chunk = target_chunk.model_copy(
        update={
            "chunk_id": "income-tax-act-2023-older-row",
            "text": "Stock dividend | 15 percent | older year",
            "normalized_text": "stock dividend 15 percent older year",
            "metadata": {**target_chunk.metadata, "tax_year": "2024-2025"},
        }
    )
    target_chunk = target_chunk.model_copy(
        update={
            "text": "Stock dividend | 10 percent | current year",
            "normalized_text": "stock dividend 10 percent current year",
            "metadata": {**target_chunk.metadata, "tax_year": "2025-2026"},
        }
    )
    chunks = [target_chunk, older_chunk, *[chunk for chunk in chunks if chunk.chunk_id != target_chunk.chunk_id]]

    embedder = DeterministicTextEmbedder(
        EmbedderConfig(provider=EmbeddingProvider.DETERMINISTIC, model_name="deterministic", dimensions=32)
    )
    vector_store = _vector_store_for_chunks(chunks, embedder)
    retriever = HybridRetriever(
        linked_document=linked_document,
        chunks_or_artifacts=chunks,
        embedder=embedder,
        vector_store=vector_store,
        bm25_index=build_bm25_index(chunks),
    )

    result = retriever.search(
        HybridSearchRequest(
            question="What tax rate applies to stock dividend under section 23?",
            filters={"tax_year": {"$eq": "2025-2026"}},
        )
    )

    assert result.candidates
    assert all(candidate.chunk.metadata.get("tax_year") == "2025-2026" for candidate in result.candidates)
    assert result.candidates[0].chunk.chunk_id == target_chunk.chunk_id


def _definition_fixture():
    parsed_document = ParsedDocument(
        source_path="Income_tax_act_2023.pdf",
        parser_provider="fallback",
        pages=[
            build_parsed_page_from_text(
                1,
                "\n".join(
                    [
                        "2. Definitions.— In this Act, unless there is anything repugnant in the subject or context,—",
                        '(1) "Commissioner" means Commissioner of Taxes.',
                        "(a) Chief Commissioner of Taxes;",
                        "Provided that this definition applies only where the context so requires.",
                        "Explanation 1.— Reference to Commissioner includes Large Taxpayer Unit.",
                    ]
                ),
            )
        ],
    )
    structured = build_legal_structure(parsed_document, document_id="income-tax-act-2023", act_title="Income Tax Act 2023")
    linked = link_parent_child_relationships(tag_legal_metadata(structured))
    artifacts = build_legal_chunks(linked)
    return linked, artifacts.retrieval_chunks


def _table_fixture():
    parsed_document = ParsedDocument(
        source_path="Income_tax_act_2023.pdf",
        parser_provider="fallback",
        pages=[
            build_parsed_page_from_text(
                10,
                "\n".join(
                    [
                        "23. Tax on stock dividend.—The tax shall be charged at the following rates:",
                        "Serial | Income | Rate",
                        "1 | Stock dividend | 10 percent",
                        "2 | Cash dividend | 20 percent",
                    ]
                ),
            )
        ],
    )
    structured = build_legal_structure(parsed_document, document_id="income-tax-act-2023", act_title="Income Tax Act 2023")
    linked = link_parent_child_relationships(tag_legal_metadata(structured))
    artifacts = build_legal_chunks(linked)
    return linked, artifacts.retrieval_chunks


def _vector_store_for_chunks(chunks: list, embedder: DeterministicTextEmbedder) -> InMemoryVectorStore:
    vector_store = InMemoryVectorStore()
    batch = embedder.embed_texts([chunk.normalized_text for chunk in chunks])
    vector_store.upsert(
        [
            VectorRecord(
                record_id=chunk.chunk_id,
                vector=vector,
                metadata={
                    "section_number": chunk.section_number,
                    "chunk_type": chunk.chunk_type,
                    **chunk.metadata,
                },
                text=chunk.text,
            )
            for chunk, vector in zip(chunks, batch.vectors, strict=True)
        ]
    )
    return vector_store


def _metadata_matches(metadata: dict, filters: dict) -> bool:
    for key, expected in filters.items():
        actual = metadata.get(key)
        if isinstance(expected, dict):
            for operator, operand in expected.items():
                if operator == "$eq" and actual != operand:
                    return False
                if operator == "$in" and actual not in operand:
                    return False
                if operator == "$gte" and (actual is None or actual < operand):
                    return False
                if operator == "$lte" and (actual is None or actual > operand):
                    return False
            continue
        if actual != expected:
            return False
    return True
