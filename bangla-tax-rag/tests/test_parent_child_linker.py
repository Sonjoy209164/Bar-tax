from app.domain import CitationRelation, LegalNodeType
from app.ingestion import (
    ParsedDocument,
    build_legal_structure,
    build_parsed_page_from_text,
    link_parent_child_relationships,
    tag_legal_metadata,
    validate_linked_document,
)


def test_parent_child_linker_attaches_special_units_and_reasoning_parents() -> None:
    parsed_document = ParsedDocument(
        source_path="Income_tax_act_2023.pdf",
        parser_provider="fallback",
        pages=[
            build_parsed_page_from_text(
                1,
                "\n".join(
                    [
                        "2. Definitions.— In this Act, unless there is anything repugnant in the subject or context,—",
                        "(1) “Commissioner” means Commissioner of Taxes.",
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
    tagged = tag_legal_metadata(structured)
    linked = link_parent_child_relationships(tagged)
    validate_linked_document(linked)

    node_map = {node.node_id: node for node in linked.nodes}
    subsection = next(node for node in linked.nodes if node.node_type is LegalNodeType.SUBSECTION)
    clause_a = next(node for node in linked.nodes if node.node_type is LegalNodeType.CLAUSE and node.clause_number == "a")
    clause_b = next(node for node in linked.nodes if node.node_type is LegalNodeType.CLAUSE and node.clause_number == "b")
    proviso = next(node for node in linked.nodes if node.node_type is LegalNodeType.PROVISO)
    explanation = next(node for node in linked.nodes if node.node_type is LegalNodeType.EXPLANATION)

    assert clause_a.metadata["reasoning_parent_id"] == subsection.node_id
    assert clause_b.metadata["reasoning_parent_id"] == subsection.node_id
    assert clause_a.metadata["sibling_ids"] == [clause_b.node_id]
    assert clause_b.metadata["sibling_ids"] == [clause_a.node_id]

    assert proviso.metadata["governing_rule_id"] == subsection.node_id
    assert explanation.metadata["governing_rule_id"] == subsection.node_id
    assert proviso.node_id in node_map[subsection.node_id].metadata["attached_proviso_ids"]
    assert explanation.node_id in node_map[subsection.node_id].metadata["attached_explanation_ids"]

    sibling_links = [
        link
        for link in linked.links
        if link.relation is CitationRelation.SIBLING_CONTEXT
    ]
    assert any(link.source_node_id == clause_a.node_id and link.target_node_id == clause_b.node_id for link in sibling_links)
    assert any(link.source_node_id == clause_b.node_id and link.target_node_id == clause_a.node_id for link in sibling_links)

    governing_links = [
        link
        for link in linked.links
        if link.relation is CitationRelation.GOVERNING_RULE
    ]
    assert any(link.source_node_id == proviso.node_id and link.target_node_id == subsection.node_id for link in governing_links)
    assert any(link.source_node_id == explanation.node_id and link.target_node_id == subsection.node_id for link in governing_links)


def test_parent_child_linker_attaches_tables_to_governing_section() -> None:
    parsed_document = ParsedDocument(
        source_path="Income_tax_act_2023.pdf",
        parser_provider="fallback",
        pages=[
            build_parsed_page_from_text(
                10,
                "\n".join(
                    [
                        "163. Rate of tax.—The tax shall be charged at the following rates:",
                        "Rate | Amount | Note",
                        "10% | 100000 | sample",
                        "15% | 200000 | higher slab",
                    ]
                ),
            )
        ],
    )

    structured = build_legal_structure(parsed_document, document_id="income-tax-act-2023", act_title="Income Tax Act 2023")
    tagged = tag_legal_metadata(structured)
    linked = link_parent_child_relationships(tagged)

    section = next(node for node in linked.nodes if node.node_type is LegalNodeType.SECTION)
    table = next(node for node in linked.nodes if node.node_type is LegalNodeType.TABLE)

    assert table.metadata["governing_rule_id"] == section.node_id
    assert table.metadata["reasoning_parent_id"] == section.node_id
    assert table.node_id in section.metadata["attached_table_ids"]
    assert section.node_id in table.metadata["expand_to_node_ids"]
    assert any(
        link.source_node_id == table.node_id
        and link.target_node_id == section.node_id
        and link.relation is CitationRelation.ATTACHED_TABLE
        for link in linked.links
    )


def test_parent_child_linker_expansion_metadata_includes_attached_units() -> None:
    parsed_document = ParsedDocument(
        source_path="Income_tax_act_2023.pdf",
        parser_provider="fallback",
        pages=[
            build_parsed_page_from_text(
                1,
                "\n".join(
                    [
                        "2. Definitions.— In this Act, unless there is anything repugnant in the subject or context,—",
                        "(1) “Commissioner” means Commissioner of Taxes.",
                        "Provided that this definition applies only where the context so requires.",
                        "Explanation 1.— Reference to Commissioner includes Large Taxpayer Unit.",
                    ]
                ),
            )
        ],
    )

    structured = build_legal_structure(parsed_document, document_id="income-tax-act-2023", act_title="Income Tax Act 2023")
    tagged = tag_legal_metadata(structured)
    linked = link_parent_child_relationships(tagged)

    subsection = next(node for node in linked.nodes if node.node_type is LegalNodeType.SUBSECTION)
    proviso = next(node for node in linked.nodes if node.node_type is LegalNodeType.PROVISO)
    explanation = next(node for node in linked.nodes if node.node_type is LegalNodeType.EXPLANATION)

    assert proviso.node_id in subsection.metadata["expand_to_node_ids"]
    assert explanation.node_id in subsection.metadata["expand_to_node_ids"]
