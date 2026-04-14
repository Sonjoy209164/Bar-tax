import numpy as np

from app.domain import QueryExecutionPath, QueryType
from app.ingestion import (
    ParsedDocument,
    build_legal_chunks,
    build_legal_structure,
    build_parsed_page_from_text,
    link_parent_child_relationships,
    tag_legal_metadata,
)
from app.reasoning import (
    AgentState,
    ReasoningGraphConfig,
    ReasoningGraphDependencies,
    build_agent_graph,
)
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


def test_reasoning_graph_definition_flow_produces_grounded_answer() -> None:
    graph = _build_graph(_definition_document())

    state = graph.invoke(
        AgentState(
            question="What is the definition of Commissioner?",
            query_type=QueryType.DEFINITION,
            execution_path=QueryExecutionPath.FAST_PATH,
            max_reasoning_steps=6,
        )
    )

    assert state.final_answer
    assert "Under the retrieved definition" in state.final_answer
    assert "commissioner" in state.final_answer.lower()
    assert "Under the retrieved definition, 2." not in state.final_answer
    assert state.citations
    assert state.completed_nodes == ["router", "planner", "retrieve", "reason", "verify", "compose"]
    assert state.confidence is not None and state.confidence > 0.5


def test_reasoning_graph_rate_lookup_keeps_supported_numeric_answer() -> None:
    graph = _build_graph(_table_document())

    state = graph.invoke(
        "What tax rate applies to stock dividend under section 23?",
        query_type=QueryType.RATE_LOOKUP,
        max_reasoning_steps=6,
    )

    assert state.final_answer
    assert "10 percent" in state.final_answer.lower()
    assert state.has_verification_errors is False
    assert state.latest_evidence_pack_type == "rate_table"


def test_reasoning_graph_eligibility_flow_tracks_missing_facts() -> None:
    graph = _build_graph(_eligibility_document())

    state = graph.invoke(
        AgentState(
            question="I am a labour, what will be my tax?",
            query_type=QueryType.ELIGIBILITY,
            execution_path=QueryExecutionPath.AGENTIC,
            max_reasoning_steps=6,
        )
    )

    assert state.final_answer
    assert state.missing_facts
    assert any("annual income" in fact.lower() for fact in state.missing_facts)
    assert "Missing facts:" in state.final_answer
    assert state.should_enter_agent_loop is True


def test_reasoning_graph_clarification_route_short_circuits_to_refusal() -> None:
    graph = _build_graph(_definition_document())

    state = graph.invoke(
        AgentState(
            question="Tell me the exact hidden tax rule not shown here.",
            query_type=QueryType.UNSUPPORTED_OR_UNDERSPECIFIED,
            execution_path=QueryExecutionPath.CLARIFICATION,
            max_reasoning_steps=6,
        )
    )

    assert state.final_answer
    assert "Information not found in retrieved evidence." in state.final_answer
    assert state.retrieval_attempts == []
    assert state.completed_nodes == ["router", "compose"]


def _build_graph(parsed_document: ParsedDocument):
    structured = build_legal_structure(parsed_document, document_id="income-tax-act-2023", act_title="Income Tax Act 2023")
    linked = link_parent_child_relationships(tag_legal_metadata(structured))
    artifacts = build_legal_chunks(linked)
    retrieval_chunks = artifacts.retrieval_chunks
    embedder = DeterministicTextEmbedder(
        EmbedderConfig(provider=EmbeddingProvider.DETERMINISTIC, model_name="deterministic", dimensions=32)
    )
    vector_store = _vector_store_for_chunks(retrieval_chunks, embedder)
    retriever = HybridRetriever(
        linked_document=linked,
        chunks_or_artifacts=artifacts,
        embedder=embedder,
        vector_store=vector_store,
        bm25_index=build_bm25_index(retrieval_chunks),
        query_transformer=QueryTransformer(),
    )
    return build_agent_graph(
        dependencies=ReasoningGraphDependencies(
            hybrid_retriever=retriever,
            query_transformer=QueryTransformer(),
        ),
        config=ReasoningGraphConfig(top_k=5, max_retrieval_loops=2, prefer_langgraph_backend=False),
    )


def _definition_document() -> ParsedDocument:
    return ParsedDocument(
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
                    ]
                ),
            )
        ],
    )


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


def _eligibility_document() -> ParsedDocument:
    return ParsedDocument(
        source_path="Income_tax_act_2023.pdf",
        parser_provider="fallback",
        pages=[
            build_parsed_page_from_text(
                5,
                "\n".join(
                    [
                        "2. Definitions.—",
                        '(25) "employee" includes any person receiving salary from the employer.',
                        "Provided that it shall not include a day labourer.",
                    ]
                ),
            )
        ],
    )


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
