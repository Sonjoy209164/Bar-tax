import re

from app.core.schemas import AnswerSentence, CitationRecord, RetrievalHit
from app.core.utils import truncate_text

MARKER_PATTERN = re.compile(r"\[(C\d+)\]")


def build_citation_records(evidence_hits: list[RetrievalHit]) -> list[CitationRecord]:
    citation_records: list[CitationRecord] = []
    for index, hit in enumerate(evidence_hits, start=1):
        citation_records.append(
            CitationRecord(
                marker=f"[C{index}]",
                chunk_id=hit.chunk_id,
                doc_title=hit.doc_title,
                page_no=hit.page_no,
                section_id=hit.section_id,
                subsection_id=hit.subsection_id,
                evidence_snippet=truncate_text(hit.original_text, max_length=320),
            )
        )
    return citation_records


def extract_citation_markers(text: str) -> list[str]:
    return [f"[{match}]" for match in MARKER_PATTERN.findall(text)]


def render_inline_cited_answer(answer_sentences: list[AnswerSentence]) -> str:
    rendered_sentences: list[str] = []
    for sentence in answer_sentences:
        marker_suffix = ""
        if sentence.citation_markers:
            marker_suffix = " " + " ".join(sentence.citation_markers)
        rendered_sentences.append(f"{sentence.sentence_text}{marker_suffix}".strip())
    return " ".join(rendered_sentences).strip()


def format_citations(citations_or_hits: list[CitationRecord] | list[RetrievalHit] | list[dict]) -> list[str]:
    if not citations_or_hits:
        return []
    first_item = citations_or_hits[0]
    if isinstance(first_item, CitationRecord):
        return [citation.marker for citation in citations_or_hits]
    if isinstance(first_item, RetrievalHit):
        return [citation.marker for citation in build_citation_records(citations_or_hits)]
    return [str(item["chunk_id"]) for item in citations_or_hits]


def map_markers_to_citations(citations: list[CitationRecord]) -> dict[str, CitationRecord]:
    return {citation.marker: citation for citation in citations}
