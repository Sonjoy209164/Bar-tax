from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from app.core.settings import get_settings
from app.domain import LegalNode, LegalNodeType
from app.ingestion import LinkedLegalDocument, LegalChunk, build_legal_chunks, build_legal_structure, load_linked_document
from app.reasoning import ReasoningGraphConfig, ReasoningGraphDependencies, build_agent_graph
from app.services.evaluation_service import EvaluationCase, EvaluationService, EvaluationSummary
from app.services.ingest_service import IngestService, IngestServiceConfig, IngestServiceResult
from app.services.query_service import QueryRequest, QueryResponse, QueryService
from app.retrieval import (
    HybridRetriever,
    LocalVectorStore,
    QueryTransformer,
    VectorRecord,
    build_bm25_index,
    build_embedder,
    build_reranker,
    build_vector_store,
    vector_store_config_from_settings,
)


class TraceRecord(BaseModel):
    trace_id: str
    state: dict[str, Any]


class AgenticRuntimeStatus(BaseModel):
    ready: bool
    loaded_documents: list[str] = Field(default_factory=list)
    node_count: int = 0
    link_count: int = 0
    retrieval_chunk_count: int = 0
    reasoning_chunk_count: int = 0
    vector_record_count: int = 0
    vector_backend: str
    vector_store_path: str | None = None


class TraceStore:
    def __init__(self, trace_dir: str | Path) -> None:
        self.trace_dir = Path(trace_dir)
        self.trace_dir.mkdir(parents=True, exist_ok=True)
        self._cache: dict[str, dict[str, Any]] = {}

    def save(self, state: Any) -> str:
        payload = state.model_dump(mode="json")
        trace_id = str(payload["trace_id"])
        self._cache[trace_id] = payload
        trace_path = self.trace_dir / f"{trace_id}.json"
        trace_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return trace_id

    def load(self, trace_id: str) -> dict[str, Any] | None:
        if trace_id in self._cache:
            return self._cache[trace_id]
        trace_path = self.trace_dir / f"{trace_id}.json"
        if not trace_path.exists():
            return None
        payload = json.loads(trace_path.read_text(encoding="utf-8"))
        self._cache[trace_id] = payload
        return payload


class AgenticRuntime:
    def __init__(
        self,
        *,
        store_dir: str | Path | None = None,
        vector_namespace: str | None = None,
        local_vector_store_path: str | Path | None = None,
        trace_dir: str | Path | None = None,
        query_top_k: int | None = None,
    ) -> None:
        self.settings = get_settings()
        self.store_dir = Path(store_dir or self.settings.agentic_store_dir)
        self.vector_namespace = vector_namespace if vector_namespace is not None else self.settings.vector_namespace
        self.query_top_k = query_top_k or self.settings.top_k
        self.embedder = build_embedder()
        vector_config = vector_store_config_from_settings().model_copy(
            update={
                "namespace": self.vector_namespace,
                "local_store_path": str(local_vector_store_path) if local_vector_store_path else self.settings.local_vector_store_path,
            }
        )
        self.vector_store = build_vector_store(vector_config)
        self.trace_store = TraceStore(trace_dir or self.settings.trace_dir)
        self.ingest_service = IngestService(
            embedder=self.embedder,
            vector_store=self.vector_store,
            config=IngestServiceConfig(output_root=str(self.store_dir), vector_namespace=self.vector_namespace),
        )
        self.loaded_documents: list[str] = []
        self.node_count = 0
        self.link_count = 0
        self.retrieval_chunk_count = 0
        self.reasoning_chunk_count = 0
        self.query_service: QueryService | None = None
        self.evaluation_service: EvaluationService | None = None
        self.refresh()

    def refresh(self) -> None:
        corpus = _load_agentic_corpus(self.store_dir)
        self.loaded_documents = corpus["document_ids"]
        self.node_count = len(corpus["nodes"])
        self.link_count = len(corpus["links"])
        self.retrieval_chunk_count = len(corpus["retrieval_chunks"])
        self.reasoning_chunk_count = len(corpus["reasoning_chunks"])

        if not corpus["retrieval_chunks"] or not corpus["nodes"]:
            self.query_service = None
            self.evaluation_service = None
            return

        if isinstance(self.vector_store, LocalVectorStore):
            self._sync_local_vector_store(corpus["retrieval_chunks"])

        linked_document = LinkedLegalDocument(
            document_id="agentic-corpus",
            act_title="Bangla Tax Corpus",
            source_path=str(self.store_dir),
            parser_provider="runtime",
            root_node_id=corpus["root_node_id"],
            nodes=corpus["nodes"],
            links=corpus["links"],
        )
        query_transformer = QueryTransformer()
        retriever = HybridRetriever(
            linked_document=linked_document,
            chunks_or_artifacts=corpus["retrieval_chunks"],
            embedder=self.embedder,
            vector_store=self.vector_store,
            bm25_index=build_bm25_index(corpus["retrieval_chunks"]),
            query_transformer=query_transformer,
            reranker=build_reranker(),
        )
        graph = build_agent_graph(
            dependencies=ReasoningGraphDependencies(
                hybrid_retriever=retriever,
                query_transformer=query_transformer,
            ),
            config=ReasoningGraphConfig(top_k=self.query_top_k, max_retrieval_loops=2, prefer_langgraph_backend=True),
        )
        self.query_service = QueryService(reasoning_graph=graph)
        self.evaluation_service = EvaluationService(query_service=self.query_service)

    def ingest(
        self,
        source_path: str | Path,
        *,
        document_id: str | None = None,
        act_title: str | None = None,
    ) -> IngestServiceResult:
        result = self.ingest_service.ingest(
            source_path,
            document_id=document_id,
            act_title=act_title,
        )
        self.refresh()
        return result

    def query(self, request: QueryRequest) -> QueryResponse:
        if self.query_service is None:
            raise RuntimeError("No agentic corpus is loaded. Ingest a document first.")
        response, state = self.query_service.run_with_state(request)
        self.trace_store.save(state)
        return response

    def evaluate(self, cases: list[EvaluationCase]) -> EvaluationSummary:
        if self.evaluation_service is None:
            raise RuntimeError("No agentic corpus is loaded. Ingest a document first.")
        return self.evaluation_service.evaluate(cases)

    def get_trace(self, trace_id: str) -> TraceRecord | None:
        payload = self.trace_store.load(trace_id)
        if payload is None:
            return None
        return TraceRecord(trace_id=trace_id, state=payload)

    def status(self) -> AgenticRuntimeStatus:
        stats = self.vector_store.describe(namespace=self.vector_store.config.namespace)
        vector_store_path = getattr(self.vector_store.config, "local_store_path", None)
        return AgenticRuntimeStatus(
            ready=self.query_service is not None,
            loaded_documents=list(self.loaded_documents),
            node_count=self.node_count,
            link_count=self.link_count,
            retrieval_chunk_count=self.retrieval_chunk_count,
            reasoning_chunk_count=self.reasoning_chunk_count,
            vector_record_count=stats.total_vector_count or 0,
            vector_backend=self.vector_store.provider.value,
            vector_store_path=vector_store_path,
        )

    def _sync_local_vector_store(self, chunks: list[LegalChunk]) -> None:
        assert isinstance(self.vector_store, LocalVectorStore)
        target_namespace = self.vector_store.config.namespace
        expected_ids = {chunk.chunk_id for chunk in chunks}
        existing_ids = set(self.vector_store.record_ids(namespace=target_namespace))
        stale_ids = sorted(existing_ids - expected_ids)
        if stale_ids:
            self.vector_store.delete(stale_ids, namespace=target_namespace)
        missing_chunks = [chunk for chunk in chunks if chunk.chunk_id not in existing_ids]
        if not missing_chunks:
            return
        self.vector_store.upsert(
            _build_vector_records(missing_chunks, namespace=target_namespace, embedder=self.embedder),
            namespace=target_namespace,
        )


def _load_agentic_corpus(output_root: str | Path) -> dict[str, Any]:
    root = Path(output_root)
    if not root.exists():
        return {
            "document_ids": [],
            "root_node_id": "agentic-corpus:act",
            "nodes": [],
            "links": [],
            "retrieval_chunks": [],
            "reasoning_chunks": [],
        }

    document_ids: list[str] = []
    nodes: list[LegalNode] = []
    links: list[Any] = []
    retrieval_chunks: list[LegalChunk] = []
    reasoning_chunks: list[LegalChunk] = []
    root_node_id: str | None = None

    for document_dir in sorted(path for path in root.iterdir() if path.is_dir()):
        graph_dir = document_dir / "graph"
        linked_graph_path = graph_dir / "legal_graph.json"
        retrieval_chunks_path = document_dir / "chunks" / "retrieval_chunks.jsonl"
        reasoning_chunks_path = document_dir / "chunks" / "reasoning_chunks.jsonl"
        if not linked_graph_path.exists() or not retrieval_chunks_path.exists():
            continue
        linked_document = load_linked_document(graph_dir)
        if root_node_id is None:
            root_node_id = linked_document.root_node_id
        document_ids.append(linked_document.document_id)
        nodes.extend(linked_document.nodes)
        links.extend(linked_document.links)
        retrieval_chunks.extend(_load_legal_chunks(retrieval_chunks_path))
        if reasoning_chunks_path.exists():
            reasoning_chunks.extend(_load_legal_chunks(reasoning_chunks_path))

    return {
        "document_ids": document_ids,
        "root_node_id": root_node_id or "agentic-corpus:act",
        "nodes": nodes,
        "links": links,
        "retrieval_chunks": retrieval_chunks,
        "reasoning_chunks": reasoning_chunks,
    }


def _load_legal_chunks(path: str | Path) -> list[LegalChunk]:
    chunks: list[LegalChunk] = []
    with Path(path).open("r", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped:
                continue
            chunks.append(LegalChunk.model_validate_json(stripped))
    return chunks


def _build_vector_records(chunks: list[LegalChunk], *, namespace: str | None, embedder: Any) -> list[VectorRecord]:
    batch = embedder.embed_texts([chunk.normalized_text for chunk in chunks])
    return [
        VectorRecord(
            record_id=chunk.chunk_id,
            vector=vector,
            metadata={
                "document_id": chunk.document_id,
                "section_number": chunk.section_number,
                "chunk_type": chunk.chunk_type,
                "source_node_type": chunk.source_node_type.value,
                **chunk.metadata,
            },
            text=chunk.text,
            namespace=namespace,
        )
        for chunk, vector in zip(chunks, batch.vectors, strict=True)
    ]


@lru_cache(maxsize=1)
def get_agentic_runtime() -> AgenticRuntime:
    return AgenticRuntime()
