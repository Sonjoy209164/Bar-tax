from pydantic import BaseModel, Field, field_validator

from app.domain.legal_types import CitationRelation


class LegalCitation(BaseModel):
    node_id: str
    document_id: str
    act_title: str
    relation: CitationRelation = CitationRelation.DIRECT
    part_number: str | None = None
    part_title: str | None = None
    chapter_number: str | None = None
    chapter_title: str | None = None
    section_number: str | None = None
    subsection_number: str | None = None
    clause_number: str | None = None
    page_start: int | None = Field(default=None, ge=1)
    page_end: int | None = Field(default=None, ge=1)
    citability_label: str | None = None
    snippet: str | None = None

    @field_validator("page_end")
    @classmethod
    def validate_page_range(cls, value: int | None, info):  # type: ignore[no-untyped-def]
        page_start = info.data.get("page_start")
        if value is not None and page_start is not None and value < page_start:
            raise ValueError("page_end must be greater than or equal to page_start")
        return value
