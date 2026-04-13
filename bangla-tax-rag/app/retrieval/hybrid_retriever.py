from __future__ import annotations

from collections import defaultdict
from typing import Any

from pydantic import BaseModel, Field, model_validator

from app.core.utils import truncate_text
from app.domain import CitationRelation, EvidenceItem, LegalNode, QueryType, canonicalize_query_type
from app.ingestion.chunker import ChunkingArtifacts, LegalChunk
from app.ingestion.parent_child_linker import LinkedLegalDocument
from app.reasoning import QueryPlanStep
from app.retrieval.bm25_index import BM25Index, BM25SearchRequest, build_bm25_index
from app.retrieval.embedder import TextEmbedder
from app.retrieval.query_transformer import QueryPlan, QueryTransformer, build_query_plan
from app.retrieval.vector_store_base import VectorSearchMatch, VectorStore


class HybridRetrieverConfig(BaseModel):
    sparse_top_k: int = Field(default=8, ge=1, le=50)
    dense_top_k: int = Field(default=8, ge=1, le=50)
    final_top_k: int = Field(default=5, ge=1, le=20)
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
        config: HybridRetrieverConfig | None = None,
    ) -> None:
        self.linked_document = linked_document
        self.embedder = embedder
        self.vector_store = vector_store
        self.query_transformer = query_transformer or QueryTransformer()
        self.config = config or HybridRetrieverConfig()
        self.chunks = _resolve_retrieval_chunks(chunks_or_artifacts)
        self.chunk_map = {chunk.chunk_id: chunk for chunk in self.chunks}
        self.node_map = {node.node_id: node for node in linked_document.nodes}
        self.bm25_index = bm25_index or build_bm25_index(self.chunks)

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

        sorted_candidates = sorted(
            aggregate.values(),
            key=lambda item: (
                item["fused_score"],
                item.get("dense_score") or 0.0,
                item.get("sparse_score") or 0.0,
            ),
            reverse=True,
        )[:top_k]

        candidates: list[HybridCandidate] = []
        evidence_by_key: dict[tuple[str, CitationRelation], EvidenceItem] = {}
        for candidate_record in sorted_candidates:
            evidence = self._build_candidate_evidence(candidate_record["chunk"])
            for item in evidence:
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
                    evidence=evidence,
                    metadata={
                        "step_indices": sorted(candidate_record["step_indices"]),
                        "reasoning_parent_id": candidate_record["chunk"].reasoning_parent_id,
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

    def _build_candidate_evidence(self, chunk: LegalChunk) -> list[EvidenceItem]:
        evidence: list[EvidenceItem] = []
        source_node = self.node_map.get(chunk.source_node_id)
        if source_node is not None:
            evidence.append(
                _build_evidence_item(
                    node=source_node,
                    relation=CitationRelation.DIRECT,
                    retrieval_method="hybrid_direct",
                    score=1.0,
                )
            )

        expanded_node_ids = []
        if chunk.reasoning_parent_id:
            expanded_node_ids.append(chunk.reasoning_parent_id)
        expanded_node_ids.extend(chunk.metadata.get("expand_to_node_ids", []))
        if source_node is not None:
            expanded_node_ids.extend(source_node.metadata.get("expand_to_node_ids", []))
        expanded_node_ids = _ordered_unique(node_id for node_id in expanded_node_ids if node_id and node_id != chunk.source_node_id)

        for node_id in expanded_node_ids[: self.config.max_expanded_nodes_per_candidate]:
            node = self.node_map.get(node_id)
            if node is None:
                continue
            relation = _relation_for_expanded_node(chunk, node_id)
            evidence.append(
                _build_evidence_item(
                    node=node,
                    relation=relation,
                    retrieval_method="hybrid_context",
                    score=0.5,
                )
            )

        return _deduplicate_evidence(evidence)


def _build_evidence_item(
    *,
    node: LegalNode,
    relation: CitationRelation,
    retrieval_method: str,
    score: float,
) -> EvidenceItem:
    snippet = truncate_text(node.text, max_length=280)
    return EvidenceItem(
        evidence_id=f"{node.node_id}:{relation.value}",
        node_id=node.node_id,
        parent_node_id=node.parent_id,
        citation=node.to_citation(snippet=snippet).model_copy(update={"relation": relation}),
        source_text=node.text,
        score=score,
        retrieval_method=retrieval_method,
        supporting_node_ids=node.child_ids,
        metadata={"node_type": node.node_type.value},
    )


def _relation_for_expanded_node(chunk: LegalChunk, node_id: str) -> CitationRelation:
    if node_id == chunk.reasoning_parent_id:
        return CitationRelation.PARENT_CONTEXT
    if node_id == chunk.metadata.get("governing_rule_id"):
        return CitationRelation.GOVERNING_RULE
    if node_id in chunk.metadata.get("attached_table_ids", []):
        return CitationRelation.ATTACHED_TABLE
    if node_id in chunk.metadata.get("sibling_ids", []):
        return CitationRelation.SIBLING_CONTEXT
    if node_id in chunk.metadata.get("attached_proviso_ids", []) or node_id in chunk.metadata.get("attached_explanation_ids", []):
        return CitationRelation.GOVERNING_RULE
    return CitationRelation.PARENT_CONTEXT


def _rrf_score(rank: int, constant: int) -> float:
    return 1.0 / (constant + rank)


def _merge_filters(base_filters: dict[str, Any], step_filters: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base_filters)
    merged.update(step_filters)
    return merged


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


def _ordered_unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered


def _deduplicate_evidence(items: list[EvidenceItem]) -> list[EvidenceItem]:
    deduped: list[EvidenceItem] = []
    seen: set[tuple[str, CitationRelation]] = set()
    for item in items:
        key = (item.node_id, item.citation.relation)
        if key in seen:
            continue
        deduped.append(item)
        seen.add(key)
    return deduped


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
