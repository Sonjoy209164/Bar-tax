from __future__ import annotations

import re
from pathlib import Path
from typing import Callable

from pydantic import BaseModel, Field

from app.domain import LegalNode, LegalNodeType
from app.ingestion.parser_base import ParsedDocument

PART_HEADING_PATTERN = re.compile(r"^PART\s+([IVXLC0-9]+)\s*$", re.IGNORECASE)
CHAPTER_HEADING_PATTERN = re.compile(r"^CHAPTER\s+([IVXLC0-9]+)\s*$", re.IGNORECASE)
SECTION_HEADING_PATTERN = re.compile(r"^(\d+[A-Za-z]?(?:\.\d+)?)\.\s+(.+)$")
SUBSECTION_PATTERN = re.compile(r"^\((\d+[A-Za-z]?)\)\s*(.*)$")
CLAUSE_PATTERN = re.compile(r"^\(([a-z])\)\s*(.*)$", re.IGNORECASE)
PROVISO_PATTERN = re.compile(r"^(Provided(?:\s+further|\s+also)?\s+that\b.*)$", re.IGNORECASE)
EXPLANATION_PATTERN = re.compile(r"^(Explanation(?:\s+\d+|\s+[IVXLC]+)?(?:\s*[.:—-])?\s*.*)$", re.IGNORECASE)
ALL_CAPS_TITLE_PATTERN = re.compile(r"^[A-Z][A-Z\s,&/()-]{2,}$")
TABLE_LINE_PATTERN = re.compile(r"(?:\|)|(?:\S\s{2,}\S)")


class StructuredLegalDocument(BaseModel):
    document_id: str
    act_title: str
    source_path: str
    parser_provider: str
    root_node_id: str
    nodes: list[LegalNode] = Field(default_factory=list)


def build_legal_structure(
    parsed_document: ParsedDocument,
    *,
    document_id: str | None = None,
    act_title: str | None = None,
) -> StructuredLegalDocument:
    builder = _StructureBuilder(
        document_id=document_id or Path(parsed_document.source_path).stem,
        act_title=act_title or _derive_act_title(parsed_document),
        source_path=parsed_document.source_path,
        parser_provider=parsed_document.parser_provider,
    )
    return builder.build(parsed_document)


def _derive_act_title(parsed_document: ParsedDocument) -> str:
    for page in parsed_document.pages:
        for heading in page.headings:
            normalized = heading.strip()
            if normalized:
                return normalized
        for line in page.raw_text.splitlines():
            normalized = line.strip()
            if normalized:
                return normalized
    return Path(parsed_document.source_path).stem.replace("_", " ").strip() or "Legal Document"


class _StructureBuilder:
    def __init__(self, *, document_id: str, act_title: str, source_path: str, parser_provider: str) -> None:
        self.document_id = document_id
        self.act_title = act_title
        self.source_path = source_path
        self.parser_provider = parser_provider
        self.nodes: list[LegalNode] = []
        self.node_map: dict[str, LegalNode] = {}
        self.root_node = self._create_root_node()
        self.current_part_id: str | None = None
        self.current_chapter_id: str | None = None
        self.current_section_state: dict | None = None
        self.pending_part_title_id: str | None = None
        self.pending_chapter_title_id: str | None = None
        self.preamble_lines: list[str] = []

    def build(self, parsed_document: ParsedDocument) -> StructuredLegalDocument:
        line_records = self._flatten_document_lines(parsed_document)
        index = 0
        while index < len(line_records):
            page_no, line = line_records[index]
            if not line:
                index += 1
                continue

            part_match = PART_HEADING_PATTERN.match(line)
            if part_match:
                self._finalize_current_section()
                node = self._create_heading_node(
                    node_type=LegalNodeType.PART,
                    parent_id=self.root_node.node_id,
                    label=f"Part {part_match.group(1)}",
                    title=None,
                    text=line,
                    page_no=page_no,
                    part_number=part_match.group(1),
                )
                self.current_part_id = node.node_id
                self.current_chapter_id = None
                self.pending_part_title_id = node.node_id
                self.pending_chapter_title_id = None
                index += 1
                continue

            chapter_match = CHAPTER_HEADING_PATTERN.match(line)
            if chapter_match:
                self._finalize_current_section()
                parent_id = self.current_part_id or self.root_node.node_id
                node = self._create_heading_node(
                    node_type=LegalNodeType.CHAPTER,
                    parent_id=parent_id,
                    label=f"Chapter {chapter_match.group(1)}",
                    title=None,
                    text=line,
                    page_no=page_no,
                    part_number=self._current_part_number(),
                    part_title=self._current_part_title(),
                    chapter_number=chapter_match.group(1),
                )
                self.current_chapter_id = node.node_id
                self.pending_chapter_title_id = node.node_id
                index += 1
                continue

            if self.pending_part_title_id and self._is_context_title_line(line):
                node = self.node_map[self.pending_part_title_id]
                node.title = line
                node.part_title = line
                node.text = f"{node.text}\n{line}".strip()
                node.normalized_text = node.text
                self.pending_part_title_id = None
                index += 1
                continue

            if self.pending_chapter_title_id and self._is_context_title_line(line):
                node = self.node_map[self.pending_chapter_title_id]
                node.title = line
                node.chapter_title = line
                node.text = f"{node.text}\n{line}".strip()
                node.normalized_text = node.text
                self.pending_chapter_title_id = None
                index += 1
                continue

            section_match = SECTION_HEADING_PATTERN.match(line)
            if section_match:
                self._finalize_current_section()
                self.current_section_state = {
                    "section_number": section_match.group(1),
                    "title": section_match.group(2).strip(),
                    "page_start": page_no,
                    "page_end": page_no,
                    "lines": [(page_no, line)],
                    "part_number": self._current_part_number(),
                    "part_title": self._current_part_title(),
                    "chapter_number": self._current_chapter_number(),
                    "chapter_title": self._current_chapter_title(),
                }
                index += 1
                continue

            if self.current_section_state is not None:
                self.current_section_state["lines"].append((page_no, line))
                self.current_section_state["page_end"] = page_no
                index += 1
                continue

            self.preamble_lines.append(line)
            index += 1

        self._finalize_current_section()
        if self.preamble_lines:
            preamble_text = "\n".join(self.preamble_lines).strip()
            if preamble_text:
                self.root_node.text = f"{self.root_node.text}\n{preamble_text}".strip()
                self.root_node.normalized_text = self.root_node.text

        return StructuredLegalDocument(
            document_id=self.document_id,
            act_title=self.act_title,
            source_path=self.source_path,
            parser_provider=self.parser_provider,
            root_node_id=self.root_node.node_id,
            nodes=self.nodes,
        )

    def _flatten_document_lines(self, parsed_document: ParsedDocument) -> list[tuple[int, str]]:
        records: list[tuple[int, str]] = []
        for page in parsed_document.pages:
            for raw_line in page.raw_text.splitlines():
                line = raw_line.strip()
                if line:
                    records.append((page.page_no, line))
        return records

    def _create_root_node(self) -> LegalNode:
        root_id = f"{self.document_id}:act"
        root = LegalNode(
            node_id=root_id,
            document_id=self.document_id,
            act_title=self.act_title,
            node_type=LegalNodeType.ACT,
            text=self.act_title,
            normalized_text=self.act_title,
            page_start=1,
            page_end=1,
            path_ids=[root_id],
            path_labels=[self.act_title],
            label=self.act_title,
            title=self.act_title,
        )
        self.nodes.append(root)
        self.node_map[root_id] = root
        return root

    def _create_heading_node(
        self,
        *,
        node_type: LegalNodeType,
        parent_id: str,
        label: str,
        title: str | None,
        text: str,
        page_no: int,
        part_number: str | None = None,
        part_title: str | None = None,
        chapter_number: str | None = None,
        chapter_title: str | None = None,
    ) -> LegalNode:
        node_id = self._build_node_id(node_type, label)
        parent = self.node_map[parent_id]
        node = LegalNode(
            node_id=node_id,
            document_id=self.document_id,
            act_title=self.act_title,
            node_type=node_type,
            text=text,
            normalized_text=text,
            page_start=page_no,
            page_end=page_no,
            parent_id=parent_id,
            child_ids=[],
            path_ids=[*parent.path_ids, node_id],
            path_labels=[*parent.path_labels, label],
            label=label,
            title=title,
            part_number=part_number,
            part_title=part_title,
            chapter_number=chapter_number,
            chapter_title=chapter_title,
        )
        self._register_node(node)
        return node

    def _finalize_current_section(self) -> None:
        if self.current_section_state is None:
            return
        state = self.current_section_state
        section_number = state["section_number"]
        title = state["title"]
        page_start = state["page_start"]
        page_end = state["page_end"]
        line_records: list[tuple[int, str]] = state["lines"]
        section_text = "\n".join(line for _, line in line_records).strip()
        parent_id = self.current_chapter_id or self.current_part_id or self.root_node.node_id
        parent = self.node_map[parent_id]
        section_id = self._build_node_id(LegalNodeType.SECTION, section_number)
        section_node = LegalNode(
            node_id=section_id,
            document_id=self.document_id,
            act_title=self.act_title,
            node_type=LegalNodeType.SECTION,
            text=section_text,
            normalized_text=section_text,
            page_start=page_start,
            page_end=page_end,
            parent_id=parent_id,
            child_ids=[],
            path_ids=[*parent.path_ids, section_id],
            path_labels=[*parent.path_labels, f"Section {section_number}"],
            label=f"Section {section_number}",
            title=title,
            part_number=state["part_number"],
            part_title=state["part_title"],
            chapter_number=state["chapter_number"],
            chapter_title=state["chapter_title"],
            section_number=section_number,
            page_anchor_text=line_records[0][1] if line_records else None,
        )
        self._register_node(section_node)
        self._update_context_page_ranges(page_end)
        self._build_section_children(section_node, line_records[1:])
        self.current_section_state = None

    def _build_section_children(self, section_node: LegalNode, line_records: list[tuple[int, str]]) -> None:
        subsection_segments = self._segment_records(line_records, lambda line: SUBSECTION_PATTERN.match(line))
        if subsection_segments:
            for match, records in subsection_segments:
                subsection_number = match.group(1)
                subsection_text = "\n".join(line for _, line in records).strip()
                subsection_id = self._build_node_id(
                    LegalNodeType.SUBSECTION,
                    f"{section_node.section_number}.{subsection_number}",
                )
                subsection_node = LegalNode(
                    node_id=subsection_id,
                    document_id=self.document_id,
                    act_title=self.act_title,
                    node_type=LegalNodeType.SUBSECTION,
                    text=subsection_text,
                    normalized_text=subsection_text,
                    page_start=records[0][0],
                    page_end=records[-1][0],
                    parent_id=section_node.node_id,
                    child_ids=[],
                    path_ids=[*section_node.path_ids, subsection_id],
                    path_labels=[*section_node.path_labels, f"Subsection {subsection_number}"],
                    label=f"Subsection {subsection_number}",
                    title=match.group(2).strip() or None,
                    part_number=section_node.part_number,
                    part_title=section_node.part_title,
                    chapter_number=section_node.chapter_number,
                    chapter_title=section_node.chapter_title,
                    section_number=section_node.section_number,
                    subsection_number=subsection_number,
                    page_anchor_text=records[0][1],
                )
                self._register_node(subsection_node)
                self._build_clause_and_special_children(subsection_node, records[1:])
            return
        self._build_clause_and_special_children(section_node, line_records)

    def _build_clause_and_special_children(self, parent_node: LegalNode, line_records: list[tuple[int, str]]) -> None:
        clause_segments = self._segment_records(line_records, lambda line: CLAUSE_PATTERN.match(line))
        if clause_segments:
            for match, records in clause_segments:
                clause_number = match.group(1)
                clause_text = "\n".join(line for _, line in records).strip()
                clause_id = self._build_node_id(
                    LegalNodeType.CLAUSE,
                    f"{parent_node.section_number}.{parent_node.subsection_number or 'root'}.{clause_number}",
                )
                clause_node = LegalNode(
                    node_id=clause_id,
                    document_id=self.document_id,
                    act_title=self.act_title,
                    node_type=LegalNodeType.CLAUSE,
                    text=clause_text,
                    normalized_text=clause_text,
                    page_start=records[0][0],
                    page_end=records[-1][0],
                    parent_id=parent_node.node_id,
                    child_ids=[],
                    path_ids=[*parent_node.path_ids, clause_id],
                    path_labels=[*parent_node.path_labels, f"Clause {clause_number}"],
                    label=f"Clause {clause_number}",
                    part_number=parent_node.part_number,
                    part_title=parent_node.part_title,
                    chapter_number=parent_node.chapter_number,
                    chapter_title=parent_node.chapter_title,
                    section_number=parent_node.section_number,
                    subsection_number=parent_node.subsection_number,
                    clause_number=clause_number,
                    page_anchor_text=records[0][1],
                )
                self._register_node(clause_node)

        self._build_special_units(parent_node, line_records, PROVISO_PATTERN, LegalNodeType.PROVISO)
        self._build_special_units(parent_node, line_records, EXPLANATION_PATTERN, LegalNodeType.EXPLANATION)
        self._build_table_nodes(parent_node, line_records)

    def _build_special_units(
        self,
        parent_node: LegalNode,
        line_records: list[tuple[int, str]],
        pattern: re.Pattern[str],
        node_type: LegalNodeType,
    ) -> None:
        segments = self._segment_records(line_records, lambda line: pattern.match(line))
        for index, (_, records) in enumerate(segments, start=1):
            text = "\n".join(line for _, line in records).strip()
            label = f"{node_type.value.title()} {index}"
            node_id = self._build_node_id(node_type, f"{parent_node.node_id}:{index}")
            node = LegalNode(
                node_id=node_id,
                document_id=self.document_id,
                act_title=self.act_title,
                node_type=node_type,
                text=text,
                normalized_text=text,
                page_start=records[0][0],
                page_end=records[-1][0],
                parent_id=parent_node.node_id,
                child_ids=[],
                path_ids=[*parent_node.path_ids, node_id],
                path_labels=[*parent_node.path_labels, label],
                label=label,
                part_number=parent_node.part_number,
                part_title=parent_node.part_title,
                chapter_number=parent_node.chapter_number,
                chapter_title=parent_node.chapter_title,
                section_number=parent_node.section_number,
                subsection_number=parent_node.subsection_number,
                clause_number=parent_node.clause_number,
                proviso_number=str(index) if node_type is LegalNodeType.PROVISO else None,
                explanation_number=str(index) if node_type is LegalNodeType.EXPLANATION else None,
                page_anchor_text=records[0][1],
            )
            self._register_node(node)

    def _build_table_nodes(self, parent_node: LegalNode, line_records: list[tuple[int, str]]) -> None:
        blocks: list[list[tuple[int, str]]] = []
        current_block: list[tuple[int, str]] = []
        for record in line_records:
            if TABLE_LINE_PATTERN.search(record[1]):
                current_block.append(record)
            else:
                if len(current_block) >= 2:
                    blocks.append(current_block)
                current_block = []
        if len(current_block) >= 2:
            blocks.append(current_block)

        for index, block in enumerate(blocks, start=1):
            table_text = "\n".join(line for _, line in block).strip()
            node_id = self._build_node_id(LegalNodeType.TABLE, f"{parent_node.node_id}:{index}")
            node = LegalNode(
                node_id=node_id,
                document_id=self.document_id,
                act_title=self.act_title,
                node_type=LegalNodeType.TABLE,
                text=table_text,
                normalized_text=table_text,
                page_start=block[0][0],
                page_end=block[-1][0],
                parent_id=parent_node.node_id,
                child_ids=[],
                path_ids=[*parent_node.path_ids, node_id],
                path_labels=[*parent_node.path_labels, f"Table {index}"],
                label=f"Table {index}",
                part_number=parent_node.part_number,
                part_title=parent_node.part_title,
                chapter_number=parent_node.chapter_number,
                chapter_title=parent_node.chapter_title,
                section_number=parent_node.section_number,
                subsection_number=parent_node.subsection_number,
                clause_number=parent_node.clause_number,
                page_anchor_text=block[0][1],
            )
            self._register_node(node)

    def _segment_records(
        self,
        line_records: list[tuple[int, str]],
        matcher: Callable[[str], re.Match[str] | None],
    ) -> list[tuple[re.Match[str], list[tuple[int, str]]]]:
        segments: list[tuple[re.Match[str], list[tuple[int, str]]]] = []
        current_match: re.Match[str] | None = None
        current_records: list[tuple[int, str]] = []
        for record in line_records:
            match = matcher(record[1])
            if match:
                if current_match is not None and current_records:
                    segments.append((current_match, current_records))
                current_match = match
                current_records = [record]
                continue
            if current_match is not None:
                current_records.append(record)
        if current_match is not None and current_records:
            segments.append((current_match, current_records))
        return segments

    def _register_node(self, node: LegalNode) -> None:
        self.nodes.append(node)
        self.node_map[node.node_id] = node
        if node.parent_id:
            parent = self.node_map[node.parent_id]
            if node.node_id not in parent.child_ids:
                parent.child_ids.append(node.node_id)

    def _update_context_page_ranges(self, page_end: int) -> None:
        self.root_node.page_end = max(self.root_node.page_end, page_end)
        for node_id in (self.current_part_id, self.current_chapter_id):
            if node_id:
                self.node_map[node_id].page_end = max(self.node_map[node_id].page_end, page_end)

    def _is_context_title_line(self, line: str) -> bool:
        if PART_HEADING_PATTERN.match(line) or CHAPTER_HEADING_PATTERN.match(line) or SECTION_HEADING_PATTERN.match(line):
            return False
        return bool(ALL_CAPS_TITLE_PATTERN.match(line))

    def _build_node_id(self, node_type: LegalNodeType, token: str) -> str:
        slug = re.sub(r"[^a-z0-9]+", "-", token.lower()).strip("-") or "node"
        return f"{self.document_id}:{node_type.value}:{slug}"

    def _current_part_number(self) -> str | None:
        if not self.current_part_id:
            return None
        return self.node_map[self.current_part_id].part_number

    def _current_part_title(self) -> str | None:
        if not self.current_part_id:
            return None
        return self.node_map[self.current_part_id].part_title or self.node_map[self.current_part_id].title

    def _current_chapter_number(self) -> str | None:
        if not self.current_chapter_id:
            return None
        return self.node_map[self.current_chapter_id].chapter_number

    def _current_chapter_title(self) -> str | None:
        if not self.current_chapter_id:
            return None
        return self.node_map[self.current_chapter_id].chapter_title or self.node_map[self.current_chapter_id].title
