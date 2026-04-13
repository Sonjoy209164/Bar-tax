from pathlib import Path

import numpy as np

from app.core.prompts import build_prompt_registry, render_prompt
from app.domain import QueryType
from app.ingestion import (
    DocumentParser,
    ParsedDocument,
    build_legal_chunks,
    build_legal_structure,
    build_parsed_page_from_text,
    link_parent_child_relationships,
    tag_legal_metadata,
)
from app.reasoning import ReasoningGraphConfig, ReasoningGraphDependencies, build_agent_graph
from app.retrieval import (
    DeterministicTextEmbedder,
    EmbedderConfig,
    EmbeddingProvider,
    HybridRetriever,
    QueryTransformer,
    VectorRecord,
    VectorSearchMatch,
    VectorSearchResult,
    VectorStore,
    VectorStoreConfig,
    VectorStoreProvider,
    VectorStoreStats,
    build_bm25_index,
)
from app.services import (
    EvaluationCase,
    EvaluationService,
    IngestService,
    IngestServiceConfig,
    QueryRequest,
    QueryService,
)


class FakeParser(DocumentParser):
    provider_name = "fake"

    def __init__(self, parsed_document: ParsedDocument) -> None:
        self._parsed_document = parsed_document

    def parse(self, source_path: str | Path) -> ParsedDocument:
        return self._parsed_document


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


def test_prompt_registry_renders_planner_prompt() -> None:
    registry = build_prompt_registry()

    rendered = registry.planner.render(
        question="What tax rate applies to stock dividend?",
        query_type="rate_lookup",
        facts_from_user=[],
        pack_notes=["Need governing rule and table row."],
    )

    assert rendered[0]["role"] == "system"
    assert "legal-tax planner" in rendered[0]["content"].lower()
    assert "What tax rate applies to stock dividend?" in rendered[1]["content"]


def test_render_prompt_helper_works_for_verifier() -> None:
    rendered = render_prompt(
        "verifier",
        draft_answer="The tax rate is 10 percent.",
        evidence=["Stock dividend | 10 percent"],
    )

    assert rendered[1]["role"] == "user"
    assert "10 percent" in rendered[1]["content"]


def test_ingest_service_persists_graph_and_upserts_vectors(tmp_path: Path) -> None:
    parsed_document = _table_document()
    vector_store = InMemoryVectorStore()
    embedder = DeterministicTextEmbedder(
        EmbedderConfig(provider=EmbeddingProvider.DETERMINISTIC, model_name="deterministic", dimensions=32)
    )
    service = IngestService(
        parser=FakeParser(parsed_document),
        embedder=embedder,
        vector_store=vector_store,
        config=IngestServiceConfig(output_root=str(tmp_path)),
    )

    result = service.ingest(parsed_document.source_path, document_id="income-tax-act-2023", act_title="Income Tax Act 2023")

    assert result.document_store.graph_path
    assert Path(result.document_store.graph_path).exists()
    assert Path(result.bm25_index_dir).exists()
    assert result.vector_record_count == len(vector_store.records)
    assert result.retrieval_chunk_count > 0


def test_query_service_returns_api_shaped_response() -> None:
    query_service = _build_query_service(_table_document())

    response = query_service.run(
        QueryRequest(
            question="What tax rate applies to stock dividend under section 23?",
            query_type=QueryType.RATE_LOOKUP,
        )
    )

    assert response.answer
    assert "10 percent" in response.answer.lower()
    assert response.citations
    assert response.trace_id
    assert response.query_type is QueryType.RATE_LOOKUP


def test_evaluation_service_scores_cases() -> None:
    query_service = _build_query_service(_table_document())
    evaluation_service = EvaluationService(query_service=query_service)

    summary = evaluation_service.evaluate(
        [
            EvaluationCase(
                case_id="stock-dividend-rate",
                question="What tax rate applies to stock dividend under section 23?",
                expected_sections=["23"],
                required_substrings=["10 percent"],
            )
        ]
    )

    assert summary.total_cases == 1
    assert summary.passed_cases == 1
    assert summary.accuracy == 1.0


def _build_query_service(parsed_document: ParsedDocument) -> QueryService:
    structured = build_legal_structure(parsed_document, document_id="income-tax-act-2023", act_title="Income Tax Act 2023")
    linked = link_parent_child_relationships(tag_legal_metadata(structured))
    artifacts = build_legal_chunks(linked)
    retrieval_chunks = artifacts.retrieval_chunks
    embedder = DeterministicTextEmbedder(
        EmbedderConfig(provider=EmbeddingProvider.DETERMINISTIC, model_name="deterministic", dimensions=32)
    )
    vector_store = InMemoryVectorStore()
    batch = embedder.embed_texts([chunk.normalized_text for chunk in retrieval_chunks])
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
            for chunk, vector in zip(retrieval_chunks, batch.vectors, strict=True)
        ]
    )
    retriever = HybridRetriever(
        linked_document=linked,
        chunks_or_artifacts=artifacts,
        embedder=embedder,
        vector_store=vector_store,
        bm25_index=build_bm25_index(retrieval_chunks),
        query_transformer=QueryTransformer(),
    )
    graph = build_agent_graph(
        dependencies=ReasoningGraphDependencies(
            hybrid_retriever=retriever,
            query_transformer=QueryTransformer(),
        ),
        config=ReasoningGraphConfig(top_k=5, max_retrieval_loops=2, prefer_langgraph_backend=False),
    )
    return QueryService(reasoning_graph=graph)


def _table_document() -> ParsedDocument:
    return ParsedDocument(
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
