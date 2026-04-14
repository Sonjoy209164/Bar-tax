from __future__ import annotations

from pydantic import BaseModel, Field

from app.domain import LegalCitation


class CitationPayload(BaseModel):
    node_id: str
    relation: str
    section: str | None = None
    subsection: str | None = None
    clause: str | None = None
    page_start: int | None = None
    page_end: int | None = None
    label: str | None = None
    snippet: str | None = None


class CitationService:
    def build_payloads(self, citations: list[LegalCitation]) -> list[CitationPayload]:
        seen: set[tuple[str, str, str | None, str | None, str | None]] = set()
        payloads: list[CitationPayload] = []
        for citation in citations:
            key = (
                citation.node_id,
                citation.relation.value,
                citation.section_number,
                citation.subsection_number,
                citation.clause_number,
            )
            if key in seen:
                continue
            payloads.append(
                CitationPayload(
                    node_id=citation.node_id,
                    relation=citation.relation.value,
                    section=citation.section_number,
                    subsection=citation.subsection_number,
                    clause=citation.clause_number,
                    page_start=citation.page_start,
                    page_end=citation.page_end,
                    label=citation.citability_label,
                    snippet=citation.snippet,
                )
            )
            seen.add(key)
        return payloads


def build_citation_payloads(citations: list[LegalCitation]) -> list[CitationPayload]:
    return CitationService().build_payloads(citations)
