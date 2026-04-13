from __future__ import annotations

from collections import defaultdict
from typing import Any

from pydantic import BaseModel, Field

from app.domain import CitationRelation, LegalNode, LegalNodeType
from app.ingestion.structure_builder import StructuredLegalDocument


class LegalNodeLink(BaseModel):
    source_node_id: str
    target_node_id: str
    relation: CitationRelation
    metadata: dict[str, Any] = Field(default_factory=dict)


class LinkedLegalDocument(BaseModel):
    document_id: str
    act_title: str
    source_path: str
    parser_provider: str
    root_node_id: str
    nodes: list[LegalNode] = Field(default_factory=list)
    links: list[LegalNodeLink] = Field(default_factory=list)

    def related_node_ids(
        self,
        node_id: str,
        *,
        relation: CitationRelation | None = None,
        direction: str = "outgoing",
    ) -> list[str]:
        related: list[str] = []
        for link in self.links:
            if direction == "outgoing" and link.source_node_id == node_id:
                if relation is None or link.relation is relation:
                    related.append(link.target_node_id)
            if direction == "incoming" and link.target_node_id == node_id:
                if relation is None or link.relation is relation:
                    related.append(link.source_node_id)
        return related


def link_parent_child_relationships(structured_document: StructuredLegalDocument) -> LinkedLegalDocument:
    node_map = {node.node_id: node for node in structured_document.nodes}
    outgoing_keys: set[tuple[str, str, str]] = set()
    links: list[LegalNodeLink] = []
    attached_provisos: dict[str, list[str]] = defaultdict(list)
    attached_explanations: dict[str, list[str]] = defaultdict(list)
    attached_tables: dict[str, list[str]] = defaultdict(list)
    sibling_map: dict[str, list[str]] = defaultdict(list)

    def add_link(source_node_id: str, target_node_id: str, relation: CitationRelation, **metadata: Any) -> None:
        key = (source_node_id, target_node_id, relation.value)
        if key in outgoing_keys:
            return
        outgoing_keys.add(key)
        links.append(
            LegalNodeLink(
                source_node_id=source_node_id,
                target_node_id=target_node_id,
                relation=relation,
                metadata=metadata,
            )
        )

    for node in structured_document.nodes:
        if node.parent_id:
            add_link(
                node.node_id,
                node.parent_id,
                CitationRelation.PARENT_CONTEXT,
                link_kind="structural_parent",
            )

    for node in structured_document.nodes:
        if len(node.child_ids) < 2:
            continue
        typed_children: dict[LegalNodeType, list[str]] = defaultdict(list)
        for child_id in node.child_ids:
            child = node_map[child_id]
            typed_children[child.node_type].append(child_id)

        for node_type in {LegalNodeType.SUBSECTION, LegalNodeType.CLAUSE}:
            siblings = typed_children.get(node_type, [])
            for source_id in siblings:
                for target_id in siblings:
                    if source_id == target_id:
                        continue
                    sibling_map[source_id].append(target_id)
                    add_link(
                        source_id,
                        target_id,
                        CitationRelation.SIBLING_CONTEXT,
                        link_kind=f"{node_type.value}_sibling",
                    )

    for node in structured_document.nodes:
        governing_rule = _find_governing_rule(node, node_map)
        reasoning_parent = _find_reasoning_parent(node, node_map)
        governing_section = _find_ancestor_of_type(node, node_map, LegalNodeType.SECTION)

        if node.node_type is LegalNodeType.PROVISO and governing_rule:
            attached_provisos[governing_rule.node_id].append(node.node_id)
            add_link(
                node.node_id,
                governing_rule.node_id,
                CitationRelation.GOVERNING_RULE,
                link_kind="attached_proviso",
            )

        if node.node_type is LegalNodeType.EXPLANATION and governing_rule:
            attached_explanations[governing_rule.node_id].append(node.node_id)
            add_link(
                node.node_id,
                governing_rule.node_id,
                CitationRelation.GOVERNING_RULE,
                link_kind="attached_explanation",
            )

        if node.node_type is LegalNodeType.TABLE and governing_section:
            attached_tables[governing_section.node_id].append(node.node_id)
            add_link(
                node.node_id,
                governing_section.node_id,
                CitationRelation.ATTACHED_TABLE,
                link_kind="attached_table",
            )

        if reasoning_parent and reasoning_parent.node_id != node.node_id:
            add_link(
                node.node_id,
                reasoning_parent.node_id,
                CitationRelation.PARENT_CONTEXT,
                link_kind="reasoning_parent",
            )

    linked_nodes: list[LegalNode] = []
    for node in structured_document.nodes:
        reasoning_parent = _find_reasoning_parent(node, node_map)
        governing_rule = _find_governing_rule(node, node_map)
        governing_section = _find_ancestor_of_type(node, node_map, LegalNodeType.SECTION)
        node_siblings = _unique_preserve_order(sibling_map.get(node.node_id, []))
        expand_to_node_ids = _unique_preserve_order(
            [
                *node_siblings,
                *(attached_provisos.get(node.node_id, []) if node.node_id in attached_provisos else []),
                *(attached_explanations.get(node.node_id, []) if node.node_id in attached_explanations else []),
                *(attached_tables.get(node.node_id, []) if node.node_id in attached_tables else []),
                reasoning_parent.node_id if reasoning_parent and reasoning_parent.node_id != node.node_id else None,
                governing_rule.node_id if governing_rule else None,
                governing_section.node_id if governing_section else None,
            ]
        )
        linked_nodes.append(
            node.model_copy(
                update={
                    "metadata": {
                        **node.metadata,
                        "structural_parent_id": node.parent_id,
                        "reasoning_parent_id": reasoning_parent.node_id if reasoning_parent else None,
                        "governing_rule_id": governing_rule.node_id if governing_rule else None,
                        "governing_section_id": governing_section.node_id if governing_section else None,
                        "sibling_ids": node_siblings,
                        "attached_proviso_ids": _unique_preserve_order(attached_provisos.get(node.node_id, [])),
                        "attached_explanation_ids": _unique_preserve_order(attached_explanations.get(node.node_id, [])),
                        "attached_table_ids": _unique_preserve_order(attached_tables.get(node.node_id, [])),
                        "expand_to_node_ids": [node_id for node_id in expand_to_node_ids if node_id and node_id != node.node_id],
                    }
                }
            )
        )

    return LinkedLegalDocument(
        document_id=structured_document.document_id,
        act_title=structured_document.act_title,
        source_path=structured_document.source_path,
        parser_provider=structured_document.parser_provider,
        root_node_id=structured_document.root_node_id,
        nodes=linked_nodes,
        links=links,
    )


def validate_linked_document(linked_document: LinkedLegalDocument) -> None:
    node_ids = {node.node_id for node in linked_document.nodes}
    link_pairs: set[tuple[str, str, str]] = set()

    for link in linked_document.links:
        if link.source_node_id not in node_ids:
            raise ValueError(f"Unknown link source: {link.source_node_id}")
        if link.target_node_id not in node_ids:
            raise ValueError(f"Unknown link target: {link.target_node_id}")
        key = (link.source_node_id, link.target_node_id, link.relation.value)
        if key in link_pairs:
            raise ValueError(f"Duplicate link detected: {key}")
        link_pairs.add(key)

    for node in linked_document.nodes:
        metadata = node.metadata
        for key in {
            "structural_parent_id",
            "reasoning_parent_id",
            "governing_rule_id",
            "governing_section_id",
            "sibling_ids",
            "attached_proviso_ids",
            "attached_explanation_ids",
            "attached_table_ids",
            "expand_to_node_ids",
        }:
            if key not in metadata:
                raise ValueError(f"Node {node.node_id} is missing linking metadata key: {key}")


def _find_reasoning_parent(node: LegalNode, node_map: dict[str, LegalNode]) -> LegalNode | None:
    if node.node_type is LegalNodeType.SECTION:
        return node
    if node.node_type is LegalNodeType.SUBSECTION:
        return _find_ancestor_of_type(node, node_map, LegalNodeType.SECTION)
    if node.node_type is LegalNodeType.CLAUSE:
        return _find_ancestor_of_type(node, node_map, LegalNodeType.SUBSECTION) or _find_ancestor_of_type(node, node_map, LegalNodeType.SECTION)
    if node.node_type in {LegalNodeType.PROVISO, LegalNodeType.EXPLANATION}:
        return _find_governing_rule(node, node_map)
    if node.node_type is LegalNodeType.TABLE:
        return _find_ancestor_of_type(node, node_map, LegalNodeType.SECTION)
    return node_map.get(node.parent_id) if node.parent_id else node


def _find_governing_rule(node: LegalNode, node_map: dict[str, LegalNode]) -> LegalNode | None:
    if node.node_type not in {LegalNodeType.PROVISO, LegalNodeType.EXPLANATION, LegalNodeType.TABLE}:
        return _find_reasoning_parent(node, node_map)
    current = node_map.get(node.parent_id) if node.parent_id else None
    while current is not None:
        if current.node_type in {LegalNodeType.CLAUSE, LegalNodeType.SUBSECTION, LegalNodeType.SECTION}:
            return current
        current = node_map.get(current.parent_id) if current.parent_id else None
    return None


def _find_ancestor_of_type(
    node: LegalNode,
    node_map: dict[str, LegalNode],
    target_type: LegalNodeType,
) -> LegalNode | None:
    current = node_map.get(node.parent_id) if node.parent_id else None
    while current is not None:
        if current.node_type is target_type:
            return current
        current = node_map.get(current.parent_id) if current.parent_id else None
    return None


def _unique_preserve_order(values: list[str | None]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered
