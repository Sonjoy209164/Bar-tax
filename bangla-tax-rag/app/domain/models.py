from typing import Any

from pydantic import BaseModel, Field, computed_field, field_validator, model_validator

from app.domain.citations import LegalCitation
from app.domain.legal_types import LegalNodeType


class LegalNode(BaseModel):
    node_id: str = Field(..., description="Stable unique identifier for the legal node.")
    document_id: str = Field(..., description="Document identifier this node belongs to.")
    act_title: str = Field(..., description="Canonical act title.")
    node_type: LegalNodeType
    text: str = Field(..., description="Source text captured for this legal node.")
    normalized_text: str = Field(..., description="Normalized text used for retrieval and reasoning.")
    page_start: int = Field(..., ge=1)
    page_end: int = Field(..., ge=1)
    parent_id: str | None = Field(default=None, description="Immediate parent node identifier.")
    child_ids: list[str] = Field(default_factory=list)
    path_ids: list[str] = Field(default_factory=list, description="Hierarchy path including this node.")
    path_labels: list[str] = Field(default_factory=list, description="Human-readable path labels aligned to path_ids.")
    label: str | None = Field(default=None, description="Short display label such as 'Section 4'.")
    title: str | None = Field(default=None, description="Heading title for the node.")
    part_number: str | None = None
    part_title: str | None = None
    chapter_number: str | None = None
    chapter_title: str | None = None
    section_number: str | None = None
    subsection_number: str | None = None
    clause_number: str | None = None
    proviso_number: str | None = None
    explanation_number: str | None = None
    page_anchor_text: str | None = Field(default=None, description="Optional layout anchor or heading text from the source page.")
    cross_references: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("text", "normalized_text")
    @classmethod
    def validate_non_empty_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("text fields must not be empty")
        return stripped

    @field_validator("page_end")
    @classmethod
    def validate_page_range(cls, value: int, info):  # type: ignore[no-untyped-def]
        page_start = info.data.get("page_start")
        if page_start is not None and value < page_start:
            raise ValueError("page_end must be greater than or equal to page_start")
        return value

    @model_validator(mode="after")
    def validate_hierarchy(self) -> "LegalNode":
        if self.path_ids and self.path_ids[-1] != self.node_id:
            raise ValueError("path_ids must end with the node's own node_id")
        if self.path_labels and len(self.path_labels) != len(self.path_ids):
            raise ValueError("path_labels must align 1:1 with path_ids")
        if self.node_type in {
            LegalNodeType.SECTION,
            LegalNodeType.SUBSECTION,
            LegalNodeType.CLAUSE,
            LegalNodeType.PROVISO,
            LegalNodeType.EXPLANATION,
            LegalNodeType.DEFINITION,
        } and not self.section_number:
            raise ValueError(f"{self.node_type.value} nodes must include section_number")
        if self.node_type is LegalNodeType.SUBSECTION and not self.subsection_number:
            raise ValueError("subsection nodes must include subsection_number")
        if self.node_type is LegalNodeType.CLAUSE and not self.clause_number:
            raise ValueError("clause nodes must include clause_number")
        return self

    @computed_field  # type: ignore[prop-decorator]
    @property
    def citability_label(self) -> str:
        parts: list[str] = []
        if self.part_number:
            parts.append(f"Part {self.part_number}")
        if self.chapter_number:
            parts.append(f"Chapter {self.chapter_number}")
        if self.section_number:
            parts.append(f"Section {self.section_number}")
        if self.subsection_number:
            parts.append(f"Subsection {self.subsection_number}")
        if self.clause_number:
            parts.append(f"Clause {self.clause_number}")
        if self.proviso_number:
            parts.append(f"Proviso {self.proviso_number}")
        if self.explanation_number:
            parts.append(f"Explanation {self.explanation_number}")
        if parts:
            return " > ".join(parts)
        if self.label:
            return self.label
        return self.node_type.value.title()

    @computed_field  # type: ignore[prop-decorator]
    @property
    def is_leaf(self) -> bool:
        return not self.child_ids

    def to_citation(self, *, snippet: str | None = None) -> LegalCitation:
        return LegalCitation(
            node_id=self.node_id,
            document_id=self.document_id,
            act_title=self.act_title,
            part_number=self.part_number,
            part_title=self.part_title,
            chapter_number=self.chapter_number,
            chapter_title=self.chapter_title,
            section_number=self.section_number,
            subsection_number=self.subsection_number,
            clause_number=self.clause_number,
            page_start=self.page_start,
            page_end=self.page_end,
            citability_label=self.citability_label,
            snippet=snippet,
        )


class EvidenceItem(BaseModel):
    evidence_id: str
    node_id: str
    parent_node_id: str | None = None
    citation: LegalCitation
    source_text: str
    score: float = 0.0
    retrieval_method: str
    supporting_node_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("source_text")
    @classmethod
    def validate_source_text(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("source_text must not be empty")
        return stripped
