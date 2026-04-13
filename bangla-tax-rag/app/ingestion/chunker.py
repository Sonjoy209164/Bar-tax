from __future__ import annotations

import re
from itertools import count
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator

from app.core.utils import normalize_text
from app.domain import LegalNode, LegalNodeType
from app.ingestion.parent_child_linker import LinkedLegalDocument

TOKEN_PATTERN = re.compile(r"\w+|[^\w\s]", re.UNICODE)
SECTION_HEADING_PATTERN = re.compile(r"^\d+[A-Za-z]?(?:\.\d+)?\.\s+")
SUBSECTION_START_PATTERN = re.compile(r"^\((\d+[A-Za-z]?)\)\s+")
CLAUSE_START_PATTERN = re.compile(r"^\(([a-z])\)\s+", re.IGNORECASE)
PROVISO_START_PATTERN = re.compile(r"^Provided(?:\s+further|\s+also)?\s+that\b", re.IGNORECASE)
EXPLANATION_START_PATTERN = re.compile(r"^Explanation(?:\s+\d+|\s+[IVXLC]+)?(?:\s*[.:—-])?", re.IGNORECASE)
SENTENCE_BOUNDARY_PATTERN = re.compile(r"(?<=[.;:!?])\s+")


class ChunkingConfig(BaseModel):
    retrieval_min_tokens: int = 150
    retrieval_target_tokens: int = 200
    retrieval_max_tokens: int = 250
    reasoning_min_tokens: int = 1200
    reasoning_target_tokens: int = 1600
    reasoning_max_tokens: int = 2200

    @model_validator(mode="after")
    def validate_ranges(self) -> "ChunkingConfig":
        if not (self.retrieval_min_tokens <= self.retrieval_target_tokens <= self.retrieval_max_tokens):
            raise ValueError("Retrieval token targets must satisfy min <= target <= max")
        if not (self.reasoning_min_tokens <= self.reasoning_target_tokens <= self.reasoning_max_tokens):
            raise ValueError("Reasoning token targets must satisfy min <= target <= max")
        return self


class LegalChunk(BaseModel):
    chunk_id: str
    document_id: str
    act_title: str
    chunk_scope: Literal["retrieval_child", "reasoning_parent"]
    chunk_variant: str = "body"
    source_node_id: str
    source_node_type: LegalNodeType
    reasoning_parent_id: str | None = None
    parent_node_id: str | None = None
    chunk_type: str
    text: str
    normalized_text: str
    token_count: int
    page_start: int
    page_end: int
    page_numbers: list[int] = Field(default_factory=list)
    part_number: str | None = None
    part_title: str | None = None
    chapter_number: str | None = None
    chapter_title: str | None = None
    section_number: str | None = None
    subsection_number: str | None = None
    clause_number: str | None = None
    citability_label: str
    label: str | None = None
    title: str | None = None
    linked_node_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ChunkingArtifacts(BaseModel):
    document_id: str
    act_title: str
    retrieval_chunks: list[LegalChunk] = Field(default_factory=list)
    reasoning_chunks: list[LegalChunk] = Field(default_factory=list)


def build_legal_chunks(
    linked_document: LinkedLegalDocument,
    *,
    config: ChunkingConfig | None = None,
) -> ChunkingArtifacts:
    config = config or ChunkingConfig()
    chunk_counter = count(1)

    retrieval_chunks: list[LegalChunk] = []
    for section_node in _section_nodes(linked_document.nodes):
        retrieval_chunks.append(
            _build_chunk(
                chunk_id=_next_chunk_id(linked_document.document_id, "retrieval_child", chunk_counter),
                chunk_scope="retrieval_child",
                chunk_variant="anchor",
                source_node=section_node,
                text=_render_anchor_text(section_node),
                chunk_type=section_node.metadata.get("chunk_type", "rule"),
                linked_node_ids=[section_node.node_id],
                metadata={"chunk_variant": "anchor", "is_anchor_chunk": True},
            )
        )

    for node in _retrieval_source_nodes(linked_document.nodes):
        segments = _build_retrieval_segments(node)
        for segment_index, segment_text in enumerate(
            _pack_segments(
                segments,
                min_tokens=config.retrieval_min_tokens,
                target_tokens=config.retrieval_target_tokens,
                max_tokens=config.retrieval_max_tokens,
            ),
            start=1,
        ):
            retrieval_chunks.append(
                _build_chunk(
                    chunk_id=_next_chunk_id(linked_document.document_id, "retrieval_child", chunk_counter),
                    chunk_scope="retrieval_child",
                    chunk_variant="table_row" if node.node_type is LegalNodeType.TABLE else "body",
                    source_node=node,
                    text=segment_text,
                    chunk_type=node.metadata.get("chunk_type", node.node_type.value),
                    linked_node_ids=_linked_node_ids_for_retrieval(node),
                    metadata={
                        "segment_index": segment_index,
                        "expand_to_node_ids": node.metadata.get("expand_to_node_ids", []),
                    },
                )
            )

    reasoning_chunks: list[LegalChunk] = []
    for section_node in _section_nodes(linked_document.nodes):
        blocks = _build_reasoning_blocks(section_node, linked_document.nodes)
        for block_index, block_group in enumerate(
            _pack_blocks(
                blocks,
                min_tokens=config.reasoning_min_tokens,
                target_tokens=config.reasoning_target_tokens,
                max_tokens=config.reasoning_max_tokens,
            ),
            start=1,
        ):
            text = "\n\n".join(block["text"] for block in block_group).strip()
            linked_node_ids = _unique_preserve_order(
                [section_node.node_id, *[node_id for block in block_group for node_id in block["linked_node_ids"]]]
            )
            reasoning_chunks.append(
                _build_chunk(
                    chunk_id=_next_chunk_id(linked_document.document_id, "reasoning_parent", chunk_counter),
                    chunk_scope="reasoning_parent",
                    chunk_variant="context",
                    source_node=section_node,
                    text=text,
                    chunk_type="reasoning_context",
                    linked_node_ids=linked_node_ids,
                    metadata={
                        "block_index": block_index,
                        "included_node_ids": linked_node_ids,
                        "reasoning_root_id": section_node.node_id,
                    },
                )
            )

    return ChunkingArtifacts(
        document_id=linked_document.document_id,
        act_title=linked_document.act_title,
        retrieval_chunks=retrieval_chunks,
        reasoning_chunks=reasoning_chunks,
    )


def _section_nodes(nodes: list[LegalNode]) -> list[LegalNode]:
    return sorted(
        [node for node in nodes if node.node_type is LegalNodeType.SECTION],
        key=lambda node: (node.page_start, node.section_number or "", node.node_id),
    )


def _retrieval_source_nodes(nodes: list[LegalNode]) -> list[LegalNode]:
    retrieval_types = {
        LegalNodeType.SECTION,
        LegalNodeType.SUBSECTION,
        LegalNodeType.CLAUSE,
        LegalNodeType.PROVISO,
        LegalNodeType.EXPLANATION,
        LegalNodeType.TABLE,
        LegalNodeType.DEFINITION,
        LegalNodeType.ILLUSTRATION,
    }
    selected: list[LegalNode] = []
    for node in sorted(nodes, key=lambda item: (item.page_start, len(item.path_ids), item.node_id)):
        if node.node_type not in retrieval_types:
            continue
        if node.node_type in {LegalNodeType.SECTION, LegalNodeType.SUBSECTION} and node.child_ids:
            continue
        selected.append(node)
    return selected


def _render_anchor_text(node: LegalNode) -> str:
    parts = [node.label or node.citability_label]
    if node.title:
        parts.append(node.title)
    if node.page_anchor_text and node.page_anchor_text not in parts:
        parts.append(node.page_anchor_text)
    return "\n".join(part.strip() for part in parts if part and part.strip())


def _build_retrieval_segments(node: LegalNode) -> list[str]:
    if node.node_type is LegalNodeType.TABLE:
        return _build_table_row_segments(node.text)

    source_text = _trim_text_for_node(node)
    lines = [line.strip() for line in source_text.splitlines() if line.strip()]
    if not lines:
        return []

    segments: list[str] = []
    current_lines: list[str] = []
    for line in lines:
        if current_lines and _starts_new_legal_unit(line):
            segments.append("\n".join(current_lines).strip())
            current_lines = [line]
            continue
        current_lines.append(line)
    if current_lines:
        segments.append("\n".join(current_lines).strip())

    if not segments:
        return [node.text.strip()]

    safe_segments: list[str] = []
    for segment in segments:
        if estimate_token_count(segment) <= 250:
            safe_segments.append(segment)
            continue
        safe_segments.extend(_split_long_segment(segment, max_tokens=250))
    return [segment for segment in safe_segments if segment.strip()]


def _build_table_row_segments(text: str) -> list[str]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) <= 2:
        return ["\n".join(lines).strip()] if lines else []
    header = lines[0]
    return [f"{header}\n{row}".strip() for row in lines[1:]]


def _starts_new_legal_unit(line: str) -> bool:
    return bool(
        SECTION_HEADING_PATTERN.match(line)
        or SUBSECTION_START_PATTERN.match(line)
        or CLAUSE_START_PATTERN.match(line)
        or PROVISO_START_PATTERN.match(line)
        or EXPLANATION_START_PATTERN.match(line)
    )


def _split_long_segment(segment: str, *, max_tokens: int) -> list[str]:
    sentences = [piece.strip() for piece in SENTENCE_BOUNDARY_PATTERN.split(segment) if piece.strip()]
    if len(sentences) <= 1:
        return _split_by_token_window(segment, max_tokens=max_tokens)

    chunks: list[str] = []
    current_parts: list[str] = []
    current_tokens = 0
    for sentence in sentences:
        sentence_tokens = estimate_token_count(sentence)
        if current_parts and current_tokens + sentence_tokens > max_tokens:
            chunks.append(" ".join(current_parts).strip())
            current_parts = []
            current_tokens = 0
        if sentence_tokens > max_tokens:
            if current_parts:
                chunks.append(" ".join(current_parts).strip())
                current_parts = []
                current_tokens = 0
            chunks.extend(_split_by_token_window(sentence, max_tokens=max_tokens))
            continue
        current_parts.append(sentence)
        current_tokens += sentence_tokens
    if current_parts:
        chunks.append(" ".join(current_parts).strip())
    return chunks


def _split_by_token_window(text: str, *, max_tokens: int) -> list[str]:
    tokens = TOKEN_PATTERN.findall(text)
    if len(tokens) <= max_tokens:
        return [text.strip()]
    chunks: list[str] = []
    for start in range(0, len(tokens), max_tokens):
        token_slice = tokens[start : start + max_tokens]
        chunks.append(" ".join(token_slice).strip())
    return chunks


def _pack_segments(
    segments: list[str],
    *,
    min_tokens: int,
    target_tokens: int,
    max_tokens: int,
) -> list[str]:
    if not segments:
        return []
    packed: list[str] = []
    current_segments: list[str] = []
    current_tokens = 0

    for segment in segments:
        segment_tokens = estimate_token_count(segment)
        if current_segments and current_tokens + segment_tokens > max_tokens:
            packed.append("\n".join(current_segments).strip())
            current_segments = []
            current_tokens = 0
        current_segments.append(segment)
        current_tokens += segment_tokens
        if current_tokens >= target_tokens:
            packed.append("\n".join(current_segments).strip())
            current_segments = []
            current_tokens = 0

    if current_segments:
        if packed and current_tokens < min_tokens:
            remainder = "\n".join(current_segments).strip()
            packed[-1] = f"{packed[-1]}\n{remainder}".strip()
        else:
            packed.append("\n".join(current_segments).strip())
    return packed


def _build_reasoning_blocks(
    section_node: LegalNode,
    nodes: list[LegalNode],
) -> list[dict[str, Any]]:
    header_text = _render_anchor_text(section_node)
    blocks: list[dict[str, Any]] = [
        {
            "text": header_text,
            "linked_node_ids": [section_node.node_id],
        }
    ]
    section_related_nodes = [
        node
        for node in nodes
        if node.node_id != section_node.node_id
        and (
            node.metadata.get("governing_section_id") == section_node.node_id
            or node.section_number == section_node.section_number
        )
        and node.node_type
        in {
            LegalNodeType.SUBSECTION,
            LegalNodeType.CLAUSE,
            LegalNodeType.PROVISO,
            LegalNodeType.EXPLANATION,
            LegalNodeType.TABLE,
            LegalNodeType.DEFINITION,
            LegalNodeType.ILLUSTRATION,
        }
    ]
    section_related_nodes.sort(key=lambda node: (node.page_start, len(node.path_ids), node.node_id))

    if not section_related_nodes:
        blocks.append({"text": section_node.text.strip(), "linked_node_ids": [section_node.node_id]})
        return blocks

    for node in section_related_nodes:
        block_text = _render_reasoning_block(node)
        blocks.append(
            {
                "text": block_text,
                "linked_node_ids": [node.node_id, *node.metadata.get("expand_to_node_ids", [])],
            }
        )
    return blocks


def _render_reasoning_block(node: LegalNode) -> str:
    heading = node.label or node.citability_label or node.title or node.node_type.value.title()
    title = node.title if node.title and node.title != heading else None
    parts = [heading]
    if title:
        parts.append(title)
    if node.node_type in {LegalNodeType.SECTION, LegalNodeType.SUBSECTION} and node.child_ids:
        text = ""
    else:
        text = _trim_text_for_node(node)
    if text and text not in parts:
        parts.append(text)
    return "\n".join(part.strip() for part in parts if part and part.strip())


def _trim_text_for_node(node: LegalNode) -> str:
    lines = [line.strip() for line in node.text.splitlines() if line.strip()]
    if len(lines) <= 1:
        return "\n".join(lines).strip()

    trimmed_lines: list[str] = []
    for index, line in enumerate(lines):
        if index > 0 and _line_belongs_to_descendant(node, line):
            break
        trimmed_lines.append(line)
    return "\n".join(trimmed_lines).strip()


def _line_belongs_to_descendant(node: LegalNode, line: str) -> bool:
    if node.node_type is LegalNodeType.CLAUSE:
        return bool(PROVISO_START_PATTERN.match(line) or EXPLANATION_START_PATTERN.match(line) or CLAUSE_START_PATTERN.match(line))
    if node.node_type is LegalNodeType.PROVISO:
        return bool(EXPLANATION_START_PATTERN.match(line) or PROVISO_START_PATTERN.match(line) or CLAUSE_START_PATTERN.match(line))
    if node.node_type is LegalNodeType.EXPLANATION:
        return bool(EXPLANATION_START_PATTERN.match(line) or PROVISO_START_PATTERN.match(line) or CLAUSE_START_PATTERN.match(line))
    if node.node_type is LegalNodeType.SUBSECTION:
        return bool(CLAUSE_START_PATTERN.match(line) or PROVISO_START_PATTERN.match(line) or EXPLANATION_START_PATTERN.match(line))
    return False


def _pack_blocks(
    blocks: list[dict[str, Any]],
    *,
    min_tokens: int,
    target_tokens: int,
    max_tokens: int,
) -> list[list[dict[str, Any]]]:
    total_tokens = sum(estimate_token_count(block["text"]) for block in blocks)
    if total_tokens <= max_tokens:
        return [blocks]

    grouped: list[list[dict[str, Any]]] = []
    current_group: list[dict[str, Any]] = []
    current_tokens = 0

    for block in blocks:
        block_tokens = estimate_token_count(block["text"])
        if current_group and current_tokens + block_tokens > max_tokens:
            grouped.append(current_group)
            current_group = []
            current_tokens = 0
        current_group.append(block)
        current_tokens += block_tokens
        if current_tokens >= target_tokens:
            grouped.append(current_group)
            current_group = []
            current_tokens = 0

    if current_group:
        if grouped and current_tokens < min_tokens:
            grouped[-1].extend(current_group)
        else:
            grouped.append(current_group)
    return grouped


def _linked_node_ids_for_retrieval(node: LegalNode) -> list[str]:
    return _unique_preserve_order(
        [
            node.node_id,
            node.metadata.get("reasoning_parent_id"),
            node.metadata.get("governing_rule_id"),
            node.metadata.get("governing_section_id"),
            *node.metadata.get("expand_to_node_ids", []),
        ]
    )


def _build_chunk(
    *,
    chunk_id: str,
    chunk_scope: Literal["retrieval_child", "reasoning_parent"],
    chunk_variant: str,
    source_node: LegalNode,
    text: str,
    chunk_type: str,
    linked_node_ids: list[str],
    metadata: dict[str, Any],
) -> LegalChunk:
    cleaned_text = text.strip()
    normalized = normalize_text(cleaned_text)
    return LegalChunk(
        chunk_id=chunk_id,
        document_id=source_node.document_id,
        act_title=source_node.act_title,
        chunk_scope=chunk_scope,
        chunk_variant=chunk_variant,
        source_node_id=source_node.node_id,
        source_node_type=source_node.node_type,
        reasoning_parent_id=source_node.metadata.get("reasoning_parent_id") or source_node.node_id,
        parent_node_id=source_node.parent_id,
        chunk_type=chunk_type,
        text=cleaned_text,
        normalized_text=normalized,
        token_count=estimate_token_count(cleaned_text),
        page_start=source_node.page_start,
        page_end=source_node.page_end,
        page_numbers=list(range(source_node.page_start, source_node.page_end + 1)),
        part_number=source_node.part_number,
        part_title=source_node.part_title,
        chapter_number=source_node.chapter_number,
        chapter_title=source_node.chapter_title,
        section_number=source_node.section_number,
        subsection_number=source_node.subsection_number,
        clause_number=source_node.clause_number,
        citability_label=source_node.citability_label,
        label=source_node.label,
        title=source_node.title,
        linked_node_ids=_unique_preserve_order(linked_node_ids),
        metadata=metadata,
    )


def _next_chunk_id(document_id: str, scope: str, counter: count[int]) -> str:
    return f"{document_id}:{scope}:{next(counter):05d}"


def estimate_token_count(text: str) -> int:
    return len(TOKEN_PATTERN.findall(text))


def _unique_preserve_order(values: list[str | None]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        ordered.append(value)
    return ordered
