import numpy as np

from app.ingestion import (
    ParsedDocument,
    build_legal_chunks,
    build_legal_structure,
    build_parsed_page_from_text,
    link_parent_child_relationships,
    tag_legal_metadata,
)
from app.retrieval import (
    CohereDocumentReranker,
    DeterministicDocumentReranker,
    DeterministicTextEmbedder,
    DocumentReranker,
    EmbedderConfig,
    EmbeddingProvider,
    HybridRetriever,
    HybridSearchRequest,
    RerankResult,
    RerankedDocument,
    RerankerConfig,
    RerankerDocument,
    RerankerProvider,
    TransformersDocumentReranker,
    VectorRecord,
    VectorSearchMatch,
    VectorSearchResult,
    VectorStore,
    VectorStoreConfig,
    VectorStoreProvider,
    VectorStoreStats,
    build_bm25_index,
    build_reranker,
)
from app.retrieval import reranker as reranker_module


class InMemoryVectorStore(VectorStore):
    def __init__(self) -> None:
        super().__init__(VectorStoreConfig(provider=VectorStoreProvider.PINECONE, dimensions=32))
        self.records: dict[str, VectorRecord] = {}

    def upsert(self, records: list[VectorRecord], *, namespace: str | None = None) -> None:
        for record in records:
            self.records[record.record_id] = record.model_copy(update={"namespace": namespace or record.namespace})

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
        matches.sort(key=lambda item: item.score, reverse=True)
        return VectorSearchResult(provider=self.provider, matches=matches[:top_k], top_k=top_k, namespace=namespace)

    def delete(self, record_ids: list[str], *, namespace: str | None = None) -> None:
        for record_id in record_ids:
            self.records.pop(record_id, None)

    def describe(self, *, namespace: str | None = None) -> VectorStoreStats:
        return VectorStoreStats(provider=self.provider, index_name="in-memory", total_vector_count=len(self.records))


class FixedOrderReranker(DocumentReranker):
    def rerank(self, query_text: str, documents: list[RerankerDocument], *, top_k: int | None = None) -> RerankResult:
        ordered = sorted(documents, key=lambda item: item.document_id, reverse=True)
        limited = ordered[: top_k or len(ordered)]
        return RerankResult(
            provider=self.provider,
            model_name=self.config.model_name,
            top_k=len(limited),
            backend="fixed_order_test",
            results=[
                RerankedDocument(
                    document_id=document.document_id,
                    text=document.text,
                    metadata=document.metadata,
                    relevance_score=1.0 - (index * 0.1),
                    rank=index + 1,
                )
                for index, document in enumerate(limited)
            ],
        )


def test_build_reranker_factory_supports_all_future_providers() -> None:
    deterministic = build_reranker(
        RerankerConfig(provider=RerankerProvider.DETERMINISTIC, model_name="deterministic-test")
    )
    assert isinstance(deterministic, DeterministicDocumentReranker)

    transformers = build_reranker(
        RerankerConfig(provider=RerankerProvider.TRANSFORMERS, model_name="demo-cross-encoder")
    )
    assert isinstance(transformers, TransformersDocumentReranker)

    cohere = build_reranker(
        RerankerConfig(provider=RerankerProvider.COHERE, model_name="rerank-v3.5", api_key="token")
    )
    assert isinstance(cohere, CohereDocumentReranker)

    assert build_reranker(RerankerConfig(provider=RerankerProvider.NONE, model_name="none")) is None


def test_deterministic_reranker_prefers_higher_overlap_document() -> None:
    reranker = DeterministicDocumentReranker(
        RerankerConfig(provider=RerankerProvider.DETERMINISTIC, model_name="deterministic")
    )

    result = reranker.rerank(
        "What is the definition of Commissioner?",
        [
            RerankerDocument(document_id="general", text="Commissioner may issue directions under this Act."),
            RerankerDocument(document_id="definition", text='"Commissioner" means Commissioner of Taxes.'),
        ],
        top_k=2,
    )

    assert result.results[0].document_id == "definition"
    assert result.results[0].relevance_score >= result.results[1].relevance_score


def test_cohere_reranker_posts_expected_payload_and_parses_results(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "results": [
                    {"index": 1, "relevance_score": 0.91},
                    {"index": 0, "relevance_score": 0.42},
                ]
            }

    class FakeClient:
        def __init__(self, *, timeout):
            captured["timeout"] = timeout

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, url, *, headers, json):
            captured["url"] = url
            captured["headers"] = headers
            captured["json"] = json
            return FakeResponse()

    monkeypatch.setattr(reranker_module.httpx, "Client", FakeClient)

    reranker = CohereDocumentReranker(
        RerankerConfig(
            provider=RerankerProvider.COHERE,
            model_name="rerank-v3.5",
            api_key="secret",
        )
    )
    result = reranker.rerank(
        "What is the definition of Commissioner?",
        [
            RerankerDocument(document_id="d1", text="Tax Day means 30 November."),
            RerankerDocument(document_id="d2", text='"Commissioner" means Commissioner of Taxes.'),
        ],
        top_k=2,
    )

    assert captured["url"] == f"{reranker_module.DEFAULT_COHERE_BASE_URL}/rerank"
    assert captured["json"] == {
        "model": "rerank-v3.5",
        "query": "What is the definition of Commissioner?",
        "documents": ["Tax Day means 30 November.", '"Commissioner" means Commissioner of Taxes.'],
        "top_n": 2,
    }
    assert result.results[0].document_id == "d2"
    assert result.results[0].relevance_score == 0.91


def test_hybrid_retriever_records_reranker_scores_and_uses_reranked_order() -> None:
    linked_document, chunks = _fixture()
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
        reranker=FixedOrderReranker(RerankerConfig(provider=RerankerProvider.DETERMINISTIC, model_name="fixed")),
    )

    result = retriever.search(HybridSearchRequest(question="What is the definition of Commissioner?"))

    assert result.candidates
    assert result.candidates[0].chunk.chunk_id > result.candidates[-1].chunk.chunk_id
    assert result.candidates[0].metadata["reranker_backend"] == "fixed_order_test"
    assert result.candidates[0].metadata["reranker_score"] is not None
    assert result.candidates[0].metadata["reranker_rank"] == 1


def _fixture():
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
                        "(b) Commissioner of Taxes (Appeals);",
                    ]
                ),
            )
        ],
    )
    structured = build_legal_structure(parsed_document, document_id="income-tax-act-2023", act_title="Income Tax Act 2023")
    linked = link_parent_child_relationships(tag_legal_metadata(structured))
    artifacts = build_legal_chunks(linked)
    return linked, artifacts.retrieval_chunks


def _vector_store_for_chunks(chunks, embedder):
    store = InMemoryVectorStore()
    batch = embedder.embed_texts([chunk.normalized_text for chunk in chunks])
    store.upsert(
        [
            VectorRecord(
                record_id=chunk.chunk_id,
                vector=vector,
                metadata={"section_number": chunk.section_number, "chunk_type": chunk.chunk_type, **chunk.metadata},
                text=chunk.text,
            )
            for chunk, vector in zip(chunks, batch.vectors, strict=True)
        ]
    )
    return store
