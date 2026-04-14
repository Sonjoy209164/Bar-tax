from app.domain import CitationRelation, LegalNodeType
from app.ingestion import (
    ParsedDocument,
    build_legal_chunks,
    build_legal_structure,
    build_parsed_page_from_text,
    link_parent_child_relationships,
    tag_legal_metadata,
)
from app.retrieval import GraphExpander


def test_graph_expander_expands_clause_to_parent_siblings_proviso_and_explanation() -> None:
    linked_document, chunks = _definition_fixture()
    clause_chunk = next(
        chunk
        for chunk in chunks
        if chunk.source_node_type is LegalNodeType.CLAUSE and "chief commissioner" in chunk.normalized_text.lower()
    )

    result = GraphExpander(linked_document).expand_chunk(clause_chunk)

    relations = {item.citation.relation for item in result.evidence}
    expanded_ids = set(result.expanded_node_ids)

    assert CitationRelation.DIRECT in relations
    assert CitationRelation.PARENT_CONTEXT in relations
    assert CitationRelation.SIBLING_CONTEXT in relations
    assert CitationRelation.GOVERNING_RULE in relations
    assert any(node_id != clause_chunk.source_node_id for node_id in expanded_ids)


def test_graph_expander_expands_section_anchor_to_attached_table() -> None:
    linked_document, chunks = _table_fixture()
    anchor_chunk = next(chunk for chunk in chunks if chunk.chunk_variant == "anchor")

    result = GraphExpander(linked_document).expand_chunk(anchor_chunk)

    relations = {item.citation.relation for item in result.evidence}
    assert CitationRelation.DIRECT in relations
    assert CitationRelation.ATTACHED_TABLE in relations


def _definition_fixture():
    parsed_document = ParsedDocument(
        source_path="Income_tax_act_2023.pdf",
        parser_provider="fallback",
        pages=[
            build_parsed_page_from_text(
                1,
                "\n".join(
                    [
                        "2. Definitions.— In this Act, unless there is anything repugnant in the subject or context,—",
                        '(1) "Commissioner" means Commissioner of Taxes.',
                        "(a) Chief Commissioner of Taxes;",
                        "(b) Commissioner of Taxes (Appeals);",
                        "Provided that this definition applies only where the context so requires.",
                        "Explanation 1.— Reference to Commissioner includes Large Taxpayer Unit.",
                    ]
                ),
            )
        ],
    )
    structured = build_legal_structure(parsed_document, document_id="income-tax-act-2023", act_title="Income Tax Act 2023")
    linked = link_parent_child_relationships(tag_legal_metadata(structured))
    artifacts = build_legal_chunks(linked)
    return linked, artifacts.retrieval_chunks


def _table_fixture():
    parsed_document = ParsedDocument(
        source_path="Income_tax_act_2023.pdf",
        parser_provider="fallback",
        pages=[
            build_parsed_page_from_text(
                10,
                "\n".join(
                    [
                        "23. Tax on stock dividend.—The tax shall be charged at the following rates:",
                        "Serial | Income | Rate",
                        "1 | Stock dividend | 10 percent",
                        "2 | Cash dividend | 20 percent",
                    ]
                ),
            )
        ],
    )
    structured = build_legal_structure(parsed_document, document_id="income-tax-act-2023", act_title="Income Tax Act 2023")
    linked = link_parent_child_relationships(tag_legal_metadata(structured))
    artifacts = build_legal_chunks(linked)
    return linked, artifacts.retrieval_chunks
