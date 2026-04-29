from app.domain import LegalNodeType
from app.ingestion import (
    ParsedDocument,
    build_legal_chunks,
    build_legal_structure,
    build_parsed_page_from_text,
    link_parent_child_relationships,
    tag_legal_metadata,
)


def test_structure_builder_preserves_hierarchy_for_statute_page() -> None:
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
                        "(1) “Commissioner” means Commissioner of Taxes.",
                        "(a) Chief Commissioner of Taxes.",
                        "Provided that this definition applies only where the context so requires.",
                        "Explanation 1.— Reference to Commissioner includes Large Taxpayer Unit.",
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
    node_map = {node.node_id: node for node in structured.nodes}

    assert structured.root_node_id == "income-tax-act-2023:act"
    part_node = next(node for node in structured.nodes if node.node_type is LegalNodeType.PART)
    chapter_node = next(node for node in structured.nodes if node.node_type is LegalNodeType.CHAPTER)
    section_node = next(node for node in structured.nodes if node.node_type is LegalNodeType.SECTION)
    subsection_node = next(node for node in structured.nodes if node.node_type is LegalNodeType.SUBSECTION)
    clause_node = next(node for node in structured.nodes if node.node_type is LegalNodeType.CLAUSE)
    proviso_node = next(node for node in structured.nodes if node.node_type is LegalNodeType.PROVISO)
    explanation_node = next(node for node in structured.nodes if node.node_type is LegalNodeType.EXPLANATION)

    assert part_node.part_number == "I"
    assert part_node.title == "PRELIMINARY"
    assert chapter_node.chapter_number == "I"
    assert chapter_node.title == "BASIS OF CHARGE"
    assert section_node.section_number == "2"
    assert section_node.parent_id == chapter_node.node_id
    assert subsection_node.parent_id == section_node.node_id
    assert subsection_node.subsection_number == "1"
    assert clause_node.parent_id == subsection_node.node_id
    assert clause_node.clause_number == "a"
    assert proviso_node.parent_id == subsection_node.node_id
    assert explanation_node.parent_id == subsection_node.node_id
    assert node_map[section_node.node_id].child_ids


def test_structure_builder_extends_section_across_pages_until_next_section() -> None:
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
    sections = [node for node in structured.nodes if node.node_type is LegalNodeType.SECTION]
    section_4 = next(node for node in sections if node.section_number == "4")
    section_5 = next(node for node in sections if node.section_number == "5")

    assert section_4.page_start == 1
    assert section_4.page_end == 2
    assert section_5.page_start == 2


def test_structure_builder_extracts_table_node_under_governing_section() -> None:
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
    section_node = next(node for node in structured.nodes if node.node_type is LegalNodeType.SECTION)
    table_node = next(node for node in structured.nodes if node.node_type is LegalNodeType.TABLE)

    assert table_node.parent_id == section_node.node_id
    assert table_node.section_number == "163"
    assert "10%" in table_node.text


def test_structure_builder_detects_bangla_paripatra_headings_without_splitting_numbered_lists() -> None:
    parsed_document = ParsedDocument(
        source_path="Income-tax_Paripatra_2025-2026-1.pdf",
        parser_provider="fallback",
        pages=[
            build_parsed_page_from_text(
                1,
                "\n".join(
                    [
                        "১। ২০২৬-২০২৭ এবং ২০২৭-২০২৮ করবর্ষের জন্য প্রযোজ্য আয়করের হার",
                        "১.১ স্বাভাবিক ব্যক্তি ও হিন্দু অবিভক্ত পরিবারের করহার",
                        "মোট আয় হার",
                        "১. মহিলা করদাতা এবং ৬৫ বছর বা তদূর্ধ্ব বয়সের করদাতার ক্ষেত্রে ৪,২৫,০০০ টাকা;",
                        "২. তৃতীয় লিঙ্গের করদাতা এবং প্রতিবন্ধী ব্যক্তির ক্ষেত্রে ৫,০০,০০০ টাকা;",
                        "১.২ ট্রাস্ট, ফার্ম, ব্যক্তিসংঘের করহার",
                        "(১) ট্রাস্টের আয়ের উপর প্রযোজ্য কর- উক্ত আয়ের ২৭.৫%",
                    ]
                ),
            )
        ],
    )

    structured = build_legal_structure(
        parsed_document,
        document_id="income-tax-paripatra-2025-2026",
        act_title="আয়কর পরিপত্র ২০২৫-২০২৬",
    )
    sections = [node for node in structured.nodes if node.node_type is LegalNodeType.SECTION]
    section_numbers = [node.section_number for node in sections]

    assert section_numbers == ["1", "1.1", "1.2"]
    assert all(node.title for node in sections)
    assert "মহিলা করদাতা" in next(node for node in sections if node.section_number == "1.1").text


def test_bangla_paripatra_sections_feed_existing_legal_chunk_flow() -> None:
    parsed_document = ParsedDocument(
        source_path="Income-tax_Paripatra_2025-2026-1.pdf",
        parser_provider="fallback",
        pages=[
            build_parsed_page_from_text(
                1,
                "\n".join(
                    [
                        "২। ২০২৫-২০২৬ করবর্ষের জন্য প্রযোজ্য আয়করের হার",
                        "২.১ স্বাভাবিক ব্যক্তি, হিন্দু অবিভক্ত পরিবার ও ফার্মের জন্য ২০২৫-২০২৬ করবর্ষের করহার",
                        "মোট আয় হার",
                        "(ক) প্রথম ৩,৫০,০০০ টাকা পর্যন্ত মোট আয়ের উপর -- শূন্য",
                        "(খ) পরবর্তী ১,০০,০০০ টাকা পর্যন্ত মোট আয়ের উপর -- ৫%",
                    ]
                ),
            )
        ],
    )

    structured = build_legal_structure(
        parsed_document,
        document_id="income-tax-paripatra-2025-2026",
        act_title="আয়কর পরিপত্র ২০২৫-২০২৬",
    )
    linked = link_parent_child_relationships(tag_legal_metadata(structured))
    chunks = build_legal_chunks(linked)

    assert chunks.retrieval_chunks
    assert any(chunk.section_number == "2.1" for chunk in chunks.retrieval_chunks)
    assert any("৩,৫০,০০০" in chunk.text for chunk in chunks.retrieval_chunks)
