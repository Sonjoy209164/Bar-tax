from __future__ import annotations

import re
from typing import Iterable

from pydantic import BaseModel, Field

from app.domain import LegalNode, LegalNodeType
from app.ingestion.structure_builder import StructuredLegalDocument

SECTION_REFERENCE_PATTERN = re.compile(r"\bsection\s+(\d+[A-Za-z]?)\b", re.IGNORECASE)
SUBSECTION_REFERENCE_PATTERN = re.compile(r"\bsub-?section\s+\((\d+[A-Za-z]?)\)", re.IGNORECASE)
CLAUSE_REFERENCE_PATTERN = re.compile(r"\bclause\s+\(([a-z])\)", re.IGNORECASE)


class LegalNodeMetadata(BaseModel):
    node_id: str
    document_id: str
    act_title: str
    node_type: LegalNodeType
    chunk_type: str
    parent_id: str | None = None
    child_ids: list[str] = Field(default_factory=list)
    sibling_ids: list[str] = Field(default_factory=list)
    path_ids: list[str] = Field(default_factory=list)
    path_labels: list[str] = Field(default_factory=list)
    part_number: str | None = None
    part_title: str | None = None
    chapter_number: str | None = None
    chapter_title: str | None = None
    section_number: str | None = None
    subsection_number: str | None = None
    clause_number: str | None = None
    proviso_number: str | None = None
    explanation_number: str | None = None
    page_number: int
    page_start: int
    page_end: int
    page_numbers: list[int] = Field(default_factory=list)
    citability_label: str
    label: str | None = None
    title: str | None = None
    governing_node_id: str | None = None
    governing_section_number: str | None = None
    governing_subsection_number: str | None = None
    governing_clause_number: str | None = None
    is_leaf: bool = False
    cross_references: list[str] = Field(default_factory=list)


def tag_legal_metadata(structured_document: StructuredLegalDocument) -> StructuredLegalDocument:
    node_map = {node.node_id: node for node in structured_document.nodes}
    tagged_nodes: list[LegalNode] = []

    for node in structured_document.nodes:
        metadata = build_node_metadata(node, node_map)
        tagged_nodes.append(
            node.model_copy(
                update={
                    "cross_references": metadata.cross_references,
                    "metadata": {
                        **node.metadata,
                        **metadata.model_dump(mode="python"),
                    },
                }
            )
        )

    return structured_document.model_copy(update={"nodes": tagged_nodes})


def validate_tagged_document(structured_document: StructuredLegalDocument) -> None:
    required_keys = {
        "document_id",
        "act_title",
        "node_type",
        "chunk_type",
        "page_number",
        "page_start",
        "page_end",
        "parent_id",
        "child_ids",
        "citability_label",
    }
    for node in structured_document.nodes:
        missing_keys = sorted(key for key in required_keys if key not in node.metadata)
        if missing_keys:
            raise ValueError(f"Node {node.node_id} is missing metadata keys: {', '.join(missing_keys)}")
        if node.metadata["document_id"] != node.document_id:
            raise ValueError(f"Node {node.node_id} has inconsistent document_id metadata")
        if node.metadata["act_title"] != node.act_title:
            raise ValueError(f"Node {node.node_id} has inconsistent act_title metadata")
        if node.metadata["citability_label"] != node.citability_label:
            raise ValueError(f"Node {node.node_id} has inconsistent citability metadata")


def build_node_metadata(node: LegalNode, node_map: dict[str, LegalNode]) -> LegalNodeMetadata:
    parent = node_map.get(node.parent_id) if node.parent_id else None
    sibling_ids = [
        child_id
        for child_id in (parent.child_ids if parent else [])
        if child_id != node.node_id
    ]
    page_numbers = list(range(node.page_start, node.page_end + 1))
    governing_node_id = parent.node_id if node.node_type in {LegalNodeType.PROVISO, LegalNodeType.EXPLANATION, LegalNodeType.TABLE} and parent else None

    return LegalNodeMetadata(
        node_id=node.node_id,
        document_id=node.document_id,
        act_title=node.act_title,
        node_type=node.node_type,
        chunk_type=_infer_chunk_type(node, parent, node_map),
        parent_id=node.parent_id,
        child_ids=list(node.child_ids),
        sibling_ids=sibling_ids,
        path_ids=list(node.path_ids),
        path_labels=list(node.path_labels),
        part_number=node.part_number,
        part_title=node.part_title,
        chapter_number=node.chapter_number,
        chapter_title=node.chapter_title,
        section_number=node.section_number,
        subsection_number=node.subsection_number,
        clause_number=node.clause_number,
        proviso_number=node.proviso_number,
        explanation_number=node.explanation_number,
        page_number=node.page_start,
        page_start=node.page_start,
        page_end=node.page_end,
        page_numbers=page_numbers,
        citability_label=node.citability_label,
        label=node.label,
        title=node.title,
        governing_node_id=governing_node_id,
        governing_section_number=parent.section_number if governing_node_id and parent else node.section_number,
        governing_subsection_number=parent.subsection_number if governing_node_id and parent else node.subsection_number,
        governing_clause_number=parent.clause_number if governing_node_id and parent else node.clause_number,
        is_leaf=node.is_leaf,
        cross_references=_extract_cross_references(node.text),
    )


def _infer_chunk_type(node: LegalNode, parent: LegalNode | None, node_map: dict[str, LegalNode]) -> str:
    if node.node_type is LegalNodeType.DEFINITION:
        return "definition"
    if node.node_type is LegalNodeType.PROVISO:
        return "proviso"
    if node.node_type is LegalNodeType.EXPLANATION:
        return "explanation"
    if node.node_type is LegalNodeType.TABLE:
        return "table"
    if node.node_type is LegalNodeType.ILLUSTRATION:
        return "illustration"
    if node.node_type in {LegalNodeType.SECTION, LegalNodeType.SUBSECTION, LegalNodeType.CLAUSE}:
        if _looks_like_definition_text(node.text, parent, node_map):
            return "definition"
        if node.title and "definition" in node.title.lower():
            return "definition_section"
        return "rule"
    return node.node_type.value


def _looks_like_definition_text(text: str, parent: LegalNode | None, node_map: dict[str, LegalNode]) -> bool:
    normalized = text.lower()
    if " means " in normalized or normalized.startswith("means "):
        return True
    return _ancestor_has_definition_context(parent, node_map)


def _ancestor_has_definition_context(node: LegalNode | None, node_map: dict[str, LegalNode]) -> bool:
    current = node
    while current is not None:
        title_candidates = [current.title or "", current.label or "", current.text.splitlines()[0] if current.text else ""]
        if any("definition" in candidate.lower() for candidate in title_candidates if candidate):
            return True
        current = node_map.get(current.parent_id) if current.parent_id else None
    return False


def _extract_cross_references(text: str) -> list[str]:
    references: list[str] = []
    references.extend(f"section:{match}" for match in _unique_matches(SECTION_REFERENCE_PATTERN, text))
    references.extend(f"subsection:{match}" for match in _unique_matches(SUBSECTION_REFERENCE_PATTERN, text))
    references.extend(f"clause:{match}" for match in _unique_matches(CLAUSE_REFERENCE_PATTERN, text))
    return references


def _unique_matches(pattern: re.Pattern[str], text: str) -> list[str]:
    seen: set[str] = set()
    results: list[str] = []
    for match in pattern.findall(text):
        value = match if isinstance(match, str) else "".join(match)
        if value not in seen:
            seen.add(value)
            results.append(value)
    return results
