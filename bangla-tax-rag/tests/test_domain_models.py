import pytest
from pydantic import ValidationError

from app.domain import CitationRelation, EvidenceItem, LegalCitation, LegalNode, LegalNodeType


def test_legal_node_builds_citation_label_from_hierarchy() -> None:
    node = LegalNode(
        node_id="node-sec-4-clause-a",
        document_id="income-tax-act-2023",
        act_title="Income Tax Act 2023",
        node_type=LegalNodeType.CLAUSE,
        text="The National Board of Revenue.",
        normalized_text="The National Board of Revenue.",
        page_start=24,
        page_end=24,
        parent_id="node-sec-4-sub-1",
        path_ids=["node-act", "node-sec-4", "node-sec-4-sub-1", "node-sec-4-clause-a"],
        path_labels=["Act", "Section 4", "Subsection (1)", "Clause (a)"],
        section_number="4",
        subsection_number="1",
        clause_number="a",
    )

    assert node.citability_label == "Section 4 > Subsection 1 > Clause a"
    assert node.is_leaf is True


def test_legal_node_requires_section_number_for_subordinate_nodes() -> None:
    with pytest.raises(ValidationError):
        LegalNode(
            node_id="node-sub-1",
            document_id="income-tax-act-2023",
            act_title="Income Tax Act 2023",
            node_type=LegalNodeType.SUBSECTION,
            text="Subject to this Act...",
            normalized_text="Subject to this Act...",
            page_start=8,
            page_end=8,
            subsection_number="1",
        )


def test_legal_node_validates_path_alignment() -> None:
    with pytest.raises(ValidationError):
        LegalNode(
            node_id="node-sec-2",
            document_id="income-tax-act-2023",
            act_title="Income Tax Act 2023",
            node_type=LegalNodeType.SECTION,
            text="Definitions.",
            normalized_text="Definitions.",
            page_start=6,
            page_end=6,
            section_number="2",
            path_ids=["node-act", "wrong-node"],
            path_labels=["Act", "Section 2"],
        )


def test_legal_node_to_citation_preserves_page_and_section_metadata() -> None:
    node = LegalNode(
        node_id="node-def-commissioner",
        document_id="income-tax-act-2023",
        act_title="Income Tax Act 2023",
        node_type=LegalNodeType.DEFINITION,
        text="Commissioner means Commissioner of Taxes.",
        normalized_text="Commissioner means Commissioner of Taxes.",
        page_start=6,
        page_end=6,
        parent_id="node-sec-2",
        path_ids=["node-act", "node-sec-2", "node-def-commissioner"],
        path_labels=["Act", "Section 2", "Definition"],
        section_number="2",
        clause_number="19",
    )

    citation = node.to_citation(snippet="Commissioner means Commissioner of Taxes.")

    assert citation.node_id == node.node_id
    assert citation.section_number == "2"
    assert citation.page_start == 6
    assert citation.citability_label == node.citability_label


def test_citation_rejects_invalid_page_range() -> None:
    with pytest.raises(ValidationError):
        LegalCitation(
            node_id="node-1",
            document_id="doc",
            act_title="Act",
            relation=CitationRelation.DIRECT,
            page_start=10,
            page_end=9,
        )


def test_evidence_item_requires_non_empty_source_text() -> None:
    citation = LegalCitation(
        node_id="node-1",
        document_id="doc",
        act_title="Act",
        relation=CitationRelation.DIRECT,
        page_start=4,
        page_end=4,
    )

    with pytest.raises(ValidationError):
        EvidenceItem(
            evidence_id="e1",
            node_id="node-1",
            citation=citation,
            source_text="   ",
            retrieval_method="hybrid",
        )
