from __future__ import annotations

from collections import defaultdict
import logging
from typing import Any

from pydantic import BaseModel, Field, model_validator

from app.domain import CitationRelation, EvidenceItem, QueryType, canonicalize_query_type
from app.ingestion.chunker import ChunkingArtifacts, LegalChunk
from app.ingestion.parent_child_linker import LinkedLegalDocument
from app.reasoning.state import QueryPlanStep
from app.retrieval.bm25_index import BM25Index, BM25SearchRequest, build_bm25_index
from app.retrieval.embedder import TextEmbedder
from app.retrieval.graph_expander import GraphExpander, GraphExpansionConfig
from app.retrieval.query_transformer import QueryPlan, QueryTransformer, build_query_plan
from app.retrieval.reranker import DocumentReranker, RerankerDocument
from app.retrieval.vector_store_base import VectorSearchMatch, VectorStore

logger = logging.getLogger(__name__)


class HybridRetrieverConfig(BaseModel):
    sparse_top_k: int = Field(default=8, ge=1, le=50)
    dense_top_k: int = Field(default=8, ge=1, le=50)
    final_top_k: int = Field(default=5, ge=1, le=20)
    rerank_top_n: int = Field(default=12, ge=1, le=100)
    max_expanded_nodes_per_candidate: int = Field(default=4, ge=0, le=20)
    reciprocal_rank_constant: int = Field(default=60, ge=1, le=200)


class HybridSearchRequest(BaseModel):
    question: str
    top_k: int | None = Field(default=None, ge=1)
    query_type: QueryType | None = None
    filters: dict[str, Any] = Field(default_factory=dict)
    query_plan: QueryPlan | None = None

    @model_validator(mode="after")
    def validate_request(self) -> "HybridSearchRequest":
        self.query_type = canonicalize_query_type(self.query_type)
        return self


class HybridCandidate(BaseModel):
    chunk: LegalChunk
    fused_score: float
    sparse_score: float | None = None
    dense_score: float | None = None
    sparse_rank: int | None = None
    dense_rank: int | None = None
    matched_sub_queries: list[str] = Field(default_factory=list)
    source_methods: list[str] = Field(default_factory=list)
    evidence: list[EvidenceItem] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class HybridRetrievalResult(BaseModel):
    question: str
    query_plan: QueryPlan
    top_k: int
    applied_filters: dict[str, Any] = Field(default_factory=dict)
    candidates: list[HybridCandidate] = Field(default_factory=list)
    evidence: list[EvidenceItem] = Field(default_factory=list)


class HybridRetriever:
    def __init__(
        self,
        *,
        linked_document: LinkedLegalDocument,
        chunks_or_artifacts: list[LegalChunk] | ChunkingArtifacts,
        embedder: TextEmbedder,
        vector_store: VectorStore,
        bm25_index: BM25Index | None = None,
        query_transformer: QueryTransformer | None = None,
        graph_expander: GraphExpander | None = None,
        reranker: DocumentReranker | None = None,
        config: HybridRetrieverConfig | None = None,
    ) -> None:
        self.linked_document = linked_document
        self.embedder = embedder
        self.vector_store = vector_store
        self.query_transformer = query_transformer or QueryTransformer()
        self.config = config or HybridRetrieverConfig()
        self.chunks = _resolve_retrieval_chunks(chunks_or_artifacts)
        self.chunk_map = {chunk.chunk_id: chunk for chunk in self.chunks}
        self.bm25_index = bm25_index or build_bm25_index(self.chunks)
        self.graph_expander = graph_expander or GraphExpander(
            linked_document,
            config=GraphExpansionConfig(max_related_nodes=self.config.max_expanded_nodes_per_candidate),
        )
        self.reranker = reranker

    def search(self, request: HybridSearchRequest) -> HybridRetrievalResult:
        query_plan = request.query_plan or self.query_transformer.transform(
            request.question,
            query_type=request.query_type,
        )
        top_k = request.top_k or self.config.final_top_k

        aggregate: dict[str, dict[str, Any]] = defaultdict(dict)
        for step_index, step in enumerate(query_plan.steps, start=1):
            combined_filters = _merge_filters(request.filters, step.metadata_filters)
            sparse_result = self.bm25_index.search(
                BM25SearchRequest(
                    query=step.sub_query,
                    top_k=self.config.sparse_top_k,
                    query_type=query_plan.query_type,
                    section_reference=query_plan.section_references[0] if query_plan.section_references else None,
                    filters=combined_filters,
                )
            )
            for match in sparse_result.matches:
                record = aggregate.setdefault(match.chunk.chunk_id, _empty_aggregate(match.chunk))
                record["sparse_score"] = max(record.get("sparse_score") or 0.0, match.score)
                rank = match.rank
                if record.get("sparse_rank") is None or rank < record["sparse_rank"]:
                    record["sparse_rank"] = rank
                record["fused_score"] += _rrf_score(rank, self.config.reciprocal_rank_constant)
                record["matched_sub_queries"].add(step.sub_query)
                record["source_methods"].add("sparse")
                record["step_indices"].add(step_index)

            dense_matches = self._dense_search(step, query_plan=query_plan, filters=combined_filters)
            for rank, dense_match in enumerate(dense_matches, start=1):
                chunk = self.chunk_map.get(dense_match.record_id)
                if chunk is None:
                    continue
                record = aggregate.setdefault(chunk.chunk_id, _empty_aggregate(chunk))
                record["dense_score"] = max(record.get("dense_score") or 0.0, dense_match.score)
                if record.get("dense_rank") is None or rank < record["dense_rank"]:
                    record["dense_rank"] = rank
                record["fused_score"] += _rrf_score(rank, self.config.reciprocal_rank_constant)
                record["matched_sub_queries"].add(step.sub_query)
                record["source_methods"].add("dense")
                record["step_indices"].add(step_index)

        preliminary_candidates = sorted(
            aggregate.values(),
            key=lambda item: (
                item["fused_score"],
                item.get("dense_score") or 0.0,
                item.get("sparse_score") or 0.0,
            ),
            reverse=True,
        )
        sorted_candidates = self._apply_reranker(
            preliminary_candidates,
            question=request.question,
            top_k=top_k,
        )[:top_k]

        candidates: list[HybridCandidate] = []
        evidence_by_key: dict[tuple[str, CitationRelation], EvidenceItem] = {}
        for candidate_record in sorted_candidates:
            expansion_result = self.graph_expander.expand_chunk(candidate_record["chunk"])
            for item in expansion_result.evidence:
                evidence_by_key.setdefault((item.node_id, item.citation.relation), item)
            candidates.append(
                HybridCandidate(
                    chunk=candidate_record["chunk"],
                    fused_score=round(candidate_record["fused_score"], 6),
                    sparse_score=candidate_record.get("sparse_score"),
                    dense_score=candidate_record.get("dense_score"),
                    sparse_rank=candidate_record.get("sparse_rank"),
                    dense_rank=candidate_record.get("dense_rank"),
                    matched_sub_queries=sorted(candidate_record["matched_sub_queries"]),
                    source_methods=sorted(candidate_record["source_methods"]),
                    evidence=expansion_result.evidence,
                    metadata={
                        "step_indices": sorted(candidate_record["step_indices"]),
                        "reasoning_parent_id": candidate_record["chunk"].reasoning_parent_id,
                        "expanded_node_ids": expansion_result.expanded_node_ids,
                        "reranker_score": candidate_record.get("reranker_score"),
                        "reranker_rank": candidate_record.get("reranker_rank"),
                        "reranker_backend": candidate_record.get("reranker_backend"),
                    },
                )
            )

        return HybridRetrievalResult(
            question=request.question,
            query_plan=query_plan,
            top_k=top_k,
            applied_filters=request.filters,
            candidates=candidates,
            evidence=list(evidence_by_key.values()),
        )

    def _dense_search(
        self,
        step: QueryPlanStep,
        *,
        query_plan: QueryPlan,
        filters: dict[str, Any],
    ) -> list[VectorSearchMatch]:
        query_vector = self.embedder.embed_text(step.sub_query)
        dense_result = self.vector_store.query(
            query_vector,
            top_k=self.config.dense_top_k,
            filters=filters,
            namespace=self.vector_store.config.namespace,
        )
        filtered_matches: list[VectorSearchMatch] = []
        for match in dense_result.matches:
            chunk = self.chunk_map.get(match.record_id)
            if chunk is None:
                continue
            if not _chunk_matches_filters(chunk, filters):
                continue
            filtered_matches.append(match)
        return filtered_matches

    def _apply_reranker(
        self,
        candidates: list[dict[str, Any]],
        *,
        question: str,
        top_k: int,
    ) -> list[dict[str, Any]]:
        if self.reranker is None or not candidates:
            return candidates

        rerank_pool = candidates[: max(top_k, self.config.rerank_top_n)]
        try:
            rerank_result = self.reranker.rerank(
                question,
                [
                    RerankerDocument(
                        document_id=candidate["chunk"].chunk_id,
                        text=_build_reranker_text(candidate["chunk"]),
                        metadata={
                            "section_number": candidate["chunk"].section_number,
                            "chunk_type": candidate["chunk"].chunk_type,
                            "source_node_type": candidate["chunk"].source_node_type.value,
                        },
                    )
                    for candidate in rerank_pool
                ],
                top_k=len(rerank_pool),
            )
        except Exception as exc:  # pragma: no cover - graceful runtime fallback
            logger.warning("Reranker failed; returning fused ranking order.", extra={"error": str(exc)})
            return candidates

        reranked_records: list[dict[str, Any]] = []
        candidate_map = {candidate["chunk"].chunk_id: candidate for candidate in rerank_pool}
        for item in rerank_result.results:
            candidate = candidate_map.get(item.document_id)
            if candidate is None:
                continue
            candidate["reranker_score"] = item.relevance_score
            candidate["reranker_rank"] = item.rank
            candidate["reranker_backend"] = rerank_result.backend
            reranked_records.append(candidate)

        reranked_ids = {candidate["chunk"].chunk_id for candidate in reranked_records}
        for candidate in rerank_pool:
            if candidate["chunk"].chunk_id not in reranked_ids:
                reranked_records.append(candidate)
        reranked_records.extend(candidates[len(rerank_pool) :])
        return reranked_records


def _rrf_score(rank: int, constant: int) -> float:
    return 1.0 / (constant + rank)


def _merge_filters(base_filters: dict[str, Any], step_filters: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base_filters)
    merged.update(step_filters)
    return merged


def _build_reranker_text(chunk: LegalChunk) -> str:
    parts = [chunk.citability_label, chunk.label, chunk.title, chunk.text]
    return "\n".join(part.strip() for part in parts if part and part.strip())


def _resolve_retrieval_chunks(chunks_or_artifacts: list[LegalChunk] | ChunkingArtifacts) -> list[LegalChunk]:
    if isinstance(chunks_or_artifacts, ChunkingArtifacts):
        return [chunk for chunk in chunks_or_artifacts.retrieval_chunks if chunk.chunk_scope == "retrieval_child"]
    return [chunk for chunk in chunks_or_artifacts if chunk.chunk_scope == "retrieval_child"]


def _empty_aggregate(chunk: LegalChunk) -> dict[str, Any]:
    return {
        "chunk": chunk,
        "fused_score": 0.0,
        "sparse_score": None,
        "dense_score": None,
        "sparse_rank": None,
        "dense_rank": None,
        "matched_sub_queries": set(),
        "source_methods": set(),
        "step_indices": set(),
    }


def _chunk_matches_filters(chunk: LegalChunk, filters: dict[str, Any]) -> bool:
    for key, expected in filters.items():
        actual = getattr(chunk, key, None)
        if actual is None:
            actual = chunk.metadata.get(key)
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
