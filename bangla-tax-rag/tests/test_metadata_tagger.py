import pytest

from app.domain import LegalNodeType
from app.ingestion import (
    ParsedDocument,
    build_legal_structure,
    build_parsed_page_from_text,
    tag_legal_metadata,
    validate_tagged_document,
)


def test_metadata_tagger_attaches_required_fields_and_semantic_chunk_types() -> None:
    parsed_document = ParsedDocument(
        source_path="Income_tax_act_2023.pdf",
        parser_provider="fallback",
        pages=[
            build_parsed_page_from_text(
                1,
                "\n".join(
                    [
                        "PART I",
                        "PRELIMINARY",
                        "CHAPTER I",
                        "BASIS OF CHARGE",
                        "2. Definitions.— In this Act, unless there is anything repugnant in the subject or context,—",
                        "(1) “Commissioner” means Commissioner of Taxes as referred to in section 4.",
                        "(a) Chief Commissioner of Taxes under clause (b).",
                        "Provided that this definition applies only where the context so requires.",
                        "Explanation 1.— Reference to Commissioner includes Large Taxpayer Unit under sub-section (2).",
                    ]
                ),
            )
        ],
    )

    structured = build_legal_structure(
        parsed_document,
        document_id="income-tax-act-2023",
        act_title="Income Tax Act 2023",
    )
    tagged = tag_legal_metadata(structured)
    validate_tagged_document(tagged)

    node_map = {node.node_id: node for node in tagged.nodes}
    section_node = next(node for node in tagged.nodes if node.node_type is LegalNodeType.SECTION)
    subsection_node = next(node for node in tagged.nodes if node.node_type is LegalNodeType.SUBSECTION)
    clause_node = next(node for node in tagged.nodes if node.node_type is LegalNodeType.CLAUSE)
    proviso_node = next(node for node in tagged.nodes if node.node_type is LegalNodeType.PROVISO)
    explanation_node = next(node for node in tagged.nodes if node.node_type is LegalNodeType.EXPLANATION)

    assert section_node.metadata["document_id"] == "income-tax-act-2023"
    assert section_node.metadata["act_title"] == "Income Tax Act 2023"
    assert section_node.metadata["part_number"] == "I"
    assert section_node.metadata["chapter_number"] == "I"
    assert section_node.metadata["section_number"] == "2"
    assert section_node.metadata["page_number"] == 1
    assert section_node.metadata["citability_label"] == section_node.citability_label

    assert subsection_node.metadata["chunk_type"] == "definition"
    assert clause_node.metadata["chunk_type"] == "definition"
    assert "section:4" in subsection_node.metadata["cross_references"]
    assert "clause:b" in clause_node.metadata["cross_references"]

    assert proviso_node.metadata["chunk_type"] == "proviso"
    assert proviso_node.metadata["governing_node_id"] == subsection_node.node_id
    assert explanation_node.metadata["chunk_type"] == "explanation"
    assert "subsection:2" in explanation_node.metadata["cross_references"]
    assert clause_node.node_id in node_map[subsection_node.node_id].child_ids


def test_metadata_tagger_tracks_page_ranges_and_siblings_for_multi_page_sections() -> None:
    parsed_document = ParsedDocument(
        source_path="Income_tax_act_2023.pdf",
        parser_provider="fallback",
        pages=[
            build_parsed_page_from_text(
                1,
                "\n".join(
                    [
                        "4. Income tax authorities.—For the purposes of this Act there shall be the following classes of income tax authorities, namely:—",
                        "(a) The National Board of Revenue;",
                    ]
                ),
            ),
            build_parsed_page_from_text(
                2,
                "\n".join(
                    [
                        "(b) Chief Commissioner of Taxes;",
                        "5. Appointment of income-tax authorities.—The Board may appoint income-tax authorities.",
                    ]
                ),
            ),
        ],
    )

    structured = build_legal_structure(parsed_document, document_id="income-tax-act-2023", act_title="Income Tax Act 2023")
    tagged = tag_legal_metadata(structured)

    section_4 = next(node for node in tagged.nodes if node.node_type is LegalNodeType.SECTION and node.section_number == "4")
    subsection_a = next(
        node
        for node in tagged.nodes
        if node.node_type is LegalNodeType.CLAUSE and node.clause_number == "a"
    )
    subsection_b = next(
        node
        for node in tagged.nodes
        if node.node_type is LegalNodeType.CLAUSE and node.clause_number == "b"
    )

    assert section_4.metadata["page_number"] == 1
    assert section_4.metadata["page_start"] == 1
    assert section_4.metadata["page_end"] == 2
    assert section_4.metadata["page_numbers"] == [1, 2]
    assert subsection_a.metadata["sibling_ids"] == [subsection_b.node_id]
    assert subsection_b.metadata["sibling_ids"] == [subsection_a.node_id]


def test_validate_tagged_document_rejects_untagged_nodes() -> None:
    parsed_document = ParsedDocument(
        source_path="Income_tax_act_2023.pdf",
        parser_provider="fallback",
        pages=[build_parsed_page_from_text(1, "1. Short title.—This Act may be called the Income Tax Act 2023.")],
    )
    structured = build_legal_structure(parsed_document, document_id="income-tax-act-2023", act_title="Income Tax Act 2023")

    with pytest.raises(ValueError, match="missing metadata keys"):
        validate_tagged_document(structured)
