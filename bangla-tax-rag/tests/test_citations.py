from app.core.schemas import AnswerSentence, RetrievalHit
from app.generation.citations import (
    build_citation_records,
    extract_citation_markers,
    map_markers_to_citations,
    render_inline_cited_answer,
)


def _hit(chunk_id: str, page_no: int = 1) -> RetrievalHit:
    return RetrievalHit(
        chunk_id=chunk_id,
        doc_id="doc-1",
        doc_title="Income Tax Circular",
        page_no=page_no,
        section_id="3",
        subsection_id="3.1",
        chunk_type="table",
        authority_level="national",
        tax_year="2025-2026",
        original_text="ধারা 3.1 অনুযায়ী করহার 10 শতাংশ",
        normalized_text="ধারা 3.1 অনুযায়ী করহার 10 শতাংশ",
        heading_path=["ধারা 3.1"],
        content="ধারা 3.1 অনুযায়ী করহার 10 শতাংশ",
        score=3.2,
        intermediate_scores={},
    )


def test_citation_marker_rendering() -> None:
    sentences = [
        AnswerSentence(sentence_text="করহার ১০ শতাংশ।", citation_markers=["[C1]"]),
        AnswerSentence(sentence_text="এটি কোম্পানির জন্য প্রযোজ্য।", citation_markers=["[C2]"]),
    ]

    rendered = render_inline_cited_answer(sentences)

    assert "[C1]" in rendered
    assert "[C2]" in rendered


def test_citation_mapping_and_marker_extraction() -> None:
    citations = build_citation_records([_hit("chunk-a"), _hit("chunk-b", page_no=2)])
    citation_map = map_markers_to_citations(citations)
    markers = extract_citation_markers("করহার ১০ শতাংশ। [C1] এটি প্রযোজ্য। [C2]")

    assert citations[0].marker == "[C1]"
    assert citation_map["[C2]"].chunk_id == "chunk-b"
    assert markers == ["[C1]", "[C2]"]
