from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.core.utils import truncate_text
from app.domain import CitationRelation, EvidenceItem, LegalNode
from app.ingestion.chunker import LegalChunk
from app.ingestion.parent_child_linker import LinkedLegalDocument


class GraphExpansionConfig(BaseModel):
    include_parent_context: bool = True
    include_siblings: bool = True
    include_provisos: bool = True
    include_explanations: bool = True
    include_tables: bool = True
    include_governing_rule: bool = True
    max_related_nodes: int = Field(default=6, ge=0, le=30)


class ExpandedGraphNode(BaseModel):
    node_id: str
    relation: CitationRelation
    source: str


class GraphExpansionResult(BaseModel):
    chunk_id: str
    source_node_id: str
    expanded_nodes: list[ExpandedGraphNode] = Field(default_factory=list)
    evidence: list[EvidenceItem] = Field(default_factory=list)

    @property
    def expanded_node_ids(self) -> list[str]:
        return [item.node_id for item in self.expanded_nodes]


class GraphExpander:
    def __init__(
        self,
        linked_document: LinkedLegalDocument,
        *,
        config: GraphExpansionConfig | None = None,
    ) -> None:
        self.linked_document = linked_document
        self.config = config or GraphExpansionConfig()
        self.node_map = {node.node_id: node for node in linked_document.nodes}

    def expand_chunk(self, chunk: LegalChunk) -> GraphExpansionResult:
        source_node = self.node_map.get(chunk.source_node_id)
        if source_node is None:
            return GraphExpansionResult(chunk_id=chunk.chunk_id, source_node_id=chunk.source_node_id)

        evidence = [
            _build_evidence_item(
                node=source_node,
                relation=CitationRelation.DIRECT,
                retrieval_method="graph_direct",
                score=1.0,
            )
        ]

        candidates = self._collect_expansion_candidates(chunk, source_node)
        expanded_nodes: list[ExpandedGraphNode] = []
        for candidate in candidates[: self.config.max_related_nodes]:
            node = self.node_map.get(candidate.node_id)
            if node is None:
                continue
            expanded_nodes.append(candidate)
            evidence.append(
                _build_evidence_item(
                    node=node,
                    relation=candidate.relation,
                    retrieval_method="graph_context",
                    score=0.5,
                )
            )

        return GraphExpansionResult(
            chunk_id=chunk.chunk_id,
            source_node_id=chunk.source_node_id,
            expanded_nodes=expanded_nodes,
            evidence=_deduplicate_evidence(evidence),
        )

    def _collect_expansion_candidates(self, chunk: LegalChunk, source_node: LegalNode) -> list[ExpandedGraphNode]:
        node_metadata = source_node.metadata
        related: list[ExpandedGraphNode] = []
        seen: set[tuple[str, CitationRelation]] = set()

        def add(node_id: str | None, relation: CitationRelation, source: str) -> None:
            if not node_id or node_id == source_node.node_id:
                return
            key = (node_id, relation)
            if key in seen:
                return
            seen.add(key)
            related.append(ExpandedGraphNode(node_id=node_id, relation=relation, source=source))

        reasoning_parent_id = chunk.reasoning_parent_id or node_metadata.get("reasoning_parent_id")
        governing_rule_id = node_metadata.get("governing_rule_id") or chunk.metadata.get("governing_rule_id")
        governing_section_id = node_metadata.get("governing_section_id") or chunk.metadata.get("governing_section_id")
        governance_source_ids = _ordered_unique(
            [
                source_node.node_id,
                reasoning_parent_id,
                governing_rule_id,
                governing_section_id,
            ]
        )

        if self.config.include_parent_context and reasoning_parent_id:
            add(reasoning_parent_id, CitationRelation.PARENT_CONTEXT, "reasoning_parent")

        if self.config.include_governing_rule and governing_rule_id and governing_rule_id != reasoning_parent_id:
            add(governing_rule_id, CitationRelation.GOVERNING_RULE, "governing_rule")

        if self.config.include_siblings:
            for sibling_id in _ordered_unique(
                [
                    *chunk.metadata.get("sibling_ids", []),
                    *node_metadata.get("sibling_ids", []),
                ]
            ):
                add(sibling_id, CitationRelation.SIBLING_CONTEXT, "sibling")

        if self.config.include_provisos:
            for source_id in governance_source_ids:
                source_node_for_relation = self.node_map.get(source_id)
                if source_node_for_relation is None:
                    continue
                for proviso_id in source_node_for_relation.metadata.get("attached_proviso_ids", []):
                    add(proviso_id, CitationRelation.GOVERNING_RULE, "attached_proviso")

        if self.config.include_explanations:
            for source_id in governance_source_ids:
                source_node_for_relation = self.node_map.get(source_id)
                if source_node_for_relation is None:
                    continue
                for explanation_id in source_node_for_relation.metadata.get("attached_explanation_ids", []):
                    add(explanation_id, CitationRelation.GOVERNING_RULE, "attached_explanation")

        if self.config.include_tables:
            for source_id in governance_source_ids:
                source_node_for_relation = self.node_map.get(source_id)
                if source_node_for_relation is None:
                    continue
                for table_id in source_node_for_relation.metadata.get("attached_table_ids", []):
                    add(table_id, CitationRelation.ATTACHED_TABLE, "attached_table")

        fallback_expand_ids = _ordered_unique(
            [
                *chunk.metadata.get("expand_to_node_ids", []),
                *node_metadata.get("expand_to_node_ids", []),
            ]
        )
        for node_id in fallback_expand_ids:
            if any(expanded.node_id == node_id for expanded in related):
                continue
            add(node_id, _fallback_relation(chunk, source_node, node_id), "fallback_expand_to")

        return related


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


def _fallback_relation(chunk: LegalChunk, source_node: LegalNode, node_id: str) -> CitationRelation:
    if node_id == (chunk.reasoning_parent_id or source_node.metadata.get("reasoning_parent_id")):
        return CitationRelation.PARENT_CONTEXT
    if node_id == source_node.metadata.get("governing_rule_id"):
        return CitationRelation.GOVERNING_RULE
    if node_id in source_node.metadata.get("sibling_ids", []):
        return CitationRelation.SIBLING_CONTEXT
    if node_id in source_node.metadata.get("attached_table_ids", []):
        return CitationRelation.ATTACHED_TABLE
    return CitationRelation.PARENT_CONTEXT


def _ordered_unique(values: list[str | None]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if not value or value in seen:
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
